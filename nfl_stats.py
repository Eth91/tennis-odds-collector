#!/usr/bin/env python3
"""NFL game logs for Pickz: nflverse's weekly stats, snap counts and play by play -> nfl_stats.sqlite (read by nfl_research).

One row per player per game, this season and last, with everything a prop is graded on and the usage behind it:
    logs        the box score (passing, rushing, receiving, kicking, the defense's sacks and tackles), the snaps he played
                and his share of them, his targets' share and air yards, and from the play by play what the weekly file
                lacks: his longest completion / rush / reception, red-zone targets and carries, deep (20+ air yard) targets.
                Each row carries its game's context: home, his team's final margin, days of rest, his team's spread and
                the total (nflverse's closing lines).
    players     name, team, position, headshot, ESPN id (the live box scores and injuries key on it), depth chart spot
    team_games  per team per game: offensive plays, passes, runs, the neutral-script pass rate, seconds a play, points
    rush_dir    where his carries went (left end ... right end) and what each defense allowed there, by season
    tgt_tree    where his targets went (behind the line / short / intermediate / deep x left / middle / right), by season
    meta        when it was built and the last week of each file

Rebuilt whole on every run (two seasons is ~30k rows; a minute on the VM). Last season's files are cached for a week, this
season's for CUR_MAX_AGE (nflverse refreshes them through the week, the weekly stats the morning after a game).

    python3 nfl_stats.py              # this season and last
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import io
import json
import os
import sqlite3
from collections import defaultdict
from pathlib import Path

import nfl_common as C

HERE = Path(__file__).resolve().parent
DB = Path(os.environ.get("NFL_STATS_DB", HERE / "nfl_stats.sqlite"))
CUR_MAX_AGE, OLD_MAX_AGE = 3600, 7 * 86400
LOG_COLS = ("date", "gid", "week", "team", "opp", "home", "margin", "rest", "spr", "tot", "snaps", "snap_pct",
            "pass_att", "pass_comp", "pass_yds", "pass_tds", "pass_int", "sacked", "long_comp",
            "rush_att", "rush_yds", "rush_tds", "long_rush", "rush_share",
            "targets", "rec", "rec_yds", "rec_tds", "long_rec", "air_yds", "yac", "tgt_share", "air_share",
            "rz_tgt", "rz_rush", "deep_tgt", "td", "fg_made", "fg_att", "pat_made", "kick_pts", "sacks", "tackles")
# rush direction (nflverse run_location x run_gap) and the target tree's cells
DIRS = ("le", "lt", "lg", "m", "rg", "rt", "re")
DEPTHS = ("bl", "sh", "in", "dp")              # behind the line (<0 air yards), 0-9, 10-19, 20+
LOCS = ("l", "m", "r")
OFF_POS = {"QB", "RB", "FB", "WR", "TE", "K"}
DEF_GROUPS = {"DL", "LB", "DB"}

DDL = f"""
DROP TABLE IF EXISTS logs; DROP TABLE IF EXISTS players; DROP TABLE IF EXISTS team_games;
DROP TABLE IF EXISTS rush_dir; DROP TABLE IF EXISTS tgt_tree; DROP TABLE IF EXISTS meta; DROP TABLE IF EXISTS names;
DROP TABLE IF EXISTS team_adv; DROP TABLE IF EXISTS player_adv; DROP TABLE IF EXISTS def_zone;
CREATE TABLE logs (season INTEGER, pid INTEGER, pos TEXT, {", ".join(c + (" TEXT" if c in ("date", "gid", "team", "opp") else " REAL") for c in LOG_COLS)},
                   PRIMARY KEY (pid, gid));
CREATE INDEX logs_season ON logs (season, team);
CREATE TABLE players (pid INTEGER PRIMARY KEY, name TEXT, team TEXT, pos TEXT, headshot TEXT, espn TEXT, jersey TEXT,
                      depth_pos TEXT, status TEXT);
CREATE TABLE team_games (season INTEGER, gid TEXT, week INTEGER, date TEXT, team TEXT, opp TEXT, home INTEGER, plays INTEGER,
                         pass INTEGER, rush INTEGER, neutral_pass REAL, sec_play REAL, pts REAL, opp_pts REAL,
                         PRIMARY KEY (team, gid));
CREATE TABLE rush_dir (season INTEGER, kind TEXT, key TEXT, cells TEXT, PRIMARY KEY (season, kind, key));
CREATE TABLE tgt_tree (season INTEGER, pid INTEGER, cells TEXT, PRIMARY KEY (season, pid));
CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE names (pid INTEGER PRIMARY KEY, name TEXT, pos TEXT);   -- everyone in the logs, gone or not
-- the Matchup page's football: per team its offense and defense (big plays, pressure, blitzes, stacked boxes, contact,
-- pass rate over expected), per player his advanced lines (pressure, blitz splits, contact, separation, coverage), and
-- each defense's passing allowed by field zone (depth x side) to each group of receivers
CREATE TABLE team_adv (season INTEGER, team TEXT, js TEXT, PRIMARY KEY (season, team));
CREATE TABLE player_adv (season INTEGER, pid INTEGER, team TEXT, pos TEXT, js TEXT, PRIMARY KEY (season, pid));
CREATE TABLE def_zone (season INTEGER, team TEXT, grp TEXT, js TEXT, PRIMARY KEY (season, team, grp));
"""


def _n(x):
    if x is None or x == "" or x == "NA":
        return None
    try:
        v = float(x)
    except ValueError:
        return None
    return int(v) if v.is_integer() else v


def _z(x):
    v = _n(x)
    return 0 if v is None else v


def _age(season, cur):
    return CUR_MAX_AGE if season == cur else OLD_MAX_AGE


WEEKLY_KEEP = ("player_id", "player_display_name", "player_name", "position", "position_group", "season_type", "game_id",
               "team", "completions", "attempts", "passing_yards", "passing_tds", "passing_interceptions", "sacks_suffered",
               "carries", "rushing_yards", "rushing_tds", "receptions", "targets", "receiving_yards", "receiving_tds",
               "receiving_air_yards", "receiving_yards_after_catch", "target_share", "air_yards_share", "special_teams_tds",
               "fg_made", "fg_att", "pat_made", "def_sacks", "def_tackles_solo", "def_tackle_assists")


def weekly(season, cur):
    """nflverse weekly player stats, only the columns used (renamed stats_player in 2025; the old player_stats file
    serves earlier seasons)."""
    try:
        it = C.iter_rows(f"stats_player/stats_player_week_{season}.csv", _age(season, cur))
        first = next(it)
    except Exception:
        it = C.iter_rows(f"player_stats/player_stats_{season}.csv", _age(season, cur))
        first = next(it)
    keep = lambda r: {k: r.get(k) for k in WEEKLY_KEEP}
    return [keep(first)] + [keep(r) for r in it]


def pbp_rows(season, cur):
    """(header index, rows) of a season's play by play, streamed from the gzip with csv.reader (DictReader over 372
    columns is slow; the whole file decompressed in memory cost the VM 600 MB)."""
    f = C.cached(f"pbp/play_by_play_{season}.csv.gz", _age(season, cur))
    fh = gzip.open(f, "rt", encoding="utf-8-sig", newline="")
    rd = csv.reader(fh)
    hdr = next(rd)
    return {c: i for i, c in enumerate(hdr)}, rd


PBP_CACHE_V = 3               # bump when from_pbp's output changes: a cached past season is rebuilt


def from_pbp_cached(season, cur, posmap=None, ftn=None):
    """from_pbp, with a past season's results kept in the cache beside its file (a finished season's file changes
    rarely; its parse is most of a build's minute)."""
    if season == cur:
        return from_pbp(season, cur, posmap, ftn)
    src = C.cached(f"pbp/play_by_play_{season}.csv.gz", _age(season, cur))
    f = C.CACHE / f"derived_pbp_{season}.json"
    try:
        j = json.loads(f.read_text())
        if j.get("mtime") == src.stat().st_mtime and j.get("v") == PBP_CACHE_V:
            per = {(int(k.split("|")[0]), k.split("|")[1]): v for k, v in j["per"].items()}
            team = {(k.split("|")[0], k.split("|")[1]): v for k, v in j["team"].items()}
            rdir = {(k.split("|")[0], k.split("|")[1]): v for k, v in j["rdir"].items()}
            tree = {int(k): v for k, v in j["tree"].items()}
            return per, team, rdir, tree, j["extra"]
    except (OSError, ValueError, KeyError):
        pass
    per, team, rdir, tree, extra = from_pbp(season, cur, posmap, ftn)
    f.write_text(json.dumps({"mtime": src.stat().st_mtime, "v": PBP_CACHE_V, "extra": extra, "per": {f"{a}|{b}": v for (a, b), v in per.items()},
                             "team": {f"{a}|{b}": v for (a, b), v in team.items()},
                             "rdir": {f"{a}|{b}": {d: c for d, c in v.items()} for (a, b), v in rdir.items()},
                             "tree": {str(k): dict(v) for k, v in tree.items()}}))
    return per, team, rdir, tree, extra


ZONE_GRP = {"WR": "WR", "TE": "TE", "RB": "RB", "FB": "RB"}


def zone_of(ay, loc):
    """A pass's field zone: depth (behind the line, 0-9, 10-19, 20+ air yards) + side (l / m / r), or None."""
    loc = {"left": "l", "middle": "m", "right": "r"}.get(loc)
    if ay is None or not loc:
        return None
    return ("bl" if ay < 0 else "sh" if ay < 10 else "in" if ay < 20 else "dp") + loc


def from_pbp(season, cur, posmap=None, ftn=None):
    """Per (pid, gid): longest completion / rush / reception, red-zone targets and carries, deep targets; per team-game:
    plays, passes, runs, the neutral pass rate (win probability 20-80%, quarters 1-3) and seconds a play; per season:
    each rusher's and each defense's carries by direction, each receiver's target tree. And `extra`, for the Matchup
    page: each defense's passing allowed by field zone and receiver group (posmap: pid -> position), each offense's
    big plays (20+ yard completions, 10+ yard runs), longest plays, dropbacks, sacks and pass rate over expected
    (nflverse's xpass), and with FTN's charting (ftn: (gid, play_id) -> (blitzers, men in the box)) blitzes and
    stacked boxes it faced, each passer's line against the blitz and without it, each player's big plays."""
    posmap, ftn = posmap or {}, ftn or {}
    zone = defaultdict(lambda: defaultdict(lambda: [0, 0, 0, 0]))   # (defense, group) -> zone -> [tgt, comp, yds, td]
    tg = defaultdict(lambda: defaultdict(float))                    # (offense, gid) -> counters
    qbb = defaultdict(lambda: {"b": [0] * 7, "n": [0] * 7})         # passer -> blitz / none: [db, att, comp, yds, td, int, sack]
    pexp = defaultdict(lambda: defaultdict(int))                    # pid -> rec20 / rush10 / rush20
    rbl = defaultdict(lambda: {"b": [0] * 4, "n": [0] * 4, "team": None})   # receiver -> blitz / none: [tgt, rec, yds, td]
    tbl = defaultdict(lambda: {"b": 0, "n": 0})                     # offense -> charted targets blitzed / not
    ix, rd = pbp_rows(season, cur)
    g = lambda r, c: r[ix[c]] if c in ix else ""            # a column an older file lacks reads as blank
    per = defaultdict(lambda: {"long_comp": None, "long_rush": None, "long_rec": None, "rz_tgt": 0, "rz_rush": 0, "deep_tgt": 0})
    team = defaultdict(lambda: {"plays": 0, "pass": 0, "rush": 0, "npass": 0, "nplays": 0, "secs": 0.0, "nsec": 0})
    rdir = defaultdict(lambda: defaultdict(lambda: [0, 0, 0]))       # (kind, key) -> dir -> [att, yds, td]
    tree = defaultdict(lambda: defaultdict(lambda: [0, 0, 0]))       # pid -> cell -> [tgt, rec, yds]
    last_t = {}
    for r in rd:
        if g(r, "season_type") != "REG" and g(r, "season_type") != "POST":
            continue
        pt = g(r, "play_type")
        if pt not in ("pass", "run") or g(r, "two_point_attempt") == "1" or g(r, "aborted_play") == "1":
            continue
        gid, pos_t, def_t = g(r, "game_id"), C.team(g(r, "posteam")), C.team(g(r, "defteam"))
        if not pos_t:
            continue
        yl, yds = _n(g(r, "yardline_100")), _z(g(r, "yards_gained"))
        is_pass = g(r, "pass_attempt") == "1" or g(r, "qb_dropback") == "1"
        x = tg[(pos_t, gid)]
        xp = _n(g(r, "xpass"))
        if xp is not None:                                   # pass rate over expected: dropbacks less nflverse's xpass
            x["xn"] += 1
            x["xp"] += xp
            x["pp"] += 1 if g(r, "pass") == "1" else 0
        ch = ftn.get((gid, g(r, "play_id")))
        sack = g(r, "sack") == "1"
        if g(r, "qb_dropback") == "1":
            x["db"] += 1
            x["sacks"] += 1 if sack else 0
            if ch is not None:
                x["cdb"] += 1
                x["blitz"] += 1 if ch[0] > 0 else 0
            passer0 = C.pid_of(g(r, "passer_player_id"))
            if passer0 is not None and ch is not None:
                s7 = qbb[passer0]["b" if ch[0] > 0 else "n"]
                s7[0] += 1
                if g(r, "pass_attempt") == "1" and not sack:
                    s7[1] += 1
                    s7[2] += 1 if g(r, "complete_pass") == "1" else 0
                    s7[3] += yds if g(r, "complete_pass") == "1" else 0
                    s7[4] += 1 if g(r, "pass_touchdown") == "1" else 0
                    s7[5] += 1 if g(r, "interception") == "1" else 0
                s7[6] += 1 if sack else 0
        elif g(r, "rush_attempt") == "1" and ch is not None and g(r, "qb_scramble") != "1":
            x["crun"] += 1
            x["box8"] += 1 if ch[1] >= 8 else 0
        if g(r, "pass_attempt") == "1" and not sack and g(r, "complete_pass") == "1":
            x["long_pass"] = max(x["long_pass"], yds)
            x["big_pass"] += 1 if yds >= 20 else 0
        elif g(r, "rush_attempt") == "1":
            x["long_run"] = max(x["long_run"], yds)
            x["big_run"] += 1 if yds >= 10 else 0
        t = team[(pos_t, gid)]
        t["plays"] += 1
        t["pass" if is_pass else "rush"] += 1
        wp, q = _n(g(r, "wp")), _n(g(r, "qtr"))
        if wp is not None and .2 <= wp <= .8 and q is not None and q <= 3:
            t["nplays"] += 1
            t["npass"] += 1 if is_pass else 0
        gs = _n(g(r, "game_seconds_remaining"))
        k = (pos_t, gid)
        if gs is not None and k in last_t and 0 < last_t[k] - gs < 60:
            t["secs"] += last_t[k] - gs
            t["nsec"] += 1
        if gs is not None:
            last_t[k] = gs
        passer, rcv, rush = (C.pid_of(g(r, c)) for c in ("passer_player_id", "receiver_player_id", "rusher_player_id"))
        if g(r, "pass_attempt") == "1" and g(r, "sack") != "1":
            comp = g(r, "complete_pass") == "1"
            if passer is not None and comp:
                p = per[(passer, gid)]
                p["long_comp"] = max(p["long_comp"] or 0, yds) if p["long_comp"] is not None else yds
            if rcv is not None:
                p = per[(rcv, gid)]
                if comp:
                    p["long_rec"] = max(p["long_rec"], yds) if p["long_rec"] is not None else yds
                if yl is not None and yl <= 20:
                    p["rz_tgt"] += 1
                ay = _n(g(r, "air_yards"))
                if ay is not None and ay >= 20:
                    p["deep_tgt"] += 1
                zk = zone_of(ay, g(r, "pass_location"))
                if zk:
                    c = tree[rcv][zk]
                    c[0] += 1
                    if comp:
                        c[1] += 1
                        c[2] += yds
                    if def_t:
                        td = 1 if g(r, "pass_touchdown") == "1" else 0
                        for grp in ("all", ZONE_GRP.get(posmap.get(rcv))):
                            if grp:
                                z = zone[(def_t, grp)][zk]
                                z[0] += 1
                                z[1] += 1 if comp else 0
                                z[2] += yds if comp else 0
                                z[3] += td
                if comp and yds >= 20:
                    pexp[rcv]["rec20"] += 1
                if ch is not None:                       # a charted target: against the blitz or not
                    bk = "b" if ch[0] > 0 else "n"
                    s4 = rbl[rcv][bk]
                    s4[0] += 1
                    s4[1] += 1 if comp else 0
                    s4[2] += yds if comp else 0
                    s4[3] += 1 if g(r, "pass_touchdown") == "1" else 0
                    rbl[rcv]["team"] = pos_t
                    tbl[pos_t][bk] += 1
        elif g(r, "rush_attempt") == "1" and rush is not None:
            p = per[(rush, gid)]
            p["long_rush"] = max(p["long_rush"], yds) if p["long_rush"] is not None else yds
            pexp[rush]["rush10"] += 1 if yds >= 10 else 0
            pexp[rush]["rush20"] += 1 if yds >= 20 else 0
            if yl is not None and yl <= 20:
                p["rz_rush"] += 1
            if g(r, "qb_scramble") != "1":
                loc, gap = g(r, "run_location"), g(r, "run_gap")
                d = "m" if loc == "middle" else ({"left": "l", "right": "r"}.get(loc, "") + {"end": "e", "tackle": "t", "guard": "g"}.get(gap, "")
                                                  if loc in ("left", "right") else "")
                if d in DIRS:
                    td = 1 if g(r, "touchdown") == "1" and C.pid_of(g(r, "td_player_id")) == rush else 0
                    for kk in (("p", str(rush)), ("d", def_t or "")):
                        c = rdir[kk][d]
                        c[0] += 1
                        c[1] += yds
                        c[2] += td
    extra = {"zone": {f"{d}|{gp}": dict(v) for (d, gp), v in zone.items()},
             "tg": {f"{t_}|{gd}": dict(v) for (t_, gd), v in tg.items()},
             "qbb": {str(k): v for k, v in qbb.items()}, "pexp": {str(k): dict(v) for k, v in pexp.items()},
             "rbl": {str(k): v for k, v in rbl.items()}, "tbl": dict(tbl)}
    return per, team, rdir, tree, extra


# ── the Matchup page's advanced data: FTN's charting, Pro Football Reference's advanced stats, Next Gen Stats ──────
def ftn_plays(season, cur):
    """{(gid, play_id): (blitzers, men in the box)} from FTN's charting (every play, a few days behind); {} without it."""
    out = {}
    try:
        for r in C.iter_rows(f"ftn_charting/ftn_charting_{season}.csv", _age(season, cur)):
            out[(r.get("nflverse_game_id"), str(r.get("nflverse_play_id")).split(".")[0])] = (int(_z(r.get("n_blitzers"))), int(_z(r.get("n_defense_box"))))
    except Exception:                                               # noqa: BLE001 — a season FTN has not charted
        pass
    return out


def pfr_rows(season, cur, kind):
    """Pro Football Reference's weekly advanced stats (pass / rush / rec / def), streamed; nothing without the file."""
    try:
        yield from C.iter_rows(f"pfr_advstats/advstats_week_{kind}_{season}.csv", _age(season, cur))
    except Exception:                                               # noqa: BLE001
        return


def ngs_season(kind, season, cur):
    """{pid: row} — Next Gen Stats' season-to-date line (week 0 in nflverse's file) for passing / rushing / receiving."""
    out = {}
    try:
        for r in C.iter_rows(f"nextgen_stats/ngs_{kind}.csv.gz", CUR_MAX_AGE if season == cur else OLD_MAX_AGE):
            if r.get("season") == str(season) and r.get("season_type") == "REG" and r.get("week") == "0":
                pid = C.pid_of(r.get("player_gsis_id"))
                if pid is not None:
                    out[pid] = r
    except Exception:                                               # noqa: BLE001
        pass
    return out


def passer_rating(att, comp, yds, td, ints):
    """The NFL passer rating from totals (None with no attempts)."""
    if not att:
        return None
    cl = lambda x: max(0.0, min(2.375, x))
    a, b, c, d = cl((comp / att - .3) * 5), cl((yds / att - 3) * .25), cl(td / att * 20), cl(2.375 - ints / att * 25)
    return round((a + b + c + d) / 6 * 100, 1)


def _r(x, d=1):
    return None if x is None else round(x, d)


def advanced(season, cur, extra, games, rows, roster):
    """({team: {"off", "def"}}, {pid: {...}}, {(defense, group): zone cells}) for one season.
    team off / def: games, 20+ yard completions and 10+ yard runs a game (made / allowed), the longest of each, sacks
    and pressures a dropback (PFR's pressures on the passer), blitzes a charted dropback and 8+ men in the box a
    charted run (FTN), yards before contact a carry (PFR), pass rate over expected (nflverse's xpass: the offense's,
    and offenses' against the defense).
    player: a passer's pressure and bad throws (PFR), his line against the blitz and without it (FTN), time to throw
    and aggressiveness (NGS); a runner's yards before / after contact and broken tackles (PFR), yards over expected and
    stacked boxes faced (NGS); a receiver's drops, broken tackles and passer rating when targeted (PFR), separation,
    cushion and YAC over expected (NGS); everyone's 20+ catches and 10+ / 20+ runs; a defender's coverage (targets,
    completions, yards, TDs, passer rating allowed), pressures, sacks and missed tackles (PFR)."""
    by_pfr = {r["pfr"]: pid for pid, r in roster.items() if r.get("pfr")}
    col = {c: i for i, c in enumerate(LOG_COLS)}
    logs = defaultdict(list)
    for r in rows:                                          # (season, pid, pos, *LOG_COLS)
        logs[r[1]].append(r[3:])
    off, dfn = defaultdict(lambda: defaultdict(float)), defaultdict(lambda: defaultdict(float))
    for key, v in extra.get("tg", {}).items():
        tm, gid = key.split("|")
        g = games.get(gid)
        if not g or g["season"] != season or tm not in (g["home"], g["away"]):
            continue
        opp = g["away"] if tm == g["home"] else g["home"]
        for agg in (off[tm], dfn[opp]):
            agg["g"] += 1
            for k in ("db", "sacks", "cdb", "blitz", "crun", "box8", "big_pass", "big_run", "xn", "xp", "pp"):
                agg[k] += v.get(k, 0)
            agg["long_pass"] = max(agg["long_pass"], v.get("long_pass", 0))
            agg["long_run"] = max(agg["long_run"], v.get("long_run", 0))
    P = defaultdict(lambda: defaultdict(float))             # pid -> PFR sums
    tw = defaultdict(float)                                 # pid -> targets behind the rating average
    tgt_of = {(pid, r[col["gid"]]): r[col["targets"]] or 0 for pid, rs in logs.items() for r in rs}
    pid_of = lambda r: by_pfr.get(r.get("pfr_player_id"))
    for r in pfr_rows(season, cur, "pass"):
        tm, op = C.team(r.get("team")), C.team(r.get("opponent"))
        pr = _z(r.get("times_pressured"))
        off[tm]["pressured"] += pr
        dfn[op]["pressured"] += pr
        pid = pid_of(r)
        if pid is not None:
            for k in ("times_pressured", "times_blitzed", "times_hurried", "times_hit", "passing_bad_throws", "times_sacked"):
                P[pid][k] += _z(r.get(k))
    for r in pfr_rows(season, cur, "rush"):
        op = C.team(r.get("opponent"))
        dfn[op]["ybc"] += _z(r.get("rushing_yards_before_contact"))
        dfn[op]["pfr_car"] += _z(r.get("carries"))
        pid = pid_of(r)
        if pid is not None:
            for k in ("carries", "rushing_yards_before_contact", "rushing_yards_after_contact", "rushing_broken_tackles"):
                P[pid][k] += _z(r.get(k))
    for r in pfr_rows(season, cur, "rec"):
        pid = pid_of(r)
        if pid is None:
            continue
        P[pid]["receiving_drop"] += _z(r.get("receiving_drop"))
        P[pid]["receiving_broken_tackles"] += _z(r.get("receiving_broken_tackles"))
        rat, t = _n(r.get("receiving_rat")), tgt_of.get((pid, r.get("game_id")), 0)
        if rat is not None and t:
            P[pid]["rat_w"] += rat * t
            tw[pid] += t
    cov = defaultdict(lambda: defaultdict(float))
    cov_team = {}
    for r in pfr_rows(season, cur, "def"):
        pid = pid_of(r)
        if pid is None:
            continue
        c = cov[pid]
        cov_team[pid] = C.team(r.get("team"))
        c["g"] += 1
        for k in ("def_targets", "def_completions_allowed", "def_yards_allowed", "def_receiving_td_allowed", "def_ints",
                  "def_air_yards_completed", "def_yards_after_catch", "def_times_blitzed", "def_pressures", "def_sacks",
                  "def_missed_tackles", "def_tackles_combined"):
            c[k] += _z(r.get(k))
        if _n(r.get("def_adot")) is not None and _z(r.get("def_targets")):
            c["adot_w"] += _n(r.get("def_adot")) * _z(r.get("def_targets"))
    ngs = {k: ngs_season(k, season, cur) for k in ("passing", "rushing", "receiving")}
    teams = {}
    for t in set(off) | set(dfn):
        o, d = off[t], dfn[t]
        pct = lambda a, b: _r(100 * a / b) if b else None
        side = lambda x: {"games": int(x["g"]), "big_pass_pg": _r(x["big_pass"] / x["g"], 2) if x["g"] else None,
                          "big_run_pg": _r(x["big_run"] / x["g"], 2) if x["g"] else None, "long_pass": int(x["long_pass"]),
                          "long_run": int(x["long_run"]), "sack_pct": pct(x["sacks"], x["db"]), "press_pct": pct(x["pressured"], x["db"]),
                          "blitz_pct": pct(x["blitz"], x["cdb"]), "box8_pct": pct(x["box8"], x["crun"]),
                          "proe": _r(100 * (x["pp"] - x["xp"]) / x["xn"]) if x["xn"] else None, "db_pg": _r(x["db"] / x["g"]) if x["g"] else None}
        dd = side(d)
        dd["ybc"] = _r(d["ybc"] / d["pfr_car"], 2) if d["pfr_car"] else None
        teams[t] = {"off": side(o), "def": dd}
    players = {}
    for pid, rs in logs.items():
        rec = roster.get(pid) or {}
        pos = rec.get("pos") or ""
        g = len(rs)
        a = {"team": rs[-1][col["team"]], "pos": pos, "g": g}
        x = P.get(pid, {})
        db = sum((r[col["pass_att"]] or 0) + (r[col["sacked"]] or 0) for r in rs)
        if pos == "QB" and db:
            att = sum(r[col["pass_att"]] or 0 for r in rs)
            a.update(db=db, press_pct=_r(100 * x.get("times_pressured", 0) / db), bad_pct=_r(100 * x.get("passing_bad_throws", 0) / att) if att else None,
                     hit=int(x.get("times_hit", 0)), blitzed=int(x.get("times_blitzed", 0)))
            b = (extra.get("qbb") or {}).get(str(pid))
            if b:
                a["vs_blitz"] = b                                # [dropbacks, att, comp, yds, td, int, sacks] blitzed / not
            n = ngs["passing"].get(pid)
            if n:
                a.update(ttt=_r(_n(n.get("avg_time_to_throw")), 2), aggr=_r(_n(n.get("aggressiveness"))),
                         cpoe=_r(_n(n.get("completion_percentage_above_expectation"))), iay=_r(_n(n.get("avg_intended_air_yards"))))
        if x.get("carries"):
            a.update(ybc=_r(x["rushing_yards_before_contact"] / x["carries"], 2), yac_r=_r(x["rushing_yards_after_contact"] / x["carries"], 2),
                     brk_r=int(x["rushing_broken_tackles"]))
        n = ngs["rushing"].get(pid)
        if n:
            a.update(ryoe=_r(_n(n.get("rush_yards_over_expected_per_att")), 2), box8=_r(_n(n.get("percent_attempts_gte_eight_defenders"))),
                     eff=_r(_n(n.get("efficiency")), 2))
        tg = sum(r[col["targets"]] or 0 for r in rs)
        if tg:
            a.update(drops=int(x.get("receiving_drop", 0)), brk_c=int(x.get("receiving_broken_tackles", 0)),
                     rat=_r(x["rat_w"] / tw[pid]) if tw.get(pid) else None)
        n = ngs["receiving"].get(pid)
        if n:
            a.update(sep=_r(_n(n.get("avg_separation")), 2), cush=_r(_n(n.get("avg_cushion")), 2),
                     yacoe=_r(_n(n.get("avg_yac_above_expectation")), 2), iay_r=_r(_n(n.get("avg_intended_air_yards"))),
                     ay_sh=_r(_n(n.get("percent_share_of_intended_air_yards"))))
        rb = (extra.get("rbl") or {}).get(str(pid))
        if rb and rb["b"][0] + rb["n"][0] >= 10:
            tb = (extra.get("tbl") or {}).get(rb["team"]) or {"b": 0, "n": 0}
            a["rblitz"] = {"b": rb["b"], "n": rb["n"], "tb": tb["b"], "tn": tb["n"]}
        e = (extra.get("pexp") or {}).get(str(pid))
        if e:
            a.update(rec20=e.get("rec20", 0), rush10=e.get("rush10", 0), rush20=e.get("rush20", 0))
        if len(a) > 3:
            players[pid] = a
    for pid, c in cov.items():                              # defenders (their own logs or not)
        if not c["def_targets"]:
            continue
        rec = roster.get(pid) or {}
        a = players.setdefault(pid, {"team": cov_team.get(pid) or rec.get("team"), "pos": rec.get("depth_pos") or rec.get("pos") or "",
                                     "g": int(c["g"])})
        if rec.get("depth_pos"):
            a["pos"] = rec["depth_pos"]                     # CB / FS / SS / OLB, not the roster's DB / LB
        a["cov"] = {"g": int(c["g"]), "tgt": int(c["def_targets"]), "cmp": int(c["def_completions_allowed"]), "yds": int(c["def_yards_allowed"]),
                    "td": int(c["def_receiving_td_allowed"]), "int": int(c["def_ints"]),
                    "rat": passer_rating(c["def_targets"], c["def_completions_allowed"], c["def_yards_allowed"], c["def_receiving_td_allowed"], c["def_ints"]),
                    "adot": _r(c["adot_w"] / c["def_targets"]), "yac": int(c["def_yards_after_catch"]),
                    "press": int(c["def_pressures"]), "sacks": c["def_sacks"], "missed": int(c["def_missed_tackles"])}
    zones = {}
    for key, cells in (extra.get("zone") or {}).items():
        t, grp = key.split("|")
        zones[(t, grp)] = {"g": int(dfn[t]["g"]), "cells": cells}
    return teams, players, zones


COV_V = 1                     # bump when coverage_splits' output changes
COV_MIN_ROUTES = 20           # a player's splits are kept once he has run 20 routes
COV_KIND = {"MAN_COVERAGE": "man", "ZONE_COVERAGE": "zone"}


def coverage_splits(season, cur, roster):
    """({pid: {"man": [routes, tgt, rec, yds, td], "zone": [...], "rt": [routes, team dropbacks]}}, {team: {"man": n,
    "zone": n}}) from nflverse's participation file (who was on the field each play, and the defense's coverage),
    joined to the play by play. A "route" is a dropback with him on the field: close to his routes for a receiver, an
    overcount for a tight end or back who stays in to block. The file comes out after a season, so this season has
    none until then: ({}, {}) without it."""
    try:
        part = C.cached(f"pbp_participation/pbp_participation_{season}.csv", _age(season, cur))
    except Exception:                                               # noqa: BLE001 — not published yet
        return {}, {}
    f = C.CACHE / f"derived_cov_{season}.json"
    try:
        j = json.loads(f.read_text())
        if j.get("mtime") == part.stat().st_mtime and j.get("v") == COV_V:
            return {int(k): v for k, v in j["players"].items()}, j["teams"]
    except (OSError, ValueError, KeyError):
        pass
    ix, rd = pbp_rows(season, cur)
    g = lambda r, c: r[ix[c]] if c in ix else ""
    plays = {}                                                      # (gid, play_id) -> (offense, defense, receiver, comp, yds, td)
    for r in rd:
        if g(r, "qb_dropback") != "1" or g(r, "two_point_attempt") == "1" or g(r, "play_type") not in ("pass", "run"):
            continue
        rcv = C.pid_of(g(r, "receiver_player_id")) if g(r, "pass_attempt") == "1" and g(r, "sack") != "1" else None
        comp = g(r, "complete_pass") == "1"
        plays[(g(r, "game_id"), str(g(r, "play_id")).split(".")[0])] = (
            C.team(g(r, "posteam")), C.team(g(r, "defteam")), rcv, comp, _z(g(r, "yards_gained")) if comp else 0,
            1 if g(r, "pass_touchdown") == "1" else 0)
    skill = {pid for pid, x in roster.items() if x.get("pos") in ("WR", "TE", "RB", "FB")}
    P = defaultdict(lambda: {"man": [0] * 5, "zone": [0] * 5, "rt": [0, 0]})
    T = defaultdict(lambda: {"man": 0, "zone": 0})
    team_db, on = defaultdict(int), defaultdict(int)                # (team, gid) dropbacks; (pid, team, gid) routes
    for r in C.iter_rows(f"pbp_participation/pbp_participation_{season}.csv", _age(season, cur)):
        d = plays.get((r.get("nflverse_game_id"), str(r.get("play_id")).split(".")[0]))
        if d is None:
            continue
        off_t, def_t, rcv, comp, yds, td = d
        gid = r.get("nflverse_game_id")
        team_db[(off_t, gid)] += 1
        cov = COV_KIND.get(r.get("defense_man_zone_type"))
        if cov and def_t:
            T[def_t][cov] += 1
        for gs in (r.get("offense_players") or "").split(";"):
            pid = C.pid_of(gs)
            if pid not in skill:
                continue
            on[(pid, off_t, gid)] += 1
            if cov:
                c = P[pid][cov]
                c[0] += 1
                if pid == rcv:
                    c[1] += 1
                    c[2] += 1 if comp else 0
                    c[3] += yds
                    c[4] += td
    for (pid, t, gid), n in on.items():
        P[pid]["rt"][0] += n
        P[pid]["rt"][1] += team_db[(t, gid)]
    out = {pid: v for pid, v in P.items() if v["rt"][0] >= COV_MIN_ROUTES}
    f.write_text(json.dumps({"mtime": part.stat().st_mtime, "v": COV_V, "players": {str(k): v for k, v in out.items()}, "teams": dict(T)}))
    return out, dict(T)


def snap_map(season, cur, roster):
    """{(pid, gid): (offense snaps, share)} — snap counts key on PFR ids, joined through the roster (name + team when a
    PFR id is missing). Defense / kicking rows keep their own unit's snaps."""
    by_pfr = {r["pfr"]: pid for pid, r in roster.items() if r.get("pfr")}
    by_name = defaultdict(set)
    for pid, r in roster.items():
        by_name[(C.nosfx(C.fold(r["name"])), r["team"])].add(pid)
    out = {}
    for r in C.iter_rows(f"snap_counts/snap_counts_{season}.csv", _age(season, cur)):
        pid = by_pfr.get(r.get("pfr_player_id"))
        if pid is None:
            hit = by_name.get((C.nosfx(C.fold(r.get("player"))), C.team(r.get("team"))), set())
            pid = next(iter(hit)) if len(hit) == 1 else None
        if pid is None:
            continue
        off, dfn = _z(r.get("offense_snaps")), _z(r.get("defense_snaps"))
        if off >= dfn:
            out[(pid, r["game_id"])] = (off, _n(r.get("offense_pct")))
        else:
            out[(pid, r["game_id"])] = (dfn, _n(r.get("defense_pct")))
    return out


def build(seasons=None, db=DB, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    sched_all = C.schedule(None, CUR_MAX_AGE)
    cur, _ = C.current_week(sched_all, now)
    seasons = seasons or (cur - 1, cur)
    games = {g["gid"]: g for g in sched_all if g["season"] in seasons}
    con = sqlite3.connect(db)
    con.executescript(DDL)
    meta = {"built_at": now.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat(), "seasons": list(seasons)}
    players, names = {}, {}
    for season in seasons:
        roster = C.rosters(season, _age(season, cur))
        if season == cur:
            players = roster
        snaps = snap_map(season, cur, roster)
        posmap = {pid: r["pos"] for pid, r in roster.items()}
        per, team, rdir, tree, extra = from_pbp_cached(season, cur, posmap, ftn_plays(season, cur))
        stats = weekly(season, cur)
        team_carries = defaultdict(int)
        for r in stats:
            team_carries[(C.team(r.get("team")), r.get("game_id"))] += _z(r.get("carries"))
        rows, last_wk = [], 0
        for r in stats:
            if r.get("season_type") not in ("REG", "POST"):
                continue
            pid, gid, tm = C.pid_of(r.get("player_id")), r.get("game_id"), C.team(r.get("team"))
            g = games.get(gid)
            if pid is None or g is None or tm not in (g["home"], g["away"]):
                continue
            pos = r.get("position") or ""
            grp = r.get("position_group") or ""
            if pos not in OFF_POS and grp not in DEF_GROUPS:
                continue
            home = tm == g["home"]
            pf, pa = (g["home_score"], g["away_score"]) if home else (g["away_score"], g["home_score"])
            sp = None if g["spread"] is None else (-g["spread"] if home else g["spread"])
            x = per.get((pid, gid), {})
            sn = snaps.get((pid, gid), (None, None))
            fgm, pat = _z(r.get("fg_made")), _z(r.get("pat_made"))
            tc = team_carries.get((tm, gid)) or 0
            v = {"date": g["date"], "gid": gid, "week": g["week"], "team": tm, "opp": g["away"] if home else g["home"],
                 "home": 1 if home else 0, "margin": None if pf is None or pa is None else pf - pa,
                 "rest": g["home_rest"] if home else g["away_rest"], "spr": sp, "tot": g["total"],
                 "snaps": sn[0], "snap_pct": None if sn[1] is None else round(sn[1] * 100),
                 "pass_att": _z(r.get("attempts")), "pass_comp": _z(r.get("completions")), "pass_yds": _z(r.get("passing_yards")),
                 "pass_tds": _z(r.get("passing_tds")), "pass_int": _z(r.get("passing_interceptions")),
                 "sacked": _z(r.get("sacks_suffered")), "long_comp": x.get("long_comp"),
                 "rush_att": _z(r.get("carries")), "rush_yds": _z(r.get("rushing_yards")), "rush_tds": _z(r.get("rushing_tds")),
                 "long_rush": x.get("long_rush"), "rush_share": round(_z(r.get("carries")) / tc * 100) if tc else None,
                 "targets": _z(r.get("targets")), "rec": _z(r.get("receptions")), "rec_yds": _z(r.get("receiving_yards")),
                 "rec_tds": _z(r.get("receiving_tds")), "long_rec": x.get("long_rec"),
                 "air_yds": _z(r.get("receiving_air_yards")), "yac": _z(r.get("receiving_yards_after_catch")),
                 "tgt_share": None if _n(r.get("target_share")) is None else round(_n(r.get("target_share")) * 100),
                 "air_share": None if _n(r.get("air_yards_share")) is None else round(_n(r.get("air_yards_share")) * 100),
                 "rz_tgt": x.get("rz_tgt", 0), "rz_rush": x.get("rz_rush", 0), "deep_tgt": x.get("deep_tgt", 0),
                 "td": _z(r.get("rushing_tds")) + _z(r.get("receiving_tds")) + _z(r.get("special_teams_tds")),
                 "fg_made": fgm, "fg_att": _z(r.get("fg_att")), "pat_made": pat, "kick_pts": 3 * fgm + pat,
                 "sacks": _z(r.get("def_sacks")),
                 "tackles": _z(r.get("def_tackles_solo")) + _z(r.get("def_tackle_assists"))}
            # a longest play he had none of is 0 when he played the role (a receiver with no catch, a passer with no
            # completion), so an under at 9.5 yards grades the game he was blanked
            if v["snaps"]:
                if v["long_rec"] is None and pos in ("WR", "TE", "RB", "FB"):
                    v["long_rec"] = 0
                if v["long_rush"] is None and pos in ("RB", "FB", "QB"):
                    v["long_rush"] = 0
                if v["long_comp"] is None and v["pass_att"]:
                    v["long_comp"] = 0
            if pos not in OFF_POS:                       # a defender: only his defense counts (no stray zero rush rows)
                for c in ("pass_att", "pass_comp", "pass_yds", "pass_tds", "pass_int", "sacked", "rush_att", "rush_yds",
                          "rush_tds", "targets", "rec", "rec_yds", "rec_tds", "air_yds", "yac"):
                    v[c] = None if not v[c] else v[c]
            rows.append((season, pid, pos) + tuple(v[c] for c in LOG_COLS))
            names[pid] = (r.get("player_display_name") or r.get("player_name") or "", pos)
            last_wk = max(last_wk, g["week"])
        con.executemany(f"INSERT OR REPLACE INTO logs VALUES ({','.join('?' * (3 + len(LOG_COLS)))})", rows)
        for (tm, gid), t in team.items():
            g = games.get(gid)
            if g is None or tm not in (g["home"], g["away"]):
                continue
            home = tm == g["home"]
            pf, pa = (g["home_score"], g["away_score"]) if home else (g["away_score"], g["home_score"])
            con.execute("INSERT OR REPLACE INTO team_games VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (season, gid, g["week"], g["date"], tm, g["away"] if home else g["home"], 1 if home else 0,
                         t["plays"], t["pass"], t["rush"], round(t["npass"] / t["nplays"], 3) if t["nplays"] else None,
                         round(t["secs"] / t["nsec"], 1) if t["nsec"] else None, pf, pa))
        for (kind, key), cells in rdir.items():
            con.execute("INSERT OR REPLACE INTO rush_dir VALUES (?,?,?,?)",
                        (season, kind, key, json.dumps({d: cells[d] for d in DIRS if d in cells})))
        for pid, cells in tree.items():
            con.execute("INSERT OR REPLACE INTO tgt_tree VALUES (?,?,?)", (season, pid, json.dumps(dict(cells))))
        meta[f"logs_{season}"] = {"rows": len(rows), "last_week": last_wk}
        tadv, padv, zones = advanced(season, cur, extra, games, rows, roster)
        vcov, dcov = coverage_splits(season, cur, roster)
        for pid, v in vcov.items():                          # man / zone and route rates (seasons with the file)
            rec = roster.get(pid) or {}
            padv.setdefault(pid, {"team": rec.get("team"), "pos": rec.get("pos") or "", "g": 0})["vcov"] = v
        for t, v in dcov.items():
            if t in tadv and v["man"] + v["zone"]:
                tadv[t]["def"]["man_pct"] = round(100 * v["man"] / (v["man"] + v["zone"]), 1)
        con.executemany("INSERT OR REPLACE INTO team_adv VALUES (?,?,?)", [(season, t, json.dumps(v)) for t, v in tadv.items()])
        con.executemany("INSERT OR REPLACE INTO player_adv VALUES (?,?,?,?,?)",
                        [(season, pid, v.pop("team", None), v.pop("pos", None), json.dumps(v)) for pid, v in padv.items()])
        con.executemany("INSERT OR REPLACE INTO def_zone VALUES (?,?,?,?)",
                        [(season, t, grp, json.dumps(v)) for (t, grp), v in zones.items()])
        meta[f"adv_{season}"] = {"teams": len(tadv), "players": len(padv), "zones": len(zones), "coverage": len(vcov),
                                 "charted": sum(1 for v in tadv.values() if v["off"].get("blitz_pct") is not None)}
    for pid, r in players.items():
        con.execute("INSERT OR REPLACE INTO players VALUES (?,?,?,?,?,?,?,?,?)",
                    (pid, r["name"], r["team"], r["pos"], r["headshot"], r["espn"], r["jersey"], r["depth_pos"], r["status"]))
    con.executemany("INSERT OR REPLACE INTO names VALUES (?,?,?)", [(k, v[0], v[1]) for k, v in names.items()])
    con.execute("INSERT OR REPLACE INTO meta VALUES ('meta', ?)", (json.dumps(meta),))
    con.commit()
    con.close()
    return meta


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB))
    a = ap.parse_args()
    tmp = Path(a.db + ".build")
    if tmp.exists():
        tmp.unlink()
    m = build(db=tmp)
    os.replace(tmp, a.db)                       # readers never see a half-built store
    print(f"nfl_stats: {json.dumps(m)}")
