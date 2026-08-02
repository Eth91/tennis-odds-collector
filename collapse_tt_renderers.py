"""Collapse the two TT renderers into one.

THE PROBLEM. The card was drawn twice — _tt_totals_card in Python (131 lines) and _applyTTTotals in
JS (125 lines) — implementing the same entry-building AND the same markup in two languages. Five
bugs today came from exactly that: the BetMGM bet invisible on the phone, the "FanDuel" label
hardcoded in one copy, the Python bets-pass silently lost while the JS copy survived, an
idempotency guard colliding with a pre-existing helper, and a patch anchored on the JS block
believing it was the Python one. Keeping two copies in sync is not a discipline problem, it is a
design problem.

THE COLLAPSE. The JS becomes the single renderer. Python's job shrinks to shipping the DATA:

    _tt_panel  ->  <script>window._TT_BOOT = {board, h2h, upcoming, bets}</script>
                   <div id="tt-totals"></div>          (empty; the JS fills it)

The JS seeds itself from _TT_BOOT and paints IMMEDIATELY — no network on first render — then polls
the live JSON every 60s and re-renders through the same function. So:

  * one implementation of the entry logic and the markup;
  * first paint is instant and works with the network down, which is what the server-side bake was
    actually buying;
  * the 60s freshness that matters for a speed-based edge is unchanged.

WHY THIS IS SAFE. The page already requires JS — the tab switching that reveals the TT panel is JS,
so a no-JS visitor never sees this card either way. The health banner stays OUTSIDE #tt-totals, as
before, so a re-render cannot wipe it.

131 lines of duplicated Python deleted.
"""
import ast
import io
import re
import shutil

P = "dashboard.py"
s = io.open(P, encoding="utf-8").read()

if "_TT_BOOT" in s:
    print("  = renderers already collapsed")
    raise SystemExit(0)

# ── 1. JS seeds from the bootstrap, then polls ──────────────────────────────────────────────
old_init = """  window._fetchTTTotals();
  setInterval(window._fetchTTTotals, 60000);"""
new_init = """  // SEED FROM THE SERVER-EMBEDDED BOOTSTRAP, then poll. This is what replaced the Python bake:
  // the markup is built here and only here, but the DATA arrives with the page, so first paint is
  // instant and survives a failed fetch — which is the only thing the second renderer was buying.
  (function(){
    var b = window._TT_BOOT;
    if (!b) return;
    _ttBoard = Array.isArray(b.board) ? b.board : [];
    var mp = {}; (b.h2h || []).forEach(function(e){ mp[_ttKey(e.p1n, e.p2n)] = e; });
    _ttH2H = mp;
    _ttUpcoming = Array.isArray(b.upcoming) ? b.upcoming : [];
    _ttBets = Array.isArray(b.bets) ? b.bets : [];
    try { window._applyTTTotals(); } catch(e){}
  })();
  window._fetchTTTotals();
  setInterval(window._fetchTTTotals, 60000);"""
assert old_init in s, "js init anchor missing"
s = s.replace(old_init, new_init, 1)

# ── 2. _tt_panel emits data + an empty mount, no markup ─────────────────────────────────────
old_panel = """    h = _tt_health(data)
    warn = ("" if h["ok"] else f'<div class="mlbwarn">⚠️ TT feed issue: {html.escape(h["reason"])} — '
            f'flags may be missing (you were alerted). This is NOT a quiet slate.</div>')
    return warn + '<div id="tt-totals">' + _tt_totals_card(data) + '</div>'"""
new_panel = """    h = _tt_health(data)
    warn = ("" if h["ok"] else f'<div class="mlbwarn">⚠️ TT feed issue: {html.escape(h["reason"])} — '
            f'flags may be missing (you were alerted). This is NOT a quiet slate.</div>')
    # ONE RENDERER (2026-07-31). The card used to be built here in Python AND again in JS, and the
    # two copies drifted five separate times in a day. Python now ships only the DATA; the JS in
    # TT_LIVE_JS builds the markup, seeds itself from this bootstrap for an instant first paint, and
    # then polls the live JSON every 60s through the same function.
    fb = {}
    try:
        _f = HERE / "fd_board.json"
        if _f.exists():
            fb = json.loads(_f.read_text())
    except (ValueError, OSError):
        fb = {}
    boot = {"board": fb.get("matches") or [],
            "h2h": (data or {}).get("elite_h2h") or [],
            "upcoming": (data or {}).get("elite_upcoming") or [],
            "bets": (data or {}).get("bets") or []}
    # `</script>` inside embedded JSON would close the tag early; escaping `<` is the standard guard
    boot_js = json.dumps(boot, default=str).replace("<", "\\\\u003c")
    return (warn + f'<script>window._TT_BOOT={boot_js};</script>'
            '<div id="tt-totals"></div>')"""
assert old_panel in s, "panel anchor missing"
s = s.replace(old_panel, new_panel, 1)

# ── 3. delete the Python renderer entirely ──────────────────────────────────────────────────
m = re.search(r"\ndef _tt_totals_card\(tt_json, now=None\):.*?(?=\n(?:def |[A-Z_]+ = |# -{4,}))",
              s, re.S)
assert m, "could not delimit _tt_totals_card"
removed = m.group(0).count("\n")
s = s[:m.start()] + "\n" + s[m.end():]
assert "_tt_totals_card" not in s.replace("def _tt_totals_card", ""), "stray call remains"

ast.parse(s)
shutil.copyfile(P, "/tmp/dashboard.pre_collapse.py")
io.open(P, "w", encoding="utf-8").write(s)
print("  + JS is now the only TT renderer; Python ships data + an empty mount")
print("  + deleted _tt_totals_card (%d lines)" % removed)
