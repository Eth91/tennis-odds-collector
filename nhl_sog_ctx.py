#!/usr/bin/env python3
"""NHL_SOG_PREREG.md amendment 1: the base shots-on-goal model (nhl_sog.py) plus context it leaves out, each group judged
on the held-out seasons: EDGE (last season's), home ice and last change, zone starts by venue, lineup absences, a game
script proxy, last game's line combos (and tonight's opening lines, information only). Mac only.

    python3 nhl_sog_ctx.py --pull     # reports, EDGE and shift charts -> .projdata/nhl_sog_ctx.sqlite (resumable)
    python3 nhl_sog_ctx.py            # the tests
"""
from __future__ import annotations

import argparse
import bisect
import json
import sqlite3
import sys
import time
import urllib.parse
import zlib
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

import nhl_sog as B

CTX = B.HERE / ".projdata" / "nhl_sog_ctx.sqlite"
OUT = B.HERE / ".projdata" / "nhl_sog_ctx_result.json"
WEB = "https://api-web.nhle.com/v1"
EDGE_SEASONS = (2022, 2023, 2024)
EDGE_EPS = ("skater-zone-time", "skater-shot-location-detail", "skater-shot-speed-detail", "skater-skating-speed-detail")
REPORTS = {   # report: (table, {column: field}), keyed (gid, pid) or (gid, team id)
    "skater/puckPossessions": ("pz", {"home": "homeRoad", "ozs": "offensiveZoneStartPct", "dzs": "defensiveZoneStartPct",
                                      "nzs": "neutralZoneStartPct", "toi5": "timeOnIcePerGame5v5"}),
    "skater/summary": ("sx", {"home": "homeRoad", "goals": "goals", "assists": "assists", "points": "points"}),
    "team/summary": ("tx", {"home": "homeRoad", "gf": "goalsFor", "ga": "goalsAgainst", "opp": "opponentTeamAbbrev"}),
}
WORKERS = 4


def write(con, sql, rows, many=True):
    """One write and its commit, retried while another pull holds the lock."""
    for _ in range(60):
        try:
            (con.executemany if many else con.execute)(sql, rows)
            con.commit()
            return
        except sqlite3.OperationalError:
            con.rollback()
            time.sleep(5)
    raise SystemExit("the store stayed locked")


def ddl(con):
    con.execute("PRAGMA journal_mode=WAL")
    for t, cols in REPORTS.values():
        k2 = "team_id" if t == "tx" else "pid"
        con.execute(f"CREATE TABLE IF NOT EXISTS {t} (gid INTEGER, {k2} INTEGER, {', '.join(cols)}, PRIMARY KEY (gid, {k2}))")
    con.execute("CREATE TABLE IF NOT EXISTS done (ref TEXT PRIMARY KEY, n INTEGER)")
    con.execute("CREATE TABLE IF NOT EXISTS edge (season INTEGER, pid INTEGER, ep TEXT, raw BLOB, PRIMARY KEY (season, pid, ep))")
    con.execute("CREATE TABLE IF NOT EXISTS lm (gid INTEGER, pid INTEGER, mate INTEGER, ov_all REAL, ov_p1 REAL, "
                "PRIMARY KEY (gid, pid, mate))")
    con.execute("CREATE TABLE IF NOT EXISTS shifts_done (gid INTEGER PRIMARY KEY, n INTEGER)")


def pull_reports(con):
    have = {r for (r,) in con.execute("SELECT ref FROM done")}
    for s in B.SEASONS:
        for a, b in B.windows(s):
            for rep, (t, cols) in REPORTS.items():
                ref = f"{rep}|{s}|{a}"
                if ref in have:
                    continue
                cay = f'seasonId={s}{s + 1} and gameTypeId>=2 and gameDate>="{a}" and gameDate<"{b}"'
                d = B.fetch(f"{B.REST}/{rep}?isAggregate=false&isGame=true&start=0&limit=-1&cayenneExp=" + urllib.parse.quote(cay))
                rows = d.get("data") or []
                if len(rows) < (d.get("total") or 0) or len(rows) >= 10000:
                    raise SystemExit(f"{ref}: {len(rows)} of {d.get('total')} rows: the window is too wide")
                k2 = "teamId" if t == "tx" else "playerId"
                for attempt in range(20):                 # the other pulls hold the write lock for a while
                    try:
                        con.executemany(f"INSERT OR REPLACE INTO {t} VALUES ({','.join('?' * (2 + len(cols)))})",
                                        [(r["gameId"], r[k2], *[r.get(f) for f in cols.values()]) for r in rows])
                        con.execute("INSERT INTO done VALUES (?, ?)", (ref, len(rows)))
                        con.commit()
                        break
                    except sqlite3.OperationalError:
                        con.rollback()
                        time.sleep(10)
                else:
                    raise SystemExit(f"{ref}: the store stayed locked")
                print(f"{ref}: {len(rows)}", flush=True)
                time.sleep(0.3)


def overlaps(rows):
    """{pid: {mate: (seconds together, seconds together in the first period)}} for teammates, from shift-chart rows."""
    sec = lambda t: int(t.split(":")[0]) * 60 + int(t.split(":")[1]) if t else None
    by = {}
    for r in rows:
        if r.get("typeCode") != 517 or not r.get("startTime") or not r.get("endTime"):
            continue
        a, b = sec(r["startTime"]), sec(r["endTime"])
        if b is None or a is None or b <= a:
            continue
        by.setdefault((r["teamId"], r["period"]), {}).setdefault(r["playerId"], []).append((a, b))
    out = {}
    for (_team, per), pl in by.items():
        ids = sorted(pl)
        n = max(b for v in pl.values() for _a, b in v) + 1
        m = np.zeros((len(ids), n), bool)
        for i, p in enumerate(ids):
            for a, b in pl[p]:
                m[i, a:b] = True
        ov = m.astype(np.int32) @ m.T.astype(np.int32)
        for i, p in enumerate(ids):
            for j, q in enumerate(ids):
                if i != j and ov[i, j]:
                    e = out.setdefault(p, {}).setdefault(q, [0, 0])
                    e[0] += int(ov[i, j])
                    if per == 1:
                        e[1] += int(ov[i, j])
    return out


def shifts_of(gid):
    d = B.fetch(f"{B.REST}/shiftcharts?cayenneExp=gameId={gid}")
    ov = overlaps(d.get("data") or [])
    rows = []
    for p, mates in ov.items():
        for q, (a, f) in sorted(mates.items(), key=lambda x: -x[1][0])[:6]:
            rows.append((gid, p, q, a, f))
    return gid, rows


def pull_shifts(con):
    gids = [g for (g,) in sqlite3.connect(B.STORE).execute("SELECT DISTINCT gid FROM sk ORDER BY gid")]
    have = {g for (g,) in con.execute("SELECT gid FROM shifts_done")}
    todo = [g for g in gids if g not in have]
    print(f"shift charts: {len(todo)} of {len(gids)} games to read", flush=True)
    with ThreadPoolExecutor(WORKERS) as ex:
        for i, (gid, rows) in enumerate(ex.map(shifts_of, todo)):
            write(con, "INSERT OR REPLACE INTO lm VALUES (?,?,?,?,?)", rows)
            write(con, "INSERT OR REPLACE INTO shifts_done VALUES (?, ?)", (gid, len(rows)), many=False)
            if i % 50 == 0:
                print(f"  shifts {i}/{len(todo)}  (game {gid}: {len(rows)} pairs)", flush=True)
    con.commit()


def edge_of(job):
    season, pid, ep = job
    for i in range(3):
        try:
            d = B.fetch(f"{WEB}/edge/{ep}/{pid}/{season}{season + 1}/2", tries=2)
            return season, pid, ep, zlib.compress(json.dumps(d).encode())
        except Exception:
            time.sleep(3 * (i + 1))
    return season, pid, ep, None


def pull_edge(con):
    """Last season's EDGE for everyone who played that season and the next (regular season)."""
    st = sqlite3.connect(B.STORE)
    played = {}
    for gid, pid, pos in st.execute("SELECT gid, pid, pos FROM sk"):
        if pos != "G":
            played.setdefault(gid // 1000000, set()).add(pid)
    have = {(s, p, e) for s, p, e in con.execute("SELECT season, pid, ep FROM edge")}
    jobs = [(s, p, e) for s in EDGE_SEASONS for p in sorted(played.get(s, set()) & played.get(s + 1, set()))
            for e in EDGE_EPS if (s, p, e) not in have]
    print(f"EDGE: {len(jobs)} calls", flush=True)
    with ThreadPoolExecutor(WORKERS) as ex:
        for i, (s, p, e, raw) in enumerate(ex.map(edge_of, jobs)):
            write(con, "INSERT OR REPLACE INTO edge VALUES (?,?,?,?)", (s, p, e, raw), many=False)
            if i % 200 == 0:
                print(f"  edge {i}/{len(jobs)}", flush=True)
    con.commit()


def pull(what):
    con = sqlite3.connect(CTX, timeout=60)
    ddl(con)
    {"reports": pull_reports, "shifts": pull_shifts, "edge": pull_edge}[what](con)
    con.close()


# ---- the features ------------------------------------------------------------------------------------------------
FEATS = {
    "E": ("e_oz_time", "e_oz_start", "e_long", "e_high", "e_speed", "e_bursts", "e_missing"),
    "H": ("home", "home_x_ev", "venue_split"),
    "Z": ("z_ozs", "z_dzs"),
    "L": ("freed_ev", "freed_pp", "layoff"),
    "S": ("margin",),
    "C": ("c_pts", "c_att", "c_missing"),
    "T": ("t_pts", "t_att", "t_promo", "t_missing"),
}
GROUPS = ("E", "H", "Z", "L", "S", "C")
CUM_KEYS = ("att", "hrs", "points", "att_h", "hrs_h", "att_r", "hrs_r", "oz5", "dz5", "t5", "oz5_h", "dz5_h", "t5_h",
            "oz5_r", "dz5_r", "t5_r")
K_VENUE, K_ZONE = 3.0, 100.0                   # hours of ice time; 5v5 minutes


class Cum:
    """Per player and season, prefix sums by date. A query reads his games this season before the date and last season
    worth at most 20 games (the base model's weights)."""

    def __init__(self, rows):
        self.d = {}
        for pid, gl in rows.items():
            per = {}
            for date, season, v in gl:
                ds, vs = per.setdefault(season, ([], []))
                ds.append(date)
                vs.append([v[k] for k in CUM_KEYS])
            self.d[pid] = {s: (ds, np.vstack([np.zeros(len(CUM_KEYS)), np.cumsum(np.array(vs, float), axis=0)]))
                           for s, (ds, vs) in per.items()}

    def get(self, pid, season, date):
        """({key: weighted sum}, weighted games), or None without a game."""
        p = self.d.get(pid)
        if not p:
            return None
        tot, n = np.zeros(len(CUM_KEYS)), 0.0
        if season in p:
            ds, cs = p[season]
            i = bisect.bisect_left(ds, date)
            tot, n = tot + cs[i], n + i
        if season - 1 in p:
            ds, cs = p[season - 1]
            w = min(1.0, B.LAST_AS / len(ds))
            tot, n = tot + w * cs[len(ds)], n + w * len(ds)
        return (dict(zip(CUM_KEYS, tot)), n) if n else None


class TeamGD:
    """A team's goal differential per game, this season before the date and last season worth 20 games."""

    def __init__(self, rows):
        self.v = defaultdict(list)
        for date, season, team, gf, ga in sorted(rows):
            self.v[team].append(((season, date), gf - ga))
        self.idx = {t: [k for k, _ in v] for t, v in self.v.items()}

    def get(self, team, season, date):
        v, idx = self.v.get(team, []), self.idx.get(team, [])
        this = [x for _, x in v[bisect.bisect_left(idx, (season, "")):bisect.bisect_left(idx, (season, date))]]
        last = [x for _, x in v[bisect.bisect_left(idx, (season - 1, "")):bisect.bisect_left(idx, (season, ""))]]
        w = min(1.0, B.LAST_AS / len(last)) if last else 0.0
        n = len(this) + w * len(last)
        return (sum(this) + w * sum(last)) / n if n else None


def edge_feats(e, games_played):
    """Last season's EDGE values, or None without all four endpoints."""
    if not e or len(e) < len(EDGE_EPS) or not games_played:
        return None
    zt = next((z for z in e["skater-zone-time"].get("zoneTimeDetails") or [] if z.get("strengthCode") == "all"), {})
    zs = e["skater-zone-time"].get("zoneStarts") or {}
    tot = {t.get("locationCode"): t.get("sog") or 0 for t in e["skater-shot-location-detail"].get("shotLocationTotals") or []}
    sp = (e["skater-shot-speed-detail"].get("shotSpeedDetails") or {}).get("avgShotSpeed") or {}
    sk = e["skater-skating-speed-detail"].get("skatingSpeedDetails") or {}
    bursts = sum(((sk.get(k) or {}).get("value") or 0) for k in ("burstsOver22", "bursts20To22"))
    al = tot.get("all") or 0
    return {"e_oz_time": zt.get("offensiveZonePctg"), "e_oz_start": zs.get("offensiveZoneStartsPctg"),
            "e_long": tot.get("long", 0) / al if al else None, "e_high": tot.get("high", 0) / al if al else None,
            "e_speed": sp.get("imperial") or None, "e_bursts": bursts / games_played}


def mates_of(rows, team_now, grp, dressed, gmin, gid, key):
    """His linemates in a game: the top two forwards (a forward) or the top defenseman (a defenseman) of his team by
    shift overlap (key 1 = the whole game, 2 = the first period)."""
    want = 2 if grp == "F" else 1
    out = []
    for r in sorted(rows, key=lambda r: -r[key]):
        q = r[0]
        if r[key] > 0 and q in dressed[gid][team_now] and gmin[(gid, q)][2] == grp:
            out.append(q)
        if len(out) == want:
            break
    return out


def quality(mates, cum, season, date):
    """The linemates' points and shot attempts per hour (before the date), averaged; None without one."""
    pts, att = [], []
    for q in mates:
        c = cum.get(q, season, date)
        if c and c[0]["hrs"] > 0:
            pts.append(c[0]["points"] / c[0]["hrs"])
            att.append(c[0]["att"] / c[0]["hrs"])
    return (sum(pts) / len(pts), sum(att) / len(att)) if pts else None


def features(by_pid, games, recs, ctx=CTX):
    """{(gid, pid): {feature: raw value or None}} for every record, from his and his team's games before the date (and
    tonight's lineup, and tonight's first period for T only)."""
    con = sqlite3.connect(f"file:{ctx}?mode=ro", uri=True)
    pz = {(g, p): r for g, p, *r in con.execute("SELECT gid, pid, home, ozs, dzs, toi5 FROM pz")}
    sx = {(g, p): r for g, p, *r in con.execute("SELECT gid, pid, home, points FROM sx")}
    tx = list(con.execute("SELECT gid, gf, ga, opp FROM tx"))
    edge = defaultdict(dict)
    for s, p, e, raw in con.execute("SELECT season, pid, ep, raw FROM edge WHERE raw IS NOT NULL"):
        edge[(s, p)][e] = json.loads(zlib.decompress(raw))
    lm = defaultdict(list)
    for g, p, q, a, f in con.execute("SELECT gid, pid, mate, ov_all, ov_p1 FROM lm"):
        lm[(g, p)].append((q, a, f))
    con.close()

    rows, dressed, gmin, gp = defaultdict(list), defaultdict(lambda: defaultdict(set)), {}, defaultdict(int)
    for pid, gl in by_pid.items():
        for g in gl:
            s_, z = sx.get((g["gid"], pid)), pz.get((g["gid"], pid))
            home = ((s_ or z or ("",))[0]) == "H"
            g["home"] = home
            hrs = (g["min_ev"] + g["min_pp"] + g["min_sh"]) / 60
            t5 = (z[3] or 0) / 60 if z else 0.0
            oz5, dz5 = ((z[1] or 0) * t5, (z[2] or 0) * t5) if z else (0.0, 0.0)
            v = {"att": g["att"], "hrs": hrs, "points": ((s_[1] or 0) if s_ else 0), "oz5": oz5, "dz5": dz5, "t5": t5}
            for sfx, on in (("_h", home), ("_r", not home)):
                for k, x in (("att", g["att"]), ("hrs", hrs), ("oz5", oz5), ("dz5", dz5), ("t5", t5)):
                    v[k + sfx] = x if on else 0.0
            rows[pid].append((g["date"], g["season"], v))
            dressed[g["gid"]][g["team"]].add(pid)
            gmin[(g["gid"], pid)] = (g["min_ev"], g["min_pp"], g["grp"])
            if not g["po"]:
                gp[(g["season"], pid)] += 1
    cum = Cum(rows)
    tgd = []
    for gid, gf, ga, opp in tx:
        teams = games.get(gid, (None, {}))[1]
        mine = [t for t, o in teams.items() if o == B.team(opp)]
        if len(mine) == 1 and gf is not None and ga is not None:
            tgd.append((games[gid][0], gid // 1000000, mine[0], gf, ga))
    gd = TeamGD(tgd)
    sched = defaultdict(list)
    for gid, (date, teams) in games.items():
        for t in teams:
            sched[t].append((date, gid))
    for v in sched.values():
        v.sort()
    sdates = {t: [d for d, _ in v] for t, v in sched.items()}
    zavg = defaultdict(lambda: [0.0, 0.0, 0.0])                # 2023-24 5v5 start shares by group
    for pid, gl in by_pid.items():
        for g, (_d, _s, v) in zip(gl, rows[pid]):
            if g["season"] == B.FIT:
                a = zavg[g["grp"]]
                a[0], a[1], a[2] = a[0] + v["oz5"], a[1] + v["dz5"], a[2] + v["t5"]
    zavg = {k: (a[0] / a[2], a[1] / a[2]) for k, a in zavg.items()}
    evm = defaultdict(list)
    for (g, f) in recs.values():
        if g["season"] == B.FIT:
            evm[g["grp"]].append(f["mins"]["ev"])
    evz = {k: (np.mean(v), np.std(v) or 1.0) for k, v in evm.items()}

    out = {}
    for pid, gl in by_pid.items():
        for i, g in enumerate(gl):
            key = (g["gid"], pid)
            if key not in recs:
                continue
            f = recs[key][1]
            x = dict.fromkeys(sum(FEATS.values(), ()), None)
            # E: last season's EDGE
            e = edge_feats(edge.get((g["season"] - 1, pid)), gp.get((g["season"] - 1, pid), 0))
            if e:
                x.update(e)
            x["e_missing"] = 0.0 if e else 1.0
            # H: home ice and last change
            x["home"] = 1.0 if g["home"] else 0.0
            x["home_x_ev"] = x["home"] * (f["mins"]["ev"] - evz[g["grp"]][0]) / evz[g["grp"]][1]
            c = cum.get(pid, g["season"], g["date"])
            W = c[0] if c else None
            sfx = "_h" if g["home"] else "_r"
            if W and W["hrs"] > 0 and W["att"] > 0:
                rate = W["att"] / W["hrs"]
                x["venue_split"] = float(np.log((W["att" + sfx] + K_VENUE * rate) / (W["hrs" + sfx] + K_VENUE) / rate))
            # Z: zone starts at tonight's venue
            if W and W["t5"] > 0:
                oz_all, dz_all = W["oz5"] / W["t5"], W["dz5"] / W["t5"]
                x["z_ozs"] = (W["oz5" + sfx] + K_ZONE * oz_all) / (W["t5" + sfx] + K_ZONE) - zavg[g["grp"]][0]
                x["z_dzs"] = (W["dz5" + sfx] + K_ZONE * dz_all) / (W["t5" + sfx] + K_ZONE) - zavg[g["grp"]][1]
            # L: tonight's lineup against his team's last 5 games
            t = g["team"]
            prior = [gid for d, gid in sched[t][:bisect.bisect_left(sdates[t], g["date"])] if gid // 1000000 == g["season"]]
            last5 = prior[-5:]
            x["freed_ev"], x["freed_pp"], x["layoff"] = 0.0, 0.0, 0.0
            if last5:
                cnt = defaultdict(int)
                for gid in last5:
                    for p in dressed[gid][t]:
                        cnt[p] += 1
                tonight = dressed[g["gid"]][t]
                absent = {p for p, n in cnt.items() if n >= min(3, len(last5))} - tonight
                mm = lambda p, j: np.mean([gmin[(gid, p)][j] for gid in last5 if (gid, p) in gmin])
                grp_of = lambda p: next(gmin[(gid, p)][2] for gid in last5 if (gid, p) in gmin)
                n_grp = sum(1 for p in tonight if gmin[(g["gid"], p)][2] == g["grp"])
                x["freed_ev"] = sum(mm(p, 0) for p in absent if grp_of(p) == g["grp"]) / max(1, n_grp)
                x["freed_pp"] = sum(mm(p, 1) for p in absent)
                if any(pid in dressed[gid][t] for gid in prior):
                    miss = 0
                    for gid in reversed(prior):
                        if pid in dressed[gid][t]:
                            break
                        miss += 1
                    x["layoff"] = 1.0 if miss >= 3 else 0.0
            # S: the game-script proxy
            a, b = gd.get(t, g["season"], g["date"]), gd.get(g["opp"], g["season"], g["date"])
            if a is not None and b is not None:
                x["margin"] = a - b
            # C: his last game's linemates
            qc = None
            if i:
                pg = gl[i - 1]
                ms = mates_of(lm.get((pg["gid"], pid), []), pg["team"], g["grp"], dressed, gmin, pg["gid"], 1)
                qc = quality(ms, cum, g["season"], g["date"]) if ms else None
            if qc:
                x["c_pts"], x["c_att"] = qc
            x["c_missing"] = 0.0 if qc else 1.0
            # T: tonight's first-period linemates (information only)
            mt = mates_of(lm.get(key, []), t, g["grp"], dressed, gmin, g["gid"], 2)
            qt = quality(mt, cum, g["season"], g["date"]) if mt else None
            if qt:
                x["t_pts"], x["t_att"] = qt
                if qc:
                    x["t_promo"] = qt[0] - qc[0]
            x["t_missing"] = 0.0 if qt else 1.0
            out[key] = x
    return out


# ---- the second stage --------------------------------------------------------------------------------------------
def standardize(keys, feats, fit_keys):
    """{feature: (mean, sd)} on the fit season's records (missing values left out)."""
    out = {}
    for k in sum(FEATS.values(), ()):
        v = np.array([feats[r][k] for r in fit_keys if feats[r][k] is not None], float)
        out[k] = (float(v.mean()), float(v.std()) or 1.0) if len(v) else (0.0, 1.0)
    return out


def glm(X, y, off):
    """A Poisson regression with a log link and a fixed offset, no intercept (the features are centred on 2023-24)."""
    b = np.zeros(X.shape[1])
    for _ in range(100):
        mu = np.exp(off + X @ b)
        step = np.linalg.solve(X.T @ (X * mu[:, None]) + 1e-6 * np.eye(len(b)), X.T @ (y - mu))
        b += step
        if np.abs(step).max() < 1e-10:
            break
    return b


def p_over_vec(mu, line, r):
    mu = np.maximum(mu, 1e-3)
    d = B.st.nbinom(r, r / (r + mu))
    whole = line == np.floor(line)
    return np.where(whole, d.sf(line) / np.maximum(1 - d.pmf(line), 1e-12), d.sf(np.floor(line)))


def main():
    by_pid, games, tg, names = B.load()
    pri = B.priors(by_pid)
    recs = {}
    for gl in by_pid.values():
        for g, f in B.history(gl):
            if f is not None and g["season"] >= B.FIT:
                recs[(g["gid"], g["pid"])] = (g, f)
    beta = B.toi_fit([(g, f) for g, f in recs.values() if g["season"] == B.FIT])
    opp = B.Opp(tg)
    for g, f in recs.values():
        mins = B.toi_proj(f, beta)
        att, ot, _sog = B.rates(f, g["grp"], pri)
        f["mins"] = mins
        f["proj"] = sum(mins[k] / 60 * att[k] for k in B.STR) * ot * opp.factor(g["opp"], g["season"], g["date"])
    feats = features(by_pid, games, recs)
    keys = list(recs)
    season = np.array([recs[k][0]["season"] for k in keys])
    y = np.array([recs[k][0]["shots"] for k in keys], float)
    mu0 = np.array([recs[k][1]["proj"] for k in keys])
    fit = season == B.FIT
    sd = standardize(keys, feats, [k for k, m in zip(keys, fit) if m])
    allf = sum(FEATS.values(), ())
    Z = np.array([[0.0 if feats[k][c] is None else (feats[k][c] - sd[c][0]) / sd[c][1] for c in allf] for k in keys])
    col = {c: i for i, c in enumerate(allf)}
    res = {"coverage": {c: {int(s): float(np.mean([feats[k][c] is not None for k, ss in zip(keys, season) if ss == s]))
                            for s in (B.FIT,) + B.TEST} for c in allf}, "variants": {}}
    print("coverage (share of player-games with a value):")
    for c in allf:
        print(f"  {c:12s} " + "  ".join(f"{s}: {res['coverage'][c][s]:.2f}" for s in res["coverage"][c]))

    rungs = B.main_rungs()
    pairs, counts = B.match(rungs, games, recs, names)
    idx = {k: i for i, k in enumerate(keys)}
    P = [(r, idx[(g["gid"], g["pid"])]) for r, (g, f) in pairs if g["shots"] != r[3]]
    pi = np.array([i for _r, i in P])
    line = np.array([r[3] for r, _ in P])
    q = np.array([r[6] for r, _ in P])
    pseason = season[pi]
    yo = (y[pi] > line).astype(float)
    avg = np.array([recs[keys[i]][1]["avg"] for i in pi])
    base_props = [{"season": int(pseason[j]), "line": float(line[j]), "over": r[4], "under": r[5], "act": float(y[i]),
                   "gid": recs[keys[i]][0]["gid"]} for j, (r, i) in enumerate(P)]
    print(f"\nmain-line props graded: {len(P)}")

    def run(name, groups):
        cols = [col[c] for gname in groups for c in FEATS[gname]]
        if cols:
            b = glm(Z[fit][:, cols], y[fit], np.log(mu0[fit]))
            mu = mu0 * np.exp(Z[:, cols] @ b)
        else:
            b, mu = np.zeros(0), mu0
        r = B.nb_size(y[fit], mu[fit])
        ll = {int(s): float(B.nb_ll(y[season == s], mu[season == s], r).mean()) for s in (B.FIT,) + B.TEST}
        pm = p_over_vec(mu[pi], line, r)
        tr = pseason == B.FIT
        X = np.column_stack([np.ones(len(pm)), B.logit(pm), B.logit(q)])
        cal = B.logistic(X[tr], yo[tr])
        p = 1 / (1 + np.exp(-X @ cal))
        lo = {int(s): B.ll(p[pseason == s], yo[pseason == s]) for s in (B.FIT,) + B.TEST}
        mae = {int(s): (float(np.abs(y[pi][pseason == s] - mu[pi][pseason == s]).mean()),
                        float(np.abs(y[pi][pseason == s] - avg[pseason == s]).mean())) for s in (B.FIT,) + B.TEST}
        test = [dict(bp, p=float(pp)) for bp, pp, s in zip(base_props, p, pseason) if s in B.TEST]
        bets = B.bets_of(test, "p")
        per = {s: B.boot([x["u"] for x in bets if x["season"] == s])[0] for s in B.TEST}
        pooled = B.boot([x["u"] for x in bets])[0]
        v = {"groups": list(groups), "coef": {c: round(float(x), 4) for c, x in zip([c for g_ in groups for c in FEATS[g_]], b)},
             "nb_size": r, "ll": ll, "logloss": lo, "book_logloss": {int(s): B.ll(q[pseason == s], yo[pseason == s])
                                                                       for s in (B.FIT,) + B.TEST},
             "mae": mae, "C": {"seasons": per, "pooled": pooled}, "calibration": cal.tolist()}
        res["variants"][name] = v
        return v

    base = run("base", ())
    print(f"\nbase: NB size {base['nb_size']:.1f}  C pooled {base['C']['pooled'].get('roi', 0):+.3f} on {base['C']['pooled']['n']}")
    hdr = "variant          LL/game 2024 | 2025 (vs base)        prop log loss 2024 | 2025 (vs base)     C pooled          adds"
    print("\n" + hdr)
    rows_ = [("+" + g_, (g_,)) for g_ in GROUPS] + [("full", GROUPS), ("+T (info)", ("T",)), ("full+T (info)", GROUPS + ("T",))]
    for name, groups in rows_:
        v = run(name, groups)
        da = [v["ll"][s] - base["ll"][s] for s in B.TEST]
        db = [v["logloss"][s] - base["logloss"][s] for s in B.TEST]
        adds = all(d > 0 for d in da) and all(d < 0 for d in db)
        v["adds"] = adds
        c = v["C"]["pooled"]
        print(f"{name:15s} {v['ll'][2024]:.5f} ({da[0]:+.5f}) | {v['ll'][2025]:.5f} ({da[1]:+.5f})   "
              f"{v['logloss'][2024]:.5f} ({db[0]:+.5f}) | {v['logloss'][2025]:.5f} ({db[1]:+.5f})   "
              f"{c.get('roi', 0):+.3f} [{c.get('lo', 0):+.3f}] n {c['n']:4d}   {'YES' if adds else 'no'}")
    full = res["variants"]["full"]
    a_ok = all(full["mae"][s][0] < full["mae"][s][1] for s in B.TEST)
    b_ok = all(full["logloss"][s] < full["book_logloss"][s] for s in B.TEST)
    cp, cs = full["C"]["pooled"], full["C"]["seasons"]
    c_ok = bool(cp.get("roi", -1) > 0 and cp.get("lo", -1) > 0 and all(cs[s].get("roi", -1) > 0 for s in B.TEST))
    replaces = bool(a_ok and b_ok and c_ok and full["adds"])
    res["full_verdict"] = {"A": a_ok, "B": b_ok, "C": c_ok, "a_b_vs_base": full["adds"], "replaces_base": replaces}
    print(f"\nfull model: A {'PASS' if a_ok else 'FAIL'}, B {'PASS' if b_ok else 'FAIL'}, C {'PASS' if c_ok else 'FAIL'}, "
          f"(a)+(b) vs base {'PASS' if full['adds'] else 'FAIL'} -> {'REPLACES the base' if replaces else 'the base stays'}")
    print("  full C by season: " + "  ".join(f"{s}: {cs[s].get('roi', 0):+.3f} on {cs[s]['n']}" for s in B.TEST))
    print("  full coefficients: " + json.dumps(full["coef"]))
    print("  full+T coefficients: " + json.dumps(res["variants"]["full+T (info)"]["coef"]))
    OUT.write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pull", choices=("reports", "shifts", "edge"))
    a = ap.parse_args()
    sys.exit(pull(a.pull) if a.pull else main())
