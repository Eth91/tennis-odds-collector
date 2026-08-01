"""Impose ONE spacing scale on the WNBA card and drawer, and kill the duplicate rules.

The audit is the whole story — current values are 13, 14, 9, 7, 8, 11, 12. Those are not a system,
they are a sequence of individual guesses, and that is exactly why it does not read as Apple.
Apple's layout is a 4pt grid and almost nothing else; the consistency IS the design.

    4    hairline-adjacent nudges
    8    label -> its content, chips
    12   related rows inside a block
    16   block -> block inside a card, card padding
    20   card -> card

Also: there were THREE separate `.bars.open` rules (padding declared at lines ~3597, ~3661, ~4121)
accumulated across passes, so the card-to-drawer gap depended on which one happened to win. They
are consolidated into one.

THE GAP the user is describing: the drawer sat directly under the summary's bottom padding with no
top spacing of its own, so the panel read as welded to the card rather than nested inside it. The
summary now ends on 16 and the drawer adds 4 above itself, giving a deliberate 20 between the card
content and the panel edge — one step up the scale from the 16 used inside the panel, so the
nesting is legible.
"""
import ast
import io
import re
import shutil

P = "dashboard.py"
s = io.open(P, encoding="utf-8").read()

if "CUPERTINO-SPACE4" in s:
    print("  = already applied")
    raise SystemExit(0)

# ── remove every competing .bars.open padding rule; one authoritative rule is added below ────────
before = len(re.findall(r"#wnba \.bars\.open \{\{[^}]*\}\}", s))
s = re.sub(r"  #wnba \.bars\.open \{\{[^}]*\}\}\n", "", s)
after = len(re.findall(r"#wnba \.bars\.open \{\{[^}]*\}\}", s))
print(f"  removed {before - after} competing .bars.open rules")

CSS = r"""
  /* ══════════════════ CUPERTINO-SPACE4 ══════════════════
     One 4pt scale for the WNBA card and drawer. Every value below is 4/8/12/16/20 — no exceptions,
     because the consistency is the design. Previous values were 13/14/9/7/8/11/12, which is a
     sequence of guesses rather than a system, and that is what made it not read as Apple.

     Also consolidates the .bars.open padding, which had accumulated into three separate rules
     across earlier passes, so the card-to-drawer gap depended on which one happened to win. */

  /* section header -> group */
  #wnba .cu-sh {{ padding:8px 4px; gap:8px; }}
  #wnba .cu-out {{ padding:0 4px 8px; gap:8px; }}
  #wnba .game {{ margin-bottom:20px; }}          /* card -> card */
  #wnba .cu-grp {{ margin-bottom:0; }}

  /* inside the card */
  #wnba .cu-sum {{ padding:16px; }}
  #wnba .cu-hd {{ margin-bottom:12px; gap:8px; }}
  #wnba .cu-ttl {{ margin-bottom:2px; gap:8px; }}   /* title+sub are one pair, deliberately tight */
  #wnba .cu-sub {{ margin-bottom:16px; }}
  #wnba .cu-bet {{ margin-bottom:16px; gap:8px; }}
  #wnba .cu-cf {{ gap:12px; }}

  /* card -> drawer: 16 from the summary plus 4 here = 20, one step ABOVE the 16 used inside the
     panel, so the drawer reads as nested rather than welded to the card */
  #wnba .bars {{ padding:0; }}
  #wnba .bars.open {{ padding:4px 12px 12px; }}
  #wnba .bars.open .dw {{ padding:16px; }}

  /* inside the drawer */
  #wnba .dw-s + .dw-s {{ margin-top:16px; padding-top:16px; }}
  #wnba .dw-l {{ margin-bottom:8px; }}
  #wnba .dw .meter {{ margin-bottom:12px; gap:12px; }}
  #wnba .dw .meter:last-child {{ margin-bottom:0; }}
  #wnba .dw .rgsub {{ margin-top:8px; }}
  #wnba .dw .cmps {{ margin-top:12px; gap:8px; }}
  #wnba .dw-opps {{ margin-top:8px; }}
  #wnba .dw-note {{ margin-top:12px; }}

  @media (max-width:520px) {{
    #wnba .cu-sum {{ padding:16px; }}
  }}
"""
a = "</style></head><body>"
assert a in s, "style anchor"
s = s.replace(a, CSS + a, 1)

ast.parse(s)
shutil.copyfile(P, "/tmp/dashboard.prespace4.py")
io.open(P, "w", encoding="utf-8").write(s)
print("  + 4pt scale applied to card + drawer")
