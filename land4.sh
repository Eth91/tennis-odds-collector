#!/bin/bash
set -u
cd ~/tennis-odds-collector || exit 1
set -a; . ~/wnba-loop.env; set +a
URL="https://x-access-token:${GIT_PAT}@github.com/fgf9p6ks2f-ux/tennis-odds-collector.git"
rm -rf .git/rebase-merge .git/rebase-apply
for f in pga_e3.py pga_audit.py pga_birdies.py fix_e3wave.py fix_players_of.py; do [ -f "$f" ] && git add "$f"; done
if ! git diff --cached --quiet; then
  git -c user.email=vm@local -c user.name=vm commit -q -F - <<'MSG'
PGA wave: read the orchestrator tee sheet, use the fitted coefficient

The live wave block had two separate defects. It read ESPN's per-competitor teeTime stamp,
which stays empty until a round is basically underway — that is the audit's "0 tee times
known -> dormant". And its shift was `0.04 * wind_gap`, under a comment conceding the
thesis was "0.5-1.5 strokes for a real wave split, which this reproduces". Reproducing an
assumption is not measuring one.

Now: the sheet comes from the PGA orchestrator, which posts it days earlier (294 entries
for the Rocket Classic while ESPN showed 0) and is re-harvested every run so a Tue/Wed
release is picked up immediately; the shift comes from pga_wave.fit_wave, which regresses
the AM/PM stroke gap on the wave wind-exposure gap WITHIN each event-round so course, field
and par mix all cancel. ESPN remains a fallback, but now with the fitted beta.

Also guards players_of against events with no modelled leaderboard (team formats, one
abandoned event) — that killed the 2024-25 backfill 33 events in.
MSG
  echo "committed $(git rev-parse --short HEAD)"
fi
for i in $(seq 1 25); do
  rm -rf .git/rebase-merge .git/rebase-apply
  git fetch -q "$URL" main 2>/dev/null
  [ "$(git rev-parse HEAD)" = "$(git rev-parse FETCH_HEAD)" ] && { echo identical; break; }
  git rebase -q --autostash FETCH_HEAD >/dev/null 2>&1
  if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; then
    git rebase --abort >/dev/null 2>&1; rm -rf .git/rebase-merge .git/rebase-apply; sleep 2; continue; fi
  git push -q "$URL" HEAD:main 2>/dev/null && { echo "PUSHED attempt $i"; break; }
  sleep 2
done
L=$(git rev-parse HEAD); R=$(git ls-remote "$URL" main 2>/dev/null | cut -f1)
[ "$L" = "$R" ] && echo "MATCH" || echo "MISMATCH local=$L remote=$R"
tail -2 birdie_backfill.log
