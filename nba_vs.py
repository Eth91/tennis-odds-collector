#!/usr/bin/env python3
"""Opponent tables for the props page's Matchup page: docs/vs/{TEAM}.json, one per team — its last N_GAMES games and,
in each, the other team's players (MIN_MIN+ minutes) with their position group (G / F / C), stat line and, where the
board had one, their closing main line and over price per market (FanDuel, else DraftKings). The page lists "Recent
games vs <group> <market>" from it.

Box rows come from docs/box/{gid}.json (nba_boxscore); groups from nba_matchup, point in time (his most frequent start
before that game that season, else the index); closing lines from nba_lines (nba_research_score.boards_before_tip),
cached per game in nba_vs_close.json, since a final game's closing board never changes. The board starts 2026-10-22,
so older games have results and no line.

File: {team, rows: [[date, gid, team, pid, name, group, min, pts, reb, ast, fg3m, {market: [line, over, book]}]]},
newest game first, the most minutes first within a game.

    python3 nba_vs.py --box /home/ubuntu/tennis-odds-collector/docs/box --out /home/ubuntu/tennis-odds-collector/docs/vs
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from collections import defaultdict
from pathlib import Path

import nba_matchup as MU
import nba_research as R

HERE = Path(__file__).resolve().parent
CACHE = HERE / "nba_vs_close.json"
N_GAMES = 25
MIN_MIN = 10


def closing_mains(q, gids):
    """{gid: {"pid|stat": [line, over, book]}}: each player's main line and its over price on the last board before
    tip, FanDuel's when it posted one, else DraftKings'. Every gid asked for gets an entry (empty without a board)."""
    import nba_research_score as RSC
    out = {g: {} for g in gids}
    for (gid, pid, stat, book), rec in RSC.boards_before_tip(q, gids).items():
        m = R.main_of(rec["close"] or {})
        if not m or m[1] is None:
            continue
        k = f"{pid}|{stat}"
        if book == "fd" or k not in out[gid]:
            out[gid][k] = [m[0], m[1], book]
    return out


def team_rows(team, games, boxes, group, lines):
    """The rows of `team`'s file. games: [(gid, date)] newest first; boxes: {gid: box}; group(pid, date) -> G/F/C;
    lines: {gid: {"pid|stat": [line, over, book]}}."""
    rows = []
    for gid, date in games:
        b = boxes.get(gid)
        if not b:
            continue
        for t in b["teams"]:
            if t["tri"] == team:
                continue
            for p in sorted(t["players"], key=lambda r: -r[3]):
                if p[3] < MIN_MIN:
                    continue
                ln = {k.split("|")[1]: v for k, v in (lines.get(gid) or {}).items() if k.split("|")[0] == str(p[0])}
                rows.append([date, gid, t["tri"], p[0], p[1], group(p[0], date), p[3], p[4], p[5], p[6], p[9], ln])
    return rows


def build(mcon, q, box_dir, out_dir, cache=CACHE, idx=None):
    """Write docs/vs/{TEAM}.json for every team with a cached final. Returns the number of files written."""
    box_dir, out_dir = Path(box_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    finals = mcon.execute("SELECT gid, date, season, home, away FROM games WHERE home_pts IS NOT NULL "
                          "ORDER BY date DESC, gid DESC").fetchall()
    by_team = defaultdict(list)
    for gid, date, season, h, a in finals:
        for t in (h, a):
            if len(by_team[t]) < N_GAMES:
                by_team[t].append((gid, date, season))
    need = sorted({g for v in by_team.values() for g, _, _ in v})
    try:
        cached = json.loads(Path(cache).read_text())
    except (OSError, ValueError):
        cached = {}
    todo = [g for g in need if g not in cached]
    if todo and q is not None:
        cached.update(closing_mains(q, todo))
        tmp = Path(cache).with_suffix(".tmp")
        tmp.write_text(json.dumps(cached, separators=(",", ":")))
        os.replace(tmp, cache)
    boxes = {}
    for g in need:
        try:
            boxes[g] = json.loads((box_dir / f"{g}.json").read_text())
        except (OSError, ValueError):
            pass
    if idx is None:
        try:
            idx = json.loads(R.INDEX.read_text()).get("players", {})
        except (OSError, ValueError):
            idx = {}
    pos = {int(k): v[2] for k, v in idx.items()}
    seasons = {}

    def group(pid, date):
        s = R.season_of(date)
        if s not in seasons:
            seasons[s] = MU.Season(mcon, s, index_pos=pos)
        return seasons[s].group(pid, date)
    n = 0
    for team, games in by_team.items():
        rows = team_rows(team, [(g, d) for g, d, _ in games], boxes, group, cached)
        tmp = out_dir / f".{team}.json.tmp"
        tmp.write_text(json.dumps({"team": team, "rows": rows}, separators=(",", ":")))
        os.replace(tmp, out_dir / f"{team}.json")
        n += 1
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--box", required=True, help="the box score folder (docs/box, nba_boxscore)")
    ap.add_argument("--out", required=True, help="the folder the page reads (docs/vs)")
    a = ap.parse_args()
    mcon = sqlite3.connect(f"file:{MU.DB}?mode=ro", uri=True)
    q = R._ro(R.LINES)
    n = build(mcon, q, a.box, a.out)
    print(f"nba_vs: {n} team files -> {a.out}")


if __name__ == "__main__":
    main()
