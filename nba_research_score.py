#!/usr/bin/env python3
"""Research scorecard for the Pickz NBA prop page: does anything the page shows predict results beyond the price?

Every finished game this season that had prices before tip is replayed as the page would have shown it then:
  prices    each book's board rebuilt from nba_lines.quotes (a CHANGE log — nba_research.replay carries the board
            forward and drops pulled rungs) as of the last change BEFORE tip; graded at FanDuel's main rung, else
            DraftKings'. The fair probability = the books' mean no-vig at that rung (nba_research.fair_at).
  history   the player's box scores strictly before the game date (no peeking).
  ranks     defense-vs-position as this season stood that day, last season final, and the blend the page uses.
  injuries  the official report's latest snapshot published before tip.
Each signal picks a side; it is graded on wins against the fair probability of that side (what the price already
said) and on return at the best closing price. A signal "helps" only when it beats the price by more than 2
standard errors over 100+ picks. Props from the same game are not independent, so 2 SE is a loose bar.

Read-only. Writes docs/nba_research_score.json, which the page shows. Nightly cron on the VM.
    python3 nba_research_score.py --out /home/ubuntu/tennis-odds-collector/docs
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
from collections import defaultdict
from pathlib import Path

import nba_research as R

MIN_N, HELP_Z = 100, 2.0
TOO_FEW = 50


def boards_before_tip(q, gids):
    """{(gid, pid, stat, book): {"open": main (line, o, u) at the first two-sided board, "close": {(line, side):
    odds} as of the last change before tip}} from the change log."""
    out = {}
    if not gids:
        return out
    marks = ",".join("?" * len(gids))
    tips = dict(q.execute(f"SELECT gid, MIN(tip_utc) FROM quotes WHERE gid IN ({marks}) GROUP BY gid", list(gids)))
    rows = q.execute(f"SELECT seen_at, book, gid, pid, stat, line, side, odds FROM quotes WHERE gid IN ({marks}) "
                     f"AND pid IS NOT NULL ORDER BY seen_at", list(gids))
    for t, changed in R.replay(r for r in rows if r[4] in R.MARKETS):
        for k, st_ in changed.items():
            tip = (tips.get(k[0]) or "")[:19]
            if not tip or t >= tip:
                continue
            rec = out.setdefault(k, {"open": None, "close": None})
            if rec["open"] is None:
                rec["open"] = R.main_of(st_)
            rec["close"] = dict(st_)
    return out


def report_before(ncon, date, tip):
    """{team: [pid]} Out / Doubtful in the official report's latest snapshot published before `tip`."""
    out = defaultdict(list)
    if ncon is None:
        return out
    row = ncon.execute("SELECT mark FROM snapshots WHERE game_date=? AND published_at < ? ORDER BY published_at DESC "
                       "LIMIT 1", (date, tip)).fetchone()
    if not row:
        return out
    for team, pid, status in ncon.execute("SELECT team, pid, status FROM snapshots WHERE game_date=? AND mark=?",
                                          (date, row[0])):
        if pid is not None and status in ("Out", "Doubtful"):
            out[team].append(int(pid))
    return out


def grade(lines=None, matchup=None, news=None, season=None):
    """[{gid, date, pid, stat, line, over (bool), fair, books (rung data), signals...}] for every gradable prop."""
    import nba_matchup as MU
    q, ncon = R._ro(lines or R.LINES), R._ro(news or R.NEWS)
    mpath = Path(matchup or MU.DB)
    m = MU.connect(mpath) if mpath.exists() else None
    if q is None or m is None:
        return []
    season = season or R.season_of(dt.date.today().isoformat())
    prev = R.prev_season(season)
    games = {g: (d, h, a) for g, d, h, a in m.execute(
        "SELECT gid, date, home, away FROM games WHERE season=? AND home_pts IS NOT NULL", (season,))}
    boards = boards_before_tip(q, list(games))
    keys = defaultdict(dict)                                  # (gid, pid, stat) -> {book: board}
    for (gid, pid, stat, book), b in boards.items():
        keys[(gid, pid, stat)][book] = b
    box = {(g, p): {"pts": a, "reb": b, "ast": c, "fg3m": d, "team": t} for g, p, a, b, c, d, t in m.execute(
        f"SELECT gid, pid, pts, reb, ast, fg3m, team FROM player_games WHERE gid IN ({','.join('?' * len(games))})",
        list(games))}
    tips = dict(q.execute(f"SELECT gid, MIN(tip_utc) FROM quotes WHERE gid IN ({','.join('?' * len(games))}) "
                          f"GROUP BY gid", list(games)))
    pids = {k[1] for k in keys}
    logs = R.game_logs(m, pids, (prev, season))
    S, S_prev = MU.Season(m, season), MU.Season(m, prev)
    dates = sorted({games[k[0]][0] for k in keys})
    rk = {d: {"cur": R.rank_tables(S, m, d), "blend": R.rank_tables_blend(S, S_prev, m, d)} for d in dates}
    rk_prev = R.rank_tables(S_prev, m, "9999-12-31")
    reports, team_logs = {}, {}
    sched = defaultdict(list)                                # team -> [(date, gid)] finals, both seasons
    for g, d, h, a in m.execute("SELECT gid, date, home, away FROM games WHERE home_pts IS NOT NULL"):
        sched[h].append((d, g)); sched[a].append((d, g))
    for v in sched.values():
        v.sort()
    out = []
    for (gid, pid, stat), bks in sorted(keys.items()):
        date, home, away = games[gid]
        b = box.get((gid, pid))
        if not b:
            continue                                        # did not play: void
        books = {}
        for bk, brd in bks.items():
            if brd["close"]:
                rr = R.rungs_of(brd["close"])
                books[bk] = {"rungs": rr, "main": R.main_line(rr), "open": brd["open"]}
        main_bk = books.get("fd") if (books.get("fd") or {}).get("main") is not None else books.get("dk")
        if not main_bk or main_bk["main"] is None:
            continue
        line = main_bk["main"]
        fair, nb = R.fair_at(books, line)
        val = R.stat_value(b, stat)
        if fair is None or val is None or val == line:
            continue                                        # unpriced, or a push: void
        prior = [dict(zip(R.LOG_COLS, r)) for r in logs.get(pid, []) if r[0] < date]
        vals = [v for v in (R.stat_value(l, stat) for l in prior) if v is not None]
        team = b["team"]
        opp = away if team == home else home

        def win(n):
            w = vals[-n:] if n else [v for l, v in zip(prior, vals) if R.season_of(l["date"]) == season]
            return sum(1 for v in w if v > line), len(w)
        grp = S.group(pid, date) or S_prev.group(pid, "9999-12-31")
        mk = R.MATCHUP_KEY.get(stat)

        def tier(tbl):
            try:
                r_, n_ = tbl["dvp"][grp][mk][opp], tbl["teams"]
            except (KeyError, TypeError):
                return None
            return "soft" if r_ > n_ * 2 / 3 else "tough" if r_ <= n_ / 3 else "mid"
        tip = (tips.get(gid) or "")[:19]
        if (date, tip) not in reports:
            reports[(date, tip)] = report_before(ncon, date, tip + "+00:00" if tip else "9")
        out_ids = [x for x in reports[(date, tip)].get(team, []) if x != pid]
        mates = []
        for x in out_ids:                                    # rotation teammates: >= 10 games, >= 20 min, this team
            if x not in team_logs:
                team_logs[x] = [r for r in R.game_logs(m, [x], (prev, season)).get(x, [])]
            rows = [r for r in team_logs[x] if r[2] == team and r[0] < date]
            if len(rows) >= 10 and sum(r[6] for r in rows) / len(rows) >= 20:
                played = {r[1] for r in rows}
                last5 = [g for d, g in sched[team] if d < date][-R.FRESH_GAMES:]
                mates.append({"played": played, "since": rows[0][0], "fresh": any(g in played for g in last5)})
        wo = None
        if mates:
            w = [v for l, v in zip(prior, vals) if l["team"] == team and l["date"] >= mates[0]["since"]
                 and l["gid"] not in mates[0]["played"]]
            wo = (sum(1 for v in w if v > line), len(w))
        fd_open = (books.get("fd") or {}).get("open")
        out.append({"gid": gid, "date": date, "pid": pid, "stat": stat, "line": line, "over": val > line,
                    "fair": fair, "nbooks": nb, "books": books,
                    "l5": win(5), "l10": win(10), "l20": win(20), "szn": win(0),
                    "tier": {"cur": tier(rk[date]["cur"]), "prev": tier(rk_prev), "blend": tier(rk[date]["blend"])},
                    "move": (books["fd"]["main"] - fd_open[0]) if fd_open and books.get("fd", {}).get("main") is not None
                    else None,
                    "mate_out": bool(mates), "fresh_out": any(x["fresh"] for x in mates), "wo": wo})
    for c in (q, ncon, m):
        if c is not None:
            c.close()
    return out


def best_price(r, side):
    v = R.value_at(r["books"], r["line"], side)
    return v["price"] if v else None


def score(picks, label, rule):
    """picks = [(record, side)] -> the signal's line on the scorecard."""
    n = len(picks)
    row = {"signal": label, "rule": rule, "n": n}
    if not n:
        return dict(row, verdict="no picks yet")
    wins = sum(1 for r, s in picks if r["over"] == (s == "over"))
    implied = sum(r["fair"] if s == "over" else 1 - r["fair"] for r, s in picks) / n
    pay = [((best_price(r, s) or 1) - 1) if r["over"] == (s == "over") else -1 for r, s in picks]
    rate = wins / n
    se = math.sqrt(max(implied * (1 - implied), 1e-9) / n)
    z = (rate - implied) / se
    verdict = ("too few picks" if n < TOO_FEW else "helps" if n >= MIN_N and z >= HELP_Z else
               "hurts" if n >= MIN_N and z <= -HELP_Z else "no edge yet")
    return dict(row, wins=wins, rate=round(rate, 4), implied=round(implied, 4), diff=round(rate - implied, 4),
                z=round(z, 2), roi=round(sum(pay) / n, 4), verdict=verdict)


def z_side(hits_n, fair):
    h, n = hits_n
    z = R.zscore(h, n, fair)
    return None if z is None else ("over" if z >= 1 else "under" if z <= -1 else None)


def scorecard(recs):
    """The page's signals, each graded. Shared rules with the page: nba_research_ui (JS) mirrors these."""
    if not recs:
        return {"props": 0, "signals": []}
    n = len(recs)
    brier = lambda f: round(sum((f(r) - r["over"]) ** 2 for r in recs if f(r) is not None) /
                            max(1, sum(1 for r in recs if f(r) is not None)), 4)
    rate = lambda hn: hn[0] / hn[1] if hn[1] else None
    sig = []
    sig.append(score([(r, z_side(r["l10"], r["fair"])) for r in recs if r["l10"][1] >= 5 and z_side(r["l10"], r["fair"])],
                     "Colored L10 box", "L10 hit rate at least 1 SD from what the price implies (the page's green/red)"))
    sig.append(score([(r, "over" if rate(r["l10"]) >= .7 else "under") for r in recs if r["l10"][1] >= 8 and
                      (rate(r["l10"]) >= .7 or rate(r["l10"]) <= .3)],
                     "Raw 70% L10 (props.cash style)", "L10 hit rate 70%+ one way, ignoring the price"))
    sig.append(score([(r, s) for r in recs for s in [trend_side(r)] if s], "Trends tab", TREND_RULE))
    vals = []
    for r in recs:
        for s in ("over", "under"):
            v = R.value_at(r["books"], r["line"], s)
            if v and v["ev"] > 0:
                vals.append((r, s))
    sig.append(score(vals, "Value > 0", "the best price beats the two books' fair price (positive EV)"))
    for key, lab in (("blend", "DvP (blended, as shown)"), ("cur", "DvP this season only"), ("prev", "DvP last season")):
        sig.append(score([(r, "over" if r["tier"][key] == "soft" else "under") for r in recs
                          if r["tier"][key] in ("soft", "tough")], lab, "soft third → over, tough third → under"))
    sig.append(score([(r, "under" if r["move"] > 0 else "over") for r in recs if r["move"]],
                     "Fade the line move", "the line rose since open → under; fell → over"))
    sig.append(score([(r, "over") for r in recs if r["mate_out"]], "Teammate out → over",
                     "a rotation teammate (20+ min) is Out or Doubtful, however long"))
    sig.append(score([(r, "over") for r in recs if r["fresh_out"]], "Fresh absence → over",
                     f"that teammate played in one of the team's last {R.FRESH_GAMES} games (the badge)"))
    sig.append(score([(r, s) for r in recs if r["wo"] and r["wo"][1] >= 5 for s in [z_side(r["wo"], r["fair"])] if s],
                     "Without-teammate split", "his hit rate without that teammate 1+ SD from the price (5+ games)"))
    return {"props": n, "nights": len({r["date"] for r in recs}), "from": min(r["date"] for r in recs),
            "to": max(r["date"] for r in recs),
            "brier": {"price (no-vig)": brier(lambda r: r["fair"]), "L10 hit rate": brier(lambda r: rate(r["l10"])),
                      "coin flip": brier(lambda r: .5)},
            "over_rate": round(sum(r["over"] for r in recs) / n, 4),
            "fair_over": round(sum(r["fair"] for r in recs) / n, 4), "signals": sig}


TREND_RULE = "L10 and L20 hit rates both 1+ SD from the price, the same way (8+ games each)"


def trend_side(r):
    a, b = z_side(r["l10"], r["fair"]), z_side(r["l20"], r["fair"])
    return a if a and a == b and r["l10"][1] >= 8 and r["l20"][1] >= 8 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.environ.get("NBA_RESEARCH_OUT", str(R.HERE / "docs")))
    a = ap.parse_args()
    sc = scorecard(grade())
    sc["generated_at"] = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / ".nba_research_score.json.tmp"
    tmp.write_text(json.dumps(sc, separators=(",", ":")))
    os.replace(tmp, out / "nba_research_score.json")
    print(f"nba_research_score: {sc['props']} props over {sc.get('nights', 0)} nights -> {out}")
    for s in sc["signals"]:
        print(f"  {s['signal']:32s} n {s['n']:5d}  {s.get('rate', 0):.3f} vs {s.get('implied', 0):.3f}  "
              f"z {s.get('z', 0):+.2f}  roi {s.get('roi', 0):+.3f}  {s['verdict']}")


if __name__ == "__main__":
    main()
