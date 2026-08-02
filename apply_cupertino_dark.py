"""Wire the Cupertino-dark card design into the dashboard, with league/team/book logos.

WHY A CSS LAYER RATHER THAN A REWRITE. The board's 544-line stylesheet and the `_prop_row` /
`_player_block` / `_game_group` trio already carry a lot of hard-won behaviour — the drawer, the
rung ladders, the contra flag, the tier chips, the in-progress price freeze. Rewriting the card
would put all of that at risk to change how it LOOKS. So the structure is left alone and the
Cupertino palette is applied as an override layer appended at the end of the stylesheet, where it
wins the cascade without touching a single existing rule.

The existing DOM already maps onto Apple's grouped list almost exactly:

    .game  -> the section          (header with league + team logos)
    .pblk  -> the rounded group    (secondarySystemGroupedBackground)
    .prop  -> a row in the group   (hairline inset separators)
    .bars  -> the expanded detail  (tertiary — ELEVATED, see below)

DARK MODE IS NOT AN INVERSION. Three things flip rather than swap, and getting them backwards is
what makes a dark theme look like a recolour:

  1. ELEVATION REVERSES. In light mode the drawer recedes to #F2F2F7 inside a white card. In dark
     it RISES to #2C2C2E inside a #1C1C1E group. Same hierarchy, opposite direction — that is how
     iOS signals depth without shadows.
  2. SEMANTIC COLOURS GET BRIGHTER. Light mode darkens them for AA on white (#248A3D); dark mode
     uses Apple's own dark variants (#30D158), which are lighter, not darker.
  3. THE HOVER WASH INVERTS. Black at 3% becomes white at 4%.

LOGOS. Nothing is fabricated. docs/logos/ already ships all 14 WNBA team marks, plus wnba.png,
mlb.png and pga.png; docs/ ships book-fd.png and book-dk.png, and BetMGM is already an inline SVG
data URI. This patch adds the LEAGUE mark to the game header (it was only on the tracker cards) and
gives every mark a real containing box so a 404 degrades to a monogram instead of a gap. TT Elite
has no licensed mark and therefore renders as a monogram — that is a real coverage gap, not a
placeholder to be filled with something invented.
"""
import ast
import io
import shutil

P = "dashboard.py"
s = io.open(P, encoding="utf-8").read()

if "CUPERTINO-DARK" in s:
    print("  = already applied")
    raise SystemExit(0)

# ── 1. league mark helper ───────────────────────────────────────────────────────────────────────
old_mlogo = 'def _mlogo(ab, cls="glogo"):'
new_mlogo = '''LEAGUE_LOGO = {"wnba": "logos/wnba.png", "mlb": "logos/mlb.png", "pga": "logos/pga.png"}


def _llogo(league, cls="llogo"):
    """League mark for a section header. Falls back to a monogram box when no licensed asset
    exists (TT Elite), so the slot geometry is identical either way and a 404 never leaves a gap."""
    src = LEAGUE_LOGO.get((league or "").lower())
    ab = (league or "").upper()[:3]
    if not src:
        return f'<span class="{cls} mono">{ab}</span>'
    return (f'<span class="{cls}"><img src="{src}" alt="{ab}" loading="lazy" '
            f'onerror="this.parentNode.className=\\'{cls} mono\\';this.parentNode.textContent=\\'{ab}\\'">'
            f'</span>')


def _mlogo(ab, cls="glogo"):'''
assert old_mlogo in s, "mlogo anchor missing"
s = s.replace(old_mlogo, new_mlogo, 1)

# ── 2. the bet reads as a WORD, not a letter ────────────────────────────────────────────────────
# Cupertino puts "UNDER 74.5" on one baseline with the direction subordinate to the number. The
# existing markup emits a single letter in a 26px box. TT and MLB render .pind from other code
# paths, so the new CSS sizes the slot to its content and both forms keep working.
old_ind = '''    side = (r.get("side") if hasattr(r, "get") else r["side"]) or "over"
    o = "O" if side == "over" else "U"'''
new_ind = '''    side = (r.get("side") if hasattr(r, "get") else r["side"]) or "over"
    o = "O" if side == "over" else "U"
    oword = "OVER" if side == "over" else "UNDER"'''
assert old_ind in s, "side anchor missing"
s = s.replace(old_ind, new_ind, 1)

old_pind = '<span class="pind {o.lower()}">{o}</span>'
new_pind = '<span class="pind {o.lower()}">{oword}</span>'
assert old_pind in s, "pind anchor missing"
s = s.replace(old_pind, new_pind, 1)

# ── 3. league mark on the game header ───────────────────────────────────────────────────────────
old_ghd = '''            f'<div class="ghd"><span class="gmatch">{glogo(team)}{team}'
            f'<span class="gvs">vs</span>{glogo(opp)}{opp or "—"}</span>' '''.rstrip() + "\n"
new_ghd = '''            f'<div class="ghd">{_llogo("wnba")}<span class="gmatch">{glogo(team)}{team}'
            f'<span class="gvs">vs</span>{glogo(opp)}{opp or "—"}</span>'
'''
assert old_ghd in s, "ghd anchor missing"
s = s.replace(old_ghd, new_ghd, 1)

# ── 4. the Cupertino dark layer ─────────────────────────────────────────────────────────────────
CSS = r"""
  /* ══════════════════ CUPERTINO-DARK ══════════════════
     Apple's dark system palette applied over the existing structure. Appended last so it wins the
     cascade without editing the rules above. Light mode would be the same sheet with these tokens
     swapped — geometry never changes between themes, only colour. */
  :root {{
    --cu-bg:#000;                      /* systemGroupedBackground (dark) — true black, not grey */
    --cu-grp:#1c1c1e;                  /* secondarySystemGroupedBackground — cards live here */
    --cu-grp2:#2c2c2e;                 /* tertiary — the drawer RISES to this, it does not recede */
    --cu-lbl:#fff;
    --cu-lbl2:rgba(235,235,245,.6);
    --cu-lbl3:rgba(235,235,245,.3);    /* the em-dash colour */
    --cu-fill:rgba(120,120,128,.24);   /* bar tracks — higher alpha than light mode needs */
    --cu-sep:rgba(84,84,88,.65);
    --cu-hover:rgba(255,255,255,.04);  /* inverts from black-3% in light */
    --cu-blue:#0a84ff; --cu-grn:#30d158; --cu-org:#ff9f0a; --cu-red:#ff453a;
  }}
  body {{ background:var(--cu-bg); color:var(--cu-lbl); }}

  /* group = rounded container, hairline inset separators, no border */
  .pblk {{ background:var(--cu-grp); border:0; border-radius:12px; padding:0;
           margin-bottom:16px; overflow:hidden; }}
  .phd {{ padding:12px 16px 10px; gap:10px; }}
  .pname {{ font-size:19px; font-weight:640; letter-spacing:-.022em; color:var(--cu-lbl); }}
  .plogo {{ width:26px; height:26px; background:var(--cu-fill); padding:2px; }}
  .prop {{ padding:12px 16px 14px; border-top:.5px solid var(--cu-sep); margin-top:0;
           transition:background .13s; }}
  .pblk .prop:first-of-type {{ border-top:.5px solid var(--cu-sep); margin-top:0; }}
  .prop:hover {{ background:var(--cu-hover); }}
  .prop:has(+ .bars.open) {{ background:rgba(255,255,255,.025); }}

  /* THE BET — direction is a subordinate word, the number is the object. 36px vs 19px name. */
  .pind {{ width:auto; height:auto; border-radius:0; background:none !important;
           font-size:13px; font-weight:700; letter-spacing:.06em;
           color:var(--cu-lbl2) !important; display:inline; place-items:unset; }}
  .plno {{ font-size:36px; font-weight:680; letter-spacing:-.04em; color:var(--cu-lbl); }}
  .plno.rng {{ font-size:24px; }}
  .pstat {{ font-size:14px; font-weight:600; color:var(--cu-lbl2); letter-spacing:0; }}
  .prow {{ gap:8px; align-items:baseline; }}

  /* price + book. Over/under carries NO colour — direction is a label, not a state; green and red
     stay reserved for outcome and injury. */
  .podds {{ font-size:20px; font-weight:640; letter-spacing:-.02em; color:var(--cu-lbl) !important; }}
  .podds.bmgm {{ color:#d4af37 !important; }}
  .bklogo {{ width:26px; height:26px; border-radius:7px; background:var(--cu-fill);
             padding:3px; vertical-align:-7px; margin-left:7px; }}
  .pedge {{ font-size:15px; font-weight:640; color:var(--cu-lbl2); }}
  .pedge.hi {{ color:var(--cu-grn); }}
  .pedge.mid {{ color:var(--cu-lbl2); }}
  .pedge.lo {{ color:var(--cu-lbl3); }}
  .pchev {{ color:var(--cu-lbl3); font-size:16px; }}
  .pctx {{ color:var(--cu-lbl2); font-size:14px; }}

  /* confidence meters — system fills, semantic only at the ends */
  .meter .mbar {{ background:var(--cu-fill); border-radius:4px; height:7px; }}
  .meter .mbar i {{ background:var(--cu-blue); border-radius:4px; }}
  .meter.good .mbar i {{ background:var(--cu-grn); }}
  .meter.bad .mbar i {{ background:var(--cu-red); }}
  .meter .mlab {{ color:var(--cu-lbl2); }}
  .meter .mval {{ color:var(--cu-lbl); font-variant-numeric:tabular-nums; }}

  /* the drawer ELEVATES — this is the single detail that makes it read as iOS dark */
  .bars.open {{ background:var(--cu-grp2); border-radius:10px;
                margin:0 12px 12px; padding:12px 14px; }}
  .bwrap .meters {{ border-bottom:.5px solid var(--cu-sep); }}

  /* section header: league mark then the two team marks */
  .ghd {{ gap:9px; padding:0 4px 10px; }}
  .llogo {{ width:26px; height:26px; border-radius:7px; flex:none; display:inline-flex;
            align-items:center; justify-content:center; overflow:hidden;
            background:var(--cu-fill); }}
  .llogo img {{ width:100%; height:100%; object-fit:contain; padding:3px; }}
  .llogo.mono {{ font-size:9px; font-weight:700; letter-spacing:-.03em;
                 color:var(--cu-lbl2); }}
  .gmatch {{ font-size:13px; font-weight:600; letter-spacing:0; text-transform:uppercase;
             color:var(--cu-lbl2); }}
  .glogo {{ width:22px; height:22px; background:var(--cu-fill); padding:2px; }}
  .gtime {{ color:var(--cu-lbl2); font-size:14px; font-variant-numeric:tabular-nums; }}
  .gout {{ color:var(--cu-lbl2); font-size:14px; }}

  /* status chips — semantic at 18% alpha; a tint needs more weight on black than on white */
  .pflag {{ color:var(--cu-lbl2); font-size:13px; }}
  .tchip {{ border-radius:11px; font-size:12px; font-weight:600; padding:2px 8px; }}
  .pmin {{ color:var(--cu-lbl2); font-size:14px; font-variant-numeric:tabular-nums; }}

  /* an unavailable value is a designed state, not a gap */
  .na, .pedge:empty::before {{ color:var(--cu-lbl3); }}
  .pedge:empty::before {{ content:"—"; }}

  @media (max-width:520px) {{
    .plno {{ font-size:30px; }}
    .podds {{ font-size:18px; }}
  }}
"""

anchor = "</style></head><body>"
assert anchor in s, "style close anchor missing"
s = s.replace(anchor, CSS + anchor, 1)

ast.parse(s)
shutil.copyfile(P, "/tmp/dashboard.precupertino.py")
io.open(P, "w", encoding="utf-8").write(s)
print("  + Cupertino dark layer applied")
print("  + league mark on game headers (wnba.png); TT falls back to a monogram")
print("  + bet reads OVER/UNDER at 36px, direction subordinate")
print("  backup: /tmp/dashboard.precupertino.py")
