#!/bin/bash
set -u
cd ~/tennis-odds-collector || exit 1
set -a; . ~/wnba-loop.env; set +a
URL="https://x-access-token:${GIT_PAT}@github.com/fgf9p6ks2f-ux/tennis-odds-collector.git"
# document the negative result at the top of the harvester so nobody re-wires it on a hunch
python3 - <<'PY'
import io
p = "pga_sg.py"
s = io.open(p).read()
mark = "NEGATIVE RESULT 2026-07-30"
if mark in s:
    print("  = already documented"); raise SystemExit
add = '''
NEGATIVE RESULT 2026-07-30 — SEASON-LEVEL SG DOES NOT IMPROVE THE RULER. DO NOT WIRE IT IN.
The premise checks out: SG_OTT is the most persistent category (self-corr +0.696 Y->Y+1) and
SG_PUTT the least (+0.503), and forward power orders as expected (T2G +0.524 > APP +0.384 >
OTT +0.332 > PUTT +0.171). But the PARTIAL correlations — what each category adds ONCE this
year's SG_TOT is known — are ~zero: OTT +0.001, APP +0.016, ARG +0.044, PUTT -0.044.

Tested head-on against the ruler anyway (2026 PGA events, same test set, prior-season SG only
so there is no leakage, 77% coverage). Every variant HURT:
    blend rating toward -SG_TOT:  L=.10 -0.0017  L=.20 -0.0034  L=.50 -0.0010
    penalise putting-earned:      B=.10 -0.0024  B=.25 -0.0021  B=.50 -0.0082
Baseline 0.6048.

WHY: our rating already correlates +0.876 with SG_TOT, and it is built from ROUND-level scores
with recency weighting and a field-quality correction — finer information than a SEASON-level
aggregate. Blending in season SG adds staleness, not signal.

WHAT THIS DOES NOT RULE OUT: ROUND-level SG (scorecardStatsV3 / historicalScorecardStats) is a
different proposition and untested. Season aggregates being useless is not evidence about
per-round data. The harvest below is kept for exactly that follow-up.
'''
i = s.index('"""', s.index('"""') + 3)
s = s[:i] + add + s[i:]
io.open(p, "w").write(s)
print("  + negative result documented in pga_sg.py")
PY
for t in $(seq 1 40); do [ -f .git/index.lock ] || break; sleep 2; done
rm -rf .git/rebase-merge .git/rebase-apply
for f in pga_sg.py measure_sg_persistence.py test_sg_blend.sh; do [ -f "$f" ] && git add "$f"; done
if ! git diff --cached --quiet; then
  git -c user.email=vm@local -c user.name=vm commit -q -F - <<'MSG'
PGA: season-level SG does NOT improve the ruler — measured, not wired in

I ranked "no strokes-gained decomposition" as blind spot #1 in the DataGolf audit. That was
reasoning, not measurement, and the measurement says it is worth ~nothing at the granularity
available free.

The premise is sound: SG_OTT is the most persistent category (self-corr +0.696 year-over-year),
SG_PUTT the least (+0.503), and forward power orders exactly as the conventional wisdom claims
(T2G +0.524 > APP +0.384 > OTT +0.332 > PUTT +0.171). But the PARTIAL correlations — what each
category adds once this year's SG_TOT is known — are ~zero: OTT +0.001, APP +0.016, ARG +0.044,
PUTT -0.044.

Tested directly against the ruler regardless, on 2026 PGA events with the test set held fixed and
only prior-season SG used (no leakage; 77% coverage). Baseline 0.6048. Every variant hurt:
    blend toward -SG_TOT   L=.10 -0.0017   L=.20 -0.0034   L=.50 -0.0010
    penalise SG_PUTT       B=.10 -0.0024   B=.25 -0.0021   B=.50 -0.0082

Why: the rating already correlates +0.876 with SG_TOT and is built from ROUND-level scores with
recency weighting and field-quality correction — finer information than a season aggregate.
Blending a season number in adds staleness, not signal.

The harvester stays (4,290 rows, free, no cost to keep) and the negative result is documented at
the top of it so nobody re-wires it on a hunch. It does NOT rule out ROUND-level SG via
scorecardStatsV3 — that is a different, untested proposition.
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
python3 pga_freeze.py --freeze >/dev/null 2>&1; python3 pga_freeze.py 2>&1 | tail -2
