"""Re-apply the golf_collect.py half of the movement change. Idempotent, ast-checked before write.

WHY THIS IS A SCRIPT AND NOT AN EDIT. The Mac's DK loop runs `git reset --hard FETCH_HEAD` every
~3 minutes. One of those resets landed between editing golf_collect.py and staging it, so the file
was already reverted on disk when `git add` ran and the commit went out with only the new untracked
file in it. Tracked files cannot be edited and committed as two steps on this box; the edit has to
be replayable in the same shell invocation as the push. Same lesson as land.sh..land18.sh.
"""
import ast
import io
import shutil

P = "golf_collect.py"
s = io.open(P, encoding="utf-8").read()

if "--only-if-tee-within" in s:
    print("  = already applied")
    raise SystemExit(0)

# ── 1. docstring: record the cadence decision where the cron entries are read ────────────────────
OLD_DOC = '''they post; the meters parse from the captured shapes. Phase-4 of PGA_PLAN.md."""
import datetime as dt
import json
import sqlite3
import urllib.request'''
NEW_DOC = '''they post; the meters parse from the captured shapes. Phase-4 of PGA_PLAN.md.

CADENCE, 2026-08-01. A flat 30 minutes is right for the archive and wrong for the close. The price
that decides whether a golf market was soft is the LAST one before that player tees, and at
30-minute spacing that price is up to 30 minutes stale — long enough that the measurement is mostly
sampling error. So the cron gains a second, cheap entry:

    */30 * * * *  golf_collect.py                           # the archive, unchanged
    */5  * * * *  golf_collect.py --only-if-tee-within 75    # dense only where it matters

`--only-if-tee-within N` exits before any HTTP unless some player tees within the next N minutes, so
the dense pass costs nothing for the ~22 hours a day when no wave is imminent. Every pass, dense or
not, folds itself into golf_moves.sqlite, which is where the paired open->close actually lives.
"""
import datetime as dt
import json
import sqlite3
import sys
import time
import urllib.request'''
assert OLD_DOC in s, "docstring anchor"
s = s.replace(OLD_DOC, NEW_DOC, 1)

# ── 2. the tee-aware gate + arg parsing ──────────────────────────────────────────────────────────
OLD_MAIN = '''def main():
    con = sqlite3.connect(HERE / "golf_lines.sqlite")'''
NEW_MAIN = '''def tee_within(minutes):
    """Is any player teeing off in the next `minutes`? (window, so a just-started wave still counts)

    FAILS OPEN. If the tee sheet is missing or unreadable this returns True and the pass collects
    anyway. The cost of an unnecessary poll is one HTTP request; the cost of skipping the pass that
    held the close is the whole measurement, and a missing tee sheet is exactly the situation where
    a round is about to start.
    """
    try:
        c = sqlite3.connect(HERE / "pga_tees.sqlite")
        # time.time(), NOT utcnow().timestamp(). tee_ms is a true epoch; .timestamp() on the naive
        # datetime utcnow() returns reads it as LOCAL time, so the window silently shifts by the
        # host's UTC offset — 6h on the Mac, 0h on the VM. That is the worst kind of bug: it tests
        # clean where it runs and is wrong where it was written.
        now = time.time() * 1000.0
        hi = now + minutes * 60_000.0
        n = c.execute("SELECT COUNT(*) FROM tee_sheet WHERE tee_ms BETWEEN ? AND ?",
                      (now - 15 * 60_000.0, hi)).fetchone()[0]
        c.close()
        return n > 0
    except Exception:                                              # noqa: BLE001
        return True


def main():
    for i, a in enumerate(sys.argv):
        if a == "--only-if-tee-within":
            m = int(sys.argv[i + 1])
            if not tee_within(m):
                return                                             # silent: this fires ~250x/day
            print("golf_collect: dense pass (a tee lands within %d min)" % m)

    con = sqlite3.connect(HERE / "golf_lines.sqlite")'''
assert OLD_MAIN in s, "main anchor"
s = s.replace(OLD_MAIN, NEW_MAIN, 1)

# ── 3. fold this snapshot into the movement table ────────────────────────────────────────────────
OLD_END = '''    print(f"golf_collect {ts}: {n} rows")

if __name__ == "__main__":'''
NEW_END = '''    print(f"golf_collect {ts}: {n} rows")

    # FOLD INTO THE MOVEMENT TABLE. Wrapped because a bug in the derived table must never be able
    # to cost us the raw capture — golf_lines is the irreplaceable artefact and this pass has
    # already committed it. golf_moves can always be rebuilt with --backfill; a missed snapshot
    # cannot be rebuilt at all.
    try:
        import golf_moves
        nk, nf = golf_moves.fold(ts)
        print(f"golf_moves {ts}: {nk} keys folded, {nf} closes frozen")
    except Exception as _me:                                       # noqa: BLE001
        print(f"golf_moves skipped: {str(_me)[:90]}")

if __name__ == "__main__":'''
assert OLD_END in s, "tail anchor"
s = s.replace(OLD_END, NEW_END, 1)

ast.parse(s)
shutil.copyfile(P, "/tmp/golf_collect.preburst.py")
io.open(P, "w", encoding="utf-8").write(s)
print("  + --only-if-tee-within gate, time.time() epoch, golf_moves.fold() wired in")
