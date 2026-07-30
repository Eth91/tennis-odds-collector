#!/bin/bash
set -u
cd ~/tennis-odds-collector || exit 1
set -a; . ~/wnba-loop.env; set +a
URL="https://x-access-token:${GIT_PAT}@github.com/fgf9p6ks2f-ux/tennis-odds-collector.git"
rm -rf .git/rebase-merge .git/rebase-apply
python3 fix_birdie_devig.py || exit 1
python3 -c "import ast,io; [ast.parse(io.open(f).read()) for f in ('pga_e3.py','pga_audit.py')]; print('  both parse')"
git add pga_e3.py pga_audit.py fix_birdie_devig.py
if ! git diff --cached --quiet; then
  git -c user.email=vm@local -c user.name=vm commit -q -F - <<'MSG'
PGA birdies: the level anchor was calibrated against the vig, not against fair

All 24 posted birdie lines carry both sides and the overround is 6.04% (tight: 1.0567-1.0618),
so the raw Over implied probability sits +3.02 points above fair. LAM was bisected so that
mean(model P(over)) == mean(1/odds_over) — the vig-inflated Over price. That forces:

    over edge  = p_over - raw_over        ~= 0      (should be -3.02: the vig must be beaten)
    under edge = (1 - p_over) - raw_under ~= -6.04

Unders therefore started six points in the hole while overs started level, which is exactly
the 10-over / 1-under split the audit flagged. And it was not cosmetic: every flagged over was
over-valued by ~3 points, so a "+5% over" was really +2%.

Now each player's two quotes are paired, devigged, and the level is anchored to the mean FAIR
probability. The EDGE is still measured against the raw offered price — that was always
correct, since you bet at the offered price and the vig is precisely what has to be overcome.
Both sides now start from the same -3.02 handicap, so any remaining asymmetry is signal.

Expect far fewer flags: at a 6% hold, clearing +5% NET needs the model to disagree with fair by
over 8 points. That is the honest bar. A one-sidedness alarm now prints, because a persistent
all-one-way split is how a wrong LEVEL announces itself — the v1 par-72 bug's signature.

The audit's section 6 had the same reference error, so every bias figure it has printed was
understated by ~3 points. It now compares against the devigged price and says so.
MSG
  echo "committed $(git rev-parse --short HEAD)"
fi
for i in $(seq 1 25); do
  rm -rf .git/rebase-merge .git/rebase-apply
  git fetch -q "$URL" main 2>/dev/null
  [ "$(git rev-parse HEAD)" = "$(git rev-parse FETCH_HEAD)" ] && break
  git rebase -q --autostash FETCH_HEAD >/dev/null 2>&1
  if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; then
    git rebase --abort >/dev/null 2>&1; rm -rf .git/rebase-merge .git/rebase-apply; sleep 2; continue; fi
  git push -q "$URL" HEAD:main 2>/dev/null && { echo "PUSHED attempt $i"; break; }
  sleep 2
done
L=$(git rev-parse HEAD); R=$(git ls-remote "$URL" main 2>/dev/null | cut -f1)
[ "$L" = "$R" ] && echo MATCH || echo MISMATCH
echo
echo "=== E3 with the devigged anchor ==="
nice -n 8 timeout 1200 python3 -u pga_e3.py 2>&1 | grep -E "birdies|E3 preview|ruler" | tail -10
