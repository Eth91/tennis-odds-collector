#!/bin/bash
set -u
cd ~/tennis-odds-collector || exit 1
set -a; . ~/wnba-loop.env; set +a
URL="https://x-access-token:${GIT_PAT}@github.com/fgf9p6ks2f-ux/tennis-odds-collector.git"
rm -rf .git/rebase-merge .git/rebase-apply
python3 fix_g2.py || exit 1
python3 -c "import pga_ruler; print('  ruler imports')"
git add pga_ruler.py fix_g2.py
if ! git diff --cached --quiet; then
  git -c user.email=vm@local -c user.name=vm commit -q -F - <<'MSG'
PGA: G2 — the gate guarding real money — was grading the WRONG TOURNAMENT

Found while answering whether the gate could be backtested instead of waited out.

WRONG EDITION. The results lookup was
    WHERE event LIKE '%'||toks[0]||'%' ORDER BY date DESC LIMIT 1
For "PGA Rocket Classic 2026" toks[0] is 'Rocket', which matches the 2025 Rocket Classic — the
most recent PLAYED edition. So the gate scored 2026 collected prices against 2025 outcomes.
All four "gradeable closes" were that. The true n is 0. Same class of bug as the course-name
token contamination fixed earlier today.

NOT A CLOSE. The price used was MAX(collected_at) per runner — the most recent price ever seen.
During a live tournament that is an IN-PLAY price which already reflects the result, and
grading against it would flatter the model enormously. A close is now the last price before the
relevant round tees off: event start for a 72-hole matchup, start+(N-1) days for round N.

The gate also now reports how many markets it DROPPED and why, so an empty gate can never again
read as a passing one.
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
echo "=== TRUE G2 STATE ==="
nice -n 8 timeout 900 python3 -u -c "import pga_ruler as RU; RU.g2_gate(verbose=True)" 2>&1 | tail -12
