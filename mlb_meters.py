"""Paper METERS for the two structural MLB edges that can't be backtested (tip-only archive):
LAG  — a book posting a main K/outs line off the 2+-book consensus; paper-bet toward consensus
       at the outlier book's posted price. If this prints, it's a stale/slow-book edge.
LU   — posted lineup K% far from the team's season baseline (the WNBA reprice mechanism ported);
       paper-bet the pitcher K side the lineup delta favors, at detection-time best price.
Shadows: NEVER ping, not on the board (ping<->board rule). Graded nightly like compass.
Judge after ~3 weeks on realized W/L + ROI; wire to real pings only if a meter clears +5% ROI.
"""
import datetime as dt
import json
import sqlite3
import time
from collections import defaultdict

from k_live import (DB, FD, FROZEN, _get, _norm, _now, _today_et, batter_rates, slate,
                    team_k, z)

STATS = ("strikeouts", "outs")
GRADE_FIELD = {"strikeouts": "strikeOuts", "outs": "outs"}


def _ensure(con):
    con.execute("""CREATE TABLE IF NOT EXISTS lag_paper (
        player TEXT, game_date TEXT, stat TEXT, book TEXT, side TEXT, line REAL, odds REAL,
        cons_line REAL, n_cons INTEGER, detected_at TEXT,
        result TEXT, actual REAL, pnl REAL, graded_at TEXT, log_date TEXT,
        PRIMARY KEY (player, game_date, stat))""")
    con.execute("""CREATE TABLE IF NOT EXISTS lu_paper (
        pitcher TEXT, game_date TEXT, dz REAL, side TEXT, line REAL, odds REAL, book TEXT,
        detected_at TEXT, result TEXT, actual REAL, pnl REAL, graded_at TEXT, log_date TEXT,
        PRIMARY KEY (pitcher, game_date))""")


def _latest_mains(stat):
    """{norm_player: {book: (line, {side: odds}, collected_at)}} from the freshest
    collection batch per book (self-collected fd_lines, today only)."""
    con = sqlite3.connect(f"file:{FD}?mode=ro", uri=True)
    cut = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=18)).strftime("%Y-%m-%dT%H:%M:%S")
    rows = con.execute(
        "SELECT player, book, line, side, odds, collected_at FROM fd_lines "
        "WHERE sport='mlb' AND stat=? AND collected_at>=?", (stat, cut)).fetchall()
    con.close()
    latest = defaultdict(lambda: defaultdict(dict))
    ts_max = defaultdict(str)
    for p, bk, ln, side, od, ts in rows:
        key = (_norm(p), bk)
        if ts > ts_max[key]:
            ts_max[key] = ts
    for p, bk, ln, side, od, ts in rows:
        key = (_norm(p), bk)
        if ts == ts_max[key]:
            latest[key[0]][bk][(ln, side)] = od
    out = defaultdict(dict)
    for np_, books in latest.items():
        for bk, m in books.items():
            two = defaultdict(dict)
            for (ln, side), od in m.items():
                two[ln][side] = od
            two = {ln: v for ln, v in two.items() if "over" in v and "under" in v}
            if two:
                main = min(two, key=lambda ln: abs(two[ln]["over"] - 1.9))
                out[np_][bk] = (main, two[main], ts_max[(np_, bk)])
    return out


def lag_meter(con, gd, ts):
    new = 0
    for stat in STATS:
        mains = _latest_mains(stat)
        for np_, books in mains.items():
            if len(books) < 3:
                continue
            lns = sorted(v[0] for v in books.values())
            med = lns[len(lns) // 2]
            cons = [bk for bk, v in books.items() if v[0] == med]
            outl = [(bk, v) for bk, v in books.items() if abs(v[0] - med) >= 1.0]
            if len(cons) < 2 or len(outl) != 1:
                continue
            bk, (ln, prices, _) = outl[0]
            side = "under" if ln > med else "over"
            od = prices.get(side)
            if not od or od < 1.4:
                continue
            con.execute("INSERT OR IGNORE INTO lag_paper (player, game_date, stat, book, side, "
                        "line, odds, cons_line, n_cons, detected_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (np_, gd, stat, bk, side, ln, od, med, len(cons), ts))
            new += con.execute("SELECT changes()").fetchone()[0]
    return new


def lu_meter(con, gd, ts):
    """|z(posted-lineup K%) - z(team K%)| >= 1.0 -> paper K bet toward the lineup delta."""
    F = FROZEN
    tk = team_k()
    br = batter_rates()
    mains = _latest_mains("strikeouts")
    new = 0
    for g in slate():
        if g["started"] or len(g["opp_lineup"]) < 9:
            continue
        oppk = tk.get(g["opp_id"])
        rates = [br.get(b) for b in g["opp_lineup"]]
        rates = [r for r in rates if r is not None]
        if oppk is None or len(rates) < 8:
            continue
        lk = sum(rates) / len(rates)
        dz = z(lk, F["lk_mu"], F["lk_sd"]) - z(oppk, F["ok_mu"], F["ok_sd"])
        if abs(dz) < 1.0:
            continue
        side = "over" if dz > 0 else "under"
        best = None
        for bk, (ln, prices, _) in (mains.get(_norm(g["pitcher"])) or {}).items():
            od = prices.get(side)
            if od and (best is None or od > best[1]):
                best = (ln, od, bk)
        if not best:
            continue
        con.execute("INSERT OR IGNORE INTO lu_paper (pitcher, game_date, dz, side, line, odds, "
                    "book, detected_at) VALUES (?,?,?,?,?,?,?,?)",
                    (g["pitcher"], gd, round(dz, 2), side, best[0], best[1], best[2], ts))
        new += con.execute("SELECT changes()").fetchone()[0]
    return new


def grade_meters(con):
    rows = [("lag_paper", "player") + r for r in con.execute(
        "SELECT player, game_date, stat, side, line, odds FROM lag_paper "
        "WHERE result IS NULL AND game_date < ?", (_today_et(),)).fetchall()]
    rows += [("lu_paper", "pitcher", p, gd, "strikeouts", side, ln, od) for p, gd, side, ln, od in
             con.execute("SELECT pitcher, game_date, side, line, odds FROM lu_paper "
                         "WHERE result IS NULL AND game_date < ?", (_today_et(),)).fetchall()]
    ids = {}
    for table, keycol, player, gd, stat, side, line, odds in rows:
        pid = ids.get(player)
        if pid is None:
            d = _get("/people/search", names=player)
            ppl = d.get("people") or []
            pid = ppl[0]["id"] if ppl else 0
            ids[player] = pid
        if not pid:
            continue
        d = _get(f"/people/{pid}/stats", stats="gameLog", group="pitching", season=int(gd[:4]))
        g = None
        for s in (d.get("stats") or [{}])[0].get("splits") or []:
            st_ = s.get("stat") or {}
            if not (st_.get("gamesStarted") or 0) or (st_.get("battersFaced") or 0) < 5:
                continue
            try:
                dd = abs((dt.date.fromisoformat(s.get("date")) - dt.date.fromisoformat(gd)).days)
            except (TypeError, ValueError):
                continue
            if dd <= 1:
                g = (s.get("date"), st_.get(GRADE_FIELD[stat]) or 0)
                break
        if not g:
            continue
        won = (g[1] > line) if side == "over" else (g[1] < line)
        con.execute(f"UPDATE {table} SET result=?, actual=?, pnl=?, graded_at=?, log_date=? "
                    f"WHERE {keycol}=? AND game_date=?" + (" AND stat=?" if table == "lag_paper" else ""),
                    ("W" if won else "L", g[1], round((odds - 1) if won else -1.0, 2), _now(),
                     g[0], player, gd) + ((stat,) if table == "lag_paper" else ()))
        time.sleep(0.1)
    con.commit()


def run():
    con = sqlite3.connect(DB)
    _ensure(con)
    gd, ts = _today_et(), _now()
    nl = lag_meter(con, gd, ts)
    nu = lu_meter(con, gd, ts)
    con.commit()
    grade_meters(con)
    for t in ("lag_paper", "lu_paper"):
        w, l = con.execute(f"SELECT SUM(result='W'), SUM(result='L') FROM {t}").fetchone()
        print(f"meter {t}: +{nl if t == 'lag_paper' else nu} new, record {w or 0}-{l or 0}")
    con.close()


if __name__ == "__main__":
    run()
