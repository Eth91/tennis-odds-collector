"""Bring EVERY remaining WNBA-panel component onto the Cupertino tokens.

Styling .card/.ttlg only changed the containers. Their contents — the Also-considered rows, the
confidence-tier legend, Also-flagged, the Watchlist, the Injury report and the drawer internals —
were all still the old design, and that is most of what you see when you scroll. This is the
full pass: one system, every component.

No markup changes. Every rule is #wnba-scoped, so #tt/#pga/#mlb keep their own boards.
"""
import ast, io, shutil
P="dashboard.py"; s=io.open(P,encoding="utf-8").read()
if "CUPERTINO-ALL" in s:
    print("  = already applied"); raise SystemExit(0)

CSS = r"""
  /* ══════════════════ CUPERTINO-ALL ══════════════════
     Every remaining component in #wnba, on the same tokens as the card. */

  /* ---- section titles shared by every panel ---- */
  #wnba .ttlg, #wnba .wl-title, #wnba .sw-title, #wnba .tierleg > b,
  #wnba .xtras > b {{ font-size:13px; font-weight:600; letter-spacing:.02em;
        text-transform:uppercase; color:var(--cu-lbl2); margin:0 0 10px; display:block; }}
  #wnba .ttfoot, #wnba .bnote {{ font-size:13px; color:var(--cu-lbl3); line-height:1.45;
        margin-top:10px; }}

  /* ---- ALSO CONSIDERED · NOT BET ---- */
  #wnba .ttbet {{ display:flex; align-items:baseline; gap:10px; padding:11px 0;
        border-bottom:.5px solid var(--cu-sep); }}
  #wnba .ttbet:last-of-type {{ border-bottom:0; }}
  #wnba .ttbet .pind {{ width:auto; height:auto; border-radius:0; background:none;
        font-size:13px; font-weight:700; letter-spacing:.06em; color:var(--cu-lbl2);
        display:inline; place-items:unset; }}
  #wnba .ttbln {{ font-size:19px; font-weight:680; letter-spacing:-.03em; color:var(--cu-lbl);
        font-variant-numeric:tabular-nums; }}
  #wnba .ttbmid {{ flex:1; min-width:0; }}
  #wnba .ttbnm {{ font-size:15px; font-weight:600; color:var(--cu-lbl); letter-spacing:-.01em; }}
  #wnba .ttbnm b {{ font-weight:600; }}
  #wnba .ttbsb {{ font-size:13px; color:var(--cu-lbl2); margin-top:2px; }}

  /* ---- CONFIDENCE TIERS ---- */
  #wnba .tierleg {{ background:var(--cu-grp); border:0; border-radius:12px; padding:14px 16px;
        margin:0 0 20px; }}
  #wnba .tlrow {{ display:flex; align-items:center; gap:10px; padding:9px 0;
        border-bottom:.5px solid var(--cu-sep); font-size:15px; }}
  #wnba .tlrow:last-child {{ border-bottom:0; }}
  #wnba .tld {{ color:var(--cu-lbl2); flex:1; }}
  #wnba .tlr {{ color:var(--cu-lbl); font-weight:590; font-variant-numeric:tabular-nums;
        text-align:right; white-space:nowrap; }}
  #wnba .tchip {{ width:24px; height:24px; border-radius:12px; flex:none; display:inline-flex;
        align-items:center; justify-content:center; font-size:12px; font-weight:700;
        padding:0; background:var(--cu-fill); color:var(--cu-lbl2); }}
  #wnba .tchip.tA {{ background:rgba(10,132,255,.18); color:var(--cu-blue); }}
  #wnba .tchip.tB {{ background:var(--cu-fill); color:var(--cu-lbl2); }}
  #wnba .tchip.tC {{ background:var(--cu-fill); color:var(--cu-lbl3); }}

  /* ---- ALSO FLAGGED ---- */
  #wnba .xtras {{ background:var(--cu-grp); border:0; border-radius:12px; padding:14px 16px;
        margin:0 0 20px; }}
  #wnba .xchip {{ display:inline-flex; align-items:center; gap:7px; background:var(--cu-grp2);
        border:0; border-radius:15px; padding:7px 12px; margin:0 6px 7px 0; font-size:14px;
        color:var(--cu-lbl); }}
  #wnba .xteam {{ font-size:12px; font-weight:600; color:var(--cu-lbl3); text-transform:uppercase;
        letter-spacing:.04em; }}
  #wnba .xt {{ color:var(--cu-lbl2); font-variant-numeric:tabular-nums; }}

  /* ---- WATCHLIST ---- */
  #wnba .watchlist {{ background:var(--cu-grp); border:0; border-radius:12px; padding:14px 16px;
        margin:0 0 20px; }}
  #wnba .wlg {{ background:var(--cu-grp2); border:0; border-radius:10px; padding:12px 14px;
        margin-bottom:10px; }}
  #wnba .wlg:last-child {{ margin-bottom:0; }}
  #wnba .wlg-hd {{ display:flex; align-items:center; gap:7px; padding:0 0 9px;
        border-bottom:.5px solid var(--cu-sep); margin-bottom:9px; }}
  #wnba .wlg-hd .gmatch {{ font-size:15px; font-weight:600; color:var(--cu-lbl);
        text-transform:none; letter-spacing:-.01em; }}
  #wnba .wlg-hd .gvs {{ color:var(--cu-lbl3); font-weight:400; }}
  #wnba .wlg-hd .gtime {{ margin-left:auto; font-size:13px; color:var(--cu-lbl2);
        font-variant-numeric:tabular-nums; }}
  #wnba .wlcond {{ font-size:13px; color:var(--cu-lbl2); margin-bottom:7px; }}
  #wnba .wlcond .out {{ color:var(--cu-org); font-weight:600; }}
  #wnba .wlin {{ color:var(--cu-lbl3); }}
  #wnba .wlplay {{ display:flex; align-items:center; gap:8px; font-size:15px; color:var(--cu-lbl2); }}
  #wnba .wlplay b {{ color:var(--cu-lbl); font-weight:600; }}
  #wnba .wlright {{ margin-left:auto; display:flex; align-items:center; gap:8px; }}
  #wnba .wlodds {{ font-size:15px; font-weight:590; color:var(--cu-lbl);
        font-variant-numeric:tabular-nums; }}

  /* ---- INJURY REPORT ---- */
  #wnba .starwatch {{ background:var(--cu-grp); border:0; border-radius:12px; padding:14px 16px;
        margin:0 0 20px; }}
  #wnba .swrow {{ display:flex; align-items:center; gap:10px; padding:11px 0;
        border-bottom:.5px solid var(--cu-sep); }}
  #wnba .swrow:last-child {{ border-bottom:0; }}
  #wnba .swhd {{ font-size:15px; font-weight:600; color:var(--cu-lbl); letter-spacing:-.01em; }}
  #wnba .swstat {{ font-size:12px; font-weight:600; padding:2px 8px; border-radius:11px;
        background:var(--cu-fill); color:var(--cu-lbl2); }}
  #wnba .swstat.out {{ color:var(--cu-red); background:rgba(255,69,58,.18); }}
  #wnba .swstat.q {{ color:var(--cu-org); background:rgba(255,159,10,.18); }}
  #wnba .swn {{ margin-left:auto; font-size:12px; font-weight:590; padding:2px 8px;
        border-radius:11px; background:var(--cu-fill); color:var(--cu-lbl2);
        font-variant-numeric:tabular-nums; }}
  #wnba .swrow .glogo {{ width:26px; height:26px; background:var(--cu-fill); padding:2px;
        border-radius:50%; }}

  /* ---- drawer internals ---- */
  #wnba .rgh, #wnba .rgsub {{ font-size:14px; line-height:1.45; color:var(--cu-lbl2); }}
  #wnba .rgh b {{ color:var(--cu-lbl); font-weight:600; }}
  #wnba .sup {{ color:var(--cu-grn); }}
  #wnba .warn {{ color:var(--cu-org); }}
  #wnba .regime {{ margin-top:10px; padding-top:10px; border-top:.5px solid var(--cu-sep); }}
  #wnba .why {{ margin-top:10px; }}
  #wnba .opps, #wnba .pline {{ color:var(--cu-lbl3); font-size:12px; }}
"""
anchor = "</style></head><body>"
assert anchor in s, "anchor"; s = s.replace(anchor, CSS + anchor, 1)
ast.parse(s); shutil.copyfile(P,"/tmp/dashboard.preall.py"); io.open(P,"w",encoding="utf-8").write(s)
print("  + Also considered / Confidence tiers / Also flagged / Watchlist / Injury / drawer -> Cupertino")
