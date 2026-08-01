"""Fix what the phone screenshot exposed, and finish the surfaces I had left alone.

Six things, four of them real bugs:

1. DEAD SPACE. The closed drawer measured 50px tall. `#wnba .bwrap` carried padding:12px 14px, and
   padding is intrinsic — a 0fr grid row with overflow:hidden clips CONTENT but cannot collapse the
   child's own padding, so grid-template-rows computed to 24px instead of 0. Padding and background
   now apply only under .bars.open.
2. "72% 72%". _cu_conf returned the percentage as its own label, so .cu-pc and .cu-n both printed
   72%. Volume rows now label with the projection they actually produced (proj 16.8).
3. BET SIZE. The max-width:520px query stepped 36px down to 34px on phones. Removed — 36px holds.
4. RECORD STRIP, and the in-progress banner (.dayhdr.live) were untouched old chrome sitting between
   the tabs and the first section.
5. .card / .ttlg — Watchlist, Injury report and Also-considered were still the old panel look.
6. The active tab kept a stray border from the old pill bar.
"""
import ast, io, shutil
P="dashboard.py"; s=io.open(P,encoding="utf-8").read()
if "CUPERTINO-POLISH" in s:
    print("  = already applied"); raise SystemExit(0)

# ---- 2. confidence label must not repeat the number -------------------------------------------
old = '''    if r.get("basis") == "volume" and r.get("proj_hit"):
        p = r["proj_hit"] * 100
        return p, f'{p:.0f}%', p >= 60'''
new = '''    if r.get("basis") == "volume" and r.get("proj_hit"):
        p = r["proj_hit"] * 100
        # NOT the percentage again — .cu-pc already prints it. Label with what the model produced.
        ea = r.get("elev_avg")
        return p, (f"proj {ea:g}" if ea is not None else "volume model"), p >= 60'''
assert old in s, "conf anchor"; s = s.replace(old, new, 1)

CSS = r"""
  /* ══════════════════ CUPERTINO-POLISH ══════════════════ */
  /* closed drawer must be ZERO tall: padding is intrinsic and survives a 0fr row, so it only
     exists once open. This was 50px of dead space under every card. */
  #wnba .bars {{ padding:0; }}
  #wnba .bars.open {{ padding:0 12px 12px; background:transparent; }}
  #wnba .bwrap {{ background:none; padding:0; border-radius:0; }}
  #wnba .bars.open .bwrap {{ background:var(--cu-grp2); border-radius:10px; padding:12px 14px; }}

  /* the bet holds 36px on phones — no step-down */
  @media (max-width:520px) {{
    #wnba .cu-line {{ font-size:36px; }}
    #wnba .cu-ttl {{ font-size:19px; }}
    #wnba .cu-sub {{ font-size:15px; }}
  }}

  /* record strip -> an iOS grouped row */
  .recstrip {{ background:var(--cu-grp); border:0; border-radius:12px; padding:12px 16px;
               margin:14px 0 0; gap:8px; font-size:15px; color:var(--cu-lbl2); }}
  .recstrip b {{ color:var(--cu-lbl); font-weight:640; }}
  .recstrip b.up {{ color:var(--cu-grn); }}
  .recstrip b.down {{ color:var(--cu-red); }}
  .recstrip span {{ color:var(--cu-lbl3); font-size:13px; }}

  /* the in-progress banner */
  #wnba .dayhdr {{ font-size:13px; letter-spacing:.02em; text-transform:uppercase;
                   color:var(--cu-lbl2); padding:16px 4px 6px; }}
  #wnba .dayhdr.live {{ color:var(--cu-org); }}

  /* Watchlist / Injury / Also-considered -> grouped cards */
  #wnba .card {{ background:var(--cu-grp); border:0; border-radius:12px; padding:14px 16px;
                 margin:0 0 20px; }}
  #wnba .ttlg {{ font-size:13px; font-weight:600; letter-spacing:.02em; text-transform:uppercase;
                 color:var(--cu-lbl2); margin:0 0 10px; }}

  /* the active tab had a leftover border from the old pill bar */
  .tab {{ border:0 !important; box-shadow:none !important; }}
  .tab.active {{ background:none !important; }}
"""
anchor = "</style></head><body>"
assert anchor in s, "style anchor"; s = s.replace(anchor, CSS + anchor, 1)
ast.parse(s); shutil.copyfile(P,"/tmp/dashboard.prepolish.py"); io.open(P,"w",encoding="utf-8").write(s)
print("  + drawer collapses to 0 (was 50px dead space)")
print("  + confidence label no longer repeats the percentage")
print("  + bet holds 36px on iPhone")
print("  + record strip / banner / watchlist / injury / considered -> Cupertino")
