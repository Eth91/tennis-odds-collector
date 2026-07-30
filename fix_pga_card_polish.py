"""Tighten the PGA card into a real bet-slip layout.

Problems with the first pass, looking at it as a card rather than as code:

  * the title carried five separate things — "⛳ PGA · Rocket Classic · PAPER — tracking only,
    not live bets · 0-0 · +0.00u" — plus TWO logo images, one of which (FanDuel) is now
    redundant because every row carries its own book badge;
  * every row was a single flex line, so the selection, the bet detail and the price all
    competed on one baseline. A sportsbook never does this: the selection reads first, the
    detail sits quietly under it, and the price owns the right edge;
  * market headings sat 10px from the rows above them, so the sections ran together.

New row shape, which is what FanDuel actually does:

    Si Woo Kim                                        +125  [FD]
    72 holes vs Chris Gotterup

Selection bold on the top line with the price right-aligned; the line/detail underneath in
muted type. Rows that have no detail (a top-20 finish is just a name) render a single line and
no empty second row.

Title is now simply "PGA Rocket Classic". The paper state moves to a small chip so it stays
honest without shouting, and the record moves to the right where a running P&L belongs.

All type and colour still comes from the shared .podds/.bklogo classes so the PGA and WNBA
cards cannot drift apart.

NOTE FOR ANYONE EDITING THE CSS HERE: this block lives inside a large f-string, so literal
braces MUST be doubled. Writing them single makes Python evaluate the rule and raise
NameError at RUNTIME — py_compile will not catch it, and the whole dashboard stops baking.
"""
import ast
import io

p = "dashboard.py"
s = io.open(p, encoding="utf-8").read()

if "pgabet" in s:
    print("  = card polish already applied")
    raise SystemExit(0)

# ── 1. header: just the event, with the paper state as a quiet chip ───────────────────
old_head = '''    armed = bool((d.get("e3") or {}).get("armed"))
    status = "LIVE" if armed else "PAPER — tracking only, not live bets"
    lg = (f'<img class="glogo" src="logos/pga.png" alt="" loading="lazy" '
          f'onerror="this.style.display=\\'none\\'">'
          f'<img class="glogo" src="logos/fd.png" alt="" loading="lazy" '
          f'onerror="this.style.display=\\'none\\'">')
    head = (f'<div class="sw-title">{lg}⛳ PGA '
            f'<span>· {html.escape(d.get("event") or "")} · {status} · '
            f'{w}-{l} · <b class="{ucls}">{u:+.2f}u</b></span></div>')'''
new_head = '''    armed = bool((d.get("e3") or {}).get("armed"))
    chip = ("" if armed else '<span class="pgapaper">PAPER</span>')
    recd = (f'<span class="pgarec">{w}-{l} <b class="{ucls}">{u:+.2f}u</b></span>'
            if (w or l or u) else "")
    head = (f'<div class="pgahead"><span class="pgatitle">'
            f'PGA {html.escape(d.get("event") or "")}</span>{chip}'
            f'<span class="pgasp"></span>{recd}</div>')'''
assert old_head in s, "header anchor missing"
s = s.replace(old_head, new_head, 1)

# ── 2. rows: selection + price on top, detail underneath ──────────────────────────────
old_row = '''        for who, line, od in sorted(groups[mkt], key=lambda x: x[2]):
            det = f'<span class="pgaline">{html.escape(line)}</span>' if line else ""
            body += (f'<div class="swrow"><div class="swhd">'
                     f'<b>{html.escape(who)}</b>{det}'
                     f'<span class="pgaodds" title="{od:.2f} decimal">'
                     f'<span class="podds fd">{html.escape(_am(od))}</span>'
                     f'<img class="bklogo" src="book-fd.png" alt="FD"></span>'
                     f'</div></div>')'''
new_row = '''        for who, line, od in sorted(groups[mkt], key=lambda x: x[2]):
            # detail on its own line, and omitted entirely when there is none — a top-20
            # finish is just a name, and an empty sub-row leaves a dead gap
            sub = f'<div class="pgasub">{html.escape(line)}</div>' if line else ""
            body += (f'<div class="pgabet"><div class="pgatop">'
                     f'<span class="pgasel">{html.escape(who)}</span>'
                     f'<span class="pgasp"></span>'
                     f'<span title="{od:.2f} decimal">'
                     f'<span class="podds fd">{html.escape(_am(od))}</span>'
                     f'<img class="bklogo" src="book-fd.png" alt="FD"></span>'
                     f'</div>{sub}</div>')'''
assert old_row in s, "row anchor missing"
s = s.replace(old_row, new_row, 1)

# ── 3. CSS. BRACES DOUBLED — this block is inside an f-string ─────────────────────────
old_css = """  .pgamkt {{ margin:10px 0 4px; font-size:11px; letter-spacing:.08em; font-weight:700;
             color:#8b94a3; text-transform:uppercase; }}
  .pgaline {{ margin-left:8px; color:#c8cfda; font-size:12.5px; }}
  .pgaodds {{ margin-left:auto; white-space:nowrap; }}"""
new_css = """  .pgahead {{ display:flex; align-items:center; gap:8px; padding-bottom:2px; }}
  .pgatitle {{ color:#e8ecf2; font-size:15px; font-weight:800; letter-spacing:-.01em; }}
  .pgapaper {{ font-size:9px; font-weight:800; letter-spacing:.06em; color:#d0a45e;
               border:1px solid #d0a45e55; border-radius:5px; padding:2px 5px; }}
  .pgarec {{ color:#7d8696; font-size:11.5px; font-variant-numeric:tabular-nums; }}
  .pgamkt {{ margin:17px 0 1px; font-size:10px; letter-spacing:.09em; font-weight:800;
             color:#79828f; text-transform:uppercase; }}
  .pgamkt:first-of-type {{ margin-top:11px; }}
  .pgabet {{ padding:10px 0 9px; border-top:1px solid #1a1f28; }}
  .pgatop {{ display:flex; align-items:center; gap:8px; }}
  .pgasel {{ color:#e8ecf2; font-size:14.5px; font-weight:700; letter-spacing:-.01em; }}
  .pgasp {{ flex:1 1 auto; }}
  .pgasub {{ color:#7d8696; font-size:12px; margin-top:2px; }}"""
assert old_css in s, "css anchor missing"
s = s.replace(old_css, new_css, 1)

ast.parse(s)
io.open(p, "w", encoding="utf-8").write(s)
print("  + title is now just 'PGA <event>'; paper state is a chip; record moved right")
print("  + rows are two-line bet-slip layout, detail omitted when absent")
print("  + market headings given real separation (17px above, tight to their rows)")
