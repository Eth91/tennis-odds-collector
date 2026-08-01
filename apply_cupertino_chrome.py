"""Wire the page chrome to the iPhone render: large title, segmented tabs, filter chips.

Three gaps remained between the board and the render, all of them OUTSIDE the card:

  1. header  — <h1> was 21px; iOS large title is 34pt, with the live row as a 14pt secondary line
  2. tabs    — a custom pill bar; the render uses an iOS segmented control
  3. chips   — the render has a filter row; the board had none

TABS ARE RESTYLED, NOT REWRITTEN. .tabs already carries a .tabthumb sliding indicator, which is
exactly the mechanism an iOS segmented control uses — so showTab()/_thumb() keep working untouched
and only the paint changes. Rewriting that JS would have risked the panel switching for nothing.

THE CHIPS ACTUALLY FILTER. A decorative filter row would be fake UI, so: cards carry data-status /
data-book / data-lad, counts are computed from the DOM at runtime, and any filter that matches
nothing is never rendered. Selecting one hides non-matching cards and collapses any section left
empty. No chip can ever show a count it did not measure.

Scoped: the chips are #wnba-only. Header and tabs are page-level chrome shared by all four boards,
so those change everywhere — deliberately, since they are the same object on every panel.
"""
import ast
import io
import shutil

P = "dashboard.py"
s = io.open(P, encoding="utf-8").read()

if "CUPERTINO-CHROME" in s:
    print("  = already applied")
    raise SystemExit(0)

# ── 1. data attributes so the chips can filter on something real ────────────────────────────────
old_c = '''      <div class="cu-c">
        <div class="cu-sum" data-side="{side}" data-k="{dk}"'''
new_c = '''      <div class="cu-c" data-status="{scls}" data-book="{best_bk}" data-lad="{1 if rungs and len(rungs) > 1 else 0}">
        <div class="cu-sum" data-side="{side}" data-k="{dk}"'''
assert old_c in s, "card anchor missing"
s = s.replace(old_c, new_c, 1)

# ── 2. the chips container, inside #wnba, above the games ───────────────────────────────────────
old_p = '''  <div class="panel" id="wnba">
    {recstrip_html}
    <div id="games">{cards}</div>'''
new_p = '''  <div class="panel" id="wnba">
    {recstrip_html}
    <div id="wnbafilters" class="cu-chips" hidden></div>
    <div id="games">{cards}</div>'''
assert old_p in s, "panel anchor missing"
s = s.replace(old_p, new_p, 1)

# ── 3. chrome CSS ───────────────────────────────────────────────────────────────────────────────
CSS = r"""
  /* ══════════════════ CUPERTINO-CHROME ══════════════════
     Page chrome to match the iPhone render: iOS large title, segmented tabs, filter chips. */
  .wrap {{ padding:14px 20px 48px; }}
  header {{ padding:0 0 2px; }}
  h1 {{ font-size:34px; font-weight:700; letter-spacing:-.037em; line-height:1.1;
        color:var(--cu-lbl); }}
  .live {{ font-size:14px; color:var(--cu-lbl2); gap:7px; margin-top:3px;
           font-variant-numeric:tabular-nums; }}
  .live .dot {{ width:7px; height:7px; border-radius:50%; background:var(--cu-grn); flex:none; }}
  .rfrsh {{ width:28px; height:28px; border-radius:14px; background:var(--cu-fill);
            border:0; color:var(--cu-lbl2); font-size:14px; margin-left:auto; }}
  .rfrsh:active {{ background:rgba(120,120,128,.4); }}

  /* segmented control — .tabthumb becomes the selected segment, so showTab() is untouched */
  .tabs {{ background:var(--cu-fill); border:0; border-radius:9px; padding:2px; gap:2px;
           margin:13px 0 0; }}
  .tab {{ border-radius:7px; padding:6px 0; font-size:13px; font-weight:590;
          color:var(--cu-lbl2) !important; gap:5px; }}
  .tab.active {{ color:var(--cu-lbl) !important; }}
  .tabthumb {{ top:2px; bottom:2px; left:2px; border-radius:7px; background:#636366 !important;
               box-shadow:0 3px 8px rgba(0,0,0,.3); }}
  .tabic {{ width:14px; height:14px; opacity:1; }}

  /* filter chips — rendered only for filters that actually match something */
  .cu-chips {{ display:flex; gap:7px; padding:12px 0 4px; overflow-x:auto;
               -webkit-overflow-scrolling:touch; scrollbar-width:none; }}
  .cu-chips::-webkit-scrollbar {{ display:none; }}
  .cu-chips[hidden] {{ display:none; }}
  .cu-ch {{ background:var(--cu-grp); border:0; border-radius:15px; font:inherit; font-size:13px;
            font-weight:500; color:var(--cu-lbl); padding:6px 12px; white-space:nowrap;
            cursor:pointer; display:inline-flex; gap:5px; align-items:center;
            transition:background .14s,color .14s; }}
  .cu-ch:hover {{ background:var(--cu-grp2); }}
  .cu-ch[aria-current="true"] {{ background:var(--cu-blue); color:#fff; }}
  .cu-ch .ct {{ font-size:12px; color:var(--cu-lbl2); font-variant-numeric:tabular-nums; }}
  .cu-ch[aria-current="true"] .ct {{ color:rgba(255,255,255,.7); }}
  .cu-ch:focus-visible {{ outline:2px solid var(--cu-blue); outline-offset:2px; }}
"""
anchor = "</style></head><body>"
assert anchor in s, "style anchor missing"
s = s.replace(anchor, CSS + anchor, 1)

# ── 4. the filter behaviour ─────────────────────────────────────────────────────────────────────
JS = r"""
  // ---- CUPERTINO-CHROME: real filter chips -------------------------------------------------
  // Counts are measured from the rendered cards, never precomputed, so a chip cannot claim a
  // number it did not find. A filter matching zero cards is not rendered at all rather than
  // shown as a dead affordance.
  (function () {{
    var host = document.getElementById('wnbafilters');
    if (!host) return;
    var cards = [].slice.call(document.querySelectorAll('#wnba .cu-c[data-status]'));
    if (cards.length < 2) return;                       // one card needs no filter row
    var defs = [
      {{ k: 'all', l: 'All',         m: function () {{ return true; }} }},
      {{ k: 'ok',  l: 'Starting',    m: function (c) {{ return c.dataset.status === 'ok'; }} }},
      {{ k: 'mid', l: 'Likely',      m: function (c) {{ return c.dataset.status === 'mid'; }} }},
      {{ k: 'pp',  l: 'In progress', m: function (c) {{ return c.dataset.status === 'pp'; }} }},
      {{ k: 'lad', l: 'Ladders',     m: function (c) {{ return c.dataset.lad === '1'; }} }},
      {{ k: 'fd',  l: 'FanDuel',     m: function (c) {{ return c.dataset.book === 'fd'; }} }},
      {{ k: 'dk',  l: 'DraftKings',  m: function (c) {{ return c.dataset.book === 'dk'; }} }}
    ];
    var cur = 'all';
    function apply() {{
      var d = defs.filter(function (x) {{ return x.k === cur; }})[0] || defs[0];
      cards.forEach(function (c) {{ c.style.display = d.m(c) ? '' : 'none'; }});
      // a section whose cards are all hidden collapses, header and all
      [].forEach.call(document.querySelectorAll('#wnba .game'), function (g) {{
        var any = [].some.call(g.querySelectorAll('.cu-c'), function (c) {{
          return c.style.display !== 'none';
        }});
        g.style.display = any ? '' : 'none';
      }});
    }}
    function draw() {{
      host.innerHTML = '';
      var shown = 0;
      defs.forEach(function (d) {{
        var n = cards.filter(d.m).length;
        if (!n) return;                                 // never render an empty filter
        shown++;
        var b = document.createElement('button');
        b.className = 'cu-ch';
        b.type = 'button';
        if (d.k === cur) b.setAttribute('aria-current', 'true');
        b.appendChild(document.createTextNode(d.l + ' '));
        var ct = document.createElement('span');
        ct.className = 'ct';
        ct.textContent = n;
        b.appendChild(ct);
        b.addEventListener('click', function () {{ cur = d.k; apply(); draw(); }});
        host.appendChild(b);
      }});
      host.hidden = shown < 2;                          // one chip is not a filter
    }}
    draw();
    apply();
  }})();
"""
js_anchor = "  function showTab(t) {{"
assert js_anchor in s, "js anchor missing"
s = s.replace(js_anchor, JS + "\n" + js_anchor, 1)

ast.parse(s)
shutil.copyfile(P, "/tmp/dashboard.prechrome.py")
io.open(P, "w", encoding="utf-8").write(s)
print("  + header -> 34pt iOS large title, live row 14pt, refresh 28pt circle")
print("  + tabs   -> segmented control (tabthumb restyled; showTab untouched)")
print("  + chips  -> real filtering, counts measured from the DOM, empty filters never rendered")
