"""Mirror the BetMGM fix into the CLIENT-side renderer — the one the phone actually sees.

The TT card is rendered TWICE: baked by _tt_totals_card in Python, then overwritten every 60s by
window._applyTTTotals in the browser from the raw fd_board/tt_board JSON. I fixed only the Python
side, so the board was correct on a fresh bake and reverted to the old behaviour a minute later —
which is why it did not appear on the phone.

Two copies of the same rule, drifting. Fifth instance today: tt_board's filter vs check_today's
gate; the correlation cap's band vs selection's band; pga_e3's first_tee vs the validator's;
elite_h2h's pick vs the skip chain; and now the baked card vs the live card. The pattern is always
the same — a second implementation is written for a good reason and then only one of them is
maintained.

The client now walks tt_board.bets for any pair the FanDuel loop did not already render, exactly as
the Python side does, and labels the source instead of hardcoding "FanDuel". `bets` is post-gate by
construction, so this can only add plays that already passed every rule.

TT_LIVE_JS is a plain triple-quoted string, not an f-string, so JS braces need no doubling here —
unlike the CSS block, where a single brace is a runtime error.
"""
import ast
import io
import shutil

P = "dashboard.py"
s = io.open(P, encoding="utf-8").read()

if "_ttBets" in s:
    print("  = client renderer already handles BetMGM bets")
    raise SystemExit(0)

# 1. add the bets pass, before the projections loop
old = """    // projected likely-flags (pre-filtered to >=70% in tt_board) — DROP the moment FanDuel posts"""
new = """    // BETS PRICED AWAY FROM FANDUEL. The loop above only sees fd_board pairs, and elite_h2h is
    // itself built from fd_board, so a bet taken at a fresh BetMGM line renders nowhere — it sat in
    // `bets`, counted in the record, invisible. An EXTRA play gets noticed; a MISSING one does not.
    // `bets` is post-gate (tt_board routes refused plays to `skipped`), so this cannot loosen anything.
    (_ttBets || []).forEach(function(b){
      if (!b || !b.play_to || !b.ts) return;
      var k = _ttKey(_ttNorm(b.p1), _ttNorm(b.p2));
      if (boardPairs[k]) return;
      var st = b.ts * 1000; if (st <= now) return;
      boardPairs[k] = 1;
      entries.push({start: st, p1: b.p1, p2: b.p2, line: +b.play_to,
                    side: (String(b.side||'').charAt(0) === 'O') ? 'over' : 'under',
                    hit: b.raw, real: true, book: 'BetMGM'});
    });
    // projected likely-flags (pre-filtered to >=70% in tt_board) — DROP the moment FanDuel posts"""
assert old in s, "projections-loop anchor missing"
s = s.replace(old, new, 1)

# 2. label the source from the entry rather than hardcoding FanDuel
old_src = """      var src = x.real ? '<span class="fd">FanDuel ' + mid + ' confirmed</span>' : '<span class="pj">projected</span>';"""
new_src = """      var src = x.real ? '<span class="fd">' + (x.book || 'FanDuel') + ' ' + mid + ' confirmed</span>' : '<span class="pj">projected</span>';"""
assert old_src in s, "source-label anchor missing"
s = s.replace(old_src, new_src, 1)

# 3. a normaliser matching fd_tt.norm closely enough to dedupe against the board keys
old_key = "  window._applyTTTotals = function(){"
new_key = """  function _ttNorm(x){ return String(x||'').toLowerCase().trim(); }
  window._applyTTTotals = function(){"""
assert old_key in s, "function anchor missing"
s = s.replace(old_key, new_key, 1)

# 4. make the bets array available to the client — exact anchors, verified in source
old_decl = "  let _ttBoard = null, _ttH2H = null, _ttUpcoming = null;"
new_decl = "  let _ttBoard = null, _ttH2H = null, _ttUpcoming = null, _ttBets = null;"
assert old_decl in s, "declaration anchor missing"
s = s.replace(old_decl, new_decl, 1)

old_asn = "_ttUpcoming = Array.isArray(d2.elite_upcoming) ? d2.elite_upcoming : []; }"
new_asn = ("_ttUpcoming = Array.isArray(d2.elite_upcoming) ? d2.elite_upcoming : []; "
           "_ttBets = Array.isArray(d2.bets) ? d2.bets : []; }")
assert old_asn in s, "assignment anchor missing"
s = s.replace(old_asn, new_asn, 1)

ast.parse(s)
shutil.copyfile(P, "/tmp/dashboard.prejsbmgm.py")
io.open(P, "w", encoding="utf-8").write(s)
print("  + client renderer mirrors the Python side: BetMGM bets render, source labelled")
