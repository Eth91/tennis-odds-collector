#!/usr/bin/env python3
"""The NBA section of the Pickz board: the SHADOW flags, as data and as an HTML fragment.

The live board is dashboard.py on the VM. It imports this file by path and drops `html(board())`
into its NBA tab. The logic lives here, in git and tested. Read-only over nba_shadow / nba_news /
nba_lines; it runs on every ~20 s bake.

SHADOW. nba_flags.LIVE_TIERS is empty: these never ping and are not bets. The section header says so,
as a label, never a paragraph (feedback_no_explanatory_ui).

ONE ROW PER OPPORTUNITY — (game, player, stat), using the EARLIEST flag, the one the speed test scores
(nba_clv). Every tier that flagged it is listed. A row shows the flag's price, FanDuel's main line now
(at tip once the game starts), and the result once graded.

RETRACTED (display only; the shadow record still scores every flag as registered). This happens when
the newest official report for that game lists the flagged player Out or Doubtful, or the absent star
Questionable, Available or Probable (Questionable since amendment 15). A retracted row moves to a compact strip and never vanishes
(feedback_ping_board_coherence). Voided flags (a pre-registered exclusion) are not plays and are not
shown.

    python nba_board.py      # print board() as JSON
"""
from __future__ import annotations

import datetime as dt
import html as H
import importlib.util
import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
SHADOW, NEWS, LINES = HERE / "nba_shadow.sqlite", HERE / "nba_news.sqlite", HERE / "nba_lines.sqlite"
ET, MT = ZoneInfo("America/New_York"), ZoneInfo("America/Denver")
STAT = {"pts": "points", "reb": "rebounds", "ast": "assists"}          # wowy/cold short keys
LABEL = {"points": "PTS", "rebounds": "REB", "assists": "AST", "pra": "PRA", "pts_reb": "P+R",
         "pts_ast": "P+A", "reb_ast": "R+A", "threes": "3PM"}
# X_BACK: amendment 15 adds Questionable (a Doubtful -> Questionable upgrade breaks the premise).
B_OFF, X_BACK = ("Out", "Doubtful"), ("Questionable", "Available", "Probable")
PING_CANON = {"pts": "points", "reb": "rebounds", "ast": "assists"}     # == nba_ping.CANON (its play key)
# USER VETO (2026-10-24, display only): a player-game the user takes off the card. It moves to the OFF
# strip with its reason (a pinged play gets a VOID through the same path). The record is untouched.
VETO_DDL = """CREATE TABLE IF NOT EXISTS vetoes (game_date TEXT, pid INTEGER, player TEXT, reason TEXT,
    at TEXT, PRIMARY KEY (game_date, pid))"""
DECISION_N = 100


def _clv():
    """nba_clv loaded by PATH under a private name, so the board's own sys.path (the VM's old
    checkout has its own module copies) is never touched."""
    spec = importlib.util.spec_from_file_location("_nba_clv_for_board", HERE / "nba_clv.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.SHADOW, m.LINES, m.NEWS = SHADOW, LINES, NEWS
    return m


def _silence():
    """nba_silence loaded by PATH (amendment 21), like _clv: the dashboard's sys.path is never touched."""
    spec = importlib.util.spec_from_file_location("_nba_silence_for_board", HERE / "nba_silence.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _ro(p):
    return sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=10) if p.exists() else None


def american(dec):
    if not dec or dec <= 1:
        return ""
    return f"+{round((dec - 1) * 100)}" if dec >= 2 else f"−{round(100 / (dec - 1))}"


def _status_by_date(news, dates):
    """{game_date: {pid: status}} from the NEWEST official report that covers each date."""
    out = {}
    if news is None:
        return out
    for d in dates:
        m = news.execute("SELECT MAX(mark) FROM snapshots WHERE game_date=?", (d,)).fetchone()[0]
        if m:
            out[d] = dict(news.execute("SELECT pid, status FROM snapshots WHERE mark=? AND game_date=?",
                                       (m, d)))
    return out


def board(now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    now_n = now.astimezone(dt.timezone.utc).replace(tzinfo=None, microsecond=0).isoformat()
    today = now.astimezone(ET).date()
    days = {(today - dt.timedelta(days=1)).isoformat(): "LAST NIGHT", today.isoformat(): "TONIGHT",
            (today + dt.timedelta(days=1)).isoformat(): "TOMORROW"}
    sh, news, q = _ro(SHADOW), _ro(NEWS), _ro(LINES)
    V, SIL = _clv(), _silence()
    out = {"generated_at": now_n, "slates": [], "retracted": [], "offcard": [], "record": None}
    if sh is None:
        return out
    sh.row_factory = sqlite3.Row
    flags = [dict(r) for r in sh.execute(
        f"SELECT * FROM flags WHERE void_reason IS NULL AND COALESCE(card, 1) = 1 "   # amendment 18: the card
        f"AND game_date IN ({','.join('?' * len(days))}) ORDER BY logged_at", tuple(days))]
    try:                                   # AMENDMENT 27: a tip-card play shows its decided price and time
        tipc = {fid: (odds, at) for fid, odds, at in sh.execute("SELECT flag_id, odds, decided_at FROM tipcard "
                                                               "WHERE card = 1")}
    except sqlite3.OperationalError:
        tipc = {}
    opp = {}
    for f in flags:
        k = (f["game_date"], f["gid"], f["pid"] or f["b"], STAT.get(f["stat"], f["stat"]))
        if f.get("card_why") == "TIP CARD":
            f["odds"], f["logged_at"] = tipc.get(f["flag_id"], (f["odds"], f["logged_at"]))
            f["tier"] += " tip"
        if k not in opp:
            opp[k] = dict(f, tiers={f["tier"]})
        else:
            opp[k]["tiers"].add(f["tier"])
    status = _status_by_date(news, {k[0] for k in opp})
    try:
        vetoed = {(gd, pid): why for gd, pid, why in sh.execute("SELECT game_date, pid, reason FROM vetoes")}
    except sqlite3.OperationalError:
        vetoed = {}
    # PINGED · OFF CARD (feedback_ping_board_coherence: if it pinged, it is on the board). A play pinged
    # before the card took it off (amendments 18-19) is listed, never hidden. Not a retraction: no VOID.
    try:
        pinged = {k for (k,) in sh.execute("SELECT key FROM pings WHERE kind='play' AND ok=1")}
    except sqlite3.OperationalError:
        pinged = set()
    carded = {(f["game_date"], f["pid"]) for f in flags}
    seen_off = set()
    for f in (dict(r) for r in sh.execute(
            f"SELECT * FROM flags WHERE void_reason IS NULL AND card = 0 "
            f"AND game_date IN ({','.join('?' * len(days))}) ORDER BY logged_at", tuple(days))):
        k = f"play|{f['game_date']}|{f['pid'] or f['b']}|{PING_CANON.get(f['stat'], f['stat'])}"
        tip = V._utc_naive(f["gtime"]) if f.get("gtime") else None
        if k not in pinged or k in seen_off or (tip and tip <= now_n) or (f["game_date"], f["pid"]) in vetoed:
            continue
        seen_off.add(k)
        st_ = STAT.get(f["stat"], f["stat"])
        out["offcard"].append({"b": f["b"], "stat": LABEL.get(st_, st_.upper()), "line": f["line"],
                               "why": f.get("card_why") or ("1 PER PLAYER" if (f["game_date"], f["pid"]) in carded
                                                            else "TEAM SLOT")})
    games = defaultdict(list)
    for (gd, gid, _p, stat), f in opp.items():
        tip = V._utc_naive(f["gtime"]) if f.get("gtime") else None
        started = bool(tip and tip <= now_n)
        fd = (V.close_of(q, gid, f["pid"], stat, tip if started else now_n, books=("fd",))
              if q is not None and f.get("pid") else None)
        st = status.get(gd, {})
        why = None
        if (gd, f["pid"]) in vetoed:
            why = f"{f['b']} VETOED: {vetoed[(gd, f['pid'])]}"
        elif not started and st.get(f["pid"]) in B_OFF:
            why = f"{f['b']} {st[f['pid']].upper()}"
        elif not started and f.get("x_pid") and st.get(f["x_pid"]) in X_BACK:
            why = f"{f['x']} {st[f['x_pid']].upper()}"
        elif (not started and news is not None and f.get("x_pid") and st.get(f["x_pid"]) not in B_OFF
              and (f.get("trigger_src") or "").startswith("news") and f.get("trigger_src") != "news:inferred"
              and SIL.silenced(news, f["x_pid"], f["team"], gd, f.get("news_at"))):
            why = f"{f['x']} NOT ON REPORT"                   # amendment 21: the silence check
        row = {"b": f["b"], "team": f["team"], "stat": LABEL.get(stat, stat.upper()), "line": f["line"],
               "odds": f["odds"], "tiers": sorted(f["tiers"]), "x": f["x"], "horizon": f.get("horizon") or 0,
               "flagged_mt": dt.datetime.fromisoformat(f["logged_at"]).replace(tzinfo=dt.timezone.utc)
               .astimezone(MT).strftime("%-I:%M %p"),
               "fd": {"line": fd[0], "odds": fd[1]} if fd else None,
               "b_status": st.get(f["pid"]), "result": f.get("result"), "actual": f.get("actual"),
               "state": ("final" if f.get("result") else "live" if started else "upcoming"),
               "x_status": st.get(f.get("x_pid")) or f.get("x_status") or "Out", "pid": f.get("pid"),
               "news_only": ((f.get("trigger_src") or "").startswith("news")
                             and st.get(f.get("x_pid")) not in B_OFF)}
        if why:
            out["retracted"].append(dict(row, why=why, matchup=f.get("matchup") or f["team"],
                                         game_date=gd, pid=f.get("pid"), raw_stat=stat,
                                         gtime=f.get("gtime")))
        else:
            games[(gd, tip or "", f.get("matchup") or f["team"])].append(row)
    order = ["TONIGHT", "TOMORROW", "LAST NIGHT"]
    for gd, label in sorted(days.items(), key=lambda kv: order.index(kv[1])):
        gs = [{"matchup": m, "tip_mt": (dt.datetime.fromisoformat(t).replace(tzinfo=dt.timezone.utc)
                                         .astimezone(MT).strftime("%-I:%M %p") if t else ""),
               "rows": sorted(rs, key=lambda r: (r["b"], r["stat"]))}
              for (d, t, m), rs in sorted(games.items()) if d == gd]
        if gs:
            out["slates"].append({"date": gd, "label": label, "games": gs})
    rows = V.collect()
    fd_rows = [V.view(r, "FD") for r in rows if r.get("x_status") != "Doubtful"   # amendment 15
               and not (r.get("x_min") is not None and r["x_min"] < 28)       # amendment 16
               and not (r.get("aidx") or 0) > 2]                               # amendment 27
    closed = [v for v in fd_rows if v["close"]]
    graded = [v for v in closed if "u_flag" in v]
    out["record"] = {"closed": len(closed), "beat": sum(1 for v in closed if v["beat"]),
                     "graded": len(graded), "units": round(sum(v["u_flag"] for v in graded), 2),
                     "games": len({v["gid"] for v in closed}), "decision_n": DECISION_N}
    for c in (sh, news, q):
        if c is not None:
            c.close()
    return out


CSS = """<style>
#nba .nst{display:grid;grid-template-columns:repeat(3,1fr);gap:0 12px;margin:2px 0 4px;padding:12px 0 14px;
  border-bottom:1px solid var(--cu-sep);font-variant-numeric:tabular-nums}
#nba .nst b{display:block;font-size:22px;font-weight:700;letter-spacing:-.02em;color:var(--cu-lbl);line-height:1.1}
#nba .nst b i{font-style:normal;font-size:13px;font-weight:600;color:var(--cu-lbl3)}
#nba .nst span{display:block;margin-top:3px;font-size:10px;font-weight:700;letter-spacing:.08em;
  text-transform:uppercase;color:var(--cu-lbl3)}
#nba .nsh{color:var(--cu-org)}
#nba .nday{display:flex;justify-content:space-between;align-items:baseline;margin:26px 0 0;font-size:11px;
  font-weight:800;letter-spacing:.1em;text-transform:uppercase;color:var(--cu-lbl)}
#nba .nday span{font-weight:700;color:var(--cu-lbl3);font-variant-numeric:tabular-nums;text-transform:none}
#nba .ng{display:flex;align-items:center;gap:7px;padding:18px 2px 9px;font-size:13px;font-weight:700;
  color:var(--cu-lbl2);letter-spacing:.02em}
#nba .ng img{width:20px;height:20px}
#nba .ng .t{margin-left:auto;font-weight:600;color:var(--cu-lbl3);font-variant-numeric:tabular-nums}
#nba .ng .t.lv{color:var(--cu-red);font-weight:800;letter-spacing:.06em}
#nba .nk{background:var(--cu-grp);border-radius:16px;padding:14px 14px 12px;margin:0 0 10px}
#nba .nk-top{display:flex;align-items:center;gap:12px}
#nba .nk-av{position:relative;flex:none;width:54px;height:54px;border-radius:50%;background:var(--cu-grp2);overflow:visible}
#nba .nk-av .hs{width:54px;height:54px;border-radius:50%;object-fit:cover;object-position:50% 12%}
#nba .nk-av .lg{position:absolute;right:-5px;bottom:-4px;width:24px;height:24px;padding:2px;border-radius:50%;
  background:#000;box-sizing:border-box}
#nba .nk-id{min-width:0;flex:1}
#nba .nk-nm{font-size:18px;font-weight:700;color:var(--cu-lbl);letter-spacing:-.01em;line-height:1.2;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#nba .nk-sub{margin-top:3px;font-size:12.5px;font-weight:600;color:var(--cu-lbl2);font-variant-numeric:tabular-nums}
#nba .nk-tg{flex:none;align-self:flex-start;text-align:right;line-height:1.7;font-size:10px;font-weight:800;
  letter-spacing:.07em;color:var(--cu-lbl3)}
#nba .nk-tg .w{display:block;color:var(--cu-org)}
#nba .pl{display:inline-block;margin-left:7px;padding:2px 6px 1px;border-radius:5px;font-size:10.5px;font-weight:800;
  letter-spacing:.04em;vertical-align:3px;background:rgba(255,214,10,.16);color:var(--cu-yel)}
#nba .nk-st{margin:14px 0 6px;font-size:11px;font-weight:800;letter-spacing:.09em;color:var(--cu-lbl2)}
#nba .nk-bt{display:flex;align-items:center;justify-content:space-between;padding:12px 14px;border-radius:12px;
  background:var(--cu-grp2);font-variant-numeric:tabular-nums}
#nba .nk-ln{font-size:26px;font-weight:800;letter-spacing:-.02em;color:var(--cu-lbl);line-height:1}
#nba .nk-ln i{font-style:normal;font-size:15px;font-weight:700;color:var(--cu-lbl2);margin-right:5px}
#nba .nk-od{font-size:18px;font-weight:700;color:var(--cu-lbl)}
#nba .nk-rs{font-size:22px;font-weight:800}
#nba .nk-ft{display:flex;flex-wrap:wrap;justify-content:space-between;gap:4px 10px;margin-top:10px;font-size:12px;
  font-weight:600;color:var(--cu-lbl3);font-variant-numeric:tabular-nums}
#nba .nk-ft b{font-weight:700;color:var(--cu-lbl)}
#nba .nk-ft .k{font-size:10px;font-weight:800;letter-spacing:.07em}
#nba .up{color:var(--cu-grn)!important} #nba .dn{color:var(--cu-red)!important}
#nba .win{color:var(--cu-grn)!important} #nba .loss{color:var(--cu-red)!important}
#nba details.nlast{margin-top:26px}
#nba details.nlast summary{list-style:none;cursor:pointer}
#nba details.nlast summary::-webkit-details-marker{display:none}
#nba details.nlast summary .nday{margin:0}
#nba details.nlast summary .nday span:after{content:"  +";white-space:pre}
#nba details.nlast[open] summary .nday span:after{content:"  −"}
#nba .noff{margin-top:26px}
#nba .noff div{padding:9px 0;border-bottom:1px solid var(--hair);font-size:12.5px;color:var(--cu-lbl3)}
#nba .noff b{color:var(--cu-lbl2);font-weight:600}
#nba .nnone{padding:28px 0;font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;
  color:var(--cu-lbl3)}
</style>"""
TIER = {"priced": "PRICED", "wowy": "WOWY", "wowy_v0": "WOWY", "cold": "COLD", "wowy tip": "WOWY · TIP CARD"}
STAT_NAME = {"PTS": "POINTS", "REB": "REBOUNDS", "AST": "ASSISTS", "PRA": "PTS + REB + AST",
             "P+R": "PTS + REB", "P+A": "PTS + AST", "R+A": "REB + AST", "3PM": "3-POINTERS MADE"}
# NBA team ids (cdn.nba.com scheduleLeagueV2, checked 2026-10-24) for the logo + headshot CDN
TEAM_ID = {"ATL": 1610612737, "BKN": 1610612751, "BOS": 1610612738, "CHA": 1610612766, "CHI": 1610612741,
           "CLE": 1610612739, "DAL": 1610612742, "DEN": 1610612743, "DET": 1610612765, "GSW": 1610612744,
           "HOU": 1610612745, "IND": 1610612754, "LAC": 1610612746, "LAL": 1610612747, "MEM": 1610612763,
           "MIA": 1610612748, "MIL": 1610612749, "MIN": 1610612750, "NOP": 1610612740, "NYK": 1610612752,
           "OKC": 1610612760, "ORL": 1610612753, "PHI": 1610612755, "PHX": 1610612756, "POR": 1610612757,
           "SAC": 1610612758, "SAS": 1610612759, "TOR": 1610612761, "UTA": 1610612762, "WAS": 1610612764}


def _logo(tri, cls="lg"):
    tid = TEAM_ID.get(tri)
    return (f'<img class="{cls}" src="https://cdn.nba.com/logos/nba/{tid}/global/D/logo.svg" alt="" loading="lazy">'
            if tid else "")


def _units(rows):
    """(wins, losses, flat units at the flagged price) over graded rows."""
    g = [r for r in rows if r["result"] in ("win", "loss")]
    w = sum(1 for r in g if r["result"] == "win")
    return w, len(g) - w, sum((r["odds"] - 1) if r["result"] == "win" else -1.0 for r in g)


def _card(r, matchup, tip):
    e = H.escape
    away, _, home = matchup.partition(" @ ")
    opp = f"vs {away}" if r["team"] == home else f"@ {home}" if home else matchup
    q = '<span class="pl">Q</span>' if r["b_status"] == "Questionable" else ""
    xn = r["x"].split(" ", 1)
    xn = f"{xn[0][0]}. {xn[1]}" if len(xn) == 2 else r["x"]
    xs = "DBT" if r["x_status"] == "Doubtful" else "OUT"
    tiers = " · ".join(dict.fromkeys(TIER.get(t, t.upper()) for t in r["tiers"]))
    head = (f'<img class="hs" src="https://cdn.nba.com/headshots/nba/latest/260x190/{int(r["pid"])}.png" alt="" '
            f'loading="lazy" onerror="this.remove()">' if r.get("pid") else "")
    if r["result"]:
        cls = "win" if r["result"] == "win" else "loss"
        right = f'<span class="nk-rs {cls}">{r["actual"]:g} {"W" if cls == "win" else "L"}</span>'
    else:
        right = f'<span class="nk-od">{american(r["odds"])}</span>'
    if r["result"] or r["state"] == "live":
        now = (f'<span><span class="k">TIP</span> <b>O{r["fd"]["line"]:g}</b> {american(r["fd"]["odds"])}</span>'
               if r["fd"] else '<span><span class="k">TIP</span> —</span>')
    elif r["fd"]:
        d = r["fd"]["line"] - r["line"]
        cls = "up" if d > 0 else "dn" if d < 0 else ""
        dp = r["fd"]["odds"] - r["odds"]                 # same line: a shorter over price = moved our way
        pcls = "" if d or abs(dp) < .02 else "up" if dp < 0 else "dn"
        now = (f'<span><span class="k">FD NOW</span> <b class="{cls}">O{r["fd"]["line"]:g}</b> '
               f'<span class="{pcls}">{american(r["fd"]["odds"])}</span></span>')
    else:
        now = '<span><span class="k">FD NOW</span> PULLED</span>'
    news = '<span class="w">NEWS ONLY</span>' if r["news_only"] and r["state"] == "upcoming" else ""
    return (f'<div class="nk"><div class="nk-top"><div class="nk-av">{head}{_logo(r["team"])}</div>'
            f'<div class="nk-id"><div class="nk-nm">{e(r["b"])}{q}</div>'
            f'<div class="nk-sub">{e(r["team"])} {e(opp)} · {e(tip)}</div></div>'
            f'<div class="nk-tg">{e(tiers)}{news}</div></div>'
            f'<div class="nk-st">{e(STAT_NAME.get(r["stat"], r["stat"]))}</div>'
            f'<div class="nk-bt"><span class="nk-ln"><i>OVER</i>{r["line"]:g}</span>{right}</div>'
            f'<div class="nk-ft">{now}<span>{e(xn)} <span class="k">{xs}</span> · {e(r["flagged_mt"])}</span></div>'
            f'</div>')


def _games(s):
    out = []
    for g in s["games"]:
        live = any(r["state"] == "live" for r in g["rows"])
        done = all(r["state"] == "final" for r in g["rows"])
        away, _, home = g["matchup"].partition(" @ ")
        t = ('<span class="t lv">LIVE</span>' if live else '<span class="t">FINAL</span>' if done
             else f'<span class="t">{H.escape(g["tip_mt"])}</span>')
        logos = (f'{_logo(away, "gl")}{H.escape(away)} @ {H.escape(home)}{_logo(home, "gl")}'
                 if home else H.escape(g["matchup"]))
        out.append(f'<div class="ng">{logos}{t}</div>')
        out.extend(_card(r, g["matchup"], "LIVE" if live else "FINAL" if done else g["tip_mt"]) for r in g["rows"])
    return out


def html(b):
    e = H.escape
    rec = b.get("record") or {}
    parts = [CSS, '<h2>NBA · <span class="nsh">SHADOW · NOT BETS</span></h2>']
    if rec:
        n = rec["closed"]
        units = (f'<b class="{"up" if rec["units"] > 0 else "dn" if rec["units"] < 0 else ""}">'
                 f'{rec["units"]:+.1f}u</b><span>{rec["graded"]} GRADED</span>') if rec["graded"] else \
            '<b>—</b><span>FLAT</span>'
        parts.append(f'<div class="nst"><div><b>{n}<i>/{rec["decision_n"]}</i></b><span>SCORED</span></div>'
                     f'<div><b>{rec["beat"]}<i>/{n}</i></b><span>BEAT FD CLOSE</span></div>'
                     f'<div>{units}</div></div>')
    if not b["slates"]:
        parts.append('<div class="nnone">NO SHADOW FLAGS ON THIS SLATE</div>')
    off = b.get("offcard") or []
    strip = ([f'<div class="noff"><div class="nday" style="margin:0 0 2px">PINGED · OFF CARD<span>{len(off)}</span></div>']
             + [f'<div><b>{e(r["b"])}</b> {e(r["stat"])} O{r["line"]:g} · {e(r["why"])}</div>' for r in off]
             + ['</div>']) if off else []
    for s in b["slates"]:
        rows = [r for g in s["games"] for r in g["rows"]]
        if s["label"] == "LAST NIGHT" and strip:
            parts.extend(strip)
            strip = []
        if s["label"] == "LAST NIGHT":
            w, l, u = _units(rows)
            tally = f'{w}–{l} · {u:+.1f}u' if w + l else f'{len(rows)}'
            parts.append(f'<details class="nlast"><summary><div class="nday">{e(s["label"])}'
                         f'<span>{e(tally)}</span></div></summary>')
            parts.extend(_games(s))
            parts.append('</details>')
        else:
            parts.append(f'<div class="nday">{e(s["label"])}<span>{len(rows)}</span></div>')
            parts.extend(_games(s))
    parts.extend(strip)
    if b["retracted"]:
        parts.append('<div class="noff"><div class="nday" style="margin:0 0 2px">OFF'
                     f'<span>{len(b["retracted"])}</span></div>')
        for r in b["retracted"]:
            why = r["why"][len(r["b"]):].strip() if r["why"].startswith(r["b"]) else r["why"]
            parts.append(f'<div><b>{e(r["b"])}</b> {e(r["stat"])} O{r["line"]:g} · {e(why)}</div>')
        parts.append('</div>')
    return "".join(parts)


def veto(game_date, pid, reason, path=None):
    """Take a player-game off the card (display + VOID ping only; every flag stays in the record)."""
    sh = sqlite3.connect(path or SHADOW)
    sh.execute(VETO_DDL)
    name = (sh.execute("SELECT b FROM flags WHERE game_date=? AND pid=? LIMIT 1", (game_date, pid)).fetchone()
            or (None,))[0]
    if not name:
        raise SystemExit(f"no flag for pid {pid} on {game_date}")
    sh.execute("INSERT OR REPLACE INTO vetoes VALUES (?,?,?,?,?)", (game_date, pid, name, reason,
               dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()))
    sh.commit()
    sh.close()
    return name


if __name__ == "__main__":
    import sys
    if sys.argv[1:2] == ["--veto"]:                  # --veto GAME_DATE PID "reason"
        print(f"vetoed {veto(sys.argv[2], int(sys.argv[3]), sys.argv[4])} on {sys.argv[2]}")
    else:
        print(json.dumps(board(), indent=1, default=str))
