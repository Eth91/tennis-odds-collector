"""Rebuild the WNBA drawer, and give TT the WNBA card layout (no drawer).

WNBA DRAWER — rebuilt, not restyled. It was a stack of divs from the old design that I had been
patching with CSS. Now it emits the same grouped-list grammar as the card: labelled sections with
hairline rules, a KV list for the numbers, prose as prose. Same data, same drawer, same toggle.

TT CARD — rebuilt to the WNBA card anatomy, per request, WITHOUT a drawer:
    status pill + book mark + lock time
    matchup title
    context sub-line
    the bet at 36px with the price right-aligned
    the hit-rate bar on the face
The old TT row put a coloured O/U chip and a floating hit pill either side of a cramped middle
column; this is the same object as a WNBA card, which is what makes them read as one product.
"""
import ast, io, shutil
P="dashboard.py"; s=io.open(P,encoding="utf-8").read()
if "CUPERTINO-REBUILD" in s: print("= already"); raise SystemExit(0)

# ── TT: emit the WNBA card shape ────────────────────────────────────────────────────────────────
old_rows = """      rows += '<div class="ttbet"><span class="pind ' + o.toLowerCase() + '">' + o + '</span>'
            + '<span class="ttbln">' + lncell + '</span>'
            + '<div class="ttbmid"><div class="ttbnm"><b>' + _ttEsc(x.p1) + '</b> v ' + _ttEsc(x.p2) + '</div>'
            + '<div class="ttbsb">' + tip + ' MT ' + mid + ' ' + x.side + ' ' + mid + ' ' + src + '</div></div>' + chip + '</div>';"""
new_rows = """      // CUPERTINO-REBUILD: same anatomy as a WNBA card — status pill + book + lock, title,
      // context sub-line, the bet at display size, hit-rate bar on the face. No drawer.
      var _st = x.real ? '<span class="cu-st ok">Confirmed</span>'
                       : '<span class="cu-st no">Projected</span>';
      var _hit = (x.hit != null)
            ? ('<span class="cu-bar"><i class="' + (x.hit >= 78 ? 'g' : '') + '" style="width:'
               + Math.min(x.hit, 100) + '%"></i></span><span class="cu-pc">' + x.hit + '%</span>'
               + '<span class="cu-n">hit rate</span>')
            : '<span class="cu-bar"></span><span class="cu-pc na">\\u2014</span>'
              + '<span class="cu-n na">no sample</span>';
      rows += '<div class="cu-c"><div class="cu-sum">'
            + '<div class="cu-hd">' + _st + _bklogo + '<span class="cu-time">' + tip + ' MT</span></div>'
            + '<div class="cu-ttl">' + _ttEsc(x.p1) + ' v ' + _ttEsc(x.p2) + '</div>'
            + '<div class="cu-sub">Head-to-head total' + (x.real ? (' \\u00b7 ' + _bk) : '') + '</div>'
            + '<div class="cu-bet"><span class="cu-dir">' + (x.side === 'over' ? 'OVER' : 'UNDER')
            + '</span><span class="cu-line">' + lncell + '</span>'
            + '<span class="cu-price">' + _oddstxt + '</span></div>'
            + '<div class="cu-cf">' + _hit + '</div>'
            + '</div></div>';"""
assert old_rows in s, "tt rows anchor"
s = s.replace(old_rows, new_rows, 1)

# split _price into logo + text so the card can place them separately
old_price = """      var _price = x.odds ? ('<span class="podds ' + _cls + '">' + x.odds + '</span>'
            + '<img class="bklogo" src="' + (_mgm ? _TTMGM : 'book-fd.png') + '" alt="'
            + (_mgm ? 'MGM' : 'FD') + '">') : '';"""
new_price = """      var _bklogo = '<img class="bklogo" src="' + (_mgm ? _TTMGM : 'book-fd.png')
            + '" onerror="if(this.src.indexOf(\\'book-mgm\\')>-1)this.src=_TTMGM_FALLBACK" alt="'
            + (_mgm ? 'MGM' : 'FD') + '">';
      var _oddstxt = x.odds ? ('<span class="cu-od' + (_mgm ? ' bmgm' : '') + '">' + x.odds + '</span>') : '';
      var _price = '';"""
assert old_price in s, "price anchor"
s = s.replace(old_price, new_price, 1)

# ── WNBA drawer: rebuild the markup ─────────────────────────────────────────────────────────────
old_why = '''    why = f'{mhtml}<div class="why">{_reasoning(r)}</div>{_regime_html(r)}\''''
new_why = '''    # CUPERTINO-REBUILD: grouped-list grammar inside the drawer — a labelled section per idea,
    # hairline-ruled, instead of a stack of bare divs.
    why = (f'{mhtml}'
           f'<div class="dsec"><div class="dlab">Why this flagged</div>'
           f'<div class="why">{_reasoning(r)}</div></div>'
           f'{_regime_html(r)}')'''
assert old_why in s, "why anchor"
s = s.replace(old_why, new_why, 1)

CSS = r"""
  /* ══════════════════ CUPERTINO-REBUILD ══════════════════ */
  /* WNBA drawer: labelled sections, hairline-ruled, one rhythm */
  #wnba .dsec {{ padding-top:14px; margin-top:14px; border-top:.5px solid var(--cu-sep); }}
  #wnba .bwrap > .meters + .dsec {{ margin-top:0; border-top:0; padding-top:0; }}
  #wnba .dlab {{ font-size:12px; font-weight:600; letter-spacing:.02em; text-transform:uppercase;
                 color:var(--cu-lbl2); margin-bottom:8px; }}
  #wnba .dsec .why {{ margin:0; }}
  #wnba .regime {{ padding-top:14px !important; margin-top:14px !important; }}

  /* TT now uses the WNBA card components — inherit them inside #tt */
  #tt .cu-c {{ border-bottom:.5px solid var(--cu-sep); }}
  #tt .cu-c:last-child {{ border-bottom:0; }}
  #tt .cu-sum {{ padding:14px 0; }}
  #tt .cu-hd {{ display:flex; align-items:center; gap:8px; margin-bottom:9px; }}
  #tt .cu-st {{ font-size:12px; font-weight:600; padding:2px 8px; border-radius:11px; }}
  #tt .cu-st.ok {{ color:var(--cu-grn); background:rgba(48,209,88,.18); }}
  #tt .cu-st.no {{ color:var(--cu-lbl2); background:var(--cu-fill); }}
  #tt .cu-time {{ margin-left:auto; font-size:14px; color:var(--cu-lbl2);
                  font-variant-numeric:tabular-nums; }}
  #tt .cu-ttl {{ font-size:19px; font-weight:640; letter-spacing:-.022em; color:var(--cu-lbl);
                 margin-bottom:2px; }}
  #tt .cu-sub {{ font-size:15px; color:var(--cu-lbl2); margin-bottom:14px; }}
  #tt .cu-bet {{ display:flex; align-items:baseline; gap:8px; margin-bottom:14px; }}
  #tt .cu-dir {{ font-size:13px; font-weight:700; letter-spacing:.06em; color:var(--cu-lbl2); }}
  #tt .cu-line {{ font-size:36px; font-weight:680; letter-spacing:-.04em; line-height:1;
                  color:var(--cu-lbl); font-variant-numeric:tabular-nums; }}
  #tt .cu-price {{ margin-left:auto; }}
  #tt .cu-od {{ font-size:20px; font-weight:640; letter-spacing:-.02em; color:var(--cu-lbl);
                font-variant-numeric:tabular-nums; }}
  #tt .cu-od.bmgm {{ color:#d4af37; }}
  #tt .cu-cf {{ display:flex; align-items:center; gap:11px; }}
  #tt .cu-bar {{ flex:1; height:7px; background:var(--cu-fill); border-radius:4px; overflow:hidden; }}
  #tt .cu-bar i {{ display:block; height:100%; background:var(--cu-blue); border-radius:4px; }}
  #tt .cu-bar i.g {{ background:var(--cu-grn); }}
  #tt .cu-pc {{ font-size:16px; font-weight:640; font-variant-numeric:tabular-nums; }}
  #tt .cu-pc.na {{ color:var(--cu-lbl3); }}
  #tt .cu-n {{ font-size:14px; color:var(--cu-lbl2); }}
  #tt .cu-n.na {{ color:var(--cu-lbl3); }}
  #tt .tld {{ color:var(--cu-lbl3); font-size:22px; }}
"""
a="</style></head><body>"; assert a in s; s=s.replace(a, CSS+a, 1)
ast.parse(s); shutil.copyfile(P,"/tmp/dashboard.prerebuild.py"); io.open(P,"w",encoding="utf-8").write(s)
print("  + WNBA drawer rebuilt as labelled sections")
print("  + TT rebuilt to the WNBA card anatomy (no drawer)")
