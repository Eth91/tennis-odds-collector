"""Replace the reskin layer with the real Cupertino stylesheet for the new card markup.

The v2 layer restyled the OLD classes. The markup is now the render's own anatomy (.cu-sh, .cu-grp,
.cu-c, .cu-hd, .cu-ttl, .cu-sub, .cu-bet, .cu-cf), so the stylesheet is replaced wholesale with the
one from the render — same tokens, same metrics, same iOS text styles.

Still scoped to #wnba: #tt, #pga and #mlb keep their own boards untouched, including the functional
colour there (TT/MLB unders red, FanDuel blue, DraftKings green, BetMGM gold).
"""
import ast
import io
import shutil

P = "dashboard.py"
s = io.open(P, encoding="utf-8").read()

if "CUPERTINO-CSS2" in s:
    print("  = already applied")
    raise SystemExit(0)

start = s.index("  /* ══════════════════ CUPERTINO-DARK v2")
end = s.index("</style></head><body>")

NEW = r"""  /* ══════════════════ CUPERTINO-CSS2 ══════════════════
     Apple dark, matching the approved render 1:1. Scoped to #wnba; #tt/#pga/#mlb are untouched.
     Dark mode is not an inversion — elevation REVERSES (the drawer rises to #2C2C2E inside a
     #1C1C1E group), semantics use Apple's brighter dark variants, and the hover wash is white. */
  :root {{
    --cu-bg:#000; --cu-grp:#1c1c1e; --cu-grp2:#2c2c2e;
    --cu-lbl:#fff; --cu-lbl2:rgba(235,235,245,.6); --cu-lbl3:rgba(235,235,245,.3);
    --cu-fill:rgba(120,120,128,.24); --cu-sep:rgba(84,84,88,.65);
    --cu-blue:#0a84ff; --cu-grn:#30d158; --cu-org:#ff9f0a; --cu-red:#ff453a;
  }}
  body {{ background:var(--cu-bg); color:var(--cu-lbl);
          font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text",system-ui,sans-serif; }}

  /* ---- grouped-list section header ---- */
  #wnba .cu-sh {{ display:flex; align-items:center; gap:8px; padding:8px 4px 7px;
                  font-size:13px; letter-spacing:.02em; text-transform:uppercase;
                  color:var(--cu-lbl2); }}
  #wnba .cu-sh b {{ font-weight:600; letter-spacing:0; text-transform:none; font-size:13px; }}
  #wnba .cu-shm {{ display:inline-flex; align-items:center; gap:5px; text-transform:none;
                   letter-spacing:0; font-size:13px; }}
  #wnba .cu-shr {{ margin-left:auto; text-transform:none; letter-spacing:0; font-size:13px;
                   font-variant-numeric:tabular-nums; }}
  #wnba .cu-gl {{ width:20px; height:20px; object-fit:contain; border-radius:5px;
                  background:var(--cu-fill); padding:2px; }}
  #wnba .llogo {{ width:24px; height:24px; border-radius:6px; flex:none; display:inline-flex;
                  align-items:center; justify-content:center; overflow:hidden;
                  background:var(--cu-fill); }}
  #wnba .llogo img {{ width:100%; height:100%; object-fit:contain; padding:3px; }}
  #wnba .llogo.mono {{ font-size:8px; font-weight:700; color:var(--cu-lbl2); }}
  #wnba .cu-out {{ display:flex; align-items:center; gap:7px; padding:0 4px 8px;
                   font-size:13px; color:var(--cu-lbl2); }}

  /* ---- the rounded group + card ---- */
  #wnba .cu-grp {{ background:var(--cu-grp); border-radius:12px; overflow:hidden;
                   margin-bottom:20px; }}
  #wnba .cu-c {{ border-bottom:.5px solid var(--cu-sep); }}
  #wnba .cu-c:last-child {{ border-bottom:0; }}
  #wnba .cu-sum {{ padding:13px 16px 14px; cursor:pointer; transition:background .13s; }}
  #wnba .cu-sum:hover {{ background:rgba(255,255,255,.04); }}
  #wnba .cu-sum:active {{ background:rgba(255,255,255,.07); }}

  /* header row: status pill, book mark, lock time */
  #wnba .cu-hd {{ display:flex; align-items:center; gap:8px; margin-bottom:9px; }}
  #wnba .cu-st {{ font-size:12px; font-weight:600; padding:2px 8px; border-radius:11px; }}
  #wnba .cu-st.ok {{ color:var(--cu-grn); background:rgba(48,209,88,.18); }}
  #wnba .cu-st.mid {{ color:var(--cu-blue); background:rgba(10,132,255,.18); }}
  #wnba .cu-st.pp {{ color:var(--cu-org); background:rgba(255,159,10,.18); }}
  #wnba .cu-st.no {{ color:var(--cu-lbl2); background:var(--cu-fill); }}
  #wnba .cu-hd .bklogo {{ width:24px; height:24px; border-radius:6px; background:var(--cu-fill);
                          padding:3px; margin:0; vertical-align:0; }}
  #wnba .cu-time {{ margin-left:auto; font-size:14px; color:var(--cu-lbl2);
                    font-variant-numeric:tabular-nums; }}

  /* title + team marks */
  #wnba .cu-ttl {{ font-size:19px; font-weight:640; letter-spacing:-.022em; color:var(--cu-lbl);
                   display:flex; align-items:center; gap:8px; margin-bottom:2px; }}
  #wnba .cu-tms {{ display:inline-flex; align-items:center; gap:4px; }}
  #wnba .cu-tms i {{ font-style:normal; font-size:13px; color:var(--cu-lbl3); font-weight:400; }}
  #wnba .cu-tm {{ width:22px; height:22px; object-fit:contain; border-radius:50%;
                  background:var(--cu-fill); padding:2px; }}
  #wnba .cu-sub {{ font-size:15px; color:var(--cu-lbl2); margin-bottom:14px; }}

  /* THE BET — 36px number, direction subordinate, price right-aligned */
  #wnba .cu-bet {{ display:flex; align-items:baseline; gap:8px; margin-bottom:14px; }}
  #wnba .cu-dir {{ font-size:13px; font-weight:700; letter-spacing:.06em; color:var(--cu-lbl2); }}
  #wnba .cu-line {{ font-size:36px; font-weight:680; letter-spacing:-.04em; line-height:1;
                    font-variant-numeric:tabular-nums; }}
  #wnba .cu-line.rng {{ font-size:26px; }}
  #wnba .cu-unit {{ font-size:14px; font-weight:600; color:var(--cu-lbl2); }}
  #wnba .cu-price {{ margin-left:auto; display:flex; align-items:center; gap:9px; }}
  #wnba .cu-od {{ font-size:20px; font-weight:640; letter-spacing:-.02em;
                  font-variant-numeric:tabular-nums; }}
  #wnba .cu-chev {{ color:var(--cu-lbl3); font-size:15px; transition:transform .18s; }}
  #wnba .cu-c:has(.bars.open) .cu-chev {{ transform:rotate(90deg); }}
  #wnba .cu-warn {{ color:var(--cu-org); font-size:14px; }}

  /* confidence on the FACE */
  #wnba .cu-cf {{ display:flex; align-items:center; gap:11px; }}
  #wnba .cu-bar {{ flex:1; height:7px; background:var(--cu-fill); border-radius:4px;
                   overflow:hidden; }}
  #wnba .cu-bar i {{ display:block; height:100%; background:var(--cu-blue); border-radius:4px; }}
  #wnba .cu-bar i.g {{ background:var(--cu-grn); }}
  #wnba .cu-pc {{ font-size:16px; font-weight:640; letter-spacing:-.02em;
                  font-variant-numeric:tabular-nums; }}
  #wnba .cu-pc.na {{ color:var(--cu-lbl3); }}
  #wnba .cu-n {{ font-size:14px; color:var(--cu-lbl2); font-variant-numeric:tabular-nums; }}
  #wnba .cu-n.na {{ color:var(--cu-lbl3); }}
  #wnba .cu-rungs {{ display:flex; gap:6px; flex-wrap:wrap; margin-top:11px; }}
  #wnba .cu-rungs .rung {{ font-size:12px; color:var(--cu-lbl2); background:var(--cu-fill);
                           border-radius:7px; padding:3px 8px; font-variant-numeric:tabular-nums; }}
  #wnba .cu-rungs .rung b {{ color:var(--cu-lbl); font-weight:600; }}

  /* ---- the drawer ELEVATES (tertiary above secondary) ---- */
  #wnba .bars {{ padding:0 12px 12px; }}
  #wnba .bars.open {{ background:transparent; }}
  #wnba .bwrap {{ background:var(--cu-grp2); border-radius:10px; padding:12px 14px; }}
  #wnba .bwrap .meters {{ margin:0 0 12px; padding-bottom:12px;
                          border-bottom:.5px solid var(--cu-sep); }}
  #wnba .meter {{ display:flex; align-items:center; gap:10px; margin-bottom:8px; }}
  #wnba .meter .mlab {{ font-size:13px; color:var(--cu-lbl2); }}
  #wnba .meter .mbar {{ flex:1; height:7px; background:var(--cu-fill); border-radius:4px;
                        overflow:hidden; }}
  #wnba .meter .mbar i {{ display:block; height:100%; background:var(--cu-blue); border-radius:4px; }}
  #wnba .meter.good .mbar i {{ background:var(--cu-grn); }}
  #wnba .meter.bad .mbar i {{ background:var(--cu-red); }}
  #wnba .meter .mval {{ font-size:13px; color:var(--cu-lbl);
                        font-variant-numeric:tabular-nums; }}
  #wnba .why, #wnba .regime {{ font-size:14px; line-height:1.42; color:var(--cu-lbl2); }}
  #wnba .why b, #wnba .regime b {{ color:var(--cu-lbl); font-weight:600; }}

  @media (max-width:520px) {{
    #wnba .cu-line {{ font-size:34px; }}
    #wnba .cu-ttl {{ font-size:18px; }}
    #wnba .cu-sub {{ font-size:14px; }}
  }}
"""

s = s[:start] + NEW + s[end:]
ast.parse(s)
shutil.copyfile(P, "/tmp/dashboard.precss2.py")
io.open(P, "w", encoding="utf-8").write(s)
print("  + Cupertino stylesheet replaced to match the render 1:1 (still #wnba-scoped)")
