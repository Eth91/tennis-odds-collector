"""Add DP World Tour rounds to the crawl. Measured overlap decides what is safe to merge.

Ratings are strokes-vs-field-mean with a two-pass field-QUALITY correction, and that correction
can only calibrate one tour against another through players who appear in BOTH. Measured 2025
overlap with the PGA field:
    eur (DP World)   248 shared players = 30% of its field  -> SAFE, strong bridge
    champions-tour    21 shared =  7%                        -> thin bridge, excluded
    lpga               0 shared =  0%                        -> DISJOINT, excluded
Merging LPGA would have produced ratings on an uncalibrated scale that LOOK comparable to PGA
numbers and are not — the failure mode would have been silent, which is why overlap was measured
before anything was added rather than after.

This matters most for the thin-sample problem: 974 of 1,373 rated players sit below MIN_ROUNDS=20,
largely because a DP World regular arriving at a PGA event has almost no history here.
"""
import ast, io
p = "pga_ruler.py"
s = io.open(p, encoding="utf-8").read()
old = '''def crawl(seasons=(2023, 2024, 2025, 2026)):
    """Season scoreboards -> rounds(player, event, date, round, score). Idempotent."""'''
new = '''def crawl(seasons=(2023, 2024, 2025, 2026), leagues=("pga", "eur")):
    """Season scoreboards -> rounds(player, event, date, round, score). Idempotent.

    leagues: ESPN golf league slugs. Defaults to PGA + DP World, chosen on MEASURED 2025 player
    overlap with the PGA field — eur shares 248 players (30% of its field), champions-tour only 21
    (7%), and lpga ZERO. The two-pass field-quality correction calibrates tours against each other
    only through shared players, so a disjoint tour would get ratings on an uncalibrated scale that
    look comparable and are not. eur is the one safe addition.
    """'''
assert old in s, "crawl anchor missing"
if 'leagues=("pga", "eur")' in s:
    print("  = crawl already multi-tour")
else:
    s = s.replace(old, new, 1)
    old_loop = '''    for yr in seasons:
        d = _get("https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard?dates=%d" % yr)
        n = 0'''
    new_loop = '''    for yr in seasons:
      for _lg in leagues:
        try:
            d = _get("https://site.api.espn.com/apis/site/v2/sports/golf/%s/scoreboard?dates=%d"
                     % (_lg, yr))
        except Exception:                                          # noqa: BLE001
            continue                                               # a tour missing a season is fine
        n = 0'''
    assert old_loop in s, "crawl loop anchor missing"
    s = s.replace(old_loop, new_loop, 1)
    ast.parse(s)
    io.open(p, "w", encoding="utf-8").write(s)
    print("  + crawl() now covers pga + eur (DP World)")
