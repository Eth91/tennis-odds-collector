"""One design system across all four tabs — WNBA, TT, PGA, Tracker.

Everything so far was #wnba-scoped, which was right while only that board was being redesigned.
The Simulator showed four different visual languages side by side, plus a layout bug on three of
them: each panel's <h2> subtitle scrolls under the sticky tab bar.

WHAT UNIFIES: surfaces (#1C1C1E group, #2C2C2E elevated), 12px radius, .5px separators, the type
scale, tabular numerals, 20pt margins, section eyebrows at 13px uppercase lbl2.

WHAT DOES NOT: colour that carries meaning stays, only its intensity is normalised to the iOS dark
palette. TT/MLB unders stay red because red = the under side there. BetMGM stays gold because that
is its brand identity in the line-shop. Wins/units stay green. What goes is DECORATIVE colour —
the glowing blue hit-rate pill, the blue odds on PGA — because those encode nothing.
"""
import ast, io, shutil
P="dashboard.py"; s=io.open(P,encoding="utf-8").read()
if "CUPERTINO-GLOBAL" in s:
    print("  = already applied"); raise SystemExit(0)

CSS = r"""
  /* ══════════════════ CUPERTINO-GLOBAL ══════════════════
     One system for all four tabs. Semantic colour is preserved and renormalised; decorative
     colour is removed. Scoped rules above (#wnba) still win where they are more specific. */

  /* panel subtitle — was scrolling UNDER the sticky tab bar on #tt/#pga/#tracker */
  .panel > h2 {{ font-size:13px; font-weight:600; letter-spacing:.02em; text-transform:uppercase;
                 color:var(--cu-lbl2); margin:18px 4px 10px; }}

  /* every card surface */
  .card, .tcard, .pgatop, .starwatch, .watchlist, .tierleg, .xtras {{
      background:var(--cu-grp); border:0 !important; border-radius:12px; padding:14px 16px;
      margin:0 0 20px; box-shadow:none !important; }}
  .thead, .pgahead, .ttlg, .wl-title, .sw-title {{ font-size:13px; font-weight:600;
      letter-spacing:.02em; text-transform:uppercase; color:var(--cu-lbl2); margin:0 0 12px;
      display:flex; align-items:center; gap:8px; }}
  .tsub, .pgasub, .ttfoot, .bnote {{ font-size:13px; color:var(--cu-lbl2); line-height:1.45; }}

  /* ---- TRACKER stat tiles ---- */
  .trow {{ display:flex; gap:8px; margin:0 0 12px; }}
  .tbox {{ flex:1; background:var(--cu-grp2); border:0 !important; border-radius:10px;
           padding:10px 12px; text-align:center; }}
  .tk {{ font-size:12px; font-weight:600; letter-spacing:.02em; text-transform:uppercase;
         color:var(--cu-lbl2); display:block; margin-bottom:4px; }}
  .tv {{ font-size:26px; font-weight:680; letter-spacing:-.035em; color:var(--cu-lbl);
         font-variant-numeric:tabular-nums; display:block; }}
  .tv.up, .tbox .up {{ color:var(--cu-grn); }}     /* units stay green — that is meaning */
  .ddbet {{ display:flex; align-items:center; gap:8px; padding:9px 0;
            border-bottom:.5px solid var(--cu-sep); font-size:15px; }}
  .ddbet:last-child {{ border-bottom:0; }}
  .ddnm {{ color:var(--cu-lbl); flex:1; min-width:0; }}
  .ddday {{ font-size:13px; color:var(--cu-lbl3); }}
  .ddwl {{ font-size:12px; font-weight:600; padding:2px 8px; border-radius:11px;
           background:var(--cu-fill); color:var(--cu-lbl2); }}
  .ddwl.w {{ color:var(--cu-grn); background:rgba(48,209,88,.18); }}
  .ddu {{ font-variant-numeric:tabular-nums; color:var(--cu-lbl2); }}
  .ddu.up {{ color:var(--cu-grn); }}

  /* ---- PGA rows ---- */
  .pgatitle {{ font-size:19px; font-weight:640; letter-spacing:-.022em; color:var(--cu-lbl);
               text-transform:none; }}
  .pgapaper {{ font-size:12px; font-weight:600; padding:2px 8px; border-radius:11px;
               color:var(--cu-org); background:rgba(255,159,10,.18); border:0; }}
  .pgarec {{ margin-left:auto; font-size:14px; color:var(--cu-lbl2);
             font-variant-numeric:tabular-nums; }}
  .pgamkt {{ font-size:13px; font-weight:600; letter-spacing:.02em; text-transform:uppercase;
             color:var(--cu-lbl2); margin:16px 0 2px; border:0; padding:0; }}
  .pgabet {{ display:flex; align-items:center; gap:10px; padding:11px 0;
             border-bottom:.5px solid var(--cu-sep); }}
  .pgabet:last-child {{ border-bottom:0; }}
  .pgasel {{ font-size:16px; font-weight:600; color:var(--cu-lbl); letter-spacing:-.015em; }}
  .pgasp {{ flex:1; }}
  /* PGA odds were blue for decoration only — no book or side meaning. Neutral. */
  #pga .podds, #pga .podds.fd {{ color:var(--cu-lbl) !important; font-size:17px; font-weight:640;
                                 letter-spacing:-.02em; }}
  #pga .bklogo, #tracker .bklogo {{ width:24px; height:24px; border-radius:6px;
                                    background:var(--cu-fill); padding:3px; vertical-align:-6px;
                                    margin-left:7px; }}

  /* ---- TT rows: keep the side semantics, drop the glow ---- */
  #tt .ttbet {{ display:flex; align-items:center; gap:11px; padding:12px 0;
                border-bottom:.5px solid var(--cu-sep); }}
  #tt .ttbet:last-of-type {{ border-bottom:0; }}
  #tt .pind {{ width:30px; height:30px; border-radius:8px; font-size:13px; font-weight:700;
               display:grid; place-items:center; }}
  #tt .pind.o {{ color:var(--cu-grn); background:rgba(48,209,88,.18); }}
  #tt .pind.u {{ color:var(--cu-red); background:rgba(255,69,58,.18); }}   /* under = red, kept */
  #tt .ttbln {{ font-size:22px; font-weight:680; letter-spacing:-.035em; color:var(--cu-lbl);
                font-variant-numeric:tabular-nums; }}
  #tt .ttbnm {{ font-size:15px; font-weight:600; color:var(--cu-lbl); }}
  #tt .ttbsb {{ font-size:13px; color:var(--cu-lbl2); margin-top:2px; }}
  #tt .podds {{ font-size:15px; font-weight:640; color:var(--cu-lbl) !important; }}
  #tt .podds.bmgm {{ color:#d4af37 !important; }}      /* BetMGM identity — kept */
  #tt .bklogo {{ width:24px; height:24px; border-radius:6px; background:var(--cu-fill);
                 padding:3px; vertical-align:-6px; margin-left:6px; }}
"""
a="</style></head><body>"; assert a in s; s=s.replace(a, CSS+a, 1)
ast.parse(s); shutil.copyfile(P,"/tmp/dashboard.preglobal.py"); io.open(P,"w",encoding="utf-8").write(s)
print("  + one system across WNBA / TT / PGA / Tracker")
print("  + h2 subtitle no longer collides with the sticky tab bar")
