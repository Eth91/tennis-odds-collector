"""Scope the Cupertino layer to #wnba so the other panels keep their existing semantics.

THE BUG. The first pass styled `.pind` and `.podds` globally with !important. Those classes are not
WNBA-only — TT and MLB both render them inside `.ttbet` rows, and the page carries FUNCTIONAL colour
there that the override silently destroyed:

    .ttbet .pind.u   TT: unders RED (overs stay green)
    #mlb   .pind.u   MLB: unders RED
    .podds.fd/.dk    FanDuel blue / DraftKings green
    .podds.bmgm      BetMGM gold

Those are not decoration — the red under and the book colour are how the TT and MLB boards are read
at a glance. Flattening them to white is a regression, and the brief was to redesign ONLY the
Today's Plays (WNBA) experience.

THE FIX. Every structural and colour rule is scoped under `#wnba`. That also lets the !important
flags go: `#wnba .pind` scores (1,1,0) against `.pind.o` at (0,2,0), so the id alone wins the
cascade inside the panel and loses everywhere else — which is exactly the desired behaviour.

Only two rules stay global: the :root token block (inert until referenced) and the body ground,
which is a page-level surface all four panels already share.
"""
import ast
import io
import re
import shutil

P = "dashboard.py"
s = io.open(P, encoding="utf-8").read()

if "CUPERTINO-DARK" not in s:
    raise SystemExit("cupertino layer not present — run apply_cupertino_dark.py first")
if "CUPERTINO-DARK v2" in s:
    print("  = already scoped")
    raise SystemExit(0)

start = s.index("  /* ══════════════════ CUPERTINO-DARK")
end = s.index("</style></head><body>")
old_block = s[start:end]

NEW = r"""  /* ══════════════════ CUPERTINO-DARK v2 ══════════════════
     Apple's dark system palette, SCOPED TO #wnba. The other panels (#tt, #pga, #mlb) keep their
     own semantics untouched — TT/MLB unders stay red, FanDuel stays blue, DraftKings green,
     BetMGM gold. Those colours are functional on those boards and are not ours to flatten.
     The #wnba prefix scores (1,1,0), which beats the existing (0,2,0) class rules inside the
     panel and loses everywhere else, so no !important is needed anywhere below. */
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
  #wnba .pblk {{ background:var(--cu-grp); border:0; border-radius:12px; padding:0;
                 margin-bottom:16px; overflow:hidden; }}
  #wnba .phd {{ padding:12px 16px 10px; gap:10px; }}
  #wnba .pname {{ font-size:19px; font-weight:640; letter-spacing:-.022em; color:var(--cu-lbl); }}
  #wnba .plogo {{ width:26px; height:26px; background:var(--cu-fill); padding:2px; }}
  #wnba .prop {{ padding:12px 16px 14px; border-top:.5px solid var(--cu-sep); margin-top:0;
                 transition:background .13s; }}
  #wnba .pblk .prop:first-of-type {{ border-top:.5px solid var(--cu-sep); margin-top:0; }}
  #wnba .prop:hover {{ background:var(--cu-hover); }}
  #wnba .prop:has(+ .bars.open) {{ background:rgba(255,255,255,.025); }}

  /* THE BET — direction is a subordinate word, the number is the object. 36px vs 19px name. */
  /* .prop-scoped ONLY. The "Also considered · NOT BET" panel also lives in #wnba but renders
     compact .ttbet rows whose .pind is a chip, not a card label — restyling it there stripped the
     chip and left a floating "O". Cupertino applies to the CARDS; that list keeps its own idiom. */
  #wnba .prop .pind {{ width:auto; height:auto; border-radius:0; background:none;
                       font-size:13px; font-weight:700; letter-spacing:.06em;
                       color:var(--cu-lbl2); display:inline; place-items:unset; }}
  #wnba .plno {{ font-size:36px; font-weight:680; letter-spacing:-.04em; color:var(--cu-lbl); }}
  #wnba .plno.rng {{ font-size:24px; }}
  #wnba .pstat {{ font-size:14px; font-weight:600; color:var(--cu-lbl2); letter-spacing:0; }}
  #wnba .prow {{ gap:8px; align-items:baseline; }}

  /* price + book. Over/under carries NO colour HERE — direction is a label, not a state; green and
     red stay reserved for outcome and injury on this board. TT/MLB keep their own scheme. */
  #wnba .podds {{ font-size:20px; font-weight:640; letter-spacing:-.02em; color:var(--cu-lbl); }}
  #wnba .bklogo {{ width:26px; height:26px; border-radius:7px; background:var(--cu-fill);
                   padding:3px; vertical-align:-7px; margin-left:7px; }}
  #wnba .pedge {{ font-size:15px; font-weight:640; color:var(--cu-lbl2); }}
  #wnba .pedge.hi {{ color:var(--cu-grn); }}
  #wnba .pedge.mid {{ color:var(--cu-lbl2); }}
  #wnba .pedge.lo {{ color:var(--cu-lbl3); }}
  #wnba .pchev {{ color:var(--cu-lbl3); font-size:16px; }}
  #wnba .pctx {{ color:var(--cu-lbl2); font-size:14px; }}

  /* confidence meters — system fills, semantic only at the ends */
  #wnba .meter .mbar {{ background:var(--cu-fill); border-radius:4px; height:7px; }}
  #wnba .meter .mbar i {{ background:var(--cu-blue); border-radius:4px; }}
  #wnba .meter.good .mbar i {{ background:var(--cu-grn); }}
  #wnba .meter.bad .mbar i {{ background:var(--cu-red); }}
  #wnba .meter .mlab {{ color:var(--cu-lbl2); }}
  #wnba .meter .mval {{ color:var(--cu-lbl); font-variant-numeric:tabular-nums; }}

  /* the drawer ELEVATES — the single detail that makes it read as iOS dark rather than a recolour */
  #wnba .bars.open {{ background:var(--cu-grp2); border-radius:10px;
                      margin:0 12px 12px; padding:12px 14px; }}
  #wnba .bwrap .meters {{ border-bottom:.5px solid var(--cu-sep); }}

  /* section header: league mark then the two team marks */
  #wnba .ghd {{ gap:9px; padding:0 4px 10px; }}
  #wnba .llogo {{ width:26px; height:26px; border-radius:7px; flex:none; display:inline-flex;
                  align-items:center; justify-content:center; overflow:hidden;
                  background:var(--cu-fill); }}
  #wnba .llogo img {{ width:100%; height:100%; object-fit:contain; padding:3px; }}
  #wnba .llogo.mono {{ font-size:9px; font-weight:700; letter-spacing:-.03em; color:var(--cu-lbl2); }}
  #wnba .gmatch {{ font-size:13px; font-weight:600; letter-spacing:0; text-transform:uppercase;
                   color:var(--cu-lbl2); }}
  #wnba .glogo {{ width:22px; height:22px; background:var(--cu-fill); padding:2px; }}
  #wnba .gtime {{ color:var(--cu-lbl2); font-size:14px; font-variant-numeric:tabular-nums; }}
  #wnba .gout {{ color:var(--cu-lbl2); font-size:14px; }}

  /* status chips — semantic at 18% alpha; a tint needs more weight on black than on white */
  #wnba .pflag {{ color:var(--cu-lbl2); font-size:13px; }}
  #wnba .tchip {{ border-radius:11px; font-size:12px; font-weight:600; padding:2px 8px; }}
  #wnba .pmin {{ color:var(--cu-lbl2); font-size:14px; font-variant-numeric:tabular-nums; }}

  /* an unavailable value is a designed state, not a gap */
  #wnba .na {{ color:var(--cu-lbl3); }}
  #wnba .pedge:empty::before {{ content:"—"; color:var(--cu-lbl3); }}

  @media (max-width:520px) {{
    #wnba .plno {{ font-size:30px; }}
    #wnba .podds {{ font-size:18px; }}
  }}
"""

s = s[:start] + NEW + s[end:]
ast.parse(s)
shutil.copyfile(P, "/tmp/dashboard.prescope.py")
io.open(P, "w", encoding="utf-8").write(s)

# prove no bare (unscoped) card rules survived in the layer
leaked = [ln.strip() for ln in NEW.splitlines()
          if re.match(r"\s*\.(pind|podds|plno|prop|pblk|bklogo|meter|bars|pedge)\b", ln)]
print("  + layer scoped to #wnba")
print("  + !important removed (id specificity does the work)")
print("  unscoped card rules remaining:", leaked or "none")
