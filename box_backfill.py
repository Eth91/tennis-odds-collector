#!/usr/bin/env python3
"""Backfill WNBA box scores for any season(s). Companion to box25.py.

WHY IT EXISTS
    box25.py takes its game ids from the stint cache and hard-stops at `game_date < 2026-01-01`,
    so it could only ever produce 2025 -- and the CURRENT season was missing from the box table
    entirely. This walks the ESPN scoreboard BY DATE instead, so any season can be pulled.
    Result on first run: 320 -> 1,088 games (2023: 262, 2024: 266, 2025: 320, 2026: 240).

    It reuses box25.parse() verbatim rather than reimplementing it, so parsing and -- critically --
    ROW ORDER stay identical. Row order is not cosmetic: ESPN lists starters first in position
    order, and that ordering is the ONLY positional signal the box table carries (verified: the
    first five average 27.7 min vs 13.4, and the median player takes 90% of starts in one slot).
    A rewrite that sorted rows would silently destroy the ability to derive position.

⚠️ FETCHING: plain urllib gets 403 Forbidden from this Oracle datacenter IP. `wnba_stints._get`
   is the fetcher that already works from this box (session + headers), and box25.py uses it, so
   use it here rather than reinventing one ESPN rejects.

Idempotent via the `done` table, so a re-run resumes instead of refetching. Refuses to call a
season successful if the scoreboard returned zero games -- a silent zero must never read as done.

    python box_backfill.py                 # default: 2023, 2024, 2026 (2025 is box25.py's)
    python box_backfill.py 2023 2024       # explicit seasons
"""
import sys, time, datetime as dt

sys.path.insert(0, "/home/ubuntu/tennis-odds-collector")
import box25
import wnba_stints as ST

# generous windows: the scoreboard simply returns nothing on non-game days
WINDOWS = {
    2023: ("2023-05-15", "2023-10-20"),
    2024: ("2024-05-10", "2024-10-22"),
    2025: ("2025-05-01", "2025-10-25"),
    2026: ("2026-05-01", "2026-10-25"),
}
DEFAULT = [2023, 2024, 2026]


def scoreboard(day):
    try:
        return ST._get(f"{ST.SITE}/scoreboard", dates=day, limit=100)
    except Exception as e:
        print("   scoreboard %s failed: %s" % (day, str(e)[:70]), flush=True)
        return None


def main(years):
    c = box25.init()
    done = {r[0] for r in c.execute("SELECT game_id FROM done")}
    print("already have %d games" % len(done), flush=True)
    total = 0
    for season in years:
        if season not in WINDOWS:
            print("no window defined for %s -- skipping" % season, flush=True)
            continue
        a, b = WINDOWS[season]
        d, d1 = dt.date.fromisoformat(a), dt.date.fromisoformat(b)
        if d1 > dt.date.today():
            d1 = dt.date.today()
        ids = []
        while d <= d1:
            js = scoreboard(d.strftime("%Y%m%d"))
            for ev in (js or {}).get("events", []) or []:
                gid = str(ev.get("id") or "")
                comp = (ev.get("competitions") or [{}])[0]
                if gid and ((comp.get("status") or {}).get("type") or {}).get("completed"):
                    ids.append((gid, str(ev.get("date") or "")[:10]))
            d += dt.timedelta(days=1)
            time.sleep(0.08)
        fresh = [(g, dd) for g, dd in ids if g not in done]
        print("%d: %d completed games, %d new" % (season, len(ids), len(fresh)), flush=True)
        if not ids:
            print("   !! season %d returned ZERO games -- NOT calling this success" % season,
                  flush=True)
            continue
        n = 0
        for i, (gid, gdate) in enumerate(fresh, 1):
            try:
                rows = box25.parse(ST._get(f"{ST.SITE}/summary", event=gid), gid, gdate)
            except Exception:
                c.execute("INSERT OR REPLACE INTO done VALUES(?,?)", (gid, -1)); c.commit()
                continue
            if rows:
                c.executemany("INSERT OR REPLACE INTO box VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", rows)
                n += 1; total += 1
            c.execute("INSERT OR REPLACE INTO done VALUES(?,?)", (gid, len(rows)))
            c.commit()
            if i % 40 == 0:
                print("   %d/%d" % (i, len(fresh)), flush=True)
            time.sleep(0.1)
        print("   season %d: +%d games" % (season, n), flush=True)
    g = c.execute("SELECT COUNT(DISTINCT game_id) FROM box").fetchone()[0]
    sp = c.execute("SELECT MIN(game_date),MAX(game_date) FROM box").fetchone()
    print("\nDONE +%d. now %d games, %s .. %s" % (total, g, sp[0], sp[1]), flush=True)
    for y, n in c.execute("SELECT substr(game_date,1,4),COUNT(DISTINCT game_id) FROM box "
                          "GROUP BY 1 ORDER BY 1"):
        print("   %s: %d games" % (y, n), flush=True)
    c.close()


if __name__ == "__main__":
    yrs = [int(x) for x in sys.argv[1:]] or DEFAULT
    main(yrs)
