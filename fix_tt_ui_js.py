"""Mirror the odds/logo/gold work into the CLIENT renderer — the one that overwrites the bake."""
import ast, io, shutil
P="dashboard.py"; s=io.open(P,encoding="utf-8").read()
if "_ttAm" in s:
    print("  = client already renders odds"); raise SystemExit(0)

# helper: format American, converting from decimal when asked (fd_board is american, bmbets decimal)
old_h = "  function _ttNorm(x){"
new_h = ("""  // fd_board stores AMERICAN, bmbets stores DECIMAL in book.od — printing one as the other
  // shows a plausible, wrong price, so the conversion is explicit at the call site.
  function _ttAm(v, dec){
    if (v === null || v === undefined || v === '') return null;
    var n = Number(v); if (!isFinite(n)) return null;
    if (dec){ if (n <= 1) return null; n = (n >= 2) ? Math.round((n-1)*100) : -Math.round(100/(n-1)); }
    n = Math.round(n);
    return (n > 0 ? '+' + n : String(n));
  }
  var _TTMGM = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'"
    + "%3E%3Crect width='24' height='24' rx='6' fill='%23c9a227'/%3E%3Ctext x='12' y='16'"
    + " font-size='8.5' font-weight='700' text-anchor='middle' fill='%23151b24'"
    + " font-family='Arial,sans-serif'%3EMGM%3C/text%3E%3C/svg%3E";
  function _ttNorm(x){""")
assert old_h in s, "helper anchor missing"
s=s.replace(old_h,new_h,1)

# FanDuel entries carry the posted price for the side taken
old_fd = """      entries.push({start: new Date(m.open_date).getTime(), p1: m.p1, p2: m.p2, line: +m.line,
                    side: entry.pick.side, hit: hit, real: true});"""
new_fd = """      var _od = (entry.pick.side === 'over') ? m.over_odds : m.under_odds;
      entries.push({start: new Date(m.open_date).getTime(), p1: m.p1, p2: m.p2, line: +m.line,
                    side: entry.pick.side, hit: hit, real: true,
                    odds: _ttAm(_od), book: 'FanDuel'});"""
assert old_fd in s, "js fd anchor missing"
s=s.replace(old_fd,new_fd,1)

# BetMGM bets carry theirs, converted from decimal
old_bm = """      entries.push({start: st, p1: b.p1, p2: b.p2, line: +b.play_to,
                    side: (String(b.side||'').charAt(0) === 'O') ? 'over' : 'under',
                    hit: b.raw, real: true, book: 'BetMGM'});"""
new_bm = """      entries.push({start: st, p1: b.p1, p2: b.p2, line: +b.play_to,
                    side: (String(b.side||'').charAt(0) === 'O') ? 'over' : 'under',
                    hit: b.raw, real: true, book: 'BetMGM',
                    odds: _ttAm((b.book||{}).od, true)});"""
assert old_bm in s, "js bets anchor missing"
s=s.replace(old_bm,new_bm,1)

# render price + the right badge, in the book's own colour
old_src = """      var src = x.real ? '<span class="fd">' + (x.book || 'FanDuel') + ' ' + mid + ' confirmed</span>' : '<span class="pj">projected</span>';"""
new_src = """      var _bk = x.book || 'FanDuel', _mgm = (_bk === 'BetMGM'), _cls = _mgm ? 'bmgm' : 'fd';
      var _price = x.odds ? ('<span class="podds ' + _cls + '">' + x.odds + '</span>'
            + '<img class="bklogo" src="' + (_mgm ? _TTMGM : 'book-fd.png') + '" alt="'
            + (_mgm ? 'MGM' : 'FD') + '">') : '';
      var src = x.real ? ('<span class="' + _cls + '">' + _bk + ' ' + mid + ' confirmed</span>' + _price)
                       : '<span class="pj">projected</span>';"""
assert old_src in s, "js render anchor missing"
s=s.replace(old_src,new_src,1)
ast.parse(s)
shutil.copyfile(P,"/tmp/dashboard.prejsui.py")
io.open(P,"w",encoding="utf-8").write(s)
print("  + client: odds for both books, FD logo, BetMGM gold badge")
