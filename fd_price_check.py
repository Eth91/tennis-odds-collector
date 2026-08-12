"""
⚠️ THE BOARD DOES NOT USE THIS MODULE. Read this before wiring it in.

dashboard.py computes price drift INLINE, from the `best_dec` that `_book_prices()` has
already resolved for the card, so the drift and the price printed next to it are the same
number by construction and cannot disagree. This file re-queries the lines DB on its own
path -- importing it into the board would put a SECOND copy of that lookup on the page,
and a second copy of a gate always drifts from the first.

Keep it for what it is: a standalone CLI/ad-hoc check. If the board's drift ever needs to
change, change it in dashboard.py, not here.
"""
"""Is the flagged line still available at the flagged price?  2026-08-12

WHY NOT THE LIVE API. Clicking a selection in a logged-in session exposed
`getMarketPrices{marketIds}` and `validateMarketsEligibility?marketIds=` on
smp/fcq.ab.sportsbook.fanduel.ca. Tempting, but wrong for a STATIC board:
  · the hosts are GEO-SCOPED (.ab. = Alberta) and the board is generated on an Oracle VM,
  · a client-side call from the published page dies on CORS and has no session,
  · a build-time call is stale the moment the page is written — same as using fd_lines.
fd_collect already writes FD prices to fd_lines every ~2-4 min. Comparing the LOGGED pick
against the NEWEST fd_lines row gives the same answer with zero new failure modes.

⚠️ AMERICAN vs DECIMAL. fd_lines.odds is DECIMAL (1.9259). The ledger stores AMERICAN
(-115). They are NOT comparable raw — the TT model already recorded one wrong answer from
exactly this confusion. Convert before differencing, never eyeball.
⚠️ STALENESS IS A REAL STATE, NOT AN ERROR. If the newest quote is older than STALE_MIN the
honest answer is "unknown", NOT "unchanged". A board that shows a green check because the
collector died is worse than one that shows nothing.
"""
import sqlite3
import os
from pathlib import Path

# ⚠️ THE LOOP WRITES wnba_lines.sqlite, NOT fanduel_props.sqlite. vm_loop.sh exports
# FD_DB=wnba_lines.sqlite and that is the DB the model reads; fanduel_props.sqlite is a
# legacy secondary (63k rows, 25min stale vs 1.58M rows, 3min). Pointed at the legacy DB
# every lookup returned STALE -- fail-safe, but the badge would never say anything.
# Honour FD_DB so this file can never drift from the collector's target again.
DB = Path(os.environ.get("FD_DB") or Path(__file__).with_name("wnba_lines.sqlite"))
STALE_MIN = 12
# ⚠️ A MAGNITUDE FLOOR, NOT JUST A SIGN. The first cut flagged MOVED on `drift < 0`,
# so a single-point tick lit the badge on nearly every row -- a warning that fires
# always is a warning nobody reads. And it measured drift in AMERICAN POINTS, which is
# DISCONTINUOUS at even money (+100 and -100 are adjacent yet 200 apart). On live rows
# that ranked a 1.0pp move (2.02 -> -102, "-204 points") as FIVE TIMES worse than an
# 11.6pp move (2.85 -> +114, "-71 points") -- exactly backwards. Drift is therefore
# decided in IMPLIED PROBABILITY. The raw pp number is always shown; this floor only
# decides whether the badge shouts.
MOVE_PP = 0.015         # 1.5pp implied -- below this is book noise, not a real move          # a quote older than this is UNKNOWN, not confirmed


def _to_american(dec):
    if dec is None:
        return None
    d = float(dec)
    if d <= 1.0:
        return None
    return round((d - 1) * 100) if d >= 2.0 else round(-100 / (d - 1))




def _implied(american):
    """American -> implied probability (no vig removal; both sides share the juice)."""
    a = float(american)
    return (-a) / (-a + 100.0) if a < 0 else 100.0 / (a + 100.0)

def _as_american(x):
    """Accept EITHER odds convention and return American.

    ⚠️ THE CALLERS DISAGREE. wnba_ledger.predictions.odds is DECIMAL (2.02); the TT
    ledger and most flagged prices are AMERICAN (-110). Passing a decimal price in
    here unconverted made `int(2.02)` -> 2 and reported drift = cur - 2, i.e. a ~110
    point swing on every single row, printed with full confidence. The two ranges do
    not overlap: American is always <=-100 or >=+100, decimal is always >1 and in
    practice <100, so the discriminator is exact rather than a guess.
    """
    x = float(x)
    return _to_american(x) if 1.0 < x < 100.0 else int(round(x))

def check(player, stat, line, side, flagged_american=None, db=DB, book="fd"):
    """-> dict: status GONE | STALE | MOVED | OK, with current price and drift.

    status:
      OK     line still posted, price equal or BETTER than flagged
      MOVED  still posted but worse than flagged (by `drift` cents)
      GONE   no quote for this exact player/stat/line/side
      STALE  newest quote older than STALE_MIN -> collector may be down; DO NOT trust
    """
    # ⚠️ READ-ONLY, SHORT TIMEOUT, AND IT MUST NEVER HANG THE BOARD. fd_collect writes
    # this DB continuously and a plain connect() raised "database is locked" on the very
    # first live call. The board's own live-line filter is FAIL-OPEN by design, and this
    # must match: a 4s ceiling means a locked DB degrades to "unknown" in seconds instead
    # of stalling the render. mode=ro takes no write lock, so it also contends far less.
    # Do NOT raise this timeout -- the whole point is that the board renders regardless.
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=4.0)
    con.execute("PRAGMA busy_timeout=4000")
    try:
        row = con.execute(
            "SELECT collected_at, odds, market_id, selection_id,"
            "       CAST((julianday('now')-julianday(collected_at))*1440 AS INT) "
            "  FROM fd_lines WHERE book=? AND player=? AND stat=? AND line=? AND side=?"
            "  ORDER BY collected_at DESC LIMIT 1",
            (book, player, stat, line, side)).fetchone()
    finally:
        con.close()
    if not row:
        return {"status": "GONE", "current": None, "drift": None, "age_min": None}
    ts, dec, mkt, sel, age = row
    cur = _to_american(dec)
    if age is not None and age > STALE_MIN:
        return {"status": "STALE", "current": cur, "drift": None, "age_min": age,
                "market_id": mkt, "selection_id": sel, "as_of": ts}
    drift = None
    drift_pp = None
    status = "OK"
    if flagged_american is not None and cur is not None:
        _fa = _as_american(flagged_american)
        drift = cur - _fa                              # +ve = price improved for the bettor
        # SAME SIGN CONVENTION AS `drift`: +ve = improved. Implied prob FALLING is a
        # longer price, so flagged-minus-current, not current-minus-flagged.
        drift_pp = _implied(_fa) - _implied(cur)
        if drift_pp <= -MOVE_PP:
            status = "MOVED"                           # materially worse than flagged
        elif drift_pp >= MOVE_PP:
            status = "BETTER"                          # materially better -- also worth knowing
    return {"status": status, "current": cur, "drift": drift, "drift_pp": drift_pp, "age_min": age,
            "market_id": mkt, "selection_id": sel, "as_of": ts}


def badge(res):
    """One-glance board string. Never claims 'still there' on a stale quote."""
    s = res["status"]
    if s == "GONE":
        return "OFF THE BOARD"
    if s == "STALE":
        return f"UNKNOWN (quote {res['age_min']}m old)"
    c = res["current"]
    pp = res.get("drift_pp")
    if c is None:
        return "posted"
    if pp is None:
        return f"posted {c:+d}"
    # ⚠️ LEAD WITH THE pp, NOT THE AMERICAN DELTA. The first badge printed the American
    # points delta, which made an OK row read "-102 (-204 vs flagged)" -- a headline that
    # flatly contradicted its own status and looked like the worst move on the board when
    # it was the mildest. Show the current price and the honest probability move.
    if s == "OK":
        return f"{c:+d} (holding)"
    return f"{c:+d} ({pp * 100:+.1f}pp vs flagged)"
