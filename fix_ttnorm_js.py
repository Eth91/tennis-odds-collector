"""Make the JS normaliser mirror fd_tt.norm exactly, and add the last-name fallback.

fd_tt.norm does NFKD -> strip combining marks -> lowercase -> collapse whitespace. My JS did
`toLowerCase().trim()`, which agrees only while every name is already ASCII. TT is full of Polish
players; one diacritic and the dedup key stops matching boardPairs, so a FanDuel-priced bet renders
TWICE — once from the fd_board loop and once from the bets loop.

Also adds the last-name fallback the projections loop already uses, so a first-name spelling
difference between sources cannot produce a duplicate either. Two independent guards, because a
duplicate play on the board is exactly the kind of error that destroys trust in it.
"""
import ast, io, shutil
P="dashboard.py"; s=io.open(P,encoding="utf-8").read()
if "u0300-\\u036f" in s or "normalize('NFD')" in s:
    print("  = normaliser already mirrors fd_tt.norm"); raise SystemExit(0)

old = """  function _ttNorm(x){ return String(x||'').toLowerCase().trim(); }"""
new = ("""  // mirrors fd_tt.norm EXACTLY: NFKD, drop combining marks, lowercase, collapse whitespace.
  // toLowerCase().trim() agrees only while names are ASCII; TT is full of Polish names, and one
  // diacritic would break the dedup key and render a FanDuel-priced bet twice.
  function _ttNorm(x){
    return String(x||'').normalize('NFKD').replace(/[\\u0300-\\u036f]/g,'')
      .toLowerCase().split(/\\s+/).filter(Boolean).join(' ');
  }""")
assert old in s, "normaliser anchor missing"
s=s.replace(old,new,1)

old_dedupe = """      var k = _ttKey(_ttNorm(b.p1), _ttNorm(b.p2));
      if (boardPairs[k]) return;"""
new_dedupe = """      var n1 = _ttNorm(b.p1), n2 = _ttNorm(b.p2);
      var k = _ttKey(n1, n2);
      // two guards: the exact normalised key, and the last-name fallback the projections loop
      // already uses, so a first-name spelling difference between sources cannot duplicate a play
      if (boardPairs[k] || boardLast[_ttKey(_ttLast(n1), _ttLast(n2))]) return;"""
assert old_dedupe in s, "dedupe anchor missing"
s=s.replace(old_dedupe,new_dedupe,1)
ast.parse(s)
shutil.copyfile(P,"/tmp/dashboard.prenorm.py")
io.open(P,"w",encoding="utf-8").write(s)
print("  + JS normaliser mirrors fd_tt.norm; last-name fallback added to the bets dedupe")
