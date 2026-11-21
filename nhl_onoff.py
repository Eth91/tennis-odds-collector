#!/usr/bin/env python3
"""On/off ice splits for the NHL side of the props page's WOWY tab (docs/nhlonoff/{TEAM}.json), and each team's lines
from its last game (nhl_research's depth): from each final game's shifts and play-by-play (fetched once: a final game's
do not change; kept in nhl_onoff.sqlite).

Who is on the ice: the NHL's shift chart (api.nhle.com/stats/rest/en/shiftcharts), or where that is empty (about four in
ten games of 2026-27 so far) its HTML time-on-ice reports, one per team, by jersey number. Every change of who is on
splits the game into stretches with one set of players on the ice a side. An event (a goal, a shot, a block, a hit) is
his while he is on the ice: in the stretch that ends at its time, else the one that starts at it (a goal ends shifts);
an assist made before his change, in the stretch at the goal. Rebuilt this way every player's ice time, goals, assists,
shots, shot attempts, blocks, hits, power-play points and saves match the NHL's box score in 1141 of 1141 player-games
(30 games of 2026-27, 18 from the shift chart and 12 from the HTML reports).

A power-play point: a goal (or an assist on one) scored with more skaters on the ice than the other side, a pulled
goalie's extra skater left out (the play-by-play's situation code).

File: {season, team, built_at, games, stats, gp: {pid: games}, toi: {pid: [seconds, [stat x len(stats)]]}, names, heads,
       with: {y: {pid: [seconds, [stat x len(stats)]]}} (pid's time and stats while y was on the ice with him),
       team_on: {y: [seconds, goals for, goals against]} (the team's while y was on the ice), total: [seconds, gf, ga]}
  The page reads a player's split without y as his total less his time with y.

Lines (the lines table, one row a team): its last game's forward lines and defense pairs at five on five (the three
forwards, and the two defensemen, who played the most time together, taken in turn), its power-play units (the five
with the most power-play time, then the most-used five with at most two of them, from its last game with a power play),
and its starting goalie; each one's ice time that game.

    python3 nhl_onoff.py --out /home/ubuntu/tennis-odds-collector/docs/nhlonoff
"""
from __future__ import annotations

import argparse
import bisect
import datetime as dt
import html
import json
import os
import re
import sqlite3
import zlib
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import nhl_common as C

HERE = Path(__file__).resolve().parent
DB = Path(os.environ.get("NHL_ONOFF_DB", HERE / "nhl_onoff.sqlite"))
STATS = ("goals", "assists", "points", "shots", "attempts", "blocks", "hits", "ppp", "saves")
S = {k: i for i, k in enumerate(STATS)}
FWD, DEF = {"C", "L", "R"}, {"D"}
DDL = """CREATE TABLE IF NOT EXISTS games (gid TEXT PRIMARY KEY, season INTEGER, date TEXT, ok INTEGER, src TEXT);
CREATE TABLE IF NOT EXISTS splits (gid TEXT, team TEXT, js BLOB, PRIMARY KEY (gid, team));
CREATE TABLE IF NOT EXISTS glines (gid TEXT, team TEXT, date TEXT, js TEXT, PRIMARY KEY (gid, team));
CREATE TABLE IF NOT EXISTS lines (team TEXT PRIMARY KEY, gid TEXT, date TEXT, js TEXT);
"""


class Unreadable(Exception):
    """A game whose shifts cannot be read (no shift chart and no HTML report, or a side with no one on the ice)."""


def _sec(mmss):
    m, s = str(mmss).split(":")
    return int(m) * 60 + int(s)


# ── the sources ──────────────────────────────────────────────────────────────────────────────────────────────
def json_shifts(rows):
    """[(pid, start, end)] in game seconds from the shift chart's rows (its goal markers left out)."""
    out = []
    for r in rows:
        if r.get("typeCode") != 517 or not r.get("startTime") or not r.get("endTime") or not r.get("period"):
            continue
        base = (int(r["period"]) - 1) * 1200
        a, b = base + _sec(r["startTime"]), base + _sec(r["endTime"])
        if b > a:
            out.append((int(r["playerId"]), a, b))
    return out


_HEAD = re.compile(r'class="playerHeading[^"]*"[^>]*>\s*(\d+)\s+([^<]+?)\s*</td>')
_ROW = re.compile(r'<td[^>]*>\s*\d+\s*</td>\s*<td[^>]*>\s*(\d+|OT)\s*</td>\s*<td[^>]*>\s*(\d+:\d\d)\s*/[^<]*</td>\s*'
                  r'<td[^>]*>\s*(\d+:\d\d)\s*/[^<]*</td>')


def html_shifts(page, jersey):
    """[(pid, start, end)] from one team's HTML time-on-ice report; jersey: {number: pid} for that team."""
    s = page.decode("utf-8", "replace") if isinstance(page, bytes) else page
    heads = list(_HEAD.finditer(s))
    out = []
    for i, h in enumerate(heads):
        pid = jersey.get(int(h.group(1)))
        if pid is None:
            continue
        chunk = s[h.end(): heads[i + 1].start() if i + 1 < len(heads) else len(s)]
        for per, a, b in _ROW.findall(chunk):
            base = (4 if per == "OT" else int(per)) * 1200 - 1200
            a, b = base + _sec(a), base + _sec(b)
            if b > a:
                out.append((pid, a, b))
    return out


def report_url(gid, side, season):
    return f"https://www.nhl.com/scores/htmlreports/{C.season_id(season)}/T{side}{gid[4:]}.HTM"


def fetch_game(gid, season, get=None):
    """(play-by-play, [(pid, start, end)], source) for a final game. Raises Unreadable without shifts for both teams."""
    get = get or (lambda url, raw=False: C.fetch(url, raw=raw))
    pbp = get(f"{C.WEB}/gamecenter/{gid}/play-by-play")
    rows = (get(f"{C.REST}/shiftcharts?cayenneExp=gameId={gid}") or {}).get("data") or []
    sh, src = json_shifts(rows), "json"
    team_of = {r["playerId"]: r["teamId"] for r in pbp.get("rosterSpots", [])}
    if len({team_of.get(p) for p, _, _ in sh} - {None}) < 2:
        sh, src = [], "html"
        for side, t in (("H", pbp["homeTeam"]["id"]), ("V", pbp["awayTeam"]["id"])):
            jersey = {r["sweaterNumber"]: r["playerId"] for r in pbp.get("rosterSpots", []) if r["teamId"] == t}
            try:
                sh += html_shifts(get(report_url(gid, side, season), raw=True), jersey)
            except Exception:                                                # noqa: BLE001
                pass
    if len({team_of.get(p) for p, _, _ in sh} - {None}) < 2:
        raise Unreadable(gid)
    return pbp, sh, src


# ── the stretches and the events in them ─────────────────────────────────────────────────────────────────────
def stretches(shifts):
    """[(start, end, frozenset of pids on the ice)] — the game cut at every shift's start and end."""
    marks = sorted({t for _, a, b in shifts for t in (a, b)})
    if not marks:
        return []
    starts, ends = defaultdict(list), defaultdict(list)
    for p, a, b in shifts:
        starts[a].append(p)
        ends[b].append(p)
    on, out = defaultdict(int), []
    for i, t in enumerate(marks[:-1]):
        for p in ends[t]:
            on[p] -= 1
        for p in starts[t]:
            on[p] += 1
        cur = frozenset(p for p, k in on.items() if k > 0)
        if cur:
            out.append((t, marks[i + 1], cur))
    return out


def event_time(e):
    per = (e.get("periodDescriptor") or {}).get("number") or 0
    if (e.get("periodDescriptor") or {}).get("periodType") == "SO" or not e.get("timeInPeriod"):
        return None
    return (per - 1) * 1200 + _sec(e["timeInPeriod"])


def powerplay(code, home):
    """Did the side (home or not) have more skaters than the other, a pulled goalie's extra skater left out?"""
    if not code or len(code) != 4 or not code.isdigit():
        return False
    ag, ask, hsk, hg = (int(c) for c in code)
    a, h = ask - (1 - ag), hsk - (1 - hg)
    return h > a if home else a > h


def credits(e, home_id):
    """[(pid, stat, n)] for one play-by-play event (the stats the props use)."""
    d, k = e.get("details") or {}, e.get("typeDescKey")
    out = []
    if k == "goal":
        pp = powerplay(e.get("situationCode"), d.get("eventOwnerTeamId") == home_id)
        for x in (d.get("scoringPlayerId"),):
            if x:
                out += [(x, "goals", 1), (x, "points", 1), (x, "shots", 1), (x, "attempts", 1)] + ([(x, "ppp", 1)] if pp else [])
        for x in (d.get("assist1PlayerId"), d.get("assist2PlayerId")):
            if x:
                out += [(x, "assists", 1), (x, "points", 1)] + ([(x, "ppp", 1)] if pp else [])
    elif k == "shot-on-goal":
        if d.get("shootingPlayerId"):
            out += [(d["shootingPlayerId"], "shots", 1), (d["shootingPlayerId"], "attempts", 1)]
        if d.get("goalieInNetId"):
            out.append((d["goalieInNetId"], "saves", 1))
    elif k == "missed-shot" and d.get("shootingPlayerId"):
        out.append((d["shootingPlayerId"], "attempts", 1))
    elif k == "blocked-shot":
        if d.get("shootingPlayerId"):
            out.append((d["shootingPlayerId"], "attempts", 1))
        if d.get("blockingPlayerId") and d.get("reason") != "teammate-blocked":      # a teammate's is no block
            out.append((d["blockingPlayerId"], "blocks", 1))
    elif k == "hit" and d.get("hittingPlayerId"):
        out.append((d["hittingPlayerId"], "hits", 1))
    return [(int(p), s, n) for p, s, n in out]


def find(segs, starts, t, pid):
    """The index of the stretch a player's event at t belongs to: the one ending at t (or around it), else the one
    starting at it, with him on the ice; None when he is on in neither."""
    i = bisect.bisect_left(starts, t) - 1             # the stretch with start < t <= its end
    for j in (i, i + 1, i - 1, i + 2):
        if 0 <= j < len(segs) and pid in segs[j][2] and segs[j][0] - 1 <= t <= segs[j][1] + 1:
            return j
    return None


def parse(pbp, shifts):
    """({team: split}, {team: lines}, [unplaced events]) for one game. split: {"toi": {pid: [s, stats]}, "with": {y:
    {pid: [s, stats]}}, "team": {y: [s, gf, ga]}, "total": [s, gf, ga]}; pids as strings (JSON keys)."""
    spots = pbp.get("rosterSpots", [])
    tid = {pbp["homeTeam"]["id"]: C.team(pbp["homeTeam"]["abbrev"]), pbp["awayTeam"]["id"]: C.team(pbp["awayTeam"]["abbrev"])}
    team_of = {r["playerId"]: tid.get(r["teamId"]) for r in spots}
    pos = {r["playerId"]: r.get("positionCode") for r in spots}
    home_id, home = pbp["homeTeam"]["id"], tid[pbp["homeTeam"]["id"]]
    segs = stretches([x for x in shifts if team_of.get(x[0])])
    starts = [s[0] for s in segs]
    side = lambda s, t: frozenset(p for p in s if team_of.get(p) == t)
    zero = lambda: [0, [0] * len(STATS)]
    split = {t: {"toi": defaultdict(zero), "with": defaultdict(lambda: defaultdict(zero)), "team": defaultdict(lambda: [0, 0, 0]),
                 "total": [0, 0, 0]} for t in tid.values()}
    for a, b, s in segs:
        for t in tid.values():
            on = side(s, t)
            if not on:
                continue
            sp = split[t]
            sp["total"][0] += b - a
            for y in on:
                sp["toi"][y][0] += b - a
                sp["team"][y][0] += b - a
                for p in on:
                    if p != y:
                        sp["with"][y][p][0] += b - a
    lost = []
    for e in pbp.get("plays", []):
        t_ = event_time(e)
        cr = credits(e, home_id) if t_ is not None else []
        for pid, stat, n in cr:
            team = team_of.get(pid)
            j = find(segs, starts, t_, pid) if team else None
            if j is None and team and segs:                  # off the ice by then (an assist after his change): his
                j = max(0, min(len(segs) - 1, bisect.bisect_left(starts, t_) - 1))      # team's stretch at the time
            if j is None:
                lost.append((e.get("eventId"), pid, stat))
                continue
            sp, on = split[team], side(segs[j][2], team)
            sp["toi"][pid][1][S[stat]] += n
            for y in on:
                if y != pid:
                    sp["with"][y][pid][1][S[stat]] += n
            if stat == "goals":
                opp = next(t for t in tid.values() if t != team)
                sp["total"][1] += 1
                split[opp]["total"][2] += 1
                for y in on:
                    sp["team"][y][1] += 1
                for y in side(segs[j][2], opp):
                    split[opp]["team"][y][2] += 1
    names = {r["playerId"]: " ".join(x for x in ((r.get("firstName") or {}).get("default"), (r.get("lastName") or {}).get("default")) if x)
             for r in spots}
    out = {t: {"names": {str(p): names.get(p, "") for p in sp["toi"]},
               "toi": {str(p): v for p, v in sp["toi"].items()},
               "with": {str(y): {str(p): v for p, v in w.items()} for y, w in sp["with"].items()},
               "team": {str(y): v for y, v in sp["team"].items()}, "total": sp["total"]} for t, sp in split.items()}
    return out, {t: lines_of_game(segs, team_of, pos, t) for t in tid.values()}, lost


def _greedy(times, k, size):
    """Up to k disjoint groups of `size` from {frozenset: seconds}, the most time together first."""
    used, out = set(), []
    for grp, s in sorted(times.items(), key=lambda kv: (-kv[1], sorted(kv[0]))):
        if len(grp) == size and not grp & used:
            out.append((grp, s))
            used |= grp
            if len(out) == k:
                break
    return out


def lines_of_game(segs, team_of, pos, team):
    """{"F": [[pid x3]], "D": [[pid x2]], "PP1", "PP2": [pids], "G": [pid], "toi": {pid: minutes}, "pp_secs"} for one team."""
    trio, pair, ppu, toi, gtoi = defaultdict(int), defaultdict(int), defaultdict(int), defaultdict(int), defaultdict(int)
    for a, b, s in segs:
        mine = [p for p in s if team_of.get(p) == team]
        theirs = [p for p in s if team_of.get(p) and team_of.get(p) != team]
        g_in = any(pos.get(p) == "G" for p in mine)
        sk, osk = [p for p in mine if pos.get(p) != "G"], [p for p in theirs if pos.get(p) != "G"]
        o_in = any(pos.get(p) == "G" for p in theirs)
        for p in mine:
            (gtoi if pos.get(p) == "G" else toi)[p] += b - a
        if len(sk) == 5 and len(osk) == 5 and g_in and o_in:
            trio[frozenset(p for p in sk if pos.get(p) in FWD)] += b - a
            pair[frozenset(p for p in sk if pos.get(p) in DEF)] += b - a
        elif g_in and o_in and len(sk) > len(osk):
            ppu[frozenset(sk)] += b - a
    order = lambda grp: -sum(toi[p] for p in grp)
    by_toi = lambda grp: sorted(grp, key=lambda p: (-toi[p], p))
    F = [by_toi(g) for g, _ in sorted(_greedy(trio, 4, 3), key=lambda x: order(x[0]))]
    D = [by_toi(g) for g, _ in sorted(_greedy(pair, 3, 2), key=lambda x: order(x[0]))]
    pp = sorted(ppu.items(), key=lambda kv: (-kv[1], sorted(kv[0])))
    pp1 = next((g for g, s in pp if len(g) >= 4), None)
    pp2 = next((g for g, s in pp if pp1 and len(g) >= 4 and len(g & pp1) <= 2 and s >= 20), None)
    g = max(gtoi, key=gtoi.get) if gtoi else None
    return {"F": F, "D": D, "PP1": by_toi(pp1) if pp1 else [], "PP2": by_toi(pp2) if pp2 else [],
            "G": [g] if g else [], "toi": {str(p): round(v / 60, 1) for p, v in {**toi, **gtoi}.items()},
            "pp_secs": sum(ppu.values())}


# ── the store ────────────────────────────────────────────────────────────────────────────────────────────────
def connect(path):
    con = sqlite3.connect(path)
    con.executescript(DDL)
    return con


def store(con, gid, season, date, src, splits, lines):
    for t, sp in splits.items():
        con.execute("INSERT OR REPLACE INTO splits VALUES (?,?,?)", (gid, t, zlib.compress(json.dumps(sp, separators=(",", ":")).encode())))
    for t, L in lines.items():
        con.execute("INSERT OR REPLACE INTO glines VALUES (?,?,?,?)", (gid, t, date, json.dumps(L, separators=(",", ":"))))
    con.execute("INSERT OR REPLACE INTO games VALUES (?,?,?,?,?)", (gid, season, date, 1 if splits else 0, src))


def fetch(con, sched, season, get=None, workers=3):
    """Store every final game of the season (sched: nhl_common.schedule's) not stored yet. A game without its shifts
    yet is tried again next run; one that cannot be read after the day it was played is kept as unreadable (ok = 0).
    Returns (stored, not yet, unreadable, events unplaced)."""
    have = {g for (g,) in con.execute("SELECT gid FROM games")}
    todo = [g for g in sched if g["season"] == season and g["state"] == "final" and g["gid"] not in have]
    today = dt.datetime.now(C.ET).date().isoformat()

    def one(g):
        try:
            return fetch_game(g["gid"], season, get)
        except Unreadable:
            return "unreadable"
        except Exception:                                                     # noqa: BLE001
            return None
    stored = waiting = bad = lost = 0
    with ThreadPoolExecutor(workers) as ex:
        for g, got in zip(todo, ex.map(one, todo)):
            if got is None or (got == "unreadable" and g["date"] >= today):
                waiting += 1
                continue
            if got == "unreadable":
                store(con, g["gid"], season, g["date"], None, {}, {})
                bad += 1
            else:
                pbp, sh, src = got
                splits, lines, miss = parse(pbp, sh)
                store(con, g["gid"], season, g["date"], src, splits, lines)
                lost += len(miss)
            stored += 1
            if stored % 25 == 0:
                con.commit()
    con.commit()
    return stored, waiting, bad, lost


def refresh_lines(con):
    """Each team's lines: its last stored game's, the power-play units from its last game with a power play."""
    rows = con.execute("SELECT team, gid, date, js FROM glines ORDER BY date, gid").fetchall()
    last, pp = {}, {}
    for t, gid, date, js in rows:
        L = json.loads(js)
        if L["F"] or L["D"]:
            last[t] = (gid, date, L)
        if L["PP1"]:
            pp[t] = L
    for t, (gid, date, L) in last.items():
        if not L["PP1"] and t in pp:
            L = dict(L, PP1=pp[t]["PP1"], PP2=pp[t]["PP2"])
        con.execute("INSERT OR REPLACE INTO lines VALUES (?,?,?,?)", (t, gid, date, json.dumps(dict(L, gid=gid, date=date))))
    con.commit()
    return len(last)


def build(con, season):
    """{team: its file (see the module doc)} for the season."""
    games = dict(con.execute("SELECT gid, date FROM games WHERE season = ? AND ok = 1", (season,)))
    marks = ",".join("?" * len(games)) or "NULL"
    acc = {}
    for gid, t, blob in con.execute(f"SELECT gid, team, js FROM splits WHERE gid IN ({marks})", list(games)):
        sp = json.loads(zlib.decompress(blob))
        a = acc.setdefault(t, {"toi": {}, "with": {}, "team": {}, "total": [0, 0, 0], "gp": defaultdict(int), "games": 0, "names": {}})
        a["games"] += 1
        a["names"].update(sp.get("names") or {})
        for i in range(3):
            a["total"][i] += sp["total"][i]
        for p, (s, v) in sp["toi"].items():
            cur = a["toi"].setdefault(p, [0, [0] * len(STATS)])
            cur[0] += s
            cur[1] = [x + y for x, y in zip(cur[1], v)]
            a["gp"][p] += 1
        for y, w in sp["with"].items():
            wy = a["with"].setdefault(y, {})
            for p, (s, v) in w.items():
                cur = wy.setdefault(p, [0, [0] * len(STATS)])
                cur[0] += s
                cur[1] = [x + y_ for x, y_ in zip(cur[1], v)]
        for y, v in sp["team"].items():
            cur = a["team"].setdefault(y, [0, 0, 0])
            for i in range(3):
                cur[i] += v[i]
    built = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    return {t: {"season": C.season_id(season)[:4] + "-" + C.season_id(season)[6:], "team": t, "built_at": built,
                "games": a["games"], "stats": list(STATS), "gp": dict(a["gp"]), "toi": a["toi"], "with": a["with"],
                "team_on": a["team"], "total": a["total"], "names": {p: a["names"].get(p, "") for p in a["toi"]},
                "heads": {p: C.headshot(season, t, p) for p in a["toi"]}} for t, a in acc.items()}


def write(out, docs):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for team, doc in docs.items():
        tmp = out / f".{team}.json.tmp"
        tmp.write_text(json.dumps(doc, separators=(",", ":")))
        os.replace(tmp, out / f"{team}.json")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True, help="the folder the page reads (docs/nhlonoff)")
    a = ap.parse_args()
    con = connect(DB)
    season = C.season_of(dt.datetime.now(C.ET).date())
    stored, waiting, bad, lost = fetch(con, C.schedule(season, max_age=1800), season)
    n = refresh_lines(con)
    docs = build(con, season)
    write(a.out, docs)
    print(f"nhl_onoff: {stored} games stored ({bad} unreadable, {lost} events unplaced), {waiting} not yet · {season} · "
          f"{len(docs)} teams, {n} with lines -> {a.out}")


if __name__ == "__main__":
    main()
