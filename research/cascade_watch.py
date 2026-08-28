#!/usr/bin/env python3
"""CASCADE DRIFT WATCH — research-only, writes nothing production reads.

THE OBSERVATION (2026-08-28): every CON flag for the 08-28 slate was written in one burst at
08-27T20:46-47 off a Griner-only cascade. Olivia Nelson-Ododa was still a bet CANDIDATE at
08-28T03:59, was later ruled Out, and passes every cascade gate when tested directly — yet no CON
flag was ever updated to include her, while other teams were flagged fresh on 08-28.

So a team-slate that has ALREADY been flagged appears not to re-price when its cascade deepens.
That is the strongest version of the model's own thesis (a second starter out) being missed.

⚠️ NOT PATCHING PRODUCTION ON THAT HYPOTHESIS. The game had already tipped when it was found, so
it could not be reproduced live. This records, every cycle, the feed's out-set per team versus the
cascade the ledger actually used — with timestamps — so the next divergence is caught BEFORE tip
with evidence instead of inference.

Writes research/cascade_watch.sqlite. Imported by nothing."""
import datetime as dt
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
DB = HERE / "cascade_watch.sqlite"



_DATES = {}


def _played_dates(name, pl, W):
    """Dates a player logged real minutes. Cached — the scan asks repeatedly."""
    if name not in _DATES:
        p = pl.get(name)
        try:
            lg = (W.game_log(p["id"]) or []) if p else []
        except Exception:                                             # noqa: BLE001
            lg = []
        _DATES[name] = {str(g.get("date"))[:10] for g in lg if (g.get("min") or 0) > 0}
    return _DATES[name]


def main():
    import wnba_tonight as T
    import wnba_wowy as W

    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    con = sqlite3.connect(DB, timeout=60)
    con.execute("PRAGMA busy_timeout=60000")
    con.execute("""CREATE TABLE IF NOT EXISTS watch(
        seen_at TEXT, slate TEXT, team TEXT, hrs_to_tip REAL,
        feed_outs TEXT, ledger_outs TEXT, drift INTEGER,
        PRIMARY KEY(slate, team, feed_outs, ledger_outs))""")

    try:
        inj = T.injuries()
        pl = W.players()
        tips = T.tip_times()
    except Exception as e:                                            # noqa: BLE001
        print(f"cascade_watch: source unavailable ({str(e)[:60]}) — REFUSING to record a false zero")
        return

    # the feed's view: who is a firm, impact out per team (mirrors wnba_alert.py:174-186)
    feed = {}
    for name, status in inj.items():
        p = pl.get(name)
        if not p or status not in ("Out", "Doubtful"):
            continue
        try:
            if T.confirmed_playing(name, p["team"]) or not T.genuinely_out(name):
                continue
        except Exception:                                             # noqa: BLE001
            continue
        if p.get("min", 0) >= 20 or p.get("pts", 0) >= 10:
            feed.setdefault(p["team"], set()).add(name)

    def _n_without(ben, outs):
        """Games the beneficiary played with NONE of `outs` available — production's n_without."""
        s_ = set(_played_dates(ben, pl, W))
        for o in outs:
            s_ -= _played_dates(o, pl, W)
        return len(s_)

    slate = dt.datetime.now(dt.timezone(dt.timedelta(hours=-4))).date().isoformat()
    led = sqlite3.connect(f"file:{ROOT/'wnba_ledger.sqlite'}?mode=ro", uri=True, timeout=30)
    ledger = {}
    for team, outs in led.execute(
            "SELECT team, out_player FROM predictions WHERE pred_date=?", (slate,)):
        if team:
            ledger.setdefault(team, set()).update(
                x.strip() for x in str(outs or "").split(",") if x.strip())
    led.close()

    beneficiaries = {}
    led2 = sqlite3.connect(f"file:{ROOT/'wnba_ledger.sqlite'}?mode=ro", uri=True, timeout=30)
    for team, who in led2.execute(
            "SELECT team, player FROM predictions WHERE pred_date=?", (slate,)):
        if team:
            beneficiaries.setdefault(team, set()).add(who)
    led2.close()

    rows, drifts = [], 0
    for team, fouts in sorted(feed.items()):
        if team not in tips:
            continue                                   # not playing today
        try:
            t = tips[team]
            t = t if isinstance(t, dt.datetime) else dt.datetime.fromisoformat(str(t))
            if t.tzinfo is None:
                t = t.replace(tzinfo=dt.timezone.utc)
            hrs = (t - dt.datetime.now(dt.timezone.utc)).total_seconds() / 3600.0
        except Exception:                                             # noqa: BLE001
            hrs = None
        louts = ledger.get(team, set())
        # DRIFT = the feed knows an impact out the cascade never used, BEFORE tip, AND the
        # beneficiary would STILL have a usable sample with it included.
        #
        # ⚠️ THE NAIVE VERSION (feed_outs - ledger_outs) IS WRONG AND CRIED WOLF IMMEDIATELY.
        # wnba_alert.py:368 trims the cascade when `n_without < 2` — with six TOR outs on
        # 2026-08-28, Isabelle Harrison had ZERO games without all six, so the model correctly
        # shrank to three (n_without=4). That is the gate working, not a fault. A monitor that
        # reports correct behaviour as a failure trains you to ignore it.
        #
        # So an out is only "missing" if adding it back keeps n_without >= 2. Anything the sample
        # cannot support is EXPECTED TRIMMING and is recorded, not flagged.
        missing = set()
        for cand in (fouts - louts):
            for ben in beneficiaries.get(team, ()):
                if _n_without(ben, louts | {cand}) >= 2:
                    missing.add(cand)
                    break
        # NOT a fault flag. n_without=2 merely PASSES the gate; the model appears to prefer a
        # deeper sample over a deeper cascade (TOR 2026-08-28: it took 3 outs at n_without=4 when
        # 4 outs at n_without=2 also qualified). Recorded as an open question about cascade DEPTH,
        # never paged on — the gate is working either way.
        drift = 1 if (missing and louts and hrs is not None and hrs > 0) else 0
        drifts += drift
        rows.append((now, slate, team, round(hrs, 2) if hrs is not None else None,
                     ",".join(sorted(fouts)), ",".join(sorted(louts)), drift))
        if drift:
            print(f"  SHALLOW {team}: cascade omits {sorted(missing)} though the sample supports it "
                  f"({hrs:.2f}h before tip) — a DEPTH CHOICE, not a fault")
    con.executemany("INSERT OR IGNORE INTO watch VALUES(?,?,?,?,?,?,?)", rows)
    con.commit()
    n = con.execute("SELECT COUNT(*) FROM watch").fetchone()[0]
    d = con.execute("SELECT COUNT(*) FROM watch WHERE drift=1").fetchone()[0]
    con.close()
    print(f"cascade_watch: {len(rows)} teams checked, {drifts} drifting now; "
          f"table holds {n} snapshots, {d} drift records")


if __name__ == "__main__":
    main()
