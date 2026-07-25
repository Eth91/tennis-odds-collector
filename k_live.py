#!/usr/bin/env python3
"""K-COMPASS v4-ABS — LIVE paper tracker. Runs on the VM (systemd timer, ~10 min) because that's
where the DK/BetMGM lines live (Actions is IP-blocked — the Rodriguez/Sugano lesson).

Spec (frozen, twice-OOS-validated; constants in k_compass_frozen.json):
  S = .5·z(team K% season-to-date) + .5·z(day-of lineup K%) − .6·z(pitcher recent-5 K) + .35·z(park)
  no ump, no catcher (ABS era) · |S| >= 1.6 · one bet per pitcher-game · best of fd/dk/betmgm
  price >= 2.00 -> shadow-skipped (logged, never pinged/counted) · lineup must be POSTED (no fallback)

Own DB (k_compass.sqlite) — deliberately separate from k_paper.sqlite so the Actions grader and this
VM writer never fight over one file. Flags freeze line/odds at first sight; grading claims each
gamelog game once via log_date (the Kay-bug lesson). Pings + board (compass_board.json) + record all
read from the same table — ping<->board coherent by construction.
    python3 k_live.py            # one cycle: flag + grade + board + pings
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import time
from pathlib import Path

import requests
import unicodedata

def _norm(s):
    return unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode().lower().strip()

HERE = Path(__file__).resolve().parent
DB = HERE / "k_compass.sqlite"
FD = HERE / "fanduel_props.sqlite"
FROZEN = json.loads((HERE / "k_compass_frozen.json").read_text())
API = "https://statsapi.mlb.com/api/v1"
BOOKS = ("fd", "dk", "betmgm")
THR = FROZEN.get("thr", 1.6)
PRICE_CAP = FROZEN.get("price_cap", 2.00)
BK_CACHE = HERE / "k_bk_2026.json"          # batter K rates, refreshed daily
GL_CACHE = HERE / "k_gl_2026.json"          # pitcher gamelogs, refreshed per cycle day
ET = None
try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:
    pass


def _get(path, **params):
    for i in range(3):
        try:
            r = requests.get(f"{API}{path}", params=params, timeout=30)
            if r.status_code == 200:
                return r.json()
        except requests.RequestException:
            pass
        time.sleep(1 + i)
    return {}


def _now():
    return dt.datetime.utcnow().replace(microsecond=0).isoformat()


def _today_et():
    n = dt.datetime.now(ET) if ET else dt.datetime.utcnow()
    return n.date().isoformat()


def _con():
    c = sqlite3.connect(DB)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=60000")
    c.execute("""CREATE TABLE IF NOT EXISTS compass(
        pitcher TEXT, game_date TEXT, side TEXT, line REAL, odds REAL, book TEXT, score REAL,
        opp TEXT, flagged_at TEXT, skip TEXT, result TEXT, actual INTEGER, pnl REAL,
        graded_at TEXT, log_date TEXT, pinged INTEGER DEFAULT 0,
        PRIMARY KEY(pitcher, game_date))""")
    try:
        c.execute("ALTER TABLE compass ADD COLUMN game TEXT")
    except sqlite3.OperationalError:
        pass
    c.execute("""CREATE TABLE IF NOT EXISTS parlay(
        game_date TEXT PRIMARY KEY, legs TEXT, combo REAL, frozen INTEGER DEFAULT 0,
        result TEXT, pnl REAL, graded_at TEXT, pinged INTEGER DEFAULT 0)""")
    c.execute("""CREATE TABLE IF NOT EXISTS outlier(
        pitcher TEXT, game_date TEXT, side TEXT, line REAL, odds REAL, book TEXT, edge REAL,
        opp TEXT, flagged_at TEXT, result TEXT, actual INTEGER, pnl REAL, graded_at TEXT,
        log_date TEXT, pinged INTEGER DEFAULT 0,
        PRIMARY KEY(pitcher, game_date))""")
    return c


def batter_rates():
    """{pid: K%} season-to-date 2026, cached daily."""
    try:
        j = json.loads(BK_CACHE.read_text())
        if j.get("day") == _today_et():
            return {int(k): v for k, v in j["rates"].items()}
    except (OSError, ValueError):
        pass
    d = _get("/stats", stats="season", group="hitting", season=2026, sportId=1,
             playerPool="All", limit=3000)
    rates = {}
    for s in (d.get("stats") or [{}])[0].get("splits") or []:
        stt = s.get("stat") or {}
        if (stt.get("plateAppearances") or 0) >= 50:
            rates[s["player"]["id"]] = (stt.get("strikeOuts") or 0) / stt["plateAppearances"]
    if rates:
        BK_CACHE.write_text(json.dumps({"day": _today_et(), "rates": rates}))
    return rates


def team_k():
    """{team_id: K%} season-to-date (as-of by construction live)."""
    d = _get("/teams/stats", stats="season", group="hitting", season=2026, sportId=1)
    out = {}
    for t in (d.get("stats") or [{}])[0].get("splits") or []:
        s = t.get("stat") or {}
        pa = s.get("plateAppearances") or 0
        if pa:
            out[t["team"]["id"]] = (s.get("strikeOuts") or 0) / pa
    return out


def r5k(pid):
    """Recent-5 median K from this season's starts (cached per day)."""
    try:
        cache = json.loads(GL_CACHE.read_text())
        if cache.get("day") != _today_et():
            cache = {"day": _today_et()}
    except (OSError, ValueError):
        cache = {"day": _today_et()}
    key = str(pid)
    if key not in cache:
        d = _get(f"/people/{pid}/stats", stats="gameLog", group="pitching", season=2026)
        ks = [s["stat"].get("strikeOuts") or 0
              for s in (d.get("stats") or [{}])[0].get("splits") or []
              if (s["stat"].get("gamesStarted") or 0) and (s["stat"].get("battersFaced") or 0) >= 5]
        cache[key] = ks
        GL_CACHE.write_text(json.dumps(cache))
    ks = cache[key][-5:] if cache.get(key) else []
    if len(ks) < 3:
        return None
    ks = sorted(ks)
    return ks[len(ks) // 2] if len(ks) % 2 else (ks[len(ks) // 2 - 1] + ks[len(ks) // 2]) / 2


def slate():
    """Today's games with probables + POSTED lineups: [{pitcher, pid, opp_lineup_pids, home_team,
    start_iso, started}]. Lineup required — no fallback (matches the validated OOS)."""
    d = _get("/schedule", sportId=1, date=_today_et(), hydrate="probablePitcher,lineups")
    out = []
    for day in d.get("dates") or []:
        for g in day.get("games") or []:
            state = (g.get("status") or {}).get("abstractGameState")
            lu = g.get("lineups") or {}
            home_team = g["teams"]["home"]["team"]["name"]
            for side_lbl, opp_lbl in (("home", "away"), ("away", "home")):
                pp = (g["teams"][side_lbl].get("probablePitcher") or {})
                opp_lu = [p.get("id") for p in (lu.get(f"{opp_lbl}Players") or [])]
                if not pp.get("id"):
                    continue
                out.append({"pitcher": pp.get("fullName"), "pid": pp["id"],
                            "opp_lineup": opp_lu[:9],
                            "opp_id": g["teams"][opp_lbl]["team"]["id"],
                            "opp_name": g["teams"][opp_lbl]["team"].get("abbreviation") or
                                        g["teams"][opp_lbl]["team"]["name"],
                            "home_team": home_team, "start": g.get("gameDate"),
                            "started": state != "Preview"})
    return out


def k_lines():
    """{pitcher_name: {book: {line: {side: odds}}}} — freshest 18h strikeout quotes, all 3 books."""
    if not FD.exists():
        return {}
    con = sqlite3.connect(f"file:{FD}?mode=ro", uri=True)
    rows = con.execute("SELECT book, player, line, side, odds, collected_at FROM fd_lines "
                       "WHERE sport='mlb' AND stat='strikeouts' "
                       "AND collected_at > datetime('now','-18 hours')").fetchall()
    con.close()
    latest = {}
    for bk, pl, ln, sd, od, ca in rows:
        if ln is None or od is None or sd is None:
            continue
        k = (bk or "fd", pl, round(float(ln), 1), sd)
        if k not in latest or ca > latest[k][1]:
            latest[k] = (float(od), ca)
    out = {}
    for (bk, pl, ln, sd), (od, _c) in latest.items():
        out.setdefault(_norm(pl), {}).setdefault(bk, {}).setdefault(ln, {})[sd] = od
    return out


def z(v, mu, sd):
    return (v - mu) / (sd or 1)


def flag(con):
    F = FROZEN
    tk = team_k()
    br = batter_rates()
    lines = k_lines()
    ts = _now()
    gd = _today_et()
    topic = None
    import os
    topic = os.environ.get("NTFY_TOPIC")
    new = 0
    for g in slate():
        if g["started"]:
            continue
        row = con.execute("SELECT 1 FROM compass WHERE pitcher=? AND game_date=?",
                          (g["pitcher"], gd)).fetchone()
        if row:
            continue
        oppk = tk.get(g["opp_id"])
        rates = [br.get(b) for b in g["opp_lineup"]]
        rates = [r for r in rates if r is not None]
        rk = r5k(g["pid"])
        if oppk is None or len(rates) < 6 or rk is None:
            continue
        lk = sum(rates) / len(rates)
        S = (F["kw"] * z(oppk, F["ok_mu"], F["ok_sd"])
             + (1 - F["kw"]) * z(lk, F["lk_mu"], F["lk_sd"])
             - F["rw"] * z(rk, F["rk_mu"], F["rk_sd"]))
        pf = F["park"].get(g["home_team"])
        if pf is not None:
            S += F["pw"] * z(pf, F["park_mu"], F["park_sd"])
        side = "over" if S > 0 else "under"
        if abs(S) < THR:
            continue
        # per-book main line (2-sided nearest even), then best price for our side
        best = None
        for bk in BOOKS:
            lls = (lines.get(_norm(g["pitcher"])) or {}).get(bk) or {}
            two = {ln: v for ln, v in lls.items() if "over" in v and "under" in v}
            if not two:
                continue
            main = min(two, key=lambda ln: abs(two[ln]["over"] - 1.9))
            od = two[main].get(side)
            if od and (best is None or od > best[0]):
                best = (od, main, bk)
        if not best:
            continue
        od, ln, bk = best
        skip = "price_cap" if od >= PRICE_CAP else None
        con.execute("INSERT INTO compass (pitcher, game_date, side, line, odds, book, score, opp, "
                    "flagged_at, skip, game) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (g["pitcher"], gd, side, ln, od, bk, round(abs(S), 2), g["opp_name"], ts, skip,
                     g["home_team"] + "|" + str(g.get("start") or "")))
        new += 1
        if not skip and topic:
            am = f"+{round((od-1)*100)}" if od >= 2 else f"-{round(100/(od-1))}"
            txt = (f"🚨 ⚾K {g['opp_name']} {g['pitcher']} "
                   f"{'O' if side == 'over' else 'U'}{ln:g}K {am} {bk.upper()} S{abs(S):.1f}")
            try:
                requests.post(f"https://ntfy.sh/{topic}", data=txt.encode(),
                              params={"title": "Pickz", "priority": "high"}, timeout=15
                              ).raise_for_status()
                con.execute("UPDATE compass SET pinged=1 WHERE pitcher=? AND game_date=?",
                            (g["pitcher"], gd))
            except requests.RequestException as e:
                print(f"ping failed: {str(e)[:60]}")
    con.commit()
    if new:
        print(f"flagged {new}")


def flag_outlier(con):
    """K price-outlier (holdout +7.3%): at a shared line with >=3 two-sided books, a book whose
    devigged P(side) is >=4pts BELOW the others' mean is underpricing that side -> bet it there.
    Pure market signal: needs probables (not lineups)."""
    import os
    topic = os.environ.get("NTFY_TOPIC")
    lines = k_lines()
    ts = _now()
    gd = _today_et()
    new = 0
    for g in slate():
        if g["started"]:
            continue
        if con.execute("SELECT 1 FROM outlier WHERE pitcher=? AND game_date=?",
                       (g["pitcher"], gd)).fetchone():
            continue
        book_lines = lines.get(_norm(g["pitcher"])) or {}
        best = None                                  # (edge, side, line, odds, book)
        byline = {}
        for bk, lls in book_lines.items():
            for ln, sides in lls.items():
                if "over" in sides and "under" in sides:
                    io, iu = 1 / sides["over"], 1 / sides["under"]
                    byline.setdefault(ln, {})[bk] = (io / (io + iu), sides)
        for ln, probs in byline.items():
            if len(probs) < 3:
                continue
            for bk, (pv, sides) in probs.items():
                om = sum(v for b2, (v, _s) in probs.items() if b2 != bk) / (len(probs) - 1)
                if om - pv >= 0.04:                  # over cheap at bk
                    cand = (om - pv, "over", ln, sides["over"], bk)
                elif pv - om >= 0.04:                # under cheap at bk
                    cand = (pv - om, "under", ln, sides["under"], bk)
                else:
                    continue
                if best is None or cand[0] > best[0]:
                    best = cand
        if not best:
            continue
        edge, side, ln, od, bk = best
        con.execute("INSERT INTO outlier (pitcher, game_date, side, line, odds, book, edge, opp, "
                    "flagged_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (g["pitcher"], gd, side, ln, od, bk, round(edge, 3), g["opp_name"], ts))
        new += 1
        if topic:
            am = f"+{round((od-1)*100)}" if od >= 2 else f"-{round(100/(od-1))}"
            txt = (f"\U0001f6a8 \u26be\U0001f4b0 {g[chr(39)+chr(111)][0:0]}" if 0 else
                   f"\U0001f6a8 \u26be\U0001f4b0 {g['opp_name']} {g['pitcher']} "
                   f"{'O' if side == 'over' else 'U'}{ln:g}K {am} {bk.upper()} +{edge*100:.0f}pt")
            try:
                requests.post(f"https://ntfy.sh/{topic}", data=txt.encode(),
                              params={"title": "Pickz", "priority": "high"}, timeout=15
                              ).raise_for_status()
                con.execute("UPDATE outlier SET pinged=1 WHERE pitcher=? AND game_date=?",
                            (g["pitcher"], gd))
            except requests.RequestException as e:
                print(f"outlier ping failed: {str(e)[:60]}")
    con.commit()
    if new:
        print(f"outlier flagged {new}")


def build_parlay(con):
    """Daily 2-leg parlay = top-2 scores from DIFFERENT games (validated 40-54% hit, +20-65% ROI/yr).
    Provisional while flags accumulate; FROZEN (and pinged once) when the earliest leg's game is
    <=45 min out — the last practical bet window, closest to the backtest's end-of-day top-2."""
    import os
    gd = _today_et()
    row = con.execute("SELECT frozen FROM parlay WHERE game_date=?", (gd,)).fetchone()
    if row and row[0]:
        return
    flags = [dict(zip(("pitcher", "side", "line", "odds", "book", "score", "game"), r))
             for r in con.execute("SELECT pitcher, side, line, odds, book, score, game FROM compass "
                                  "WHERE game_date=? AND skip IS NULL ORDER BY score DESC", (gd,))]
    pick, games = [], set()
    now = dt.datetime.now(dt.timezone.utc)
    for f in flags:
        gkey, _, start = (f["game"] or "||").partition("|")
        try:
            st_dt = dt.datetime.fromisoformat((start or "").replace("Z", "+00:00"))
        except ValueError:
            st_dt = None
        if st_dt and st_dt < now:                    # game already started — leg unusable
            continue
        if gkey in games:
            continue
        f["_start"] = st_dt
        pick.append(f); games.add(gkey)
        if len(pick) == 2:
            break
    if len(pick) < 2:
        return
    combo = round(pick[0]["odds"] * pick[1]["odds"], 3)
    legs = json.dumps([{k: v for k, v in p.items() if k != "_start"} for p in pick])
    con.execute("INSERT INTO parlay (game_date, legs, combo) VALUES (?,?,?) "
                "ON CONFLICT(game_date) DO UPDATE SET legs=excluded.legs, combo=excluded.combo "
                "WHERE frozen=0", (gd, legs, combo))
    starts = [p["_start"] for p in pick if p["_start"]]
    if starts and (min(starts) - now).total_seconds() <= 45 * 60:
        con.execute("UPDATE parlay SET frozen=1 WHERE game_date=?", (gd,))
        topic = os.environ.get("NTFY_TOPIC")
        if topic:
            am = f"+{round((combo-1)*100)}"
            leg_s = " + ".join(f"{p['pitcher'].split()[-1]} "
                               f"{'O' if p['side'] == 'over' else 'U'}{p['line']:g}K" for p in pick)
            try:
                requests.post(f"https://ntfy.sh/{topic}",
                              data=f"\U0001f6a8 \u26beK 2-LEG {leg_s} {am}".encode(),
                              params={"title": "Pickz", "priority": "high"}, timeout=15
                              ).raise_for_status()
                con.execute("UPDATE parlay SET pinged=1 WHERE game_date=?", (gd,))
            except requests.RequestException as e:
                print(f"parlay ping failed: {str(e)[:60]}")
    con.commit()


def grade_parlay(con):
    for gd, legs, combo in con.execute("SELECT game_date, legs, combo FROM parlay "
                                       "WHERE frozen=1 AND result IS NULL AND game_date<?",
                                       (_today_et(),)).fetchall():
        res = []
        for p in json.loads(legs):
            r = con.execute("SELECT result FROM compass WHERE pitcher=? AND game_date=?",
                            (p["pitcher"], gd)).fetchone()
            res.append(r[0] if r else None)
        if any(x is None for x in res):
            continue                                  # wait for both legs
        won = all(x == "W" for x in res)
        con.execute("UPDATE parlay SET result=?, pnl=?, graded_at=? WHERE game_date=?",
                    ("W" if won else "L", round((combo - 1) if won else -1.0, 2), _now(), gd))
    con.commit()


def grade(con):
    rows = []
    for table in ("compass", "outlier"):
        rows += [(table,) + r for r in con.execute(
            f"SELECT pitcher, game_date, side, line, odds FROM {table} "
            "WHERE result IS NULL AND game_date < ?", (_today_et(),)).fetchall()]
    if not rows:
        return
    ids = {}
    for table, pitcher, gd, side, line, odds in rows:
        pid = ids.get(pitcher)
        if pid is None:
            d = _get("/people/search", names=pitcher)
            ppl = d.get("people") or []
            pid = ppl[0]["id"] if ppl else None
            ids[pitcher] = pid
        if not pid:
            continue
        d = _get(f"/people/{pid}/stats", stats="gameLog", group="pitching", season=int(gd[:4]))
        claimed = {r[0] for r in con.execute(
            f"SELECT log_date FROM {table} WHERE pitcher=? AND log_date IS NOT NULL", (pitcher,))}
        g = None
        for s in (d.get("stats") or [{}])[0].get("splits") or []:
            st_ = s.get("stat") or {}
            if not (st_.get("gamesStarted") or 0) or (st_.get("battersFaced") or 0) < 5:
                continue
            date = s.get("date")
            if date in claimed:
                continue
            try:
                dd = abs((dt.date.fromisoformat(date) - dt.date.fromisoformat(gd)).days)
            except (TypeError, ValueError):
                continue
            if dd <= 1:
                g = (date, st_.get("strikeOuts") or 0)
                break
        if not g:
            continue
        won = (g[1] > line) if side == "over" else (g[1] < line)
        pnl = (odds - 1) if won else -1.0
        con.execute(f"UPDATE {table} SET result=?, actual=?, pnl=?, graded_at=?, log_date=? "
                    "WHERE pitcher=? AND game_date=?",
                    ("W" if won else "L", g[1], round(pnl, 2), _now(), g[0], pitcher, gd))
        time.sleep(0.1)
    con.commit()


def board(con):
    rec = con.execute("SELECT SUM(result='W'), SUM(result='L'), ROUND(SUM(pnl),1) FROM compass "
                      "WHERE result IN ('W','L') AND skip IS NULL").fetchone()
    flags = [dict(zip(("pitcher", "side", "line", "odds", "book", "score", "opp", "skip"), r))
             for r in con.execute("SELECT pitcher, side, line, odds, book, score, opp, skip "
                                  "FROM compass WHERE game_date=? ORDER BY score DESC",
                                  (_today_et(),))]
    shadow = con.execute("SELECT SUM(result='W'), SUM(result='L'), ROUND(SUM(pnl),1) FROM compass "
                         "WHERE result IN ('W','L') AND skip IS NOT NULL").fetchone()
    prow = con.execute("SELECT legs, combo, frozen FROM parlay WHERE game_date=?",
                       (_today_et(),)).fetchone()
    prec = con.execute("SELECT SUM(result='W'), SUM(result='L'), ROUND(SUM(pnl),1) FROM parlay "
                       "WHERE result IN ('W','L')").fetchone()
    orec = con.execute("SELECT SUM(result='W'), SUM(result='L'), ROUND(SUM(pnl),1) FROM outlier "
                       "WHERE result IN ('W','L')").fetchone()
    oflags = [dict(zip(("pitcher", "side", "line", "odds", "book", "edge", "opp"), r))
              for r in con.execute("SELECT pitcher, side, line, odds, book, edge, opp FROM outlier "
                                   "WHERE game_date=? ORDER BY edge DESC", (_today_et(),))]
    (HERE / "compass_board.json").write_text(json.dumps(
        {"updated": _now(), "w": rec[0] or 0, "l": rec[1] or 0, "u": rec[2] or 0.0,
         "shadow": {"w": shadow[0] or 0, "l": shadow[1] or 0, "u": shadow[2] or 0.0},
         "today": flags,
         "outlier": {"w": orec[0] or 0, "l": orec[1] or 0, "u": orec[2] or 0.0,
                     "today": oflags},
         "parlay": {"today": (json.loads(prow[0]) if prow else None),
                    "combo": (prow[1] if prow else None),
                    "frozen": (bool(prow[2]) if prow else False),
                    "w": prec[0] or 0, "l": prec[1] or 0, "u": prec[2] or 0.0}}))


if __name__ == "__main__":
    c = _con()
    flag(c)
    # flag_outlier(c)  # BENCHED 2026-07-25 (user: K-COMPASS only) — table/grading stay dormant
    build_parlay(c)
    grade(c)
    grade_parlay(c)
    board(c)
    c.close()
    print("k_live cycle done", _now())
