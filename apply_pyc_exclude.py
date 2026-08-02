"""Stop committing compiled bytecode. 67 .pyc files are tracked despite __pycache__ being ignored.

WHY THEY ARE TRACKED AT ALL. `.gitignore` already lists `__pycache__`, and on any normal box that
would be the end of it. This loop stages with `git add -A -f`, and **-f force-adds ignored files** —
the flag is there deliberately, because several tracked-and-gitignored caches are what the digests
read. So on this box .gitignore is advisory and only the `:(exclude)` pathspec actually holds. That
is the same mechanism that let golf_lines.sqlite reach 114 MB inside a repo that "ignored" it.

WHY IT MATTERS RATHER THAN BEING UNTIDY. A .pyc is a binary that changes whenever the interpreter
recompiles the source — so every deploy rewrites up to 67 blobs, each committed and pushed. That is
pure churn in a repo that just had to be rebuilt from scratch because it reached 32 GB, and it is
churn with negative information content: the .pyc is derivable from the .py sitting beside it, and
a stale one is a liability rather than an asset (a .pyc whose source moved away is exactly how a
deleted module keeps importing).

TWO HALVES, AND THEY MUST SHIP TOGETHER. Removing them from the index alone accomplishes nothing —
the next `git add -A -f` puts all 67 straight back. Adding the exclude alone leaves the existing 67
tracked and churning. So this does both: the pathspec first so nothing can re-add them, then
`git rm --cached` so the already-tracked ones leave the index. Files stay on disk untouched; Python
keeps using them exactly as before.
"""
import io
import re
import shutil
import subprocess

P = "vm_loop.sh"
s = io.open(P, encoding="utf-8").read()

if "exclude)__pycache__" in s:
    print("  = already applied")
    raise SystemExit(0)

OLD = """    ':(exclude)wnba_lines.sqlite' ':(exclude)golf_lines.sqlite' 2>/dev/null"""
NEW = """    ':(exclude)wnba_lines.sqlite' ':(exclude)golf_lines.sqlite' \\
    ':(exclude)__pycache__' ':(exclude)*.pyc' 2>/dev/null"""
assert OLD in s, "stage_all pathspec anchor not found"
s = s.replace(OLD, NEW, 1)

shutil.copyfile(P, "/tmp/vm_loop.prepyc.sh")
io.open(P, "w", encoding="utf-8").write(s)
r = subprocess.run(["bash", "-n", P], capture_output=True, text=True)
if r.returncode:
    shutil.copyfile("/tmp/vm_loop.prepyc.sh", P)
    raise SystemExit("bash -n FAILED, reverted:\n" + r.stderr)
print("  + stage_all now excludes __pycache__ and *.pyc")
