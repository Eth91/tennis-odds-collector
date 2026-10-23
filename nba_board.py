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
Available or Probable. A retracted row moves to a compact strip and never vanishes
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
B_OFF, X_BACK = ("Out", "Doubtful"), ("Available", "Probable")
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
        f"SELECT * FROM flags WHERE void_reason IS NULL AND game_date IN ({','.join('?' * len(days))}) "
        "ORDER BY logged_at", tuple(days))]
    opp = {}
    for f in flags:
        k = (f["game_date"], f["gid"], f["pid"] or f["b"], STAT.get(f["stat"], f["stat"]))
        if k not in opp:
            opp[k] = dict(f, tiers={f["tier"]})
        else:
            opp[k]["tiers"].add(f["tier"])
    status = _status_by_date(news, {k[0] for k in opp})
    games = defaultdict(list)
    for (gd, gid, _p, stat), f in opp.items():
        tip = V._utc_naive(f["gtime"]) if f.get("gtime") else None
        started = bool(tip and tip <= now_n)
        fd = (V.close_of(q, gid, f["pid"], stat, tip if started else now_n, books=("fd",))
              if q is not None and f.get("pid") else None)
        st = status.get(gd, {})
        why = None
        if not started and st.get(f["pid"]) in B_OFF:
            why = f"{f['b']} {st[f['pid']].upper()}"
        elif not started and f.get("x_pid") and st.get(f["x_pid"]) in X_BACK:
            why = f"{f['x']} {st[f['x_pid']].upper()}"
        row = {"b": f["b"], "team": f["team"], "stat": LABEL.get(stat, stat.upper()), "line": f["line"],
               "odds": f["odds"], "tiers": sorted(f["tiers"]), "x": f["x"], "horizon": f.get("horizon") or 0,
               "flagged_mt": dt.datetime.fromisoformat(f["logged_at"]).replace(tzinfo=dt.timezone.utc)
               .astimezone(MT).strftime("%-I:%M %p"),
               "fd": {"line": fd[0], "odds": fd[1]} if fd else None,
               "b_status": st.get(f["pid"]), "result": f.get("result"), "actual": f.get("actual"),
               "state": ("final" if f.get("result") else "live" if started else "upcoming")}
        if why:
            out["retracted"].append(dict(row, why=why, matchup=f.get("matchup") or f["team"]))
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
    fd_rows = [V.view(r, "FD") for r in rows]
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
#nba .nrec{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:11px;font-weight:700;letter-spacing:.06em;
  text-transform:uppercase;color:var(--cu-lbl3);margin:0 0 6px;font-variant-numeric:tabular-nums}
#nba .nrec b{color:var(--cu-lbl);font-weight:700}
#nba .nsh{color:var(--cu-org)}
#nba .nday{font-size:10.5px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#5c6572;
  margin:22px 0 0}
#nba .ng{display:flex;justify-content:space-between;align-items:baseline;padding:12px 0 8px;
  border-bottom:1px solid var(--cu-sep);font-size:13px;font-weight:700;color:var(--cu-lbl2)}
#nba .ng .t{font-weight:600;color:var(--cu-lbl3);font-variant-numeric:tabular-nums}
#nba .nr{display:grid;grid-template-columns:1fr auto;gap:2px 12px;padding:11px 0;border-bottom:1px solid var(--hair)}
#nba .np{font-size:15.5px;font-weight:600;color:var(--cu-lbl);letter-spacing:-.01em}
#nba .nm{font-size:12px;color:var(--cu-lbl2);margin-top:2px}
#nba .nm .k{font-size:10px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--cu-lbl3)}
#nba .nx{text-align:right;font-variant-numeric:tabular-nums}
#nba .nl{font-size:15.5px;font-weight:700;color:var(--cu-lbl)}
#nba .nl .o{font-weight:600;color:var(--cu-lbl2);margin-left:6px}
#nba .nn{font-size:12px;color:var(--cu-lbl3);margin-top:2px}
#nba .up{color:var(--cu-grn)} #nba .dn{color:var(--cu-red)} #nba .q{color:var(--cu-yel)}
#nba .nw{font-weight:700} #nba .nw.win{color:var(--cu-grn)} #nba .nw.loss{color:var(--cu-red)}
#nba .noff{margin-top:22px;font-size:12px;color:var(--cu-lbl3);line-height:1.7}
#nba .noff b{color:var(--cu-lbl2);font-weight:600}
#nba .nnone{padding:28px 0;font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;
  color:var(--cu-lbl3)}
</style>"""


def _row(r):
    e = H.escape
    move = ""
    if r["fd"]:
        d = r["fd"]["line"] - r["line"]
        cls = "up" if d > 0 else "dn" if d < 0 else ""
        tag = "TIP" if r["state"] != "upcoming" else "NOW"
        move = (f'<div class="nn">FD {tag} <span class="{cls}">O{r["fd"]["line"]:g}</span>'
                f' {american(r["fd"]["odds"])}</div>')
    res = ""
    if r["result"]:
        res = (f'<div class="nn"><span class="nw {e(r["result"])}">{"W" if r["result"] == "win" else "L"}'
               f'</span> · {r["actual"]:g}</div>')
    elif r["state"] == "live":
        res = '<div class="nn">LIVE</div>'
    q = ' · <span class="q">Q</span>' if r["b_status"] == "Questionable" else ""
    h1 = ' · <span class="k">DAY BEFORE</span>' if r["horizon"] else ""
    return (f'<div class="nr"><div><div class="np">{e(r["b"])}</div>'
            f'<div class="nm"><span class="k">{e(r["stat"])}</span> · {e(r["x"])} out{q} · '
            f'<span class="k">{" · ".join(e(t) for t in r["tiers"])}</span> · {e(r["flagged_mt"])}{h1}</div></div>'
            f'<div class="nx"><div class="nl">O{r["line"]:g}<span class="o">{american(r["odds"])}</span></div>'
            f'{move}{res}</div></div>')


def html(b):
    e = H.escape
    rec = b.get("record") or {}
    parts = [CSS, '<h2>NBA · <span class="nsh">SHADOW · NOT BETS</span></h2>']
    if rec:
        n = rec["closed"]
        beat = f'{rec["beat"]}/{n}' if n else "—"
        parts.append(f'<div class="nrec"><span>FD BEAT CLOSE <b>{beat}</b></span>'
                     f'<span>AS FLAGGED <b>{rec["units"]:+.1f}u</b> · {rec["graded"]}</span>'
                     f'<span><b>{n}</b>/{rec["decision_n"]} TO DECISION</span></div>')
    if not b["slates"]:
        parts.append('<div class="nnone">NO SHADOW FLAGS ON THIS SLATE</div>')
    for s in b["slates"]:
        parts.append(f'<div class="nday">{e(s["label"])}</div>')
        for g in s["games"]:
            parts.append(f'<div class="ng"><span>{e(g["matchup"])}</span><span class="t">{e(g["tip_mt"])} MT</span></div>')
            parts.extend(_row(r) for r in g["rows"])
    if b["retracted"]:
        off = " · ".join(f'<b>{e(r["b"])}</b> {e(r["stat"])} O{r["line"]:g} — {e(r["why"])}'
                         for r in b["retracted"])
        parts.append(f'<div class="noff"><span class="nday" style="margin:0">OFF</span><br>{off}</div>')
    return "".join(parts)


if __name__ == "__main__":
    print(json.dumps(board(), indent=1, default=str))
