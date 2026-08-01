"""Compact the drawer. The rebuild was structurally right but far too tall.

Judgement, from looking at it on the device:

  - "CONFIDENCE" sat above two rows reading "when they sit 2/2 over" and "last 10 games 6/10 over".
    That is a header for self-describing content — a whole row that says nothing.
  - "WHY THIS FLAGGED" sat above prose that obviously IS the reason.
  - 16pt gaps are more air than this density needs; 12 is the right step for detail text.
  - Drawer type was the same size as the card face. Detail should read as SUBORDINATE to the
    headline, not compete with it.

Labels are kept only where the block would otherwise be ambiguous — "Same-lineup history" and
"Recent games" both need naming; the other two did not.
"""
import ast
import io
import shutil

P = "dashboard.py"
s = io.open(P, encoding="utf-8").read()

if "CUPERTINO-DW2" in s:
    print("  = already applied")
    raise SystemExit(0)

old_parts = '''    parts = [sec("Confidence", meters),
             sec("Why this flagged", f'<div class="dw-p">{_reasoning(r)}</div>'),
             sec("Same-lineup history", _regime_html(r))]'''
new_parts = '''    # No label on the meters or the reasoning: both are self-describing ("when they sit 2/2 over"
    # needs no CONFIDENCE header above it) and a label costs a full row. Labels are kept only where
    # the block would otherwise be ambiguous.
    parts = [sec("", meters),
             sec("", f'<div class="dw-p">{_reasoning(r)}</div>'),
             sec("Same-lineup history", _regime_html(r))]'''
assert old_parts in s, "parts anchor"
s = s.replace(old_parts, new_parts, 1)

old_sec = ('        return f\'<div class="dw-s"><div class="dw-l">{label}</div>{inner}</div>\''
           ' if inner else ""')
new_sec = ('        if not inner:\n'
           '            return ""\n'
           '        lab = f\'<div class="dw-l">{label}</div>\' if label else ""\n'
           '        return f\'<div class="dw-s">{lab}{inner}</div>\'')
assert old_sec in s, "sec anchor"
s = s.replace(old_sec, new_sec, 1)

CSS = r"""
  /* ══════════════════ CUPERTINO-DW2 ══════════════════
     Compacted after looking at it on device. The rebuild was structurally right but far too tall:
     two of its four labels sat above content that already describes itself, and 16pt gaps are more
     air than this density needs. 12pt rhythm, 14pt panel padding, and drawer type a step smaller
     than the card face — detail should read as subordinate to the headline, not compete with it. */
  #wnba .bars.open .dw {{ padding:14px; }}
  #wnba .dw-s + .dw-s {{ margin-top:12px; padding-top:12px; }}
  #wnba .dw-l {{ font-size:11px; margin-bottom:6px; }}
  #wnba .dw-p {{ font-size:14px; line-height:1.4; }}
  #wnba .dw .meter {{ margin-bottom:8px; gap:10px; }}
  #wnba .dw .mlab {{ font-size:13px; width:100px; }}
  #wnba .dw .mbar {{ height:6px; }}
  #wnba .dw .mval {{ font-size:13px; }}
  #wnba .dw .rgh {{ font-size:14px; line-height:1.4; }}
  #wnba .dw .rgsub {{ font-size:12px; margin-top:6px; }}
  #wnba .dw .cmps {{ margin-top:8px; gap:6px; }}
  #wnba .dw .cmp {{ font-size:12px; padding:3px 8px; }}
  #wnba .dw-chart {{ height:76px; gap:4px; }}
  #wnba .dw-bar span {{ font-size:10px; }}
  #wnba .dw-opps {{ margin-top:6px; }}
  #wnba .dw-opps span {{ font-size:10px; }}
  #wnba .dw-note {{ font-size:12px; margin-top:8px; }}
  #wnba .dw-line span {{ font-size:10px; top:-14px; }}
"""
a = "</style></head><body>"
assert a in s, "style anchor"
s = s.replace(a, CSS + a, 1)

ast.parse(s)
shutil.copyfile(P, "/tmp/dashboard.predw2.py")
io.open(P, "w", encoding="utf-8").write(s)
print("  + 2 redundant labels dropped, 12pt rhythm, drawer type subordinate")
