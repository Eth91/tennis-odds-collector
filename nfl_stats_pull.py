#!/usr/bin/env python3
"""NFL stats substrate for prop backtesting — nflverse releases → nfl_stats.sqlite.

One table per source, ALL columns kept (grading + context need different slices later, and
these files are small — completeness costs a few MB). Everything keys on nflverse player ids
+ (season, week), which join cleanly to the odds archive via player display name + game date.

    player_weeks  weekly player stat lines (the GRADING truth for every yardage/reception prop)
    snap_counts   weekly snap counts (usage context: role changes, the E1 inactives edge)
    injuries      weekly practice/game statuses (inactives-timing substrate)
    rosters       weekly rosters (position/team resolution for prop segmentation)
    games         schedule + final scores (game dates, home/away, totals context)

Idempotent per season: DELETE that season's rows, re-INSERT. Re-run any time.

    python nfl_stats_pull.py                  # seasons 2023 2024 2025
    python nfl_stats_pull.py --seasons 2025
"""
from __future__ import annotations

import argparse
import csv
import io
import sqlite3
import urllib.request
from pathlib import Path

import ssl
try:
    import certifi
    CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:                                   # pragma: no cover
    CTX = ssl.create_default_context()

HERE = Path(__file__).resolve().parent
DB = HERE / "nfl_stats.sqlite"
REL = "https://github.com/nflverse/nflverse-data/releases/download"

# table -> (release tag, per-season filename template, season column in the csv)
# player_weeks: nflverse RENAMED the release mid-2025 (player_stats -> stats_player, file
# stats_player_week_{s}.csv). Old name still serves <=2024; try old then new so a re-run of
# any season works. Column names overlap on everything the backtests key on; ensure() ALTERs
# in any new columns so mixed-era rows coexist (old-only cols are NULL on new rows).
SOURCES = {
    "player_weeks": ("player_stats", "player_stats_{s}.csv", "season"),
    "snap_counts": ("snap_counts", "snap_counts_{s}.csv", "season"),
    "injuries": ("injuries", "injuries_{s}.csv", "season"),
    "rosters": ("weekly_rosters", "roster_weekly_{s}.csv", "season"),
}
GAMES_URL = f"{REL}/schedules/games.csv"              # all seasons in one file
GAMES_FALLBACK = "http://www.habitatring.com/games.csv"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, context=CTX, timeout=120).read()


def load_csv(blob):
    rows = list(csv.reader(io.StringIO(blob.decode("utf-8-sig"))))
    return rows[0], rows[1:]


def ensure(con, table, header):
    cols = ", ".join(f'"{c}"' for c in header)
    con.execute(f'CREATE TABLE IF NOT EXISTS "{table}" ({cols})')
    have = [r[1] for r in con.execute(f'PRAGMA table_info("{table}")')]
    for c in header:                                   # nflverse adds columns some years
        if c not in have:
            con.execute(f'ALTER TABLE "{table}" ADD COLUMN "{c}"')
    return [r[1] for r in con.execute(f'PRAGMA table_info("{table}")')]


def put(con, table, header, rows, season, season_col):
    cols = ensure(con, table, header)
    idx = {c: i for i, c in enumerate(header)}
    if season_col in idx:
        con.execute(f'DELETE FROM "{table}" WHERE "{season_col}"=?', (str(season),))
    ordered = [[r[idx[c]] if c in idx and idx[c] < len(r) else None for c in cols]
               for r in rows]
    con.executemany(
        f'INSERT INTO "{table}" VALUES ({",".join("?" * len(cols))})', ordered)
    return len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", nargs="*", type=int, default=[2023, 2024, 2025])
    a = ap.parse_args()
    con = sqlite3.connect(DB)
    for table, (tag, tmpl, season_col) in SOURCES.items():
        for s in a.seasons:
            urls = [f"{REL}/{tag}/{tmpl.format(s=s)}"]
            if table == "player_weeks":
                urls.append(f"{REL}/stats_player/stats_player_week_{s}.csv")
            for i, url in enumerate(urls):
                try:
                    header, rows = load_csv(fetch(url))
                    n = put(con, table, header, rows, s, season_col)
                    con.commit()
                    tagname = " (new tag)" if i else ""
                    print(f"  {table:<13} {s}  {n:>7} rows{tagname}")
                    break
                except Exception as e:
                    if i == len(urls) - 1:
                        print(f"  {table:<13} {s}  FAILED: {str(e)[:70]}")
    # schedule: one file, filter to wanted seasons
    try:
        header, rows = load_csv(fetch(GAMES_URL))
    except Exception:
        header, rows = load_csv(fetch(GAMES_FALLBACK))
    # per-season DELETE+INSERT like every other table — a DROP here made a partial
    # `--seasons 2025` re-run silently shrink games to one season (caught 2026-07-28)
    si = header.index("season")
    for s in a.seasons:
        keep = [r for r in rows if r[si] == str(s)]
        put(con, "games", header, keep, s, "season")
        print(f"  {'games':<13} {s}  {len(keep):>7} rows")
    con.commit()
    # indexes for the joins the backtests actually do
    for t, cols in (("player_weeks", "player_display_name, season, week"),
                    ("snap_counts", "player, season, week"),
                    ("injuries", "full_name, season, week"),
                    ("rosters", "full_name, season, week")):
        try:
            con.execute(f'CREATE INDEX IF NOT EXISTS ix_{t} ON "{t}"({cols})')
        except sqlite3.OperationalError as e:
            print(f"  (index {t} skipped: {str(e)[:60]})")
    con.commit()
    con.execute("VACUUM")
    con.close()
    print(f"done -> {DB.name} ({DB.stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
