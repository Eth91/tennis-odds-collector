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
# static id->abbrev (schedule hydrate omits team abbreviation; ids are always present)
TEAM_AB = {108: "LAA", 109: "AZ", 110: "BAL", 111: "BOS", 112: "CHC", 113: "CIN", 114: "CLE",
           115: "COL", 116: "DET", 117: "HOU", 118: "KC", 119: "LAD", 120: "WSH", 121: "NYM",
           133: "ATH", 134: "PIT", 135: "SD", 136: "SEA", 137: "SF", 138: "STL", 139: "TB",
           140: "TEX", 141: "TOR", 142: "MIN", 143: "PHI", 144: "ATL", 145: "CWS", 146: "MIA",
           147: "NYY", 158: "MIL"}
THR = FROZEN.get("thr", 1.6)
PRICE_CAP = FROZEN.get("price_cap", 2.00)
BK_CACHE = HERE / "k_bk_2026.json"          # batter K rates, refreshed daily
GL_CACHE = HERE / "k_gl_2026.json"          # pitcher gamelogs, refreshed per cycle day
OUTS_F = json.loads((HERE / "outs_compass_frozen.json").read_text())
OB_CACHE = HERE / "outs_bobp_2026.json"     # batter OBP/SLG rates, refreshed daily
OGL_CACHE = HERE / "outs_gl_2026.json"      # pitcher outs/pitches gamelogs, per day
LEASH_CACHE = HERE / "outs_leash_cache.json"  # incremental team starter-outs (gitignored)
LEASH_SEED = HERE / "outs_leash_seed.json"    # committed 2026 bootstrap
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
    for tbl in ("compass", "outs_compass"):
        try:
            c.execute(f"ALTER TABLE {tbl} ADD COLUMN team TEXT")
        except sqlite3.OperationalError:
            pass
    for col in ("fitz REAL", "premium INTEGER DEFAULT 0"):
        try:
            c.execute(f"ALTER TABLE compass ADD COLUMN {col}")
        except sqlite3.OperationalError:
            pass
    for col in ("ladder_ln REAL", "ladder_od REAL", "ladder_result TEXT"):
        try:
            c.execute(f"ALTER TABLE compass ADD COLUMN {col}")
        except sqlite3.OperationalError:
            pass
    for tbl in ("compass", "outs_compass"):
        for col in ("cal_p REAL", "kelly_u REAL", "tier TEXT"):
            try:
                c.execute(f"ALTER TABLE {tbl} ADD COLUMN {col}")
            except sqlite3.OperationalError:
                pass
    try:
        c.execute("ALTER TABLE outs_compass ADD COLUMN kagree INTEGER DEFAULT 0")
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
    c.execute("""CREATE TABLE IF NOT EXISTS outs_compass(
        pitcher TEXT, game_date TEXT, side TEXT, line REAL, odds REAL, book TEXT, score REAL,
        strong INTEGER DEFAULT 0, opp TEXT, flagged_at TEXT, skip TEXT, result TEXT,
        actual INTEGER, pnl REAL, graded_at TEXT, log_date TEXT, pinged INTEGER DEFAULT 0,
        game TEXT, gap REAL, lslg REAL, penfat REAL,
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


def batter_obp():
    """{pid: OBP} + {pid: SLG} season-to-date 2026, cached daily (OUTS-COMPASS)."""
    try:
        j = json.loads(OB_CACHE.read_text())
        if j.get("day") == _today_et():
            return ({int(k): v for k, v in j["obp"].items()},
                    {int(k): v for k, v in j["slg"].items()})
    except (OSError, ValueError):
        pass
    d = _get("/stats", stats="season", group="hitting", season=2026, sportId=1,
             playerPool="All", limit=3000)
    obp, slg = {}, {}
    for s in (d.get("stats") or [{}])[0].get("splits") or []:
        stt = s.get("stat") or {}
        if (stt.get("plateAppearances") or 0) >= 50:
            for key, m in (("obp", obp), ("slg", slg)):
                try:
                    m[s["player"]["id"]] = float(stt.get(key))
                except (TypeError, ValueError):
                    pass
    if obp:
        OB_CACHE.write_text(json.dumps({"day": _today_et(), "obp": obp, "slg": slg}))
    return obp, slg


def team_obp():
    """{team_id: OBP} season-to-date."""
    d = _get("/teams/stats", stats="season", group="hitting", season=2026, sportId=1)
    out = {}
    for t in (d.get("stats") or [{}])[0].get("splits") or []:
        try:
            out[t["team"]["id"]] = float((t.get("stat") or {}).get("obp"))
        except (TypeError, ValueError, KeyError):
            pass
    return out


def r5outs(pid):
    """(ppo, pitch_budget, med_outs) over last-5 2026 starts; None-tuple if <3 starts."""
    try:
        cache = json.loads(OGL_CACHE.read_text())
        if cache.get("day") != _today_et():
            cache = {"day": _today_et()}
    except (OSError, ValueError):
        cache = {"day": _today_et()}
    key = str(pid)
    if key not in cache:
        d = _get(f"/people/{pid}/stats", stats="gameLog", group="pitching", season=2026)
        rows = [[s["stat"].get("outs") or 0, s["stat"].get("numberOfPitches") or 0]
                for s in (d.get("stats") or [{}])[0].get("splits") or []
                if (s["stat"].get("gamesStarted") or 0) and (s["stat"].get("battersFaced") or 0) >= 5]
        cache[key] = rows
        OGL_CACHE.write_text(json.dumps(cache))
    g5 = cache.get(key) or []
    g5 = g5[-5:]
    if len(g5) < 3:
        return None, None, None
    outs = sorted(o for o, _ in g5)
    med = outs[len(outs) // 2] if len(outs) % 2 else (outs[len(outs) // 2 - 1] + outs[len(outs) // 2]) / 2
    pt = [p for _, p in g5 if p > 0]
    tot_o = sum(o for o, _ in g5)
    ppo = (sum(p for _, p in g5 if p > 0) / tot_o) if (tot_o and pt) else None
    return ppo, (sum(pt) / len(pt)) if pt else None, med


def team_leash():
    """({team_id: season avg starter-outs}, {team_id: pen outs last 3d}) — incremental daily cache
    seeded from outs_leash_seed.json; processes new FINAL games via boxscore (starter = first
    pitcher listed)."""
    try:
        cache = json.loads(LEASH_CACHE.read_text())
    except (OSError, ValueError):
        cache = json.loads(LEASH_SEED.read_text())
    today = _today_et()
    d0 = dt.date.fromisoformat(cache["last_date"]) + dt.timedelta(days=1)
    day = d0
    while day.isoformat() < today:
        ds = day.isoformat()
        sched = _get("/schedule", sportId=1, date=ds)
        done = True
        for dd in sched.get("dates") or []:
            for g in dd.get("games") or []:
                if (g.get("status") or {}).get("abstractGameState") != "Final":
                    if g.get("gameType") == "R":
                        done = False
                    continue
                if g.get("gameType") != "R":
                    continue
                bx = _get(f"/game/{g['gamePk']}/boxscore")
                for side in ("home", "away"):
                    t = (bx.get("teams") or {}).get(side) or {}
                    tid = str(((t.get("team") or {}).get("id")) or "")
                    sp = (t.get("pitchers") or [None])[0]
                    if not tid or not sp:
                        continue
                    stt = ((t.get("players") or {}).get(f"ID{sp}") or {}).get("stats", {}).get("pitching", {})
                    spo = stt.get("outs")
                    if spo is None:
                        continue
                    rec = cache["teams"].setdefault(tid, {"s": 0, "n": 0})
                    rec["s"] += spo
                    rec["n"] += 1
                    r = cache["recent"].setdefault(tid, [])
                    r.append([ds, spo])
                    cache["recent"][tid] = r[-10:]
        if not done:
            break
        cache["last_date"] = ds
        day += dt.timedelta(days=1)
    try:
        LEASH_CACHE.write_text(json.dumps(cache))
    except OSError as e:
        print(f"leash cache write failed: {e}")
    leash = {int(t): v["s"] / v["n"] for t, v in cache["teams"].items() if v["n"] >= 20}
    cut = (dt.date.fromisoformat(today) - dt.timedelta(days=3)).isoformat()
    pen = {int(t): sum(max(0, 27 - o) for ds, o in v if cut <= ds < today)
           for t, v in cache.get("recent", {}).items()}
    return leash, pen


ARSENAL_CACHE = HERE / "arsenal_live.json"   # weekly-cached Savant tables (gitignored)


def arsenal_maps():
    """({pitcher_pid: {pitch_type: usage_frac}}, {batter_pid: {pitch_type: k_percent}}) —
    season-to-date Savant pitch-arsenal tables, 7-day disk cache, plain csv (no pandas: the
    VM is memory-tight). OOS-validated 2026-07-26: the K fit-gate beat baseline ROI in BOTH
    held-out years (+22.8/+18.9 vs +12.4/+15.3)."""
    try:
        j = json.loads(ARSENAL_CACHE.read_text())
        if (dt.date.today() - dt.date.fromisoformat(j["day"])).days < 7:
            return ({int(k): v for k, v in j["p"].items()},
                    {int(k): v for k, v in j["b"].items()})
    except (OSError, ValueError, KeyError):
        pass
    import csv
    import io
    pmap, bmap = {}, {}
    for typ, m, col in (("pitcher", pmap, "pitch_usage"), ("batter", bmap, "k_percent")):
        try:
            r = requests.get("https://baseballsavant.mlb.com/leaderboard/pitch-arsenal-stats",
                             params={"type": typ, "pitchType": "", "year": 2026, "team": "",
                                     "min": 25, "csv": "true"}, timeout=60)
            r.raise_for_status()
            # utf-8-sig: Savant's CSV leads with a BOM *before* the first quoted header, which
            # breaks csv quoting and shifts every fieldname by one (player_id -> team string).
            for row in csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))):
                try:
                    pid = int(row["player_id"])
                    v = float(row[col])
                    m.setdefault(pid, {})[row["pitch_type"]] = (v / 100.0 if typ == "pitcher" else v)
                except (KeyError, TypeError, ValueError):
                    continue
        except requests.RequestException as e:
            print(f"arsenal fetch failed ({typ}): {str(e)[:60]}")
            return {}, {}
    if pmap:
        ARSENAL_CACHE.write_text(json.dumps(
            {"day": dt.date.today().isoformat(), "p": pmap, "b": bmap}))
    return pmap, bmap


def arsenal_fit(pmap, bmap, pid, lineup_pids):
    """Usage-weighted lineup K rate vs THIS pitcher's arsenal; None if <60% usage covered."""
    use = pmap.get(pid)
    if not use or not lineup_pids:
        return None
    cov = 0.0
    fit = 0.0
    for pt, u in use.items():
        vals = [bmap[b][pt] for b in lineup_pids if b in bmap and pt in bmap[b]]
        if len(vals) >= 5:
            fit += u * (sum(vals) / len(vals))
            cov += u
    return (fit / cov) if cov >= 0.6 else None


VELO_CACHE = HERE / "velo_live.json"


def velo_trend(pid):
    """vd_l2p10: mean FF/SI velo of last-2 starts minus mean of last-10 (as-of, current season).
    OOS-validated 2026-07-26 (+vd w0.25 at S>=2.0 beat baseline hit% in ALL 4 years — the ONLY
    survivor of the exhaustive statcast sweep; clean by construction, no season-table lookahead).
    Per-pitcher Savant statcast CSV, 20h disk cache, stream-parsed (VM is memory-tight).
    None (term contributes 0, matching the backtest) if <4 velo starts or fetch fails."""
    try:
        cache = json.loads(VELO_CACHE.read_text())
    except (OSError, ValueError):
        cache = {}
    ent = cache.get(str(pid))
    now = dt.datetime.now(dt.timezone.utc)
    if not ent or (now - dt.datetime.fromisoformat(ent["at"])).total_seconds() > 20 * 3600:
        yr = int(_today_et()[:4])
        url = ("https://baseballsavant.mlb.com/statcast_search/csv?all=true&hfGT=R%7C"
               f"&hfSea={yr}%7C&player_type=pitcher&pitchers_lookup%5B%5D={pid}"
               "&min_pitches=0&min_results=0&group_by=name&sort_col=pitches"
               "&sort_order=desc&min_abs=0&type=details")
        try:
            import csv
            r = requests.get(url, timeout=90, stream=True)
            r.raise_for_status()
            g = {}
            rd = csv.reader(line.decode("utf-8-sig") for line in r.iter_lines())
            hdr = next(rd, None) or []
            try:
                i_pt, i_gd, i_v = (hdr.index("pitch_type"), hdr.index("game_date"),
                                   hdr.index("release_speed"))
            except ValueError:
                print(f"velo fetch: bad header for {pid}")
                return None
            for row in rd:
                gd_ = row[i_gd]
                a = g.setdefault(gd_, [0, 0, 0.0])
                a[0] += 1
                if row[i_pt] in ("FF", "SI") and row[i_v]:
                    a[1] += 1
                    a[2] += float(row[i_v])
            ent = {"at": now.isoformat(), "g": g}
            cache[str(pid)] = ent
            VELO_CACHE.write_text(json.dumps(cache))
        except (requests.RequestException, ValueError, IndexError) as e:
            print(f"velo fetch failed ({pid}): {str(e)[:60]}")
            return ent and None
    starts = sorted((gd_, a[2] / a[1] if a[1] else None)
                    for gd_, a in ent["g"].items() if a[0] >= 40)
    starts = [s for s in starts if s[0] < _today_et()]
    if len(starts) < 2 or starts[-1][1] is None or starts[-2][1] is None:
        return None
    velos = [v for _, v in starts[-10:] if v is not None]
    if len(velos) < 4:
        return None
    return (starts[-1][1] + starts[-2][1]) / 2 - sum(velos) / len(velos)


def slate():
    """Today's games with probables + POSTED lineups: [{pitcher, pid, opp_lineup_pids, home_team,
    start_iso, started}]. Lineup required — no fallback (matches the validated OOS)."""
    d = _get("/schedule", sportId=1, date=_today_et(), hydrate="probablePitcher,lineups")
    out = []
    for day in d.get("dates") or []:
        for g in day.get("games") or []:
            state = (g.get("status") or {}).get("abstractGameState")
            lu = g.get("lineups") or {}
            bx = None  # lazy pre-game boxscore fetch (schedule hydrate is empty until ~start)
            home_team = g["teams"]["home"]["team"]["name"]
            for side_lbl, opp_lbl in (("home", "away"), ("away", "home")):
                pp = (g["teams"][side_lbl].get("probablePitcher") or {})
                opp_lu = [p.get("id") for p in (lu.get(f"{opp_lbl}Players") or [])]
                if len(opp_lu) < 9 and state == "Preview":
                    if bx is None:
                        bx = _get(f"/game/{g['gamePk']}/boxscore") or {}
                    order = ((bx.get("teams") or {}).get(opp_lbl) or {}).get("battingOrder") or []
                    if len(order) >= 9:
                        opp_lu = [int(x) for x in order]
                if not pp.get("id"):
                    continue
                out.append({"pitcher": pp.get("fullName"), "pid": pp["id"],
                            "opp_lineup": opp_lu[:9],
                            "team_id": g["teams"][side_lbl]["team"]["id"],
                            "team_ab": TEAM_AB.get(g["teams"][side_lbl]["team"]["id"], ""),
                            "opp_id": g["teams"][opp_lbl]["team"]["id"],
                            "opp_name": TEAM_AB.get(g["teams"][opp_lbl]["team"]["id"]) or
                                        g["teams"][opp_lbl]["team"]["name"],
                            "home_team": home_team, "start": g.get("gameDate"),
                            "started": state != "Preview"})
    return out


def k_lines(stat="strikeouts"):
    """{pitcher_name: {book: {line: {side: odds}}}} — freshest 18h quotes for one stat, all 3 books."""
    if not FD.exists():
        return {}
    con = sqlite3.connect(f"file:{FD}?mode=ro", uri=True)
    rows = con.execute("SELECT book, player, line, side, odds, collected_at FROM fd_lines "
                       "WHERE sport='mlb' AND stat=? "
                       "AND collected_at > datetime('now','-18 hours')", (stat,)).fetchall()
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


K_DAY_SCORES = {}   # (pitcher, gd) -> signed K score for ALL gated candidates (not just flags)


def cal_p(frozen, absS, cap):
    """Calibrated win prob from frozen isotonic knots (piecewise-linear interp, clipped).
    Validated 2026-07-26: ordering transfers OOS both models; magnitude clipped (K .64, OUTS .66)
    because sandbox top-bucket rates don't transfer (pred 78% -> actual 64.6%)."""
    kn = frozen.get("cal")
    if not kn or not kn.get("x"):
        return None
    xs, ys = kn["x"], kn["y"]
    if absS <= xs[0]:
        p = ys[0]
    elif absS >= xs[-1]:
        p = ys[-1]
    else:
        import bisect
        i = bisect.bisect_right(xs, absS)
        x0, x1, y0, y1 = xs[i - 1], xs[i], ys[i - 1], ys[i]
        p = y0 + (y1 - y0) * ((absS - x0) / (x1 - x0)) if x1 > x0 else y0
    return min(cap, max(0.40, p))


def stake_tier(p, price):
    """(suggested units, tier) — quarter-Kelly on 100u nominal bank, capped 2u.
    Tiers: S >=1.5u, A >=0.9, B >=0.5, C below (still a flag; smallest ball)."""
    if p is None:
        return None, None
    b = price - 1
    if b <= 0:
        return None, None
    f = (p * b - (1 - p)) / b
    u = min(2.0, max(0.0, f * 0.25 * 100))
    return round(u, 2) if u > 0 else 0.25, None


def tier_of(is_premium, cp, price):
    """Quality-family tiers (2026-07-26 recut — validated components only, no re-tuning):
    S = OOS-validated premium family · A = calibrated edge >= 6pts · B = thin positive edge ·
    C = price beat the calibration (direction liked, number gone). Era check: S tops every era
    (62.5/66.5/73.8% hit, best ROI throughout)."""
    if is_premium:
        return "S"
    if cp is None:
        return "B"
    edge = cp * price - 1
    return "A" if edge >= 0.06 else ("B" if edge > 0 else "C")


def flag(con):
    F = FROZEN
    tk = team_k()
    br = batter_rates()
    lines = k_lines()
    pmap, bmap = arsenal_maps()
    ts = _now()
    gd = _today_et()
    topic = None
    import os
    topic = os.environ.get("NTFY_TOPIC")
    new = 0
    fn = {"pre": 0, "lu": 0, "ok": 0, "smax": 0.0}
    for g in slate():
        if g["started"]:
            continue
        fn["pre"] += 1
        if len(g["opp_lineup"]) >= 9:
            fn["lu"] += 1
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
        fn["ok"] += 1
        lk = sum(rates) / len(rates)
        S = (F["kw"] * z(oppk, F["ok_mu"], F["ok_sd"])
             + (1 - F["kw"]) * z(lk, F["lk_mu"], F["lk_sd"])
             - F["rw"] * z(rk, F["rk_mu"], F["rk_sd"]))
        pf = F["park"].get(g["home_team"])
        if pf is not None:
            S += F["pw"] * z(pf, F["park_mu"], F["park_sd"])
        # velo-trend term (frozen sandbox norm; None -> 0, exactly as backtested)
        if F.get("vd_w"):
            vd = velo_trend(g["pid"])
            if vd is not None:
                S += F["vd_w"] * z(vd, F["vd_mu"], F["vd_sd"])
        K_DAY_SCORES[(g["pitcher"], gd)] = S       # signed; flag_outs reads for the ★★ tag
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
        cp = cal_p(F, abs(S), 0.64)
        su, _ = stake_tier(cp, od)
        # ★ PREMIUM tier (OOS-validated 2026-07-26, beat baseline BOTH held-out years):
        # S>=2.0 AND arsenal fit aligned >=1z. Additive tag — the base record is unchanged.
        # (Must precede the LADDER block, which reads it — was previously below it, so the
        # ladder saw the PREVIOUS candidate's premium, or NameError'd on the first sub-2.0 over.)
        ft = arsenal_fit(pmap, bmap, g["pid"], g["opp_lineup"])
        fitz = None
        if ft is not None and F.get("fit_sd"):
            fitz = (ft - F["fit_mu"]) / F["fit_sd"]
        # fit bar 1.0 -> 0.75 (2026-07-26 widening grid: sandbox hit -0.4pt, '26 70.6%,
        # +~36% volume; S>=2.0 depth is load-bearing — every S-relaxation loses 5pts in 2023)
        premium = 1 if (abs(S) >= 2.0 and fitz is not None
                        and ((fitz >= 0.75 and side == "over")
                             or (fitz <= -0.75 and side == "under"))) else 0
        # LADDER tier (2026-07-26, the 70% challenge winner, 6/6 cells both eras): deep OVER
        # flags (S>=2.0 or *AR premium) also quote the 1-rung-down over at the posted alt price —
        # sandbox 77-79% hit / +2.6-6.6% ROI, OOS 81-85% / +10-15%. Overs only (alt Ks are
        # over-only ladders); logged in ladder_* cols, own record on the board.
        lad_ln = lad_od = None
        if side == "over" and (abs(S) >= 2.0 or premium):
            for bk2 in BOOKS:
                for l2, v2 in ((lines.get(_norm(g["pitcher"])) or {}).get(bk2) or {}).items():
                    if l2 == ln - 1 and "over" in v2:
                        if lad_od is None or v2["over"] > lad_od:
                            lad_ln, lad_od = l2, v2["over"]
        tier = tier_of(premium or abs(S) >= 2.4, cp, od)
        con.execute("INSERT INTO compass (pitcher, game_date, side, line, odds, book, score, opp, "
                    "flagged_at, skip, game, team, fitz, premium, cal_p, kelly_u, tier, "
                    "ladder_ln, ladder_od) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (g["pitcher"], gd, side, ln, od, bk, round(abs(S), 2), g["opp_name"], ts, skip,
                     g["home_team"] + "|" + str(g.get("start") or ""), g.get("team_ab") or "",
                     round(fitz, 2) if fitz is not None else None, premium,
                     round(cp, 3) if cp else None, su, tier, lad_ln, lad_od))
        new += 1
        if not skip and topic:
            am = f"+{round((od-1)*100)}" if od >= 2 else f"-{round(100/(od-1))}"
            lad = ""
            if lad_od:
                lam = (f"+{round((lad_od-1)*100)}" if lad_od >= 2
                       else f"-{round(100/(lad_od-1))}")
                lad = f" | LDR O{lad_ln:g} {lam}"
            txt = (f"🚨 ⚾K [{tier or '-'}] {g['opp_name']} {g['pitcher']} "
                   f"{'O' if side == 'over' else 'U'}{ln:g}K {am} {bk.upper()} "
                   f"{su or 0.25}u{' ★AR' if premium else ''}{lad}")
            try:
                requests.post(f"https://ntfy.sh/{topic}", data=txt.encode(),
                              params={"title": "Pickz", "priority": "high"}, timeout=15
                              ).raise_for_status()
                con.execute("UPDATE compass SET pinged=1 WHERE pitcher=? AND game_date=?",
                            (g["pitcher"], gd))
            except requests.RequestException as e:
                print(f"ping failed: {str(e)[:60]}")
    con.commit()
    print(f"funnel pre={fn['pre']} lineup={fn['lu']} gates={fn['ok']} new={new}")


def flag_outs(con):
    """OUTS-COMPASS v5: S = -tw*z(OBP blend) - pw*z(ppo) + lw*z(team leash) + bw*z(pitch budget).
    Rung rule: no unders at line<=15.5 (skip='rung_cap'). Price>=2.00 -> skip='price_cap'.
    strong = |S|>=1.30. Shadow cols gap/lslg/penfat observe only."""
    F = OUTS_F
    tobp = team_obp()
    bobp, bslg = batter_obp()
    leash, pen = team_leash()
    lines = k_lines(stat="outs")
    ts = _now()
    gd = _today_et()
    import os
    topic = os.environ.get("NTFY_TOPIC")
    new = 0
    fn = {"pre": 0, "lu": 0, "ok": 0}
    for g in slate():
        if g["started"]:
            continue
        fn["pre"] += 1
        if len(g["opp_lineup"]) >= 9:
            fn["lu"] += 1
        if con.execute("SELECT 1 FROM outs_compass WHERE pitcher=? AND game_date=?",
                       (g["pitcher"], gd)).fetchone():
            continue
        oobp = tobp.get(g["opp_id"])
        obs = [bobp.get(b) for b in g["opp_lineup"]]
        obs = [x for x in obs if x is not None]
        ppo, budget, med = r5outs(g["pid"])
        le = leash.get(g["team_id"])
        if oobp is None or len(obs) < 6 or ppo is None or budget is None or le is None:
            continue
        fn["ok"] += 1
        lobp = sum(obs) / len(obs)
        ot = (1 - F["lblend"]) * z(oobp, F["ob_mu"], F["ob_sd"]) \
            + F["lblend"] * z(lobp, F["lo_mu"], F["lo_sd"])
        S = (-F["tw"] * ot - F["pw"] * z(ppo, F["pp_mu"], F["pp_sd"])
             + F["lw"] * z(le, F["le_mu"], F["le_sd"])
             + F["bw"] * z(budget, F["bu_mu"], F["bu_sd"]))
        side = "over" if S > 0 else "under"
        if abs(S) < F["thr"]:
            continue
        best = raw_best = None
        for bk in BOOKS:
            lls = (lines.get(_norm(g["pitcher"])) or {}).get(bk) or {}
            two = {ln: v for ln, v in lls.items() if "over" in v and "under" in v}
            if not two:
                continue
            main = min(two, key=lambda ln: abs(two[ln]["over"] - 1.9))
            od = two[main].get(side)
            if not od:
                continue
            if raw_best is None or od > raw_best[0]:
                raw_best = (od, main, bk)
            # rung rule applies per book: an under is bettable only at a 16.5+ main line
            if side == "under" and main < F["under_min_line"]:
                continue
            if best is None or od > best[0]:
                best = (od, main, bk)
        if not best and not raw_best:
            continue
        skip = None
        if not best:
            best, skip = raw_best, "rung_cap"
        od, ln, bk = best
        if skip is None and od >= F["price_cap"]:
            skip = "price_cap"
        strong = 1 if abs(S) >= F["strong"] else 0
        cp = cal_p(F, abs(S), 0.66)
        su, _ = stake_tier(cp, od)
        # ★★ K-AGREEMENT tag (informational shadow — OOS 62-67% hit both years but missed the
        # beat-baseline bar by 0.8pt in 2026; forward data decides a promotion): the K model's
        # signed score for the SAME pitcher points the same way with |Sk| >= 1.0. flag() runs
        # first in the cycle and stashes every gated candidate's score in K_DAY_SCORES.
        ks = K_DAY_SCORES.get((g["pitcher"], gd))
        kagree = 1 if (ks is not None and abs(ks) >= 1.0
                       and ("over" if ks > 0 else "under") == side) else 0
        tier = tier_of(kagree, cp, od)
        sl = [bslg.get(b) for b in g["opp_lineup"]]
        sl = [x for x in sl if x is not None]
        con.execute("INSERT INTO outs_compass (pitcher, game_date, side, line, odds, book, score, "
                    "strong, opp, flagged_at, skip, game, gap, lslg, penfat, team, kagree, "
                    "cal_p, kelly_u, tier) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (g["pitcher"], gd, side, ln, od, bk, round(abs(S), 2), strong, g["opp_name"],
                     ts, skip, g["home_team"] + "|" + str(g.get("start") or ""),
                     (ln - med) if med is not None else None,
                     (sum(sl) / len(sl)) if len(sl) >= 6 else None,
                     pen.get(g["team_id"]), g.get("team_ab") or "", kagree,
                     round(cp, 3) if cp else None, su, tier))
        new += 1
        # PING POLICY (user 2026-07-26, "optimal hit/volume"): outs pings ONLY on ★★K agreement
        # (66.7%/+29% '26; 62-67% both OOS yrs). All other outs flags stay board+tracker only.
        if not skip and kagree and topic:
            am = f"+{round((od-1)*100)}" if od >= 2 else f"-{round(100/(od-1))}"
            txt = (f"🚨 ⚾O [{tier or '-'}] {g['opp_name']} {g['pitcher']} "
                   f"{'O' if side == 'over' else 'U'}{ln:g} {am} {bk.upper()} "
                   f"{su or 0.25}u{' ★' if strong else ''}{' ★★K' if kagree else ''}")
            try:
                requests.post(f"https://ntfy.sh/{topic}", data=txt.encode(),
                              params={"title": "Pickz", "priority": "high"}, timeout=15
                              ).raise_for_status()
                con.execute("UPDATE outs_compass SET pinged=1 WHERE pitcher=? AND game_date=?",
                            (g["pitcher"], gd))
            except requests.RequestException as e:
                print(f"outs ping failed: {str(e)[:60]}")
    con.commit()
    print(f"outs funnel pre={fn['pre']} lineup={fn['lu']} gates={fn['ok']} new={new}")


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
    # PARLAY BAR (2026-07-26, user's insight + sim parlay_sim3.py): legs must BOTH clear S>=1.8.
    # Rolling best-pair stays; the bar kills forced parlays on weak slates (the losing 20% of days).
    # Honest-timing sim: +25.4% pooled vs +19.2% unbarred, better in ALL 4 years, worst yr +10.9%.
    flags = [dict(zip(("pitcher", "side", "line", "odds", "book", "score", "game", "team"), r))
             for r in con.execute("SELECT pitcher, side, line, odds, book, score, game, team "
                                  "FROM compass WHERE game_date=? AND skip IS NULL AND score >= ? "
                                  "ORDER BY score DESC", (gd, FROZEN.get("parlay_bar", 1.8)))]
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


STAT_FIELD = {"compass": "strikeOuts", "outlier": "strikeOuts", "outs_compass": "outs"}


def grade(con):
    rows = []
    for table in ("compass", "outlier", "outs_compass"):
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
                g = (date, st_.get(STAT_FIELD[table]) or 0)
                break
        if not g:
            continue
        won = (g[1] > line) if side == "over" else (g[1] < line)
        pnl = (odds - 1) if won else -1.0
        con.execute(f"UPDATE {table} SET result=?, actual=?, pnl=?, graded_at=?, log_date=? "
                    "WHERE pitcher=? AND game_date=?",
                    ("W" if won else "L", g[1], round(pnl, 2), _now(), g[0], pitcher, gd))
        if table == "compass":
            lrow = con.execute("SELECT ladder_ln FROM compass WHERE pitcher=? AND game_date=?",
                               (pitcher, gd)).fetchone()
            if lrow and lrow[0] is not None:
                con.execute("UPDATE compass SET ladder_result=? WHERE pitcher=? AND game_date=?",
                            ("W" if g[1] > lrow[0] else "L", pitcher, gd))
        time.sleep(0.1)
    con.commit()


def drift_z(con, table):
    """Rolling-60d realized-vs-calibrated z on graded flags (validated 2026-07-26: fires on the
    K ump break a year early, silent on healthy OUTS). Needs cal_p rows -> quiet until ~40 accrue."""
    rows = con.execute(f"SELECT cal_p, result FROM {table} WHERE result IN ('W','L') "
                       "AND skip IS NULL AND cal_p IS NOT NULL "
                       "AND game_date >= date('now', '-60 days')").fetchall()
    if len(rows) < 40:
        return None
    exp = sum(r[0] for r in rows) / len(rows)
    act = sum(1 for r in rows if r[1] == 'W') / len(rows)
    sd = (exp * (1 - exp) / len(rows)) ** 0.5
    return round((act - exp) / sd, 2)


def board(con):
    rec = con.execute("SELECT SUM(result='W'), SUM(result='L'), ROUND(SUM(pnl),1) FROM compass "
                      "WHERE result IN ('W','L') AND skip IS NULL").fetchone()
    flags = [dict(zip(("pitcher", "side", "line", "odds", "book", "score", "opp", "skip", "team",
                       "game", "premium", "tier", "kelly_u", "ladder_ln", "ladder_od"), r))
             for r in con.execute("SELECT pitcher, side, line, odds, book, score, opp, skip, team, "
                                  "game, premium, tier, kelly_u, ladder_ln, ladder_od "
                                  "FROM compass WHERE game_date=? "
                                  "ORDER BY score DESC", (_today_et(),))]
    prem_rec = con.execute("SELECT SUM(result='W'), SUM(result='L'), ROUND(SUM(pnl),1) FROM compass "
                           "WHERE result IN ('W','L') AND skip IS NULL AND premium=1").fetchone()
    tier_recs = {}
    for t_ in ("S", "A", "B", "C"):
        w_ = l_ = 0
        u_ = 0.0
        for tbl_ in ("compass", "outs_compass"):
            r_ = con.execute(f"SELECT SUM(result='W'), SUM(result='L'), COALESCE(SUM(pnl),0) "
                             f"FROM {tbl_} WHERE result IN ('W','L') AND skip IS NULL AND tier=?",
                             (t_,)).fetchone()
            w_ += r_[0] or 0
            l_ += r_[1] or 0
            u_ += r_[2] or 0
        tier_recs[t_] = {"w": w_, "l": l_, "u": round(u_, 1)}
    lad_rec = con.execute("SELECT SUM(ladder_result='W'), SUM(ladder_result='L'), "
                          "ROUND(SUM(CASE WHEN ladder_result='W' THEN ladder_od-1 ELSE -1 END),1) "
                          "FROM compass WHERE ladder_result IN ('W','L')").fetchone()
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
    outs_rec = con.execute("SELECT SUM(result='W'), SUM(result='L'), ROUND(SUM(pnl),1) "
                           "FROM outs_compass WHERE result IN ('W','L') AND skip IS NULL").fetchone()
    outs_sh = con.execute("SELECT SUM(result='W'), SUM(result='L'), ROUND(SUM(pnl),1) "
                          "FROM outs_compass WHERE result IN ('W','L') AND skip IS NOT NULL").fetchone()
    outs_today = [dict(zip(("pitcher", "side", "line", "odds", "book", "score", "strong", "opp",
                            "skip", "team", "game", "kagree", "tier", "kelly_u"), r))
                  for r in con.execute("SELECT pitcher, side, line, odds, book, score, strong, opp, "
                                       "skip, team, game, kagree, tier, kelly_u FROM outs_compass "
                                       "WHERE game_date=? ORDER BY score DESC", (_today_et(),))]
    kag_rec = con.execute("SELECT SUM(result='W'), SUM(result='L'), ROUND(SUM(pnl),1) "
                          "FROM outs_compass WHERE result IN ('W','L') AND skip IS NULL "
                          "AND kagree=1").fetchone()
    dz_k, dz_o = drift_z(con, "compass"), drift_z(con, "outs_compass")
    import os as _os
    topic = _os.environ.get("NTFY_TOPIC")
    for nm, dz in (("K-COMPASS", dz_k), ("OUTS-COMPASS", dz_o)):
        if dz is not None and dz < -2 and topic:
            gate = HERE / "drift_pinged.json"
            try:
                seen = json.loads(gate.read_text())
            except (OSError, ValueError):
                seen = {}
            key = f"{_today_et()}|{nm}"
            if key not in seen:
                try:
                    requests.post(f"https://ntfy.sh/{topic}",
                                  data=f"⚠️ DRIFT ALARM {nm}: 60d realized {dz}σ below calibration "
                                       f"— possible regime break, review before betting".encode(),
                                  params={"title": "Pickz", "priority": "high"}, timeout=15)
                    seen[key] = 1
                    gate.write_text(json.dumps(seen))
                except requests.RequestException:
                    pass
    (HERE / "compass_board.json").write_text(json.dumps(
        {"updated": _now(), "w": rec[0] or 0, "l": rec[1] or 0, "u": rec[2] or 0.0,
         "drift": {"k": dz_k, "outs": dz_o},
         "tiers": tier_recs,
         "shadow": {"w": shadow[0] or 0, "l": shadow[1] or 0, "u": shadow[2] or 0.0},
         "premium": {"w": prem_rec[0] or 0, "l": prem_rec[1] or 0, "u": prem_rec[2] or 0.0},
         "ladder": {"w": lad_rec[0] or 0, "l": lad_rec[1] or 0, "u": lad_rec[2] or 0.0},
         "kagree": {"w": kag_rec[0] or 0, "l": kag_rec[1] or 0, "u": kag_rec[2] or 0.0},
         "today": flags,
         "outs": {"w": outs_rec[0] or 0, "l": outs_rec[1] or 0, "u": outs_rec[2] or 0.0,
                  "shadow": {"w": outs_sh[0] or 0, "l": outs_sh[1] or 0, "u": outs_sh[2] or 0.0},
                  "today": outs_today},
         "outlier": {"w": orec[0] or 0, "l": orec[1] or 0, "u": orec[2] or 0.0,
                     "today": oflags},
         "parlay": {"today": (json.loads(prow[0]) if prow else None),
                    "combo": (prow[1] if prow else None),
                    "frozen": (bool(prow[2]) if prow else False),
                    "w": prec[0] or 0, "l": prec[1] or 0, "u": prec[2] or 0.0}}))


if __name__ == "__main__":
    c = _con()
    flag(c)
    flag_outs(c)
    # flag_outlier(c)  # BENCHED 2026-07-25 (user: K-COMPASS only) — table/grading stay dormant
    build_parlay(c)
    grade(c)
    grade_parlay(c)
    board(c)
    c.close()
    try:
        import mlb_meters
        mlb_meters.run()
    except Exception as e:  # meters are shadows — must never break the flagger
        print("meters skipped:", str(e)[:80])
    print("k_live cycle done", _now())
