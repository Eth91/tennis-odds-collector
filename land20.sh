#!/bin/bash
set -u
cd ~/tennis-odds-collector || exit 1
set -a; . ~/wnba-loop.env; set +a
URL="https://x-access-token:${GIT_PAT}@github.com/fgf9p6ks2f-ux/tennis-odds-collector.git"
rm -rf .git/rebase-merge .git/rebase-apply
python3 fix_topn_pool.py || exit 1
python3 -c "import ast,io; [ast.parse(io.open(f).read()) for f in ('pga_e3.py','pga_audit.py')]; print('  both parse')"
git add pga_e3.py pga_audit.py fix_topn_pool.py
if ! git diff --cached --quiet; then
  git -c user.email=vm@local -c user.name=vm commit -q -F - <<'MSG'
PGA: two more fake-edge bugs, both inside the devig path I fixed yesterday

#8 TWO DIFFERENT PRODUCTS POOLED. "Top 20" and "Top 20 Finish (Incl. Ties)" are separate
markets with different payouts. The dedupe collapsed them into one family keeping the SHORTEST
price per runner. Measured live: 1,620 rows implying 343 qualifiers plus 253 implying 45, merged
into a pool implying 29.2 against a target of 20. Since fair = (1/od) * N / inv, that DEFLATED
every fair probability by ~28%, and the flag is `ours - fair >= TN_EDGE` — so a player whose
true fair top-20 is 0.30 saw a fair of 0.216 and collected +8.4 points of edge that did not
exist. Identical mechanism to the original +20-27% bug; the 0.4N-3N guard waves 29.2 through.

I had seen this exact number and rationalised it in the audit as "FD's top-N books run ~1.5x
overround, so our edges are understated, the safe direction." Wrong twice over: it is not an
overround, and the direction is not safe. An anomaly explained away without being investigated
should be treated as a bug until proven otherwise.

#9 `event LIKE '%PGA%'` ALSO MATCHES "LPGA". The audit's devig sanity check — whose entire job
is to catch pooling errors — could pool a women's event into the men's pool.

Fixes: key pools on the full mtype so distinct products devig separately; restrict every pool to
runners in the current field; match the tour on a word boundary.
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
echo "=== POOLS AFTER THE FIX (audit section 7) ==="
nice -n 8 timeout 1500 python3 -u pga_audit.py 2>&1 | sed -n "/\[7\]/,/\[8\]/p"
echo "=== E3 top-N streams after the fix ==="
nice -n 8 timeout 1200 python3 -u pga_e3.py 2>&1 | grep -E "skip TOP|skip OUT|E3 preview|birdies: flags" | tail -8
