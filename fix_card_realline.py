"""Card renders the REAL posted line/price/book, not the ladder zone.

The bets loop used b.play_to (a display bucket) and dug the price out of b.book.od in DECIMAL. The
payload now carries the actual b.line, b.odds (already AMERICAN, converted at the fd_tt boundary)
and b.book_name, so use those: fewer conversions, and the number on screen is the number the wager
is struck at.

Falls back to play_to when line is absent so an older payload still renders.
"""
import ast, io, shutil
P="dashboard.py"; s=io.open(P,encoding="utf-8").read()
if "b.book_name" in s:
    print("  = card already uses the real line"); raise SystemExit(0)
old = """      entries.push({start: st, p1: b.p1, p2: b.p2, line: +b.play_to,
                    side: (String(b.side||'').charAt(0) === 'O') ? 'over' : 'under',
                    hit: b.raw, real: true, book: 'BetMGM',
                    odds: _ttDecAm((b.book||{}).od)});"""
new = """      // the REAL wager: line/odds/book_name are what the bet is struck at. b.side and b.play_to
      // are the card's ladder ZONE, which is why an 81.5 line used to render as "O<=82.5".
      // b.odds is already AMERICAN (converted at the fd_tt boundary), so no second conversion.
      var _bn = (b.book_name === 'betmgm') ? 'BetMGM' : 'FanDuel';
      entries.push({start: st, p1: b.p1, p2: b.p2,
                    line: (b.line != null ? +b.line : +b.play_to),
                    side: (String(b.side||'').charAt(0) === 'O') ? 'over' : 'under',
                    hit: b.raw, real: true, book: _bn,
                    odds: (b.odds != null ? _ttAm(b.odds) : _ttDecAm((b.book||{}).od))});"""
assert old in s, "bets loop anchor missing"
s=s.replace(old,new,1)
ast.parse(s); shutil.copyfile(P,"/tmp/dashboard.prerealline.py")
io.open(P,"w",encoding="utf-8").write(s)
print("  + card uses the real line / American odds / book name")
