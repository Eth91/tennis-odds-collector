"""Simplify the WNBA card face: drop the context line, promote the name, own team logo only.

Requested:
  - the "Points · Tier A · S. Diggins, A. Stevens out" line goes — the out-players are already on
    the section header directly above it, and the market is obvious from the bet itself
  - the player's OWN team logo sits beside their name
  - the "TEAM @ TEAM" pair leaves the card; it duplicates the section header
  - the name grows into the space the line vacated

ONE THING KEPT, DELIBERATELY. That line also carried the TIER, which is the model's own confidence
band and not cosmetic — Tier A runs 82.4% against Tier B's 60.7%, and it is the distinction the
selection rules actually trade on. Deleting the line would have silently removed it from the UI
entirely, since nothing else on the card or in the drawer shows it. It moves to a chip beside the
status pill, which costs no vertical space.
"""
import ast
import io
import shutil

P = "dashboard.py"
s = io.open(P, encoding="utf-8").read()

if "CUPERTINO-CARD2" in s:
    print("  = already applied")
    raise SystemExit(0)

# ── 1. own team logo only, in front of the name ─────────────────────────────────────────────────
old_tms = """    tms = (f'<span class="cu-tms">{_tm(team)}<i>@</i>{_tm(opp)}</span>'
           if team or opp else "")"""
new_tms = """    # The player's OWN badge only. The TEAM @ TEAM pair lives on the section header above and
    # repeating it here said nothing the reader had not just read.
    tms = f'<span class="cu-tms">{_tm(team)}</span>' if team else \"\""""
assert old_tms in s, "tms anchor"
s = s.replace(old_tms, new_tms, 1)

# ── 2. tier becomes a header chip; the context line is dropped ───────────────────────────────────
old_sub = """    sub = [_FULL.get(r["stat"], stat.title() if stat else "")]
    tval = r.get("_tier")
    if tval:
        sub.append(f"Tier {tval}")"""
new_sub = """    # Context line removed. Tier survives as a header chip — see module docstring.
    tval = r.get("_tier")
    tchip = f'<span class="cu-tier">Tier {tval}</span>' if tval else ""
    sub = []"""
assert old_sub in s, "sub anchor"
s = s.replace(old_sub, new_sub, 1)

# ── 3. markup: logo before name, no sub-line, tier chip in the header ───────────────────────────
old_mk = """          <div class="cu-hd"><span class="cu-st {scls}">{slbl}</span>{btag}
            <span class="cu-time">{tipt}</span></div>
          <div class="cu-ttl">{nm}{tms}</div>
          <div class="cu-sub">{subline}</div>"""
new_mk = """          <div class="cu-hd"><span class="cu-st {scls}">{slbl}</span>{tchip}{btag}
            <span class="cu-time">{tipt}</span></div>
          <div class="cu-ttl">{tms}{nm}</div>"""
assert old_mk in s, "markup anchor"
s = s.replace(old_mk, new_mk, 1)

CSS = r"""
  /* ══════════════════ CUPERTINO-CARD2 ══════════════════
     Context line gone; the name takes the space it vacated. 24pt against the 36pt bet keeps the
     bet unmistakably the object of the card while giving the player real presence. */
  #wnba .cu-ttl {{ font-size:24px; font-weight:660; letter-spacing:-.028em; gap:10px;
                   margin-bottom:16px; align-items:center; }}
  #wnba .cu-tms {{ display:inline-flex; align-items:center; }}
  #wnba .cu-tm {{ width:26px; height:26px; }}
  #wnba .cu-tier {{ font-size:12px; font-weight:600; padding:2px 8px; border-radius:11px;
                    background:var(--cu-fill); color:var(--cu-lbl2); }}
  @media (max-width:520px) {{
    #wnba .cu-ttl {{ font-size:23px; }}
  }}
"""
a = "</style></head><body>"
assert a in s, "style anchor"
s = s.replace(a, CSS + a, 1)

ast.parse(s)
shutil.copyfile(P, "/tmp/dashboard.precard2.py")
io.open(P, "w", encoding="utf-8").write(s)
print("  + context line removed; name 19 -> 24pt with own team badge; tier kept as a header chip")
