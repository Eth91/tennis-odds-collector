"""A validator must never publish "no evidence" when it means "I could not read the evidence".

THE BUG. Both validators open their ledger like this:

    if not LEDGER.exists():
        return [], []          # wnba_validate.py:86  /  pga_validate.py:107

and the caller then writes a finished evidence document saying **INSUFFICIENT DATA — no prospective
settled bets yet**. A missing ledger and a genuinely empty one produce byte-identical output, and
wnba_validate.py:272 WRITES THAT TO WNBA_EVIDENCE.md, which is committed and published.

THIS IS NOT HYPOTHETICAL — I TRIPPED IT DURING THE AUDIT. Running wnba_validate.py on the Mac,
where wnba_ledger.sqlite is deliberately absent (the WNBA DBs are gitignored and travel as text
artifacts in data/*/), produced a confident, correctly-formatted, entirely false evidence file and
left it staged. One `git add -A` and origin's evidence document would have been replaced by the
output of a machine that has no ledger. The VM's real answer for the same moment was CONTINUE
COLLECTING, LLR -0.290, 1-1, -0.13u.

IT IS ALSO REACHABLE ON THE VM, which is the part that matters. There the ledger is a SYMLINK into
~/wnba_data (the DBs live outside the repo so a checkout can only overwrite a pointer). `Path.exists()`
follows symlinks and returns **False for a broken one** — so the exact failure the symlink design
exists to protect against, a checkout replacing the link, degrades to "no bets yet" instead of an
error. There is a db_guard in vm_loop.sh for precisely that scenario, which tells you it has
happened before.

THE FIX IS TO REFUSE, NOT TO GUESS. A missing ledger now raises, so:
  - the validator exits non-zero and the loop's own error path reports it;
  - no evidence file is written, so the last TRUE report stays in place rather than being
    overwritten by a false one. Publishing nothing is strictly better than publishing a lie.

WHAT IS DELIBERATELY NOT TOUCHED. The universe definition, the SPRT boundaries, the halt
conditions, the freeze fingerprints — nothing that decides an outcome. This changes only what
happens when the input is UNREADABLE, which is not a state the pre-registered test defines and
therefore not a state I can bias by defining it. Both streams stay frozen and validation-only.

The sibling `except Exception: sel = overs` in wnba_validate._universe is left alone and flagged
instead: if current_selection() ever throws, the universe silently widens from the selected subset
to every graded over, which CHANGES THE PRE-REGISTERED TEST mid-flight. Fixing that means deciding
what the universe should be when selection is unavailable, and that is a pre-registration decision,
not a bug fix. Verified not currently firing: current_selection() succeeds and returns 59 rows.
"""
import ast
import io
import shutil

CHANGES = [
    ("wnba_validate.py",
     '''    if not LEDGER.exists():
        return [], []''',
     '''    if not LEDGER.exists():
        # REFUSE, never report zero. A missing ledger and an empty one are not the same fact, and
        # the caller writes WNBA_EVIDENCE.md from this return value — so guessing here publishes a
        # false verdict over a true one. Path.exists() also follows symlinks, so a BROKEN link
        # (the ledger is a symlink into ~/wnba_data on the VM) lands right here.
        raise SystemExit("wnba_validate: %s is missing or its symlink is broken — refusing to "
                         "write an evidence file that would read as 'no bets'" % LEDGER)'''),
    ("pga_validate.py",
     '''    if not PAPER.exists():
        return [], 0, {}''',
     '''    if not PAPER.exists():
        # Same rule as wnba_validate: an unreadable ledger is not evidence of no bets.
        raise SystemExit("pga_validate: %s is missing — refusing to report an empty record" % PAPER),'''),
]

for path, old, new in CHANGES:
    s = io.open(path, encoding="utf-8").read()
    if "refusing to" in s:
        print("  = %s already applied" % path)
        continue
    assert old in s, "anchor not found in %s" % path
    s = s.replace(old, new.rstrip(","), 1)
    ast.parse(s)
    shutil.copyfile(path, "/tmp/%s.preloud" % path)
    io.open(path, "w", encoding="utf-8").write(s)
    print("  + %s now refuses instead of reporting an empty record" % path)
