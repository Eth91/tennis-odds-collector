"""Rebuild the WNBA card MARKUP to the Cupertino anatomy (not just its colours).

The first pass recoloured the existing card and left its structure alone. That was the wrong call:
the render and the live board are structurally different objects, so a palette layer could never
produce the render. This replaces the markup.

    render                              live board (before)
    ------                              -------------------
    header: status pill + book + time   teams + time on a separate .ghd above
    title:  name WITH team logos        name in its own .phd block
    sub:    "Points · Tier A · X out"   .pctx below the bet, different content
    bet:    direction + 36px number     one row w/ stat, tier chip, edge, chevron
    conf:   bar + % + sample ON FACE    absent — meters live only in the drawer
    group:  section -> cards            game -> player block -> props

New structure, one card per play, iOS grouped list:

    .cu-sh    [wnba mark] WNBA · POR @ IND                     8:00 PM
    .cu-grp
      .cu-c
        .cu-sum   (tap target -> toggles the drawer, unchanged)
          .cu-hd    [likely] [FD]                              8:00 PM
          .cu-ttl   M. DiLeo   [POR] @ [IND]
          .cu-sub   Points · Tier A · S. Barker out
          .cu-bet   OVER  14.5  pts                       -122  ›
          .cu-cf    [=========bar=========]  72%   proj 16.8
        .bars       (drawer verbatim — meters, reasoning, game log, regime)

EVERYTHING ON THE FACE IS REAL. The confidence bar is the model's own primary meter, promoted from
the drawer rather than invented: volume-basis rows show proj_hit, role-basis rows show the
when-they-sit record. Sample text is the actual n. Rows with neither render the bar empty and the
figure as an em-dash — the unavailable state, not a guess.

The drawer, data-k, the ladder rungs, the contra flag and the tier chip all survive; they move to
where the render puts them.
"""
import ast
import io
import re
import shutil

P = "dashboard.py"
s = io.open(P, encoding="utf-8").read()

if "CUPERTINO-CARDS" in s:
    print("  = already applied")
    raise SystemExit(0)

# ── 1. replace the card renderer ────────────────────────────────────────────────────────────────
start = s.index("def _prop_row(r, rungs=None):")
end = s.index("def _load_tt():")
old = s[start:end]

# keep the helpers the new renderer still needs, verbatim, by re-deriving them from the old body
NEW = '''# CUPERTINO-CARDS: card markup rebuilt to the approved render anatomy.
def _cu_status(r):
    """Lineup status as an iOS pill. Real values only — the logger writes exactly these four."""
    return {"confirmed": ("Starting", "ok"), "likely": ("Likely", "mid"),
            "bench": ("Bench", "pp"), "projected": ("TBD", "no")}.get(
                r.get("confidence") or "projected", ("TBD", "no"))


def _cu_conf(r):
    """The card-face confidence bar. This is the model's OWN primary meter promoted out of the
    drawer, never a new number: volume rows show proj_hit, role rows show the when-they-sit record.
    Returns (pct, label, good) or None when the model has neither — the card then shows an em-dash
    rather than inventing a figure."""
    if r.get("basis") == "volume" and r.get("proj_hit"):
        p = r["proj_hit"] * 100
        return p, f'{p:.0f}%', p >= 60
    rec = _raw_record(r)
    if rec and rec[1]:
        p = rec[0] / rec[1] * 100
        return p, f'{rec[0]}/{rec[1]} when out', p >= 60
    sp = _splits(r) or {}
    l10 = sp.get("l10")
    if l10 and l10[1]:
        p = l10[0] / l10[1] * 100
        return p, f'{l10[0]}/{l10[1]} last 10', p >= 60
    return None


def _prop_row(r, rungs=None, player=None):
    """ONE Cupertino card: status pill + book + lock time, player + team marks, context sub-line,
    the bet at display size, and the confidence bar on the face. Tapping toggles the drawer, which
    is unchanged."""
    stat = STAT.get(r["stat"], r["stat"].upper())
    side = (r.get("side") if hasattr(r, "get") else r["side"]) or "over"
    oword = "OVER" if side == "over" else "UNDER"
    o = "o" if side == "over" else "u"

    # ---- header: status, book, lock ----
    slbl, scls = _cu_status(r)
    if r.get("_tipped"):
        slbl, scls = "In progress", "pp"
    bp = None if r.get("_tipped") else _book_prices(r)
    if bp:
        best_bk, best_dec = bp[0]
        btag = (f\'<img class="bklogo" src="book-{best_bk}.png" alt="{best_bk.upper()}">\'
                if best_bk in ("fd", "dk") else f\'<span class="pbk oth">{best_bk.upper()}</span>\')
    else:
        best_dec, best_bk = float(r["odds"]), "fd"
        btag = \'<img class="bklogo" src="book-fd.png" alt="FD">\'
    tipt = r.get("_tiptime") or ""

    # ---- title: player + both team marks ----
    nm = html.escape(_short(player or r.get("player") or ""))
    team, opp = (r.get("team") or "").upper(), (r.get("opp") or "").upper()

    def _tm(ab):
        return (f\'<img class="cu-tm" src="{LOGO.format(ab.lower())}" alt="{ab}" loading="lazy" \'
                f\'onerror="this.style.display=\\\'none\\\'">\' if ab else "")
    tms = (f\'<span class="cu-tms">{_tm(team)}<i>@</i>{_tm(opp)}</span>\'
           if team or opp else "")

    # ---- sub-line: market, tier, and the injury driver that created the spot ----
    sub = [stat.title() if stat else ""]
    tval = r.get("_tier")
    if tval:
        sub.append(f"Tier {tval}")
    outs = ", ".join(_short(x.strip()) for x in (r.get("out_player") or "").split(",") if x.strip())
    if outs:
        sub.append(f"{html.escape(outs)} out")
    dm = r.get("d_min")
    if not outs and dm is not None and dm > 2:
        sub.append(f"{dm:+.0f} min")
    subline = " · ".join(x for x in sub if x)

    # ---- the bet ----
    if rungs and len(rungs) > 1:
        lns = sorted(x["line"] for x in rungs)
        line_disp, rng = f"{lns[0]:g}–{lns[-1]:g}", " rng"
    else:
        line_disp, rng = f"{r[\'line\']:g}", ""
    unit = f\'<span class="cu-unit">{stat.lower()}</span>\' if stat else ""

    # ---- confidence bar (real meter, promoted from the drawer) ----
    cf = _cu_conf(r)
    if cf:
        pct, clbl, good = cf
        bar = (f\'<span class="cu-bar"><i class="{"g" if good else ""}" \'
               f\'style="width:{min(pct,100):.0f}%"></i></span>\'
               f\'<span class="cu-pc">{pct:.0f}%</span><span class="cu-n">{clbl}</span>\')
    else:
        bar = (\'<span class="cu-bar"></span><span class="cu-pc na">—</span>\'
               \'<span class="cu-n na">no sample</span>\')

    # ---- warnings that must stay on the face ----
    pcts = []
    rr_ = None if r.get("basis") == "volume" else _raw_record(r)
    if rr_ and rr_[1]:
        pcts.append(rr_[0] / rr_[1] * 100)
    sp = _splits(r) or {}
    for kk_ in ("l5", "l10", "szn", "h2h"):
        hh_ = sp.get(kk_)
        if hh_ and hh_[1]:
            pcts.append(hh_[0] / hh_[1] * 100)
    ncold = sum(1 for p_ in pcts if p_ <= 35)
    contra = (\'<span class="cu-warn" title="most form windows lean against this bet — open the \'
              \'drawer">⚠</span>\' if pcts and ncold >= max(2, len(pcts) / 2) else "")

    rungs_html = ""
    if rungs and len(rungs) > 1:
        chips = []
        for rr in sorted(rungs, key=lambda x: x["line"]):
            bpr = _book_prices(rr)
            chips.append(f\'<span class="rung"><b>{rr["line"]:g}</b> \'
                         f\'<span class="ro">{_am(bpr[0][1] if bpr else float(rr["odds"]))}</span></span>\')
        rungs_html = f\'<div class="cu-rungs">{"".join(chips)}</div>\'

    # the drawer keeps its original meters
    ms = []
    if r.get("basis") == "volume" and r.get("proj_hit"):
        ms.append(_meter_html("volume model", r["proj_hit"] * 100, f\'{r["proj_hit"]*100:.0f}%\',
                              "model probability off shot volume"))
    else:
        rec = _raw_record(r)
        if rec and rec[1]:
            ms.append(_meter_html("when they sit", rec[0] / rec[1] * 100, f"{rec[0]}/{rec[1]} over",
                                  "her games with tonight\\u2019s ruled-out players actually out"))
    l10 = sp.get("l10")
    if l10 and l10[1]:
        ms.append(_meter_html("last 10 games", l10[0] / l10[1] * 100, f"{l10[0]}/{l10[1]} over",
                              "all recent games, any lineup"))
    dk = html.escape(f"{r.get(\'pred_date\') or \'\'}|{r[\'player\']}|{r[\'stat\']}|{r[\'line\']:g}")
    return f"""
      <div class="cu-c">
        <div class="cu-sum" data-side="{side}" data-k="{dk}"
             onclick="this.parentNode.querySelector(\'.bars\').classList.toggle(\'open\')">
          <div class="cu-hd"><span class="cu-st {scls}">{slbl}</span>{btag}
            <span class="cu-time">{tipt}</span></div>
          <div class="cu-ttl">{nm}{tms}</div>
          <div class="cu-sub">{subline}</div>
          <div class="cu-bet"><span class="cu-dir {o}">{oword}</span>
            <span class="cu-line{rng}">{line_disp}</span>{unit}
            <span class="cu-price">{contra}<span class="cu-od">{_am(best_dec)}</span>
              <span class="cu-chev">\\u203a</span></span></div>
          <div class="cu-cf">{bar}</div>{rungs_html}
        </div>{_bars(r, "".join(ms))}
      </div>"""


def _player_block(player, rows):
    """Each play is now its own card carrying the player identity, so this just orders them."""
    groups = {}
    for r in rows:
        groups.setdefault((r["stat"], (r.get("side") or "over")), []).append(r)

    def _render(g):
        side = g[0].get("side") or "over"
        if side == "under" and len(g) > 1:
            return _prop_row(max(g, key=lambda x: x["line"]), player=player)
        g = sorted(g, key=lambda x: -(x.get("ev") or 0))
        return _prop_row(g[0], rungs=g if len(g) > 1 else None, player=player)
    ordered = sorted(groups.values(), key=lambda g: -max((x.get("ev") or 0) for x in g))
    return "".join(_render(g) for g in ordered)


def _game_group(players, tips, today=None, idx=0):
    """A GAME as an iOS grouped-list section: header (league mark + matchup + tip), then the
    rounded group of play cards."""
    r0 = players[0][1][0]
    team = (r0.get("team") or "").upper()
    opp = (r0.get("opp") or "").upper()
    pd0 = r0.get("pred_date") or (today or "")
    tip = tips.get((pd0, team)) or tips.get((pd0, opp))
    tiptime = tip.astimezone(MT).strftime("%-I:%M %p") if tip else ""
    for _, prs in players:
        for r in prs:
            r["_tiptime"] = tiptime
    outset = {_short(nm.strip()) for _, prs in players for r in prs
              for nm in (r.get("out_player") or "").split(",") if nm.strip()}
    outs = " + ".join(sorted(outset))
    cards = "".join(_player_block(p, prs) for p, prs in players)
    gedge = max((x.get("ev") or 0) for _, prs in players for x in prs)
    gtip = tip.timestamp() if tip else 9e15

    def glogo(ab):
        return (f\'<img class="cu-gl" src="{LOGO.format(ab.lower())}" alt="" loading="lazy" \'
                f\'onerror="this.style.display=\\\'none\\\'">\' if ab else "")
    outline = (f\'<div class="cu-out"><i class="sdot warn"></i>{html.escape(outs)} out</div>\'
               if outs else "")
    return (f\'<div class="game" data-edge="{gedge:.4f}" data-tip="{gtip:.0f}" style="--i:{idx}">\'
            f\'<div class="cu-sh">{_llogo("wnba")}<b>WNBA</b>\'
            f\'<span class="cu-shm">{glogo(team)}{team} @ {glogo(opp)}{opp or "—"}</span>\'
            f\'<span class="cu-shr">{tiptime}</span></div>\'
            f\'{outline}<div class="cu-grp">{cards}</div></div>\')


'''
s = s[:start] + NEW + s[end:]

# ── 2. _meter_html: the drawer meter, lifted out of the old _prop_row closure ───────────────────
anchor = "def _bars(r, meters=\"\"):"
helper = '''def _meter_html(label, pct, valtext, title=""):
    cls = " good" if pct >= 60 else (" bad" if pct <= 40 else "")
    return (f\'<div class="meter{cls}" title="{html.escape(title)}"><span class="mlab">{label}</span>\'
            f\'<span class="mbar"><i style="width:{min(pct, 100):.0f}%"></i></span>\'
            f\'<span class="mval">{valtext}</span></div>\')


'''
assert anchor in s, "bars anchor missing"
s = s.replace(anchor, helper + anchor, 1)

ast.parse(s)
shutil.copyfile(P, "/tmp/dashboard.precards.py")
io.open(P, "w", encoding="utf-8").write(s)
print("  + _prop_row rebuilt as a Cupertino card (status/book/time, title+teams, sub, bet, conf bar)")
print("  + _player_block flattened; _game_group emits .cu-sh section + .cu-grp group")
print("  + _meter_html extracted so the drawer keeps its meters")
