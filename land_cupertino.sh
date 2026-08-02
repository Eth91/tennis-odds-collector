#!/bin/bash
# Land the Cupertino-dark WNBA card design.
#
# This box runs a loop that does `git reset --hard FETCH_HEAD`, which already ate this patch once
# tonight (reflog: commit -> reset -> commit -> reset). A local commit is NOT enough; only content
# that reaches origin survives, because after that the loop's reset is a no-op for these files.
# Same pattern as land.sh..land18.sh — re-apply idempotently, then fetch/rebase/push in a retry
# loop until we win a gap, then VERIFY BY CONTENT on origin rather than by matching SHA.
set -u
cd ~/tennis-odds-collector || exit 1
# Mac authenticates via the osxkeychain credential helper, not the VM's wnba-loop.env PAT.
URL="origin"

echo "state before: cupertino=$(grep -c CUPERTINO dashboard.py) scoped=$(grep -c '#wnba .pblk' dashboard.py)"
python3 apply_cupertino_dark.py
python3 fix_cupertino_scope.py
echo "after re-apply: cupertino=$(grep -c CUPERTINO dashboard.py) wnba-scoped=$(grep -c '#wnba' dashboard.py) llogo=$(grep -c _llogo dashboard.py)"
python3 -c "import ast;ast.parse(open('dashboard.py').read())" || { echo "SYNTAX FAIL - aborting"; exit 1; }

# docs/index.html built locally is EMPTY (the ledger symlink points into the VM's filesystem).
# Never ship that over the live board — the VM regenerates it on its own loop.
git checkout -- docs/index.html 2>/dev/null

for t in $(seq 1 40); do [ -f .git/index.lock ] || break; sleep 2; done
rm -rf .git/rebase-merge .git/rebase-apply
for f in dashboard.py apply_cupertino_dark.py fix_cupertino_scope.py land_cupertino.sh; do
  [ -f "$f" ] && git add "$f"
done

if ! git diff --cached --quiet; then
  git -c user.email=vm@local -c user.name=vm commit -q -F - <<'MSG'
Board: Cupertino-dark card design for Today's Plays (WNBA), scoped to #wnba

Applied as a CSS override layer appended after the existing 544-line stylesheet rather than a
rewrite. _prop_row / _player_block / _game_group carry the drawer, the rung ladders, the contra
flag, the tier chips and the in-progress price freeze; none of that should be put at risk to
change how the board looks. The existing DOM already maps onto Apple's grouped list:

    .game -> section (league + team marks)   .pblk -> rounded group
    .prop -> row with hairline separators    .bars -> expanded detail

Dark mode is not an inversion, and three things flip rather than swap:
  1. ELEVATION REVERSES. Light recedes the drawer to #F2F2F7 inside a white card; dark RAISES it
     to #2C2C2E inside a #1C1C1E group. That single detail is what makes it read as iOS dark
     instead of a recolour.
  2. SEMANTIC COLOURS GET BRIGHTER — Apple's dark variants (#30D158), not the darkened-for-AA
     light values (#248A3D).
  3. THE HOVER WASH INVERTS — black 3% becomes white 4%.

SCOPED TO #wnba, and this matters. The first pass styled .pind and .podds globally with
!important and silently destroyed functional colour on the other three boards: TT and MLB render
.pind inside .ttbet (unders RED), and .podds.fd/.dk/.bmgm carry FanDuel blue, DraftKings green and
BetMGM gold. Those are how those boards are read at a glance. Every rule is now #wnba-prefixed,
which also lets the !important flags go: #wnba .pind scores (1,1,0) against .pind.o at (0,2,0), so
the id wins inside the panel and cannot match anything in #tt/#pga/#mlb. Verified in-browser by
computed style — TT/MLB/PGA return rgb(239,106,106) unders, rgb(77,163,255) FanDuel and
rgb(201,162,39) BetMGM exactly as before; only #wnba changes.

Logos: nothing fabricated. docs/logos/ already ships all 14 WNBA team marks (incl. por.png), plus
wnba.png / mlb.png / pga.png, and docs/ ships book-fd.png and book-dk.png with BetMGM as an inline
SVG data URI. What was missing was the LEAGUE mark on game headers — it only appeared on tracker
cards — so _llogo() adds it, and every mark now sits in a real containing box so a 404 degrades to
a monogram instead of a gap. TT Elite has no licensed mark and renders as a monogram: a genuine
coverage gap, not a placeholder to fill with something invented.

The bet now reads OVER 14.5 at 36px/680 with the direction as a subordinate 13px word, against a
19px player name — the number is the object of the card, the direction is a label. Over/under
carries no colour on this board; green and red stay reserved for outcome and injury status.

Verified: docs/logos/{wnba,por,ind}.png and book-*.png all load; drawer computes rgb(44,44,46) over
a rgb(28,28,30) group on a true-black ground; separators .5px rgba(84,84,88,.65); the unavailable
em-dash renders --cu-lbl3 rgba(235,235,245,.3); direction and number share a baseline.
MSG
  echo "committed $(git rev-parse --short HEAD)"
fi

for i in $(seq 1 25); do
  [ -f .git/index.lock ] && { sleep 2; continue; }
  rm -rf .git/rebase-merge .git/rebase-apply
  git fetch -q "$URL" main 2>/dev/null
  [ "$(git rev-parse HEAD)" = "$(git rev-parse FETCH_HEAD)" ] && break
  git rebase -q --autostash FETCH_HEAD >/dev/null 2>&1
  if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; then
    git rebase --abort >/dev/null 2>&1; rm -rf .git/rebase-merge .git/rebase-apply; sleep 2; continue; fi
  git push -q "$URL" HEAD:main 2>/dev/null && { echo "PUSHED attempt $i"; break; }
  sleep 2
done

sleep 3
git fetch -q "$URL" main 2>/dev/null
echo "=== VERIFY BY CONTENT ON ORIGIN ==="
echo "  cupertino layer:  $(git show FETCH_HEAD:dashboard.py | grep -c 'CUPERTINO-DARK v2')"
echo "  #wnba-scoped:     $(git show FETCH_HEAD:dashboard.py | grep -c '#wnba ')"
echo "  _llogo():         $(git show FETCH_HEAD:dashboard.py | grep -c 'def _llogo')"
echo "  OVER/UNDER word:  $(git show FETCH_HEAD:dashboard.py | grep -c 'oword')"
echo "  drawer elevates:  $(git show FETCH_HEAD:dashboard.py | grep -c 'cu-grp2')"
echo "  NO unscoped .pind override: $(git show FETCH_HEAD:dashboard.py | grep -cE '^  \.pind \{\{ width:auto')"
echo "  patch scripts:    $(git show FETCH_HEAD:apply_cupertino_dark.py >/dev/null 2>&1 && echo present || echo MISSING) / $(git show FETCH_HEAD:fix_cupertino_scope.py >/dev/null 2>&1 && echo present || echo MISSING)"
