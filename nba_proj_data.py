#!/usr/bin/env python3
"""Point-in-time data for the projection engine (NBA_PROJECTION_PREREG.md).

One row per player APPEARANCE (min > 0) in a regular-season game, every season the stores hold, with the
game's date, the player's team and opponent, home/away, and his team's possession count; plus book prices:
  historical  basketball_nba_odds_hist.sqlite — one snapshot per game ~29 min before tip, 4 books, main lines
  2026-27     nba_lines.quotes — a CHANGE log; each book's board is rebuilt at the cutoff (nba_research.replay)

Sources and their grain (verified 2026-10-26, see the prereg's table):
  nba_gamelogs.logs_full   2022-23 .. 2025-26, whole-minute minutes, all box columns (stats.nba.com)
  nba_matchup.player_games 2025-26 .. now, decimal minutes, starter flag (cdn.nba.com); used for 2026-27
  nba_profiles.team_games  home/away 2022-23 .. 2024-25;  nba_matchup.games  home/away 2025-26 ..
  nba_gamelogs.positions   the player index's position (static)

A row with min == 0 is a DNP: never a conditional outcome, never minutes history (dnp() lists them).
Read-only over every store.
"""
from __future__ import annotations

import re
import sqlite3
import unicodedata
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATS = ("min", "pts", "reb", "ast", "fg3m", "stl", "blk", "tov")          # the modeled outcome vector
COUNTS = STATS[1:]
MARKET_PARTS = {"points": ("pts",), "rebounds": ("reb",), "assists": ("ast",), "threes": ("fg3m",),
                "steals": ("stl",), "blocks": ("blk",), "turnovers": ("tov",), "pra": ("pts", "reb", "ast"),
                "pts_reb": ("pts", "reb"), "pts_ast": ("pts", "ast"), "reb_ast": ("reb", "ast")}
for _s in STATS:                                                         # each base stat is its own "market" too
    MARKET_PARTS.setdefault(_s, (_s,))
ODDS_MARKET = {"player_points": "points", "player_rebounds": "rebounds", "player_assists": "assists",
               "player_threes": "threes", "player_steals": "steals", "player_blocks": "blocks",
               "player_points_rebounds_assists": "pra", "player_points_rebounds": "pts_reb",
               "player_points_assists": "pts_ast", "player_rebounds_assists": "reb_ast"}
BOOK = {"fanduel": "fd", "draftkings": "dk", "betmgm": "mgm", "williamhill_us": "czr"}
SEASONS = {"2022-23": ("2022-10-01", "2023-04-30"), "2023-24": ("2023-10-01", "2024-04-30"),
           "2024-25": ("2024-10-01", "2025-04-30"), "2025-26": ("2025-10-01", "2026-04-30"),
           "2026-27": ("2026-10-01", "2027-04-30")}
TEAM_NAMES = {
    "Atlanta Hawks": "ATL", "Boston Celtics": "BOS", "Brooklyn Nets": "BKN", "Charlotte Hornets": "CHA",
    "Chicago Bulls": "CHI", "Cleveland Cavaliers": "CLE", "Dallas Mavericks": "DAL", "Denver Nuggets": "DEN",
    "Detroit Pistons": "DET", "Golden State Warriors": "GSW", "Houston Rockets": "HOU", "Indiana Pacers": "IND",
    "Los Angeles Clippers": "LAC", "LA Clippers": "LAC", "Los Angeles Lakers": "LAL", "Memphis Grizzlies": "MEM",
    "Miami Heat": "MIA", "Milwaukee Bucks": "MIL", "Minnesota Timberwolves": "MIN", "New Orleans Pelicans": "NOP",
    "New York Knicks": "NYK", "Oklahoma City Thunder": "OKC", "Orlando Magic": "ORL", "Philadelphia 76ers": "PHI",
    "Phoenix Suns": "PHX", "Portland Trail Blazers": "POR", "Sacramento Kings": "SAC", "San Antonio Spurs": "SAS",
    "Toronto Raptors": "TOR", "Utah Jazz": "UTA", "Washington Wizards": "WAS"}
# odds-feed name -> the box score's (normalized); only names the roster match cannot resolve
ALIAS = {"carlton carrington": "bub carrington", "herb jones": "herbert jones", "moe wagner": "moritz wagner",
         "nicolas claxton": "nic claxton", "cam johnson": "cameron johnson", "mohamed bamba": "mo bamba",
         "vincent williams": "vince williams", "kenyon martin": "kj martin", "ron holland": "ronald holland",
         "gg jackson": "gregory jackson"}
SUFFIX = {"jr", "sr", "ii", "iii", "iv", "v"}


def season_of(date):
    y, m = int(date[:4]), int(date[5:7])
    y = y if m >= 8 else y - 1
    return f"{y}-{str(y + 1)[2:]}"


def norm(name):
    """Lower-case ASCII, initials joined ('R.J.' -> 'rj'), suffixes dropped."""
    n = unicodedata.normalize("NFKD", str(name or ""))
    n = "".join(c for c in n if not unicodedata.combining(c)).lower()
    n = re.sub(r"\b([a-z])\.\s*(?=[a-z]\.)", r"\1", n)        # r.j. -> rj.
    n = re.sub(r"[^a-z ]", " ", n)
    parts = [p for p in n.split() if p and p not in SUFFIX]
    return " ".join(parts)


def group_of(pos):
    """Position group G / F / C from 'G', 'F-C', 'PG', 'SF', ... (the first letter's family)."""
    p = (pos or "").upper()
    if not p:
        return None
    if p in ("PG", "SG"):
        return "G"
    if p in ("SF", "PF"):
        return "F"
    return {"G": "G", "F": "F", "C": "C"}.get(p[0])


def _ro(path):
    path = Path(path)
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=60) if path.exists() else None


# ── box scores ──────────────────────────────────────────────────────────────────────────────────────────
def load_box(gamelogs, matchup, profiles, seasons=None):
    """(rows, dnps, positions). rows: dicts with season, gid, date, team, opp, home (1/0/None), pid, name, group,
    min and the box counts, team_poss; sorted by (date, gid, team, pid). logs_full serves the seasons it holds;
    nba_matchup serves later ones. dnps: [(date, gid, team, pid)] for min == 0 rows."""
    gl, mu, pr = _ro(gamelogs), _ro(matchup), _ro(profiles)
    pos = {}
    if gl is not None:
        pos = {pid: p for pid, p in gl.execute("SELECT player_id, position FROM positions")}
    home = {}
    if pr is not None:
        for gid, team, h in pr.execute("SELECT game_id, team, home FROM team_games"):
            home[(gid, team)] = int(h)
    if mu is not None:
        for gid, h, a in mu.execute("SELECT gid, home, away FROM games"):
            home.setdefault((gid, h), 1)
            home.setdefault((gid, a), 0)
    raw, have = [], set()
    if gl is not None:
        for (season, gid, date, team, pid, name, mn, pts, reb, ast, fg3m, stl, blk, tov, fga, fta, oreb) in gl.execute(
                "SELECT season, game_id, date, team, player_id, player, min, pts, reb, ast, fg3m, stl, blk, tov, fga, "
                "fta, oreb FROM logs_full"):
            if seasons and season not in seasons:
                continue
            raw.append([season, gid, date, team, pid, name, mn, pts, reb, ast, fg3m, stl, blk, tov, fga, fta, oreb])
            have.add(season)
    if mu is not None:
        for (season, gid, date, team, pid, mn, pts, reb, ast, fg3m, stl, blk, tov, fga, fta, mpos) in mu.execute(
                "SELECT g.season, p.gid, g.date, p.team, p.pid, p.min, p.pts, p.reb, p.ast, p.fg3m, p.stl, p.blk, p.tov, "
                "p.fga, p.fta, p.pos FROM player_games p JOIN games g ON g.gid = p.gid "
                "WHERE g.home_pts IS NOT NULL"):
            if season in have or (seasons and season not in seasons):
                continue
            pos.setdefault(pid, mpos)
            raw.append([season, gid, date, team, pid, None, mn, pts, reb, ast, fg3m, stl, blk, tov, fga, fta, None])
        oreb_t = {(g, t): o for g, t, o in mu.execute("SELECT gid, team, oreb FROM team_games")}
    else:
        oreb_t = {}
    # team totals -> possessions (FGA + .44 FTA - OREB + TOV); nba_matchup rows carry team OREB separately
    tot = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
    for r in raw:
        t = tot[(r[1], r[3])]
        t[0] += r[14] or 0; t[1] += r[15] or 0; t[2] += r[16] or 0; t[3] += r[13] or 0
    for (g, team), o in oreb_t.items():
        if (g, team) in tot and o is not None:
            tot[(g, team)][2] = o
    teams_in = defaultdict(set)
    for r in raw:
        teams_in[r[1]].add(r[3])
    rows, dnps = [], []
    for r in raw:
        season, gid, date, team, pid, name, mn = r[:7]
        opp = [t for t in teams_in[gid] if t != team]
        if len(opp) != 1:
            continue                                         # a malformed game (one side missing): dropped
        if not mn or mn <= 0:
            dnps.append((date, gid, team, pid))
            continue
        t = tot[(gid, team)]
        rows.append({"season": season, "gid": gid, "date": date, "team": team, "opp": opp[0],
                     "home": home.get((gid, team)), "pid": pid, "name": name, "group": group_of(pos.get(pid)),
                     "min": float(mn), "pts": r[7] or 0, "reb": r[8] or 0, "ast": r[9] or 0, "fg3m": r[10] or 0,
                     "stl": r[11] or 0, "blk": r[12] or 0, "tov": r[13] or 0, "fga": r[14] or 0, "fta": r[15] or 0,
                     "team_poss": t[0] + 0.44 * t[1] - t[2] + t[3]})
    rows.sort(key=lambda x: (x["date"], x["gid"], x["team"], x["pid"]))
    return rows, dnps, pos


def names_by_team_season(rows, gamelogs=None):
    """{(season, team): {norm name: pid}} and {(season, team): {(initial, last): [pid]}} for the roster match.
    nba_matchup rows have no names: they come from logs_full / the player index for the same pid."""
    gl = _ro(gamelogs) if gamelogs else None
    pname = {}
    if gl is not None:
        for pid, name in gl.execute("SELECT DISTINCT player_id, player FROM logs_full"):
            pname[pid] = name
    full, short = defaultdict(dict), defaultdict(lambda: defaultdict(list))
    for r in rows:
        nm = r["name"] or pname.get(r["pid"])
        if not nm:
            continue
        n = norm(nm)
        full[(r["season"], r["team"])][n] = r["pid"]
        p = n.split()
        if len(p) >= 2 and r["pid"] not in short[(r["season"], r["team"])][(p[0][0], p[-1])]:
            short[(r["season"], r["team"])][(p[0][0], p[-1])].append(r["pid"])
    return full, short


def match_player(name, season, teams, full, short):
    """pid for an odds-feed name in a game between `teams`, or None (unmatched or ambiguous — never guessed)."""
    n = norm(name)
    n = ALIAS.get(n, n)
    hits = {full[(season, t)][n] for t in teams if n in full[(season, t)]}
    if len(hits) == 1:
        return hits.pop()
    if hits:
        return None
    p = n.split()
    if len(p) < 2:
        return None
    cand = {pid for t in teams for pid in short[(season, t)].get((p[0][0], p[-1]), [])}
    return cand.pop() if len(cand) == 1 else None


# ── book prices ─────────────────────────────────────────────────────────────────────────────────────────
def load_hist_lines(odds, rows, gamelogs=None, books=("fd", "dk", "mgm", "czr")):
    """[{gid, date, pid, market, book, line, over, under, snap, tip}] from the historical −29 min snapshot for the
    regular-season games in `rows`. Two-sided main line per (game, player, market, book); unmatched names and
    games are counted in the returned stats, not guessed."""
    o = _ro(odds)
    stats = defaultdict(int)
    if o is None:
        return [], stats
    game_of = {}
    for r in rows:
        game_of.setdefault((r["date"], r["team"]), (r["gid"], r["season"]))
    full, short = names_by_team_season(rows, gamelogs)
    pairs = defaultdict(dict)
    for ev, tip, gd, home, away, book, market, player, side, line, price, snap in o.execute(
            "SELECT event_id, commence_time, game_date, home_team, away_team, book, market, player, side, line, price, "
            "snapshot_ts FROM props"):
        b, mk = BOOK.get(book), ODDS_MARKET.get(market)
        if b not in books or mk is None or price is None or line is None:
            continue
        h, a = TEAM_NAMES.get(home), TEAM_NAMES.get(away)
        g = game_of.get((gd, h))
        if g is None or snap is None or tip is None or snap >= tip:
            stats["no_game_or_inplay"] += 1
            continue
        pairs[(g[0], gd, g[1], (h, a), mk, b, player)].setdefault(line, {})[side] = (price, snap, tip)
    out = []
    for (gid, gd, season, teams, mk, b, player), by_line in pairs.items():
        pid = match_player(player, season, teams, full, short)
        if pid is None:
            stats["unmatched"] += 1
            continue
        two = [(ln, s) for ln, s in by_line.items() if "over" in s and "under" in s]
        if not two:
            stats["one_sided"] += 1
            continue
        ln, s = min(two, key=lambda x: abs(x[1]["over"][0] - 1.9091))
        out.append({"gid": gid, "date": gd, "pid": pid, "market": mk, "book": b, "line": ln,
                    "over": s["over"][0], "under": s["under"][0], "snap": s["over"][1], "tip": s["over"][2]})
        stats["matched"] += 1
    return out, stats


def load_live_lines(lines_db, cutoff_min=30, books=("fd", "dk")):
    """[{gid, date?, pid, market, book, line, over, under, snap, tip}] for 2026-27 from the change log: each
    book's board as of tip − cutoff_min, main rung (two-sided, over nearest even). Also `open` (the first main)."""
    import datetime as dt
    import nba_research as R
    q = _ro(lines_db)
    if q is None:
        return []
    tips = {g: t for g, t in q.execute("SELECT gid, MIN(tip_utc) FROM quotes GROUP BY gid") if t}
    cut = {}
    for g, t in tips.items():
        tt = dt.datetime.fromisoformat(t.replace("Z", "+00:00")) - dt.timedelta(minutes=cutoff_min)
        cut[g] = tt.strftime("%Y-%m-%dT%H:%M:%S")
    close, first = {}, {}
    rows = q.execute("SELECT seen_at, book, gid, pid, stat, line, side, odds FROM quotes WHERE pid IS NOT NULL "
                     "ORDER BY seen_at")
    for t, changed in R.replay(r for r in rows if r[4] in MARKET_PARTS and r[1] in books):
        for k, st in changed.items():
            if k[0] not in cut or t > cut[k[0]]:
                continue
            m = R.main_of(st)
            if m is None:
                continue
            first.setdefault(k, (t, m))
            close[k] = (t, m)
    out = []
    for (gid, pid, stat, book), (t, m) in close.items():
        out.append({"gid": gid, "pid": pid, "market": stat, "book": book, "line": m[0], "over": m[1], "under": m[2],
                    "snap": t, "tip": tips[gid], "open": first[(gid, pid, stat, book)][1][:3]})
    return out
