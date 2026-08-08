#!/usr/bin/env python3
"""Back up a repo's SOURCE. Both betting boxes are cut off from GitHub, so this is the only copy.

WHY NOT A GIT BUNDLE — this was tried first and it FAILED
    `git bundle create --all` produced a 91 MB bundle, and `git bundle verify` PASSED it. But
    cloning that bundle back died:
        error: Could not read c32fdede...
        fatal: Failed to traverse parents of commit 13c4d752...
    Cause: the nightly `git_reshallow_any.sh` rewrites `.git/shallow` to the tip so gc can drop
    old history. The repo is SHALLOW (1 grafted boundary), so a bundle of "all refs" references
    objects that no longer exist locally.
    🔑 TWO LESSONS, both already written down elsewhere and both re-earned here:
      * `git bundle verify` is NOT proof of restorability. Only an actual clone is. This is the
        "verify the copy, not the exit code" rule — a backup whose restore is never exercised
        would have looked perfect until the day it was needed.
      * A backup that depends on something another job mutates (here: history the reshallow
        prunes) dies silently when that job runs.

WHAT THIS DOES INSTEAD
    Tars the SOURCE — tracked + untracked .py/.sh plus small config — which is the part that is
    actually irreplaceable and is only ~4.4 MB. History beyond the shallow boundary is already
    gone and cannot be backed up by anything running on this box.
    Untracked files matter more than they sound: `box25.py`, the box-score scraper, is untracked,
    so a history-only backup would miss it entirely. 26 such files here.

GUARDS
    * RESTORE-TESTED every run: the tar is extracted to a scratch dir and every file's sha256 is
      compared against the original. Cheap at this size, so there is no excuse to skip it.
    * MONOTONE file count — a shrink refuses and leaves the previous backup intact.
    * `.bak` fossils, caches, logs and binaries are excluded; real sources are not.
"""
import hashlib, io, json, os, shutil, subprocess, sys, tarfile, tempfile

EXT = (".py", ".sh", ".yml", ".yaml", ".toml", ".cfg", ".service")
SKIP_PARTS = (".bak", "__pycache__", "/node_modules/", "/.git/")


def _git(repo, *args):
    r = subprocess.run(["git", "-C", repo] + list(args), capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def _sources(repo):
    seen = set()
    for listing in (_git(repo, "ls-files"),
                    _git(repo, "ls-files", "--others", "--exclude-standard")):
        for f in listing.split("\n"):
            if not f or not f.endswith(EXT):
                continue
            if any(s in f for s in SKIP_PARTS):
                continue
            p = os.path.join(repo, f)
            if os.path.isfile(p) and os.path.getsize(p) < 4_000_000:
                seen.add(f)
    return sorted(seen)


def snapshot(repo, outdir, stamp, prev=None, label=None):
    label = label or os.path.basename(repo.rstrip("/"))
    os.makedirs(outdir, exist_ok=True)
    files = _sources(repo)
    prev = prev or {}
    was = prev.get("files")
    if was is not None and len(files) < was:
        raise RuntimeError("%s source count SHRANK %d -> %d; refusing, previous kept"
                           % (label, was, len(files)))

    name = "%s-src.%s.tar.gz" % (label, stamp)
    path = os.path.join(outdir, name)
    tmp = path + ".part"
    want = {}
    with tarfile.open(tmp, "w:gz") as tf:
        for f in files:
            p = os.path.join(repo, f)
            want[f] = hashlib.sha256(open(p, "rb").read()).hexdigest()
            tf.add(p, arcname=f)

    # RESTORE TEST, every run -- extract and compare every file's digest
    d = tempfile.mkdtemp(prefix="srcverify_")
    try:
        with tarfile.open(tmp, "r:gz") as tf:
            tf.extractall(d)
        bad = []
        for f, h in want.items():
            q = os.path.join(d, f)
            if not os.path.exists(q):
                bad.append("%s missing" % f)
            elif hashlib.sha256(open(q, "rb").read()).hexdigest() != h:
                bad.append("%s differs" % f)
        if bad:
            os.unlink(tmp)
            raise RuntimeError("%s restore test FAILED: %s" % (label, "; ".join(bad[:3])))
    finally:
        shutil.rmtree(d, ignore_errors=True)
    os.replace(tmp, path)

    head = _git(repo, "rev-parse", "HEAD")
    return {"repo": repo, "head": head,
            "commits_reachable": len((_git(repo, "log", "--format=%H") or "").split("\n")),
            "shallow": os.path.exists(os.path.join(repo, ".git", "shallow")),
            "file": name, "files": len(files), "bytes": os.path.getsize(path),
            "sha256": hashlib.sha256(open(path, "rb").read()).hexdigest(),
            "restore_tested": True}


if __name__ == "__main__":
    repo = sys.argv[1] if len(sys.argv) > 1 else "/home/ubuntu/tennis-odds-collector"
    out = sys.argv[2] if len(sys.argv) > 2 else "/tmp/codetest"
    print(json.dumps(snapshot(repo, out, "manual"), indent=2))
