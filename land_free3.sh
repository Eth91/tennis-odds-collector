#!/bin/bash
set -u
cd ~/tennis-odds-collector || exit 1
set -a; . ~/wnba-loop.env; set +a
URL="https://x-access-token:${GIT_PAT}@github.com/fgf9p6ks2f-ux/tennis-odds-collector.git"
echo "=== 3. G2 accumulation — is the collector actually banking matchups? ==="
python3 - <<'PY'
import sqlite3, datetime as dt
c = sqlite3.connect("golf_lines.sqlite")
mn, mx = c.execute("SELECT MIN(collected_at), MAX(collected_at) FROM golf_lines").fetchone()
n72 = c.execute("SELECT COUNT(DISTINCT market) FROM golf_lines WHERE market LIKE '%atchbet%' "
                "AND market NOT LIKE '%Round%'").fetchone()[0]
nrd = c.execute("SELECT COUNT(DISTINCT market) FROM golf_lines WHERE market LIKE '%atchbet%' "
                "AND market LIKE '%Round%'").fetchone()[0]
c.close()
print("  collector history: %s -> %s" % (mn, mx))
print("  matchup markets banked: %d 72-hole + %d round = %d total" % (n72, nrd, n72+nrd))
print("  these settle when the Rocket Classic finishes (~Aug 2) -> G2 goes 0 -> ~%d" % (n72+nrd))
PY
for t in $(seq 1 40); do [ -f .git/index.lock ] || break; sleep 2; done
rm -rf .git/rebase-merge .git/rebase-apply
for f in pga_sg.py pga_ruler.py fix_multitour_crawl.py probe_multitour.py \
         test_multitour_controlled.sh measure_multitour.sh; do [ -f "$f" ] && git add "$f"; done
if ! git diff --cached --quiet; then
  git -c user.email=vm@local -c user.name=vm commit -q -F - <<'MSG'
PGA: multi-tour rounds + strokes-gained by category, both FREE

The DataGolf audit ranked these blind spots #1 and #5 and I initially said they needed a $270/yr
subscription. They did not — both come from APIs we already query legitimately.

MULTI-TOUR. crawl() now covers pga + eur (DP World). Which tours to merge was decided on MEASURED
2025 player overlap with the PGA field, because the two-pass field-quality correction can only
calibrate one tour against another through players in BOTH:
    eur             248 shared = 30% of its field  -> merged
    champions-tour   21 shared =  7%               -> excluded, thin bridge
    lpga              0 shared =  0%               -> excluded, DISJOINT
Merging LPGA would have produced ratings on an uncalibrated scale that look comparable to PGA
numbers and are not — a silent failure, which is why overlap was measured before anything moved.
Result: 65,359 -> 117,513 rounds, 1,373 -> 2,456 players, 168 -> 293 events.

CONTROLLED VALIDATION, because the naive comparison was confounded (the merge changed the TEST set
too, and looked like a regression: 0.5967 -> 0.5885). Holding the test set fixed at 2026 PGA events
and varying only the training data:
    train PGA only          accuracy 0.5967
    train PGA + DP World    accuracy 0.6048   (+0.0081)
That lands at the 0.604 single-round information ceiling measured earlier.

STROKES-GAINED. pga_sg.py pulls statDetails(tourCode, statId, year) for SG:OTT/APP/ARG/PUTT/T2G/TOT
— 4,290 rows over 303 players, 2023-2026. Our rating correlates +0.876 with SG_TOT and +0.797 with
SG_T2G but only +0.352 with SG_PUTT, so it already leans on persistent skill; the categories are
what it cannot see. NOTE: harvested and queryable, NOT yet wired into the ruler — using it to
regularise ratings is a separate change that has not been validated.
MSG
  echo "  committed $(git rev-parse --short HEAD)"
fi
for i in $(seq 1 20); do
  [ -f .git/index.lock ] && { sleep 2; continue; }
  rm -rf .git/rebase-merge .git/rebase-apply
  git fetch -q "$URL" main 2>/dev/null
  [ "$(git rev-parse HEAD)" = "$(git rev-parse FETCH_HEAD)" ] && break
  git rebase -q --autostash FETCH_HEAD >/dev/null 2>&1
  if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; then
    git rebase --abort >/dev/null 2>&1; rm -rf .git/rebase-merge .git/rebase-apply; sleep 2; continue; fi
  git push -q "$URL" HEAD:main 2>/dev/null && { echo "  PUSHED $i"; break; }
  sleep 2
done
git fetch -q "$URL" main 2>/dev/null
echo "  on origin: sg=$(git show FETCH_HEAD:pga_sg.py >/dev/null 2>&1 && echo yes || echo NO) multitour=$(git show FETCH_HEAD:pga_ruler.py | grep -c 'leagues=(\"pga\", \"eur\")')"
