"""nba_backup: a snapshot restores to the rows it recorded; a store that SHRINKS is quarantined on its own (the
others still back up, its last good copy stays the baseline and survives pruning) even when only one table
shrank and the store's total grew; the current board may shrink; worker-2's pull rejects bytes that changed
after the VM wrote them; an old backup or a dead pull is reported. MUTANTS in test_mutants()."""
import datetime as dt
import importlib
import json
import pathlib
import shutil
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_backup as B
import nba_backup_pull as P

D0 = dt.date(2026, 10, 26)                       # a Monday


def db(path, **tables):
    """Create or top up a store: {table: n} inserts n rows; a negative n deletes that many."""
    c = sqlite3.connect(path)
    for t, n in tables.items():
        c.execute(f"CREATE TABLE IF NOT EXISTS {t} (k INTEGER PRIMARY KEY, v TEXT)")
        if n >= 0:
            c.executemany(f"INSERT INTO {t} (v) VALUES (?)", [("x" * 40,)] * n)
        else:
            c.execute(f"DELETE FROM {t} WHERE k IN (SELECT k FROM {t} LIMIT ?)", (-n,))
    c.commit()
    c.close()


class LocalRemote:
    """The VM's backup directory, reached as a plain directory."""

    def __init__(self, d):
        self.d = d

    def read(self, name):
        return (self.d / name).read_text()

    def fetch(self, name, dest):
        shutil.copyfile(self.d / name, dest)

    def put(self, name, text):
        (self.d / name).write_text(text)


def check(b, p=P):
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")
    root = pathlib.Path(tempfile.mkdtemp())
    src, out, w2 = root / "src", root / "vm", root / "w2"
    src.mkdir()
    lines, shadow, xlog = src / "nba_lines.sqlite", src / "nba_shadow.sqlite", src / "x.jsonl"
    stores = [("nba_lines", lines), ("nba_shadow", shadow), ("underdog_nba_log", xlog)]
    db(lines, quotes=500, board=40)
    db(shadow, flags=30, cands=60)
    xlog.write_text("".join(json.dumps({"i": i}) + "\n" for i in range(20)) + '{"torn')
    sent = []

    def night(day, **kw):
        sent.clear()
        return b.run(stores, out, D0 + dt.timedelta(day), notify=sent.append, **kw)

    def good(label):
        return json.loads((out / "latest.json").read_text())["good"][label]

    def pull(day):
        sent.clear()
        return p.pull(LocalRemote(out), w2, D0 + dt.timedelta(day), notify=sent.append)
    try:
        want(night(0) == 0 and not sent, "night 0: three stores backed up, no alert")
        r = root / "r.sqlite"
        b.gunzip(out / good("nba_lines")["file"], r)
        want(b.counts(r) == b.counts(lines) == {"quotes": 500, "board": 40}, "nba_lines restores to its rows")
        b.gunzip(out / good("underdog_nba_log")["file"], root / "r.jsonl")
        want((root / "r.jsonl").read_text().splitlines() == xlog.read_text().splitlines()[:20],
             "the X log keeps its 20 complete lines, not the torn one being appended")

        db(lines, quotes=300, board=-25)
        db(shadow, flags=5, cands=10)
        want(night(1) == 0 and not sent and good("nba_lines")["stamp"] == "20261027",
             "night 1: the board 40 -> 15 is current state, not a shrink")

        db(shadow, flags=-35, cands=100)                 # flags wiped while the store's TOTAL grows
        db(lines, quotes=100)
        rc = night(2)
        want(rc == 1 and any("nba_shadow SHRANK" in m and "flags 35 -> 0" in m for m in sent),
             "night 2: flags 35 -> 0 caught though nba_shadow's total grew (105 -> 170)")
        want((out / "nba_shadow.20261028.SHRUNK.sqlite.gz").exists() and good("nba_shadow")["stamp"] == "20261027",
             "...its snapshot kept as SHRUNK, the good copy of 10-27 stays the baseline")
        want(good("nba_lines")["stamp"] == good("underdog_nba_log")["stamp"] == "20261028",
             "...and the other stores still backed up that night (not all-or-nothing)")

        want(pull(2) == 0 and json.loads((out / "offbox.json").read_text())["stamp"] == "20261028",
             "worker-2 pulls, leaves offbox.json on the VM")
        names = {i["file"] for i in json.loads((out / "latest.json").read_text())["good"].values()}
        want({f.name for f in w2.glob("*.gz")} == names | {"nba_shadow.20261028.SHRUNK.sqlite.gz"}
             and all(b.sha256(w2 / n) == b.sha256(out / n) for n in names),
             "...every good snapshot and tonight's quarantined copy, byte for byte")
        f = out / good("nba_lines")["file"]
        keep = f.read_bytes()
        (w2 / f.name).unlink()
        f.write_bytes(keep[:-9] + bytes(9))
        want(pull(2) == 1 and any("sha256" in m for m in sent) and not (w2 / f.name).exists(),
             "a snapshot whose bytes changed on the VM is refused by the pull")
        sent.clear()
        want(b.verify(stores, out, notify=sent.append) == 1 and sent, "...and by --verify")
        f.write_bytes(keep)

        rc = night(12)                                   # nba_shadow still shrunk, 10 days later
        want(rc == 1 and any("off-box copy on worker-2 is 10 days old" in m for m in sent),
             "night 12: a pull that stopped 10 days ago is reported")
        want((out / "nba_shadow.20261027.sqlite.gz").exists() and not (out / "nba_lines.20261027.sqlite.gz").exists(),
             "pruning thins old snapshots but never the last good one of a quarantined store")
        pull(12)
        want(night(12, accept=["nba_shadow"]) == 0 and not sent and good("nba_shadow")["stamp"] == "20261107",
             "--accept nba_shadow makes the shrunk store the new baseline")
        sent.clear()
        want(b.verify(stores, out, notify=sent.append) == 0 and not sent, "--verify passes on every good snapshot")

        want(pull(20) == 1 and any("8 days old" in m for m in sent), "the pull reports a VM backup 8 days old")
        floor, b.FREE_FLOOR = b.FREE_FLOOR, 1e18
        before = sorted(x.name for x in out.iterdir())
        try:
            want(night(13) == 1 and any("REFUSED" in m for m in sent) and sorted(x.name for x in out.iterdir()) == before,
                 "low disk: refused, nothing written or pruned")
        finally:
            b.FREE_FLOOR = floor
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return ok


def test_backup():
    assert check(B)


def _mutant(mod, a, b, tag):
    src = pathlib.Path(mod.__file__).read_text()
    assert src.count(a) == 1, tag
    d = pathlib.Path(tempfile.mkdtemp())
    name = mod.__name__ + "_mut"
    (d / f"{name}.py").write_text(src.replace(a, b))
    sys.path.insert(0, str(d))
    try:
        return importlib.import_module(name)
    finally:
        sys.path.remove(str(d))


def test_mutants():
    for tag, mod, a, b in (
            ("total rows, wnba_backup's guard", B, "now.get(t, 0) < n]", "sum(now.values()) < sum(was.values())]"),
            ("no guard", B, "now.get(t, 0) < n]", "False]"),
            ("the board guarded too", B, 'EXEMPT = {("nba_lines", "board")}', "EXEMPT = set()"),
            ("a shrunk store becomes the baseline", B, 'if status == "ok":\n            latest["good"][label] = info',
             'latest["good"][label] = info\n        if status == "ok":\n            pass'),
            ("all-or-nothing, wnba_backup's refusal", B, "(--accept {label} once explained)\")\n",
             "(--accept {label} once explained)\")\n                return 1\n"),
            ("pruning ignores the pin", B, " or fn in pinned:", ":"),
            ("the pull trusts scp", P, "if got != sha:", "if False:")):
        print(f"MUTANT ({tag}) — must fail:")
        m = _mutant(mod, a, b, tag)
        try:
            assert not (check(m) if mod is B else check(B, m)), tag
        finally:
            sys.modules.pop(m.__name__, None)


if __name__ == "__main__":
    test_backup(); test_mutants()
    print("test_nba_backup: OK")
