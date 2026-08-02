"""Star Watch, Parlays and the empty state onto the Cupertino system. Idempotent, ast-checked.

THREE SECTIONS WERE NEVER CONVERTED, and one of them is visibly broken on device.

1. STAR WATCH IS LAID OUT WRONG, not merely unstyled. `#wnba .swrow` was set to `display:flex` when
   the injury report was converted — correct there, because an injury row is a single `.swhd` child
   and `.swhd` is already flex globally, so the logo/name/badge lay out inside it. But a STAR WATCH
   row is TWO children, `.swhd` + `.swo`, so flex puts the "likely to inherit the role" line
   BESIDE the header instead of under it. On the phone that renders as a ~60px column pinned to the
   right edge with the inheritor names wrapping one word per line and clipping off-screen, plus a
   tall band of dead space beside it. Exactly the `.pgabet` bug from 2026-08-01: a vertical wrapper
   made horizontal. `display:block` fixes it and leaves the injury report untouched, because a
   single flex child in a block parent lays out identically.

2. PARLAYS HAD **ZERO** #wnba RULES — still entirely on the pre-Cupertino palette (#0b0e13 card,
   #1b2130 border, #0e131b header bar, #37d67f green, an 11px uppercase "2 LEG PARLAY"). Next to a
   converted play card it reads as a different app. Rebuilt on the same primitives the play cards
   use: --cu-grp surface, 12px radius, no border, .5px hairline separators, sentence case.

3. THE EMPTY STATE is the one screen shown when nothing is flagged — i.e. the most-seen state on a
   quiet slate — and it still had a 1px border and #121620 fill.

SPACING. All three now use the same 4pt rhythm as the cards (4/8/12/16/20) rather than the old
7/9/10/11/26 values, so section-to-section spacing is uniform down the whole tab.

TEXT. The Star Watch subtitle ("· big names out that the model can't project — your call") wrapped
to two lines on a 402pt screen and restated what the section already communicates. Dropped, per the
standing instruction to delete explanatory text. The INJURY REPORT subtitle is deliberately KEPT:
it defines what `n=` means, which is not inferable from the badge.

Everything is #wnba-scoped, so #tt / #pga / #tracker keep their own semantics — the same discipline
that stopped the first Cupertino pass from flattening TT's functional colour.
"""
import ast
import io
import shutil

P = "dashboard.py"
s = io.open(P, encoding="utf-8").read()

if "CUPERTINO-SECTIONS" in s:
    print("  = already applied")
    raise SystemExit(0)

# ── 1. drop the Star Watch subtitle (it wrapped to 2 lines and said nothing) ─────────────────────
OLD_SW = """    return ('<div class="starwatch"><div class="sw-title">Star Watch '
            '<span>· big names out that the model can\\'t project — your call</span></div>'
            + rows + '</div>')"""
NEW_SW = """    # Subtitle dropped: it wrapped to two lines at 402pt and restated the section name. The
    # INJURY REPORT keeps its subtitle because that one defines `n=`, which the badge does not.
    return ('<div class="starwatch"><div class="sw-title">Star Watch</div>'
            + rows + '</div>')"""
assert OLD_SW in s, "star watch return anchor"
s = s.replace(OLD_SW, NEW_SW, 1)

# ── 2. the empty state gets real markup instead of a <br> + span ─────────────────────────────────
# The backslash line-continuation has to go with it: implicit concatenation across several lines
# is only legal inside brackets, so appending lines after a `\` is an IndentationError.
OLD_EMPTY = ('''    cards = "\\n".join(p for p in _parts if p) if order else \\
        \'<div class="empty">No plays flagged yet.<br><span>The watcher checks every ~60s and fills this in the moment a key player is ruled out.</span></div>\'''')
NEW_EMPTY = ('''    cards = "\\n".join(p for p in _parts if p) if order else (
        \'<div class="empty"><div class="empty-t">No plays flagged yet</div>\'
        \'<div class="empty-s">The watcher checks every ~60s and fills this in \'
        \'the moment a key player is ruled out.</div></div>\')''')
assert OLD_EMPTY in s, "empty state anchor"
s = s.replace(OLD_EMPTY, NEW_EMPTY, 1)

CSS = r"""
  /* ══════════════════ CUPERTINO-SECTIONS ══════════════════
     Star Watch, Parlays and the empty state — the three the earlier passes missed. All #wnba-scoped
     so the other panels keep their own semantics. */

  /* ---- STAR WATCH ----
     THE LAYOUT BUG: `#wnba .swrow` is display:flex, set when the INJURY REPORT was converted. An
     injury row has one child (.swhd, itself flex) so flex is harmless there. A star-watch row has
     TWO (.swhd + .swo), so flex put the inheritor line BESIDE the header — a ~60px column jammed
     against the right edge, one word per line, clipping off screen. block fixes it and is
     identical for a single-child row, so the injury report is unaffected. */
  #wnba .swrow {{ display:block; padding:12px 0; border-bottom:.5px solid var(--cu-sep); }}
  #wnba .swrow:first-of-type {{ padding-top:4px; }}
  #wnba .swrow:last-child {{ border-bottom:0; padding-bottom:0; }}
  #wnba .swhd {{ display:flex; align-items:center; gap:8px; flex-wrap:wrap;
                 font-size:16px; font-weight:600; letter-spacing:-.01em; color:var(--cu-lbl); }}
  #wnba .swhd b {{ font-weight:600; }}
  /* usage numbers are a trailing detail, not a competing column — they push right and never wrap */
  #wnba .swusg {{ margin-left:auto; color:var(--cu-lbl2); font-size:14px;
                  font-variant-numeric:tabular-nums; white-space:nowrap; }}
  #wnba .swvs {{ color:var(--cu-lbl2); font-size:14px; }}
  #wnba .swday {{ color:var(--cu-lbl3); font-size:13px; }}
  #wnba .swo {{ margin-top:6px; color:var(--cu-lbl2); font-size:14px; line-height:1.4; }}
  #wnba .swo b {{ color:var(--cu-lbl); font-weight:600; }}
  #wnba .sw-title {{ margin-bottom:2px; }}

  /* ---- PARLAYS ---- built on the play card's primitives so the two read as one system */
  #wnba .slips {{ display:flex; flex-direction:column; gap:12px; }}
  #wnba .slip {{ background:var(--cu-grp); border:0; border-radius:12px; overflow:hidden; }}
  #wnba .slip.splayed {{ box-shadow:inset 0 0 0 1.5px rgba(48,209,88,.45); }}
  #wnba .shd {{ display:flex; align-items:center; gap:8px; padding:12px 16px 10px;
                background:none; border-bottom:.5px solid var(--cu-sep); }}
  /* sentence case: only the tiny section eyebrows shout on this board */
  #wnba .sn {{ color:var(--cu-lbl); font-weight:600; font-size:15px;
               text-transform:none; letter-spacing:-.01em; }}
  #wnba .sodds {{ color:var(--cu-grn); font-weight:640; font-size:19px; letter-spacing:-.02em;
                  font-variant-numeric:tabular-nums; }}
  #wnba .slegs {{ padding:4px 16px; }}
  #wnba .sleg {{ padding:11px 0 11px 26px; gap:10px; }}
  #wnba .sleg + .sleg {{ border-top:.5px solid var(--cu-sep); }}
  #wnba .slp {{ color:var(--cu-lbl); font-weight:600; font-size:16px; letter-spacing:-.01em; }}
  #wnba .slm {{ color:var(--cu-lbl2); font-size:14px; margin-top:2px; }}
  #wnba .slo {{ color:var(--cu-lbl); font-weight:600; font-size:16px;
                font-variant-numeric:tabular-nums; }}
  #wnba .sleg .glogo, #wnba .sleg img {{ width:28px; height:28px; border-radius:50%;
                                          background:var(--cu-fill); }}
  #wnba .sfoot {{ padding:12px 16px; border-top:.5px solid var(--cu-sep);
                  color:var(--cu-lbl2); font-size:14px; }}
  #wnba .sfoot b {{ color:var(--cu-lbl); font-weight:600; }}
  #wnba .stag {{ font-size:12px; font-weight:600; padding:2px 8px; border-radius:11px;
                 background:var(--cu-fill); color:var(--cu-lbl2); letter-spacing:0; }}
  #wnba .sv {{ color:var(--cu-grn); font-size:13px; font-weight:600; }}
  #wnba .pmark {{ color:var(--cu-lbl3); font-size:19px; padding:0 2px; }}
  #wnba .pmark.on {{ color:var(--cu-grn); }}
  #wnba .sid {{ color:var(--cu-lbl3); font-size:12px; }}

  /* ---- EMPTY STATE ---- the most-seen screen on a quiet slate */
  #wnba .empty {{ background:var(--cu-grp); border:0; border-radius:12px;
                  padding:32px 20px; text-align:center; margin:4px 0 20px; }}
  #wnba .empty-t {{ color:var(--cu-lbl); font-size:17px; font-weight:600;
                    letter-spacing:-.02em; }}
  #wnba .empty-s {{ color:var(--cu-lbl2); font-size:14px; line-height:1.45;
                    margin:6px auto 0; max-width:30ch; }}
"""
a = "</style></head><body>"
assert a in s, "style anchor"
s = s.replace(a, CSS + a, 1)

ast.parse(s)
shutil.copyfile(P, "/tmp/dashboard.presections.py")
io.open(P, "w", encoding="utf-8").write(s)
print("  + star watch row is a COLUMN again (was flex -> inheritors clipped off-screen)")
print("  + parlays converted (they had zero #wnba rules)")
print("  + empty state on --cu-grp, 4pt rhythm throughout")
