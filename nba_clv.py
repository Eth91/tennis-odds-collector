#!/usr/bin/env python3
"""NBA speed scoreboard — did the shadow flags beat the CLOSE? The canonical query for
NBA_SPEED_PREREG.md.

The WNBA record's edge is partly timing: its bets beat the closing line 67% of the time, and
bought at the close the same bets earned +11.5% instead of +20.2% (2026-10-22, from
wnba_clv.sqlite). Every NBA backtest so far priced bets AT the close, which cannot see that.
This reads nba_shadow.sqlite (the flags, first-seen price and time) against nba_lines.quotes
(every price move and pull) and answers, per tier:

  beat the close   the closing main line rose above the flagged line, or stayed and its best
                   over price shortened
  line move        closing line minus flagged line (positive = the market moved toward the bet)
  as flagged ROI   graded result at the flagged price
  at the close ROI the same bets, bought over the closing line at the closing price
  latency          flag time minus the moment the league first published the Out

ONE OPPORTUNITY per (tier, player, stat, game) — its earliest flag — scored by HORIZON: h0 =
flagged on game day (the pre-registered primary test), h1 = flagged the day before on a ruling for
tomorrow's game (amendment 1, its own cell).

THE CLOSE is rebuilt from the change log: per (book, line, side) the last quote at or before
tip; a rung whose last event before tip is a pull (odds NULL) was not offered. The closing main
line is the two-sided rung whose best over is nearest even money — the engine's own rule.

    python nba_clv.py            # the scoreboard
    python nba_clv.py --rows     # one line per flag
"""
from __future__ import annotations

import argparse
import datetime as dt
import random
import sqlite3
import statistics as st
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHADOW = HERE / "nba_shadow.sqlite"
LINES = HERE / "nba_lines.sqlite"
NEWS = HERE / "nba_news.sqlite"              # official reports: confirms news-originated triggers
VOIDED = 0
BOARD_STAT = {"pts": "points", "reb": "rebounds", "ast": "assists"}   # wowy/cold store short keys
PRIMARY_BOOKS = ("fd",)                     # AMENDMENT 4: the primary yardstick is FanDuel alone


def _utc_naive(iso):
    t = dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    if t.tzinfo:
        t = t.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return t.replace(microsecond=0).isoformat()


def close_of(qcon, gid, pid, stat, tip, books=None):
    """(main_line, best_over, n_books) as the board stood at `tip` — any moment: the tip for the
    close, the flag's logged_at for amendment 4's flag-time FanDuel rung — or None if nothing
    two-sided was offered. `books` restricts the board to those books."""
    st_ = {}
    q, args = ("SELECT book, line, side, odds FROM quotes WHERE gid=? AND pid=? AND stat=? "
               "AND seen_at <= ?"), [gid, pid, stat, tip]
    if books:
        q += f" AND book IN ({','.join('?' * len(books))})"
        args += list(books)
    for book, line, side, odds in qcon.execute(q + " ORDER BY seen_at", args):
        st_[(book, round(line, 1), side)] = odds
    live = {k: v for k, v in st_.items() if v is not None}
    lines = defaultdict(lambda: {"over": [], "under": []})
    for (book, line, side), odds in live.items():
        lines[line][side].append(odds)
    best = None
    for line, sides in lines.items():
        if sides["over"] and sides["under"]:
            o = max(sides["over"])
            if best is None or abs(o - 1.9091) < abs(best[1] - 1.9091):
                best = (line, o, len({b for (b, l, _s) in live if l == line}))
    return best


def collect():
    if not SHADOW.exists():
        return []
    sh = sqlite3.connect(f"file:{SHADOW}?mode=ro", uri=True)
    q = sqlite3.connect(f"file:{LINES}?mode=ro", uri=True)
    nw = sqlite3.connect(f"file:{NEWS}?mode=ro", uri=True) if NEWS.exists() else None
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None).isoformat()
    cols = [r[1] for r in sh.execute("PRAGMA table_info(flags)")]
    out = []
    global VOIDED
    VOIDED = 0
    for r in (dict(zip(cols, x)) for x in sh.execute("SELECT * FROM flags")):
        if r.get("void_reason"):                        # amendment 3 (and any later voiding rule)
            VOIDED += 1
            continue
        if not r.get("pid") or not r.get("gtime"):
            continue
        tip = _utc_naive(r["gtime"])
        if tip > now:
            continue                                   # not closed yet
        stat = BOARD_STAT.get(r["stat"], r["stat"])
        c = close_of(q, r["gid"], r["pid"], stat, tip)
        f0 = close_of(q, r["gid"], r["pid"], stat, _utc_naive(r["logged_at"]), books=PRIMARY_BOOKS)
        f1 = close_of(q, r["gid"], r["pid"], stat, tip, books=PRIMARY_BOOKS)
        lat = None
        if r.get("news_at"):
            lat = (dt.datetime.fromisoformat(r["logged_at"])
                   - dt.datetime.fromisoformat(_utc_naive(r["news_at"]))).total_seconds() / 60
        row = dict(r, tip=tip, close=c, fd_flag=f0, fd_close=f1, latency_min=lat)
        # AMENDMENT 2: a news-originated trigger counts only if an official report published
        # before tip lists the absent player Out for that game; otherwise it is an audit row.
        if (r.get("trigger_src") or "report").startswith("news"):
            ok = False
            if nw is not None and r.get("x_pid"):
                for (pub,) in nw.execute("SELECT published_at FROM snapshots WHERE game_date=? "
                                         "AND pid=? AND status='Out'", (r["game_date"], r["x_pid"])):
                    if _utc_naive(pub) <= tip:
                        ok = True
                        break
            row["confirmed"] = ok
        if f0 and f1:                                  # AMENDMENT 4 primary: FanDuel at flag vs tip
            row["fd_move"] = f1[0] - f0[0]
            row["fd_beat"] = f1[0] > f0[0] or (f1[0] == f0[0] and f1[1] < f0[1])
            if r.get("actual") is not None:
                row["fd_u_flag"] = (f0[1] - 1) if r["actual"] > f0[0] else -1.0
                row["fd_u_close"] = (f1[1] - 1) if r["actual"] > f1[0] else -1.0
        if c:
            cl, co, _nb = c
            row["move"] = cl - r["line"]
            row["beat"] = cl > r["line"] or (cl == r["line"] and co < r["odds"])
            if r.get("actual") is not None:
                row["u_flag"] = (r["odds"] - 1) if r["actual"] > r["line"] else -1.0
                row["u_close"] = (co - 1) if r["actual"] > cl else -1.0
        out.append(row)
    # ONE OPPORTUNITY PER (tier, player, stat, game): its EARLIEST flag. A day-before flag and a
    # game-day re-flag at a moved line are the same news, not two bets (prereg amendment 1).
    first = {}
    for row in sorted(out, key=lambda r: r["logged_at"]):
        first.setdefault((row["tier"], row["pid"], row["stat"], row["game_date"]), row)
    return list(first.values())


def _ci_rate(rows, n=4000, seed=7):
    """95% CI of the beat-close rate, resampling GAMES: flags from one game share one piece of
    news and one market, so they are not independent (NBA_SPEED_PREREG.md)."""
    by = defaultdict(list)
    for r in rows:
        by[r["gid"]].append(1.0 if r["beat"] else 0.0)
    gs = list(by.values())
    if len(gs) < 10:
        return None
    rnd = random.Random(seed)
    m = []
    for _ in range(n):
        pick = [x for _ in gs for x in rnd.choice(gs)]
        m.append(sum(pick) / len(pick))
    m.sort()
    return m[int(.025 * n)], m[int(.975 * n)]


def view(r, yardstick):
    """One row under a yardstick. 'FD' (amendment 4, PRIMARY): FanDuel's main rung at the flag's
    logged_at vs at tip. 'FD+DK' (the registered two-book measure, now secondary): the flag's own
    line/price vs the best-over close."""
    if yardstick == "FD":
        ok = bool(r.get("fd_flag") and r.get("fd_close"))
        v = {"close": r["fd_close"] if ok else None, "beat": r.get("fd_beat"), "move": r.get("fd_move")}
        if "fd_u_flag" in r:
            v.update(u_flag=r["fd_u_flag"], u_close=r["fd_u_close"])
    else:
        v = {"close": r.get("close"), "beat": r.get("beat"), "move": r.get("move")}
        if "u_flag" in r:
            v.update(u_flag=r["u_flag"], u_close=r["u_close"])
    return dict(v, gid=r["gid"], latency_min=r.get("latency_min"))


def scoreboard(rows):
    by = defaultdict(list)
    for r in rows:
        cell = ("unconfirmed-news" if r.get("confirmed") is False
                else f"h{r.get('horizon') or 0}")
        for ys in ("FD", "FD+DK"):
            by[f"{r['tier']}/{cell} {ys}"].append(view(r, ys))
    print("one row per opportunity (earliest flag); h0 = flagged on game day (the PRIMARY test),\n"
          "h1 = a ruling for tomorrow's game, flagged the day before (amendment 1, its own cell).\n"
          "unconfirmed-news = triggered by news the official report never confirmed before tip\n"
          "(amendment 2: an audit cell, never in a verdict).\n"
          "FD = FanDuel at flag time vs FanDuel at tip (amendment 4, the PRIMARY yardstick);\n"
          "FD+DK = the flag's best-of-two price vs the best-of-two close (secondary).\n"
          "beat-close CI resamples games (clustered); a CI needs >= 10 games\n"
          f"{'cell':<30}{'closed':>7}{'w/close':>8}{'beat close':>18}{'line move':>10}"
          f"{'graded':>7}{'as flagged':>12}{'at close':>10}{'latency(min)':>13}")
    for tier, rs in sorted(by.items()):
        wc = [r for r in rs if r.get("close")]
        beats = [1.0 if r["beat"] else 0.0 for r in wc]
        ci = _ci_rate(wc)
        g = [r for r in wc if "u_flag" in r]
        lat = [r["latency_min"] for r in rs if r.get("latency_min") is not None]
        bt = (f"{100 * sum(beats) / len(beats):5.1f}%" if beats else "   - ") + \
             (f" [{100 * ci[0]:.0f},{100 * ci[1]:.0f}]" if ci else "")
        print(f"{tier:<30}{len(rs):7d}{len(wc):8d}{bt:>18}"
              f"{(st.mean(r['move'] for r in wc) if wc else 0):+10.2f}{len(g):7d}"
              f"{(100 * sum(r['u_flag'] for r in g) / len(g) if g else 0):+11.1f}%"
              f"{(100 * sum(r['u_close'] for r in g) / len(g) if g else 0):+9.1f}%"
              f"{(st.median(lat) if lat else float('nan')):13.1f}")
    if not rows:
        print("  (no closed shadow flags yet)")
    if VOIDED:
        print(f"  voided flags excluded from every cell: {VOIDED} (see NBA_SPEED_PREREG.md amendments)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", action="store_true")
    a = ap.parse_args()
    rows = collect()
    scoreboard(rows)
    if a.rows:
        for r in sorted(rows, key=lambda r: r["logged_at"]):
            c = r.get("close")
            print(f"  {r['logged_at'][:16]} {r['tier']:<6} {r['b'][:20]:<20} {r['stat']:<8} "
                  f"O{r['line']:<5} @{r['odds']:.2f} -> close "
                  + (f"{c[0]} @{c[1]:.2f} ({'BEAT' if r['beat'] else 'worse'})" if c else "n/a")
                  + (f" · actual {r['actual']:g}" if r.get("actual") is not None else ""))
