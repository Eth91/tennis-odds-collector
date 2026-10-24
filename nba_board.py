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
    V = _clv()
    out = {"generated_at": now_n, "slates": [], "retracted": [], "record": None}
    if sh is None:
        return out
    sh.row_factory = sqlite3.Row
    flags = [dict(r) for r in sh.execute(
        f"SELECT * FROM flags WHERE void_reason IS NULL AND COALESCE(card, 1) = 1 "   # amendment 18: the card
        f"AND game_date IN ({','.join('?' * len(days))}) ORDER BY logged_at", tuple(days))]
    opp = {}
    for f in flags:
        k = (f["game_date"], f["gid"], f["pid"] or f["b"], STAT.get(f["stat"], f["stat"]))
        if k not in opp:
            opp[k] = dict(f, tiers={f["tier"]})
        else:
            opp[k]["tiers"].add(f["tier"])
    status = _status_by_date(news, {k[0] for k in opp})
    try:
        vetoed = {(gd, pid): why for gd, pid, why in sh.execute("SELECT game_date, pid, reason FROM vetoes")}
    except sqlite3.OperationalError:
        vetoed = {}
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
        row = {"b": f["b"], "team": f["team"], "stat": LABEL.get(stat, stat.upper()), "line": f["line"],
               "odds": f["odds"], "tiers": sorted(f["tiers"]), "x": f["x"], "horizon": f.get("horizon") or 0,
               "flagged_mt": dt.datetime.fromisoformat(f["logged_at"]).replace(tzinfo=dt.timezone.utc)
               .astimezone(MT).strftime("%-I:%M %p"),
               "fd": {"line": fd[0], "odds": fd[1]} if fd else None,
               "b_status": st.get(f["pid"]), "result": f.get("result"), "actual": f.get("actual"),
               "state": ("final" if f.get("result") else "live" if started else "upcoming"),
               "x_status": st.get(f.get("x_pid")) or f.get("x_status") or "Out",
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
               and not (r.get("x_min") is not None and r["x_min"] < 28)]      # amendment 16
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
#nba{--ncol:62px}
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
#nba .ng,#nba .nr{display:grid;grid-template-columns:1fr var(--ncol) var(--ncol);gap:0 10px;align-items:baseline}
#nba .ng{padding:16px 0 7px;border-bottom:1px solid var(--cu-sep);font-size:12px;font-weight:700;
  color:var(--cu-lbl2);letter-spacing:.02em}
#nba .ng .t{color:var(--cu-lbl3);font-weight:600;margin-left:6px;font-variant-numeric:tabular-nums}
#nba .ng .k{text-align:right;font-size:10px;font-weight:700;letter-spacing:.08em;color:var(--cu-lbl3)}
#nba .nr{padding:12px 0 11px;border-bottom:1px solid var(--hair)}
#nba .np{font-size:16px;font-weight:600;color:var(--cu-lbl);letter-spacing:-.01em;line-height:1.25}
#nba .nm{margin-top:3px;font-size:12.5px;color:var(--cu-lbl2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#nba .nm b{font-weight:700;color:var(--cu-lbl);letter-spacing:.02em}
#nba .nm .s{font-size:10px;font-weight:700;letter-spacing:.06em;color:var(--cu-lbl3)}
#nba .nt{margin-top:3px;font-size:10px;font-weight:700;letter-spacing:.07em;text-transform:uppercase;
  color:var(--cu-lbl3)}
#nba .nt .w{color:var(--cu-org)}
#nba .pl{display:inline-block;margin-left:6px;padding:1px 5px 0;border-radius:4px;font-size:10px;font-weight:800;
  letter-spacing:.04em;vertical-align:2px;background:rgba(255,214,10,.16);color:var(--cu-yel)}
#nba .nc{text-align:right;font-variant-numeric:tabular-nums}
#nba .nc .l{font-size:16px;font-weight:700;color:var(--cu-lbl)}
#nba .nc .o{margin-top:2px;font-size:12px;font-weight:600;color:var(--cu-lbl3)}
#nba .nc.dim .l{color:var(--cu-lbl3);font-weight:600}
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
TIER = {"priced": "PRICED", "wowy": "WOWY", "wowy_v0": "WOWY", "cold": "COLD"}


def _units(rows):
    """(wins, losses, flat units at the flagged price) over graded rows."""
    g = [r for r in rows if r["result"] in ("win", "loss")]
    w = sum(1 for r in g if r["result"] == "win")
    return w, len(g) - w, sum((r["odds"] - 1) if r["result"] == "win" else -1.0 for r in g)


def _row(r):
    e = H.escape
    q = '<span class="pl">Q</span>' if r["b_status"] == "Questionable" else ""
    xs = "DBT" if r["x_status"] == "Doubtful" else "OUT"
    xn = r["x"].split(" ", 1)
    xn = f"{xn[0][0]}. {xn[1]}" if len(xn) == 2 else r["x"]           # "C. Johnson": one line on a phone
    tiers = " · ".join(dict.fromkeys(TIER.get(t, t.upper()) for t in r["tiers"]))
    news = ' · <span class="w">NEWS ONLY</span>' if r["news_only"] and r["state"] == "upcoming" else ""
    flag = (f'<div class="nc"><div class="l">O{r["line"]:g}</div>'
            f'<div class="o">{american(r["odds"])}</div></div>')
    if r["result"]:
        cls = "win" if r["result"] == "win" else "loss"
        tip = f'TIP O{r["fd"]["line"]:g}' if r["fd"] else "&nbsp;"
        right = (f'<div class="nc"><div class="l {cls}">{r["actual"]:g} {"W" if cls == "win" else "L"}</div>'
                 f'<div class="o">{tip}</div></div>')
    elif r["fd"]:
        d = r["fd"]["line"] - r["line"]
        cls = "up" if d > 0 else "dn" if d < 0 else ""
        dp = r["fd"]["odds"] - r["odds"]                 # same line: a shorter over price = moved our way
        pcls = "" if d or abs(dp) < .02 else "up" if dp < 0 else "dn"
        right = (f'<div class="nc"><div class="l {cls}">O{r["fd"]["line"]:g}</div>'
                 f'<div class="o {pcls}">{american(r["fd"]["odds"])}</div></div>')
    else:
        right = '<div class="nc dim"><div class="l">—</div><div class="o">PULLED</div></div>'
    return (f'<div class="nr"><div><div class="np">{e(r["b"])}{q}</div>'
            f'<div class="nm"><b>{e(r["stat"])}</b> · {e(r["team"])} · {e(xn)} <span class="s">{xs}</span></div>'
            f'<div class="nt">{e(tiers)} · {e(r["flagged_mt"])}{news}</div></div>{flag}{right}</div>')


def _games(s):
    out = []
    for g in s["games"]:
        live = any(r["state"] == "live" for r in g["rows"])
        done = all(r["state"] == "final" for r in g["rows"])
        k2 = "FINAL" if done else "TIP" if live else "NOW"
        t = "LIVE" if live else "" if done else f'{g["tip_mt"]}'
        out.append(f'<div class="ng"><span>{H.escape(g["matchup"])}<span class="t">{H.escape(t)}</span></span>'
                   f'<span class="k">FLAG</span><span class="k">{k2}</span></div>')
        out.extend(_row(r) for r in g["rows"])
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
    for s in b["slates"]:
        rows = [r for g in s["games"] for r in g["rows"]]
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
