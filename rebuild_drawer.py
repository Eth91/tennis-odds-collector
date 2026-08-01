"""Delete the WNBA drawer and rebuild it from scratch under a fresh namespace.

WHY A NAMESPACE, NOT ANOTHER PATCH. Three attempts at the spacing each fixed a real cause and each
failed, because a rule I had not found kept outranking the fix:

    attempt 1  .bwrap padding survived a 0fr row          -> dead space
    attempt 2  #wnba .dsec  (1,1,0) later in source       -> cancelled the gap
    attempt 3  .bwrap > .meters + .dsec  (1,3,0)          -> beat it on specificity

Chasing selectors one at a time was the mistake. The drawer now emits entirely new class names
(dw-*), which NO existing rule matches, so the legacy CSS is inert against it by construction
rather than by my having found every last rule.

STRUCTURE — a plain vertical stack. One section per idea, each with a small caps label, separated
by one hairline and one gap. No nested surfaces: the drawer is already elevated above the card, and
in dark mode raising something a second time inside it reads as a mistake.

    .dw
      .dw-s      Confidence      (the meters)
      .dw-s      Why this flagged
      .dw-s      Same-lineup history      (omitted entirely when absent)
      .dw-s      Recent games            (the chart)

The chart, reasoning, regime block and game log all keep their existing data and logic untouched —
only the wrapper markup and the class names change.
"""
import ast
import io
import re
import shutil

P = "dashboard.py"
s = io.open(P, encoding="utf-8").read()

if "CUPERTINO-DW" in s:
    print("  = already rebuilt")
    raise SystemExit(0)

# ── 1. new emitter ──────────────────────────────────────────────────────────────────────────────
start = s.index("def _bars(r, meters=\"\"):")
end = s.index("\ndef ", start + 10)
old_body = s[start:end]

NEW = '''def _bars(r, meters=""):
    """The expanded card detail. CUPERTINO-DW: a flat vertical stack of labelled sections —
    confidence, reasoning, same-lineup history, recent games — separated by one hairline each.

    Emits dw-* class names deliberately. The previous drawer accumulated rules across several
    passes that fought each other on specificity; a fresh namespace means none of them can match
    this markup, so its spacing is defined in exactly one place.
    """
    def sec(label, inner):
        """A section, or nothing at all. An absent block must not leave an orphan label or a
        trailing rule behind it — that was half of what made the old spacing look arbitrary."""
        return f'<div class="dw-s"><div class="dw-l">{label}</div>{inner}</div>' if inner else ""

    parts = [sec("Confidence", meters),
             sec("Why this flagged", f'<div class="dw-p">{_reasoning(r)}</div>'),
             sec("Same-lineup history", _regime_html(r))]

    s_ = _samples(r)
    if s_:
        s_ = list(reversed(s_))                        # newest-first -> oldest on the left
        line = float(r["line"])
        side = (r.get("side") if hasattr(r, "get") else r["side"]) or "over"
        vals = [x[0] for x in s_]
        # two scales, so the gray minutes bar always reads taller than the coloured stat bar
        mx = max(max(vals), line) * 1.62 or 1
        onside = (lambda v: v > line) if side == "over" else (lambda v: v < line)
        hits = sum(1 for v in vals if onside(v))
        cols = ""
        for x in s_:
            v = x[0]
            mn = x[2] if len(x) > 2 else 0
            cols += (f'<div class="dw-col">'
                     f'<div class="dw-min" style="height:{min(mn / 42 * 100, 97):.0f}%"></div>'
                     f'<div class="dw-bar {"on" if onside(v) else "off"}" '
                     f'style="height:{v / mx * 100:.1f}%"><span>{v:g}</span></div></div>')
        opps = "".join(f'<span>{html.escape(str(o) or "")}</span>' for _, o, *_ in s_)
        chart = (f'<div class="dw-chart">'
                 f'<div class="dw-line" style="bottom:{line / mx * 100:.1f}%"><span>{line:g}</span></div>'
                 f'{cols}</div><div class="dw-opps">{opps}</div>'
                 f'<div class="dw-note">{hits}/{len(s_)} {side} {line:g}</div>')
        parts.append(sec("Recent games", chart))
    else:
        parts.append(sec("Recent games", '<div class="dw-p">No game data.</div>'))

    return f'<div class="bars"><div class="dw">{"".join(p for p in parts if p)}</div></div>'

'''
s = s[:start] + NEW + s[end + 1:]

# ── 2. one stylesheet, appended last ────────────────────────────────────────────────────────────
CSS = r"""
  /* ══════════════════ CUPERTINO-DW ══════════════════
     The drawer, rebuilt under its own namespace. Nothing above this block matches dw-*, so this is
     the only place its spacing is defined. Collapsed state carries NO padding — padding is
     intrinsic and a 0fr grid row cannot collapse it, which is what left dead space under every
     closed card twice before. */
  #wnba .bars {{ padding:0; }}
  #wnba .bars.open {{ padding:0 12px 12px; }}
  #wnba .dw {{ padding:0; }}
  #wnba .bars.open .dw {{ background:var(--cu-grp2); border-radius:10px; padding:16px; }}

  #wnba .dw-s + .dw-s {{ margin-top:16px; padding-top:16px; border-top:.5px solid var(--cu-sep); }}
  #wnba .dw-l {{ font-size:12px; font-weight:600; letter-spacing:.02em; text-transform:uppercase;
                 color:var(--cu-lbl2); margin:0 0 10px; }}
  #wnba .dw-p {{ font-size:15px; line-height:1.45; color:var(--cu-lbl2); margin:0; }}
  #wnba .dw-p b {{ color:var(--cu-lbl); font-weight:600; }}

  /* meters, inherited from the card's language */
  #wnba .dw .meter {{ display:flex; align-items:center; gap:12px; margin:0 0 10px; }}
  #wnba .dw .meter:last-child {{ margin-bottom:0; }}
  #wnba .dw .mlab {{ font-size:14px; color:var(--cu-lbl2); width:112px; flex:none; }}
  #wnba .dw .mbar {{ flex:1; height:7px; background:var(--cu-fill); border-radius:4px; overflow:hidden; }}
  #wnba .dw .mbar i {{ display:block; height:100%; background:var(--cu-blue); border-radius:4px; }}
  #wnba .dw .meter.good .mbar i {{ background:var(--cu-grn); }}
  #wnba .dw .meter.bad .mbar i {{ background:var(--cu-red); }}
  #wnba .dw .mval {{ font-size:14px; font-weight:590; color:var(--cu-lbl); margin-left:auto;
                     font-variant-numeric:tabular-nums; }}

  /* regime block, flattened onto the drawer surface */
  #wnba .dw .regime {{ background:none !important; border:0 !important; padding:0 !important;
                       margin:0 !important; }}
  #wnba .dw .rgh {{ font-size:15px; line-height:1.45; color:var(--cu-lbl2); }}
  #wnba .dw .rgh b {{ color:var(--cu-lbl); font-weight:600; }}
  #wnba .dw .rgsub {{ font-size:13px; color:var(--cu-lbl3); margin-top:8px; }}
  #wnba .dw .cmps {{ display:flex; gap:6px; flex-wrap:wrap; margin-top:12px; }}
  #wnba .dw .cmp {{ background:var(--cu-fill); border:0; border-radius:11px; padding:4px 10px;
                    font-size:13px; color:var(--cu-lbl2); font-variant-numeric:tabular-nums; }}
  #wnba .dw .cmp b {{ color:var(--cu-lbl); font-weight:600; }}
  #wnba .dw .sup {{ color:var(--cu-grn); }}
  #wnba .dw .warn {{ color:var(--cu-org); }}

  /* game log */
  #wnba .dw-chart {{ position:relative; display:flex; align-items:flex-end; gap:5px; height:96px;
                     margin:0; }}
  #wnba .dw-col {{ position:relative; flex:1; height:100%; display:flex; align-items:flex-end;
                   justify-content:center; }}
  #wnba .dw-min {{ position:absolute; bottom:0; left:0; right:0; background:var(--cu-fill);
                   border-radius:3px 3px 0 0; }}
  #wnba .dw-bar {{ position:relative; width:100%; border-radius:3px 3px 0 0; min-height:15px;
                   display:flex; align-items:flex-start; justify-content:center; }}
  #wnba .dw-bar.on {{ background:var(--cu-grn); }}
  #wnba .dw-bar.off {{ background:rgba(255,69,58,.55); }}
  #wnba .dw-bar span {{ font-size:11px; font-weight:600; color:#000; margin-top:2px;
                        font-variant-numeric:tabular-nums; }}
  #wnba .dw-line {{ position:absolute; left:0; right:0; height:1px; background:var(--cu-lbl3);
                    z-index:2; }}
  #wnba .dw-line span {{ position:absolute; right:0; top:-16px; font-size:11px;
                         color:var(--cu-lbl3); font-variant-numeric:tabular-nums; }}
  #wnba .dw-opps {{ display:flex; gap:5px; margin-top:6px; }}
  #wnba .dw-opps span {{ flex:1; text-align:center; font-size:11px; color:var(--cu-lbl3); }}
  #wnba .dw-note {{ font-size:13px; color:var(--cu-lbl3); margin-top:10px; }}
"""
a = "</style></head><body>"
assert a in s, "style anchor"
s = s.replace(a, CSS + a, 1)

ast.parse(s)
shutil.copyfile(P, "/tmp/dashboard.predw.py")
io.open(P, "w", encoding="utf-8").write(s)
print("  + drawer deleted and rebuilt under the dw-* namespace")
print("  + legacy drawer CSS is now inert (nothing matches dw-*)")
