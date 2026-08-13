"""FanDuel SGP collector — leg prices + same-game-parlay prices for NFL prop pairs.

WHY THIS EXISTS
The simulator LOSES to the closing line on marginal props (+0.00383 Brier, z +6.57)
and that is now closed on both halves of the allocation program. But its JOINT
distribution is accurate — mean |correlation error| 0.041 over 832 team-games — and
with the MARKET's marginals fixed and only the dependence varied, the sim's copula
beats independence at pricing P(both legs over):

    POOLED n=4,052   dBrier -0.003010   z -3.17   (clustered by game)
    2023 -0.002743 (z -2.18) | 2024 -0.003294 (z -2.30)   NEGATIVE IN BOTH SEASONS
    independence mis-prices the joint by +6.1% relative, +33% on QB->receiver pairs

⚠️ THAT IS MEASURED AGAINST INDEPENDENCE, NOT AGAINST FANDUEL. Books do not price
SGPs at independence; they apply their own correlation adjustment. The archive holds
NO SGP prices, so the real edge is UNMEASURED and +6.1% is an upper bound.
**This collector exists to replace that upper bound with a number.**

⚠️ TIME-CRITICAL. SGP prices are LIVE ONLY — they appear in no historical archive and
cannot be backfilled. Every week not collected is lost permanently.

────────────────────────────────────────────────────────────────────────────────
WHAT IS VERIFIED (2026-08-13, against the live API)
  * curl works, urllib does NOT — macOS python has no CA bundle and raises
    SSL: CERTIFICATE_VERIFY_FAILED. Same gotcha as the nflverse pulls.
  * event discovery: content-managed-page?customPageId=nfl -> 50 NFL events
  * market objects carry **sgmMarket: true/false** = SGP eligibility, and the NFL
    rules text explicitly excludes some ("Market not currently available for SGP",
    e.g. QUARTERBACK_A/B_RUSHING_YARDS)
  * the event layout exposes a dedicated tab **id 150, "Same Game Parlay™",
    isSameGameMulti: true**
  * runner objects carry selectionId, handicap (the line) and
    winRunnerOdds.americanDisplayOdds.americanOddsInt
  * ⚠️ market_id + selection_id is the ONLY unambiguous address of a rung —
    selectionId REPEATS across markets (see fd_betslip.py, measured on 1,409 rows).

WHAT IS **NOT** VERIFIED — THE ONE OPEN ITEM
  The SGP PRICING call. As of 2026-08-13 the earliest NFL game is 2026-09-11 and
  **no player props are posted yet**, so there are no prop legs to combine and the
  pricing request cannot be observed. `price_sgp()` below is therefore UNIMPLEMENTED
  BY DESIGN.

  ⚠️ DO NOT GUESS THE ENDPOINT. This repo already paid for that lesson: fd_betslip.py
  records a guessed `?marketId=&selectionId=` share link that cost a device test and
  returned "selection not added". Guessing here costs more, because a wrong price
  silently poisons the correlation estimate rather than failing loudly.

  DISCOVER IT INSTEAD, the same way the PFF weekly API was found:
    1. open a live NFL game on sportsbook.fanduel.com with props posted
    2. add two prop legs to the slip (this is NOT a wager — nothing is staked)
    3. in the console:
         performance.getEntriesByType('resource')
           .filter(e => /xmlhttprequest|fetch/.test(e.initiatorType))
           .map(e => e.name)
       and find the request that fires WHEN THE SECOND LEG IS ADDED — that is the
       SGP pricing call. Resource timing survives reloads; a fetch hook does not.
    4. record its URL shape, method and body here, then implement price_sgp().

  Until then this collector captures LEGS only, which is the prerequisite either way
  and is itself time-critical.

────────────────────────────────────────────────────────────────────────────────
THE PAIRS WE MODEL (from DISTRIBUTION_PIVOT.md; sim corr vs realised over 832 games)
    QB1.pass_yds | WR1.rec_yds    +0.487 vs +0.475   <- biggest mispricing vs indep
    QB1.pass_yds | TE1.rec_yds    +0.342 vs +0.306
    QB1.pass_att | RB1.rush_att   -0.204 vs -0.137   <- negative correlation
⚠️ WR1.rec_yds | WR2.rec_yds IS DELIBERATELY EXCLUDED. It is the only pair where the
sim's copula HURTS (+0.000357, z +2.23) and the sim's correlation has the WRONG SIGN
(+0.030 vs a realised -0.028). Collect it for diagnosis, never trade it.
"""
import argparse
import datetime as dt
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

AK = os.environ.get("FD_AK", "FhMFpcPWXMeyZxOx")
STATE = os.environ.get("FD_STATE", "ny")
BASE = f"https://sbapi.{STATE}.sportsbook.fanduel.com/api"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
DB = Path(os.environ.get("FD_SGP_DB",
                         Path(__file__).resolve().parent / "fd_sgp.sqlite"))

# marketType substrings -> our canonical stat. Order matters: combos before singles.
STATS = [
    ("PASSING_YARDS", "pass_yds"), ("PASS_ATTEMPTS", "pass_att"),
    ("PASS_COMPLETIONS", "completions"),
    ("RECEIVING_YARDS", "rec_yds"), ("RECEPTIONS", "receptions"),
    ("RUSHING_YARDS", "rush_yds"), ("RUSH_ATTEMPTS", "rush_att"),
    ("ANYTIME", "anytime_td"),
]
TRADEABLE_PAIRS = [("pass_yds", "rec_yds"), ("pass_att", "rush_att")]


def get(url, timeout=30):
    """⚠️ curl, NOT urllib — macOS python has no CA bundle (SSL cert verify fails)."""
    out = subprocess.run(
        ["curl", "-s", "-m", str(timeout), "-A", UA,
         "-H", "Accept: application/json", url],
        capture_output=True, text=True)
    if out.returncode != 0 or not out.stdout.strip():
        raise RuntimeError(f"curl failed rc={out.returncode} for {url[:110]}")
    return json.loads(out.stdout)


def _ddl(con):
    con.executescript("""
    CREATE TABLE IF NOT EXISTS sgp_legs(
      collected_at TEXT, event_id TEXT, event_name TEXT, open_date TEXT,
      market_id TEXT, selection_id TEXT, market_type TEXT, market_name TEXT,
      player TEXT, stat TEXT, line REAL, side TEXT, american INTEGER,
      sgm_eligible INTEGER,
      PRIMARY KEY (collected_at, market_id, selection_id));
    CREATE TABLE IF NOT EXISTS sgp_prices(
      collected_at TEXT, event_id TEXT, pair TEXT,
      leg_a_market TEXT, leg_a_sel TEXT, leg_a_american INTEGER,
      leg_b_market TEXT, leg_b_sel TEXT, leg_b_american INTEGER,
      sgp_american INTEGER, implied_indep REAL, implied_joint REAL,
      implied_rho REAL,
      PRIMARY KEY (collected_at, event_id, pair, leg_a_market, leg_b_market));
    CREATE INDEX IF NOT EXISTS ix_legs_ev ON sgp_legs(event_id, stat);
    """)


def _am_to_prob(a):
    if a is None:
        return None
    a = float(a)
    return (-a) / ((-a) + 100) if a < 0 else 100 / (a + 100)


def classify(m):
    """-> (stat, player) or (None, None). Player identity comes from the market
    name, which is where FanDuel puts it for O/U prop markets."""
    mt = (m.get("marketType") or "").upper()
    for key, stat in STATS:
        if key in mt:
            nm = m.get("marketName") or ""
            player = nm.split(" - ")[0].strip() if " - " in nm else None
            return stat, player
    return None, None


def collect_legs(con, limit=None, verbose=True):
    ts = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    page = get(f"{BASE}/content-managed-page?page=CUSTOM&customPageId=nfl"
               f"&pbHorizonId=nfl&_ak={AK}&timezone=America%2FNew_York")
    events = page.get("attachments", {}).get("events", {}) or {}
    if not events:
        raise RuntimeError("FD returned ZERO NFL events — refusing to record an "
                           "empty pull as a successful collection")
    real = [(k, v) for k, v in events.items()
            if v.get("openDate") and "@" in (v.get("name") or "")]
    real.sort(key=lambda kv: kv[1]["openDate"])
    if limit:
        real = real[:limit]
    n_leg = n_ev = 0
    for eid, ev in real:
        try:
            d = get(f"{BASE}/event-page?eventId={eid}&_ak={AK}"
                    f"&timezone=America%2FNew_York")
        except Exception as e:
            if verbose:
                print(f"    {eid} {ev.get('name')}: {type(e).__name__}")
            continue
        mk = d.get("attachments", {}).get("markets", {}) or {}
        n_ev += 1
        for m in mk.values():
            stat, player = classify(m)
            if not stat:
                continue
            for r in (m.get("runners") or []):
                o = ((r.get("winRunnerOdds") or {}).get("americanDisplayOdds")
                     or {}).get("americanOddsInt")
                con.execute(
                    "INSERT OR REPLACE INTO sgp_legs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (ts, str(eid), ev.get("name"), ev.get("openDate"),
                     str(m.get("marketId")), str(r.get("selectionId")),
                     m.get("marketType"), m.get("marketName"),
                     player or r.get("runnerName"), stat,
                     r.get("handicap"), r.get("runnerName"), o,
                     1 if m.get("sgmMarket") else 0))
                n_leg += 1
    con.commit()
    if verbose:
        print(f"  LEGS: {n_leg} rows from {n_ev} events at {ts}")
        if n_leg == 0:
            print("  ⚠️ ZERO prop legs. Expected before props are posted (as of "
                  "2026-08-13 the earliest NFL game is 2026-09-11 and no player "
                  "props exist yet). NOT a bug — but do not read it as 'no edge'.")
    return n_leg


def price_sgp(legs):
    """UNIMPLEMENTED BY DESIGN — the pricing endpoint is not yet verified.

    See the module docstring for the discovery procedure. Raising is deliberate:
    a stub that returned None would let a caller silently write NULL prices and
    later be read as "FanDuel prices SGPs at independence", which is exactly the
    silent-zero failure this project keeps paying for.
    """
    raise NotImplementedError(
        "SGP pricing endpoint not yet discovered — no NFL prop legs exist to "
        "observe it against (earliest game 2026-09-11). Follow the discovery "
        "recipe in this module's docstring, then implement. DO NOT GUESS: "
        "fd_betslip.py records a guessed endpoint that cost a device test.")


def implied_rho(p_a, p_b, p_joint):
    """Back out the book's implied Gaussian-copula correlation from its SGP price.

    p_a, p_b are the de-vigged leg probabilities; p_joint is the de-vigged SGP
    probability. Returns the rho whose bivariate normal CDF reproduces p_joint.
    """
    from scipy.stats import norm, multivariate_normal
    za, zb = norm.ppf(1 - p_a), norm.ppf(1 - p_b)
    lo, hi = -0.95, 0.95
    for _ in range(60):
        mid = (lo + hi) / 2
        v = float(multivariate_normal(mean=[0, 0],
                                      cov=[[1, mid], [mid, 1]]).cdf([-za, -zb]))
        if v < p_joint:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--limit", type=int, default=None,
                    help="only the N soonest events (smoke testing)")
    ap.add_argument("--status", action="store_true", help="show what is stored")
    a = ap.parse_args()
    con = sqlite3.connect(DB)
    _ddl(con)
    if a.status:
        for q, lbl in (("SELECT COUNT(*), MAX(collected_at) FROM sgp_legs", "legs"),
                       ("SELECT COUNT(*), MAX(collected_at) FROM sgp_prices", "prices")):
            n, t = con.execute(q).fetchone()
            print(f"  {lbl:<7} rows={n or 0}  latest={t or 'never'}")
        for stat, n in con.execute(
                "SELECT stat, COUNT(*) FROM sgp_legs GROUP BY stat ORDER BY 2 DESC"):
            print(f"      {stat:<12} {n}")
        return
    collect_legs(con, limit=a.limit)
    con.close()


if __name__ == "__main__":
    main()
