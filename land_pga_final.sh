#!/bin/bash
set -u
cd ~/tennis-odds-collector || exit 1
set -a; . ~/wnba-loop.env; set +a
URL="https://x-access-token:${GIT_PAT}@github.com/fgf9p6ks2f-ux/tennis-odds-collector.git"

# fix market_fit's contaminated round-1 pool so the audit stops reporting an artefact
python3 - <<'PY'
import ast, io
p = "market_fit.py"
s = io.open(p).read()
old = '''    for _ in range(300):
        a, b = random.choice(fl), random.choice(fl)
        if a == b:
            continue
        pr = RU.matchup_prob(Rn, a, b, rounds=1)'''
new = '''    # ROUND-1 pairs must come from EVERYONE who played round 1, not from `fl` (players with four
    # rounds). Restricting to cut-makers conditions on an outcome downstream of round 1 and
    # inverted the verdict: measured on identical events, cut-makers-only gave slope 0.275 while
    # the unselected pool gave 1.265. The 0.310 this section used to print was that artefact.
    r1pool = [p for p in r1 if p in Rn]
    for _ in range(300):
        a, b = random.choice(r1pool), random.choice(r1pool)
        if a == b:
            continue
        pr = RU.matchup_prob(Rn, a, b, rounds=1)'''
if "ROUND-1 pairs must come from EVERYONE" in s:
    print("  = market_fit r1 pool already fixed")
else:
    assert old in s, "r1 loop anchor missing"
    s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(p, "w").write(s)
    print("  + market_fit round-1 pool de-contaminated")
PY

python3 -c "import ast,io; [ast.parse(io.open(f).read()) for f in ('pga_ruler.py','dashboard.py','market_fit.py')]; print('  all parse')"
python3 -c "
import pga_ruler as RU
print('  SPREAD=%.2f  RHO=%.2f  ties-aware=%s  threeball=%s' % (
  RU.SPREAD, RU.RHO, 'win_ties' in RU.simulate.__doc__ if RU.simulate.__doc__ else '?',
  hasattr(RU,'threeball')))"

for t in $(seq 1 40); do [ -f .git/index.lock ] || break; sleep 2; done
rm -rf .git/rebase-merge .git/rebase-apply
for f in pga_ruler.py dashboard.py market_fit.py fix_spread.py fix_ties_3ball.py \
         fix_ties_memory.py fix_ties_stride.py fix_3ball_guard.py fix_pga_tab.py \
         calib_spread.py calib_spread1r.py test_r1_selection.py test_sigma_byskill.py \
         patch_marketfit_ties.py bench_ties.sh; do [ -f "$f" ] && git add "$f"; done
if ! git diff --cached --quiet; then
  git -c user.email=vm@local -c user.name=vm commit -q -F - <<'MSG'
PGA: rating-SPREAD calibration, integer scores with real ties, 3-balls, PGA tab

SIGMA WAS RULED OUT FIRST. The "too timid" slopes on every tournament market were not a
volatility problem: sigma tests clean in all six rating bins (elite assigned 2.730 vs realized
2.711, z-sd 0.97-1.01, assigned skill-spread 0.232 vs reality 0.223).

SPREAD=1.30. K_SHRINK is right for a point estimate but a rank sim and a matchup probability are
NON-LINEAR in the rating spread, so shrunk inputs made the field look homogeneous and compressed
every probability toward its base rate. Tuned on 2025, HELD OUT on 2026: mean |slope-1| .4464 ->
.1602, a 64% cut. This is the mirror of the birdie fix, which needed MORE shrinkage.

INTEGER SCORES + REAL TIES. Golf scores are integers; continuous draws made exact ties impossible,
which left top-N-incl-ties unpriceable and 3-balls wrong. Rounding yields ties at their natural
rate: top20 incl-ties = 22.4 vs strict 20.0, and 31.5% of 3-balls have a tie for low. Positions are
1+(count strictly better), matching how books settle "incl. ties".

Two bugs found and fixed while building it: the first tie-position implementation was O(k^2) in
memory (~180MB/rep at live settings, would OOM a 956MB box), and the O(n*k) replacement collided
with tot4's 1e6 missed-cut sentinel, reading win_ties 0.00 / top20_ties 53.29 before the stride
went to 1e9. Now 6.6s and 188MB at 8000 sims.

threeball() prices 3-balls with dead-heat EV (a two-way tie for low is stake-back, not a win);
EV sums to exactly 1.0000 and it refuses a trio that is short or unrated.

ROUND-1 SLOPE WAS AN ARTEFACT. market_fit sampled round-1 pairs only among players with four
rounds — conditioning on an outcome downstream of round 1. Measured on identical events:
cut-makers-only 0.275 vs unselected 1.265. So single rounds are too TIMID like everything else,
SPREAD=1.30 helps them too, and no separate single-round constant is needed. The pool is fixed so
the audit stops printing the artefact.

Re-measured calibration (integer/ties + SPREAD): matchup72 1.009, top5 1.019, outright 0.939,
win_ties 0.988, top5_ties 1.092, top10 1.137, make_cut 1.146 — all inside the 0.85-1.15 band or
close. Still timid: top20 1.206, top20_ties 1.221, top10_ties 1.181.

Dashboard: PGA gets its own tab (icon in the same line-art style) and the PGA plays move OFF the
Table Tennis tab into it.
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
  git push -q "$URL" HEAD:main 2>/dev/null && { echo "  PUSHED attempt $i"; break; }
  sleep 2
done
git fetch -q "$URL" main 2>/dev/null
echo "  on origin: spread=$(git show FETCH_HEAD:pga_ruler.py | grep -c 'SPREAD = 1.30') ties=$(git show FETCH_HEAD:pga_ruler.py | grep -c 'win_ties') 3ball=$(git show FETCH_HEAD:pga_ruler.py | grep -c 'def threeball') pgatab=$(git show FETCH_HEAD:dashboard.py | grep -c 'data-tab=\"pga\"')"
echo
echo "=== re-freeze (pricing changed, so the old manifest MUST be violated) ==="
python3 pga_freeze.py 2>&1 | head -6
python3 pga_freeze.py --freeze >/dev/null 2>&1 && python3 pga_freeze.py 2>&1 | tail -3
