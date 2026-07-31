"""A pair with a REAL line that fails the gate must leave the board — not reappear as a projection.

THE BUG. The projections loop drops a pair once it appears in `boardPairs`, and only two things add
to that set: the FanDuel loop (which requires a passing pick) and the bets loop (passing bets). A
pair that HAS a real posted line but FAILS the gate is in `skipped` — so nothing marks it, and the
projection survives.

The board then shows the refused play as a live-looking flag at a MADE-UP line. Right now:

    Fabis v Trela        real line 81.5, over 75% -> REFUSED (needs 80%)
                         rendered as "~79.5 projected 75%"

A projected row means "we have not seen a real price yet". Once a real price exists and the model
has said no, that statement is false, and it is false in the most damaging direction — it looks like
an available bet.

THE RULE, as asked: once a flag has a FanDuel or BetMGM line, keep it on the board if it is
playable and take it off if it is not. So `skipped` pairs now mark boardPairs exactly as bets do,
which suppresses their projection. Nothing else changes: skipped plays still never render as bets,
and pairs with no real line anywhere still project normally.
"""
import ast
import io
import shutil

P = "dashboard.py"
s = io.open(P, encoding="utf-8").read()

if "_ttSkipped" in s:
    print("  = skipped pairs already suppress their projection")
    raise SystemExit(0)

# ── 1. the bootstrap must carry `skipped` ───────────────────────────────────────────────────
old_boot = '''    boot = {"board": fb.get("matches") or [],
            "h2h": (data or {}).get("elite_h2h") or [],
            "upcoming": (data or {}).get("elite_upcoming") or [],
            "bets": (data or {}).get("bets") or []}'''
new_boot = '''    boot = {"board": fb.get("matches") or [],
            "h2h": (data or {}).get("elite_h2h") or [],
            "upcoming": (data or {}).get("elite_upcoming") or [],
            "bets": (data or {}).get("bets") or [],
            # REFUSED plays travel too — not to render, but so their PROJECTION is suppressed.
            # A pair with a real line the model said no to must leave the board, and without this
            # it silently reverts to a projected row at a made-up line, which reads as a live bet.
            "skipped": (data or {}).get("skipped") or []}'''
assert old_boot in s, "bootstrap anchor missing"
s = s.replace(old_boot, new_boot, 1)

# ── 2. declare + seed + fetch the skipped list ──────────────────────────────────────────────
old_decl = "  let _ttBoard = null, _ttH2H = null, _ttUpcoming = null, _ttBets = null;"
new_decl = "  let _ttBoard = null, _ttH2H = null, _ttUpcoming = null, _ttBets = null, _ttSkipped = null;"
assert old_decl in s, "declaration anchor missing"
s = s.replace(old_decl, new_decl, 1)

old_seed = "    _ttBets = Array.isArray(b.bets) ? b.bets : [];"
new_seed = ("    _ttBets = Array.isArray(b.bets) ? b.bets : [];\n"
            "    _ttSkipped = Array.isArray(b.skipped) ? b.skipped : [];")
assert old_seed in s, "seed anchor missing"
s = s.replace(old_seed, new_seed, 1)

old_fetch = "_ttBets = Array.isArray(d2.bets) ? d2.bets : []; }"
new_fetch = ("_ttBets = Array.isArray(d2.bets) ? d2.bets : []; "
             "_ttSkipped = Array.isArray(d2.skipped) ? d2.skipped : []; }")
assert old_fetch in s, "fetch anchor missing"
s = s.replace(old_fetch, new_fetch, 1)

# ── 3. mark refused pairs so their projection is suppressed ─────────────────────────────────
old_proj = """    // projected likely-flags (pre-filtered to >=70% in tt_board) — DROP the moment FanDuel posts"""
new_proj = """    // REFUSED PLAYS SUPPRESS THEIR OWN PROJECTION. They are never rendered, but a pair that has a
    // real FanDuel/BetMGM line and failed the gate must LEAVE the board rather than fall back to a
    // projected row at an invented line — that reads as an available bet when the model said no.
    (_ttSkipped || []).forEach(function(b){
      if (!b || !b.p1 || !b.p2) return;
      var s1 = _ttNorm(b.p1), s2 = _ttNorm(b.p2);
      boardPairs[_ttKey(s1, s2)] = 1;
      boardLast[_ttKey(_ttLast(s1), _ttLast(s2))] = 1;
    });
    // projected likely-flags (pre-filtered to >=70% in tt_board) — DROP the moment FanDuel posts"""
assert old_proj in s, "projections anchor missing"
s = s.replace(old_proj, new_proj, 1)

ast.parse(s)
shutil.copyfile(P, "/tmp/dashboard.preskipproj.py")
io.open(P, "w", encoding="utf-8").write(s)
print("  + refused pairs now suppress their projection; playable ones stay")
