"""⛳ pga_sg_rounds — per-ROUND strokes gained, the follow-up pga_sg.py was kept alive for.

SEASON-level SG was tested twice and is a recorded null (pga_sg.py header 2026-07-30; learn-engine
registry 2026-08-03): partials over SG_TOT ~zero, every ruler blend hurt, r <= +0.021 against the
de-conditioned residual on 42k player-rounds. The reason was granularity — our rating is built from
ROUND-level scores, so a season aggregate is strictly coarser than what the model already knows.

THIS harvests the fine-grained version: scorecardStatsV3(id, playerId) returns per-round SG in all
four categories for one (tournament, player). Verified live 2026-08-03 (Cantlay, Rocket Classic:
R3 putting -2.502 in his collapse round, R4 approach +3.435). One query per player-tournament, so a
season is ~2-3k queries — bounded, resumable, and idempotent.

WHAT IT IS FOR — one pre-registered question, so this cannot drift into a fishing trip:
    Does a player's RECENT per-round SG decomposition (e.g. approach form over the last K rounds,
    putting excluded as noise) predict the next round's de-conditioned residual where total-score
    form (H-P1, r=+0.012, null) does not?
The learn engine owns that test once data lands; this file only collects.

PLAYER IDS come from sg_stats (the season harvest already mapped 305 regulars to PGA ids). A player
without a mapping is SKIPPED AND COUNTED, never guessed — a wrong pid silently harvests someone
else's rounds, which is the name-join corruption class again.
"""
import datetime as dt
import sqlite3
import sys
import time
from pathlib import Path

import pga_birdies as B

HERE = Path(__file__).resolve().parent
DB = HERE / "pga_model.sqlite"
D = chr(36)

DDL = """CREATE TABLE IF NOT EXISTS sg_rounds(
    tid TEXT, player_id TEXT, player TEXT, rnd INTEGER,
    sg_ott REAL, sg_app REAL, sg_arg REAL, sg_putt REAL, sg_tot REAL,
    fetched TEXT, PRIMARY KEY(tid, player_id, rnd))"""

Q = ("query S(%si: ID!, %sp: ID!){scorecardStatsV3(id: %si, playerId: %sp)"
     "{id rounds{round strokesGained{shortLabel totalNum}}}}" % (D, D, D, D))

# shortLabel -> column. 'Total' kept as a coherence check (ott+app+arg+putt should ~= tot).
_LBL = {"Off The Tee": "sg_ott", "Approach to Green": "sg_app",
        "Around The Green": "sg_arg", "Putting": "sg_putt", "Total": "sg_tot"}


def _norm(n):
    return " ".join(str(n or "").lower().replace(".", "").split())


def harvest(season=None, sleep=0.35, verbose=True):
    """Fetch per-round SG for every (tid, mapped player) pair not already stored.

    `season`: restrict to tids of one season (e.g. 2026 -> tids starting 'R2026'); None = all.
    Resumable by construction: (tid, player_id) pairs with ANY stored round are skipped, so a
    killed run continues where it stopped instead of refetching.
    """
    con = sqlite3.connect(DB)
    con.execute(DDL)
    con.commit()

    # name -> pid from the season-SG harvest; skip-and-count on misses, never guess.
    pids = {_norm(p): (i, p) for i, p in con.execute(
        "SELECT DISTINCT player_id, player FROM sg_stats")}

    want = {}
    q = "SELECT DISTINCT tid, player FROM birdie_rounds"
    if season:
        q += " WHERE tid LIKE 'R%d%%'" % int(season)
    for tid, player in con.execute(q):
        hit = pids.get(_norm(player))
        if hit:
            want.setdefault(str(tid), {})[hit[0]] = hit[1]

    have = {(t, p) for t, p in con.execute(
        "SELECT DISTINCT tid, player_id FROM sg_rounds")}

    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    total_pairs = sum(len(v) for v in want.values())
    done = wrote = errs = 0
    unmapped = len({_norm(p) for _, p in con.execute(q)} - set(pids))
    if verbose:
        print("sg_rounds: %d tournaments, %d mapped pairs to check (%d already stored, "
              "%d player names unmapped -> skipped)"
              % (len(want), total_pairs, len(have), unmapped), flush=True)

    for tid, players in sorted(want.items(), reverse=True):     # newest seasons first
        for pid, pname in players.items():
            if (tid, pid) in have:
                continue
            done += 1
            try:
                d = B.gql(Q, {"i": tid, "p": pid})
                rounds = ((d.get("data") or {}).get("scorecardStatsV3") or {}).get("rounds") or []
            except Exception as e:                              # noqa: BLE001
                errs += 1
                if verbose and errs <= 5:
                    print("   %s %s: %s" % (tid, pname, str(e)[:60]), flush=True)
                time.sleep(sleep * 3)
                continue
            rows = []
            for r in rounds:
                try:
                    rnd = int(r.get("round"))
                except (TypeError, ValueError):
                    continue
                if rnd < 1:
                    continue                                    # -1 = tournament aggregate
                vals = {}
                for sgd in (r.get("strokesGained") or []):
                    col = _LBL.get(sgd.get("shortLabel"))
                    if col is not None and sgd.get("totalNum") is not None:
                        vals[col] = float(sgd["totalNum"])
                if vals:
                    rows.append((tid, pid, pname, rnd, vals.get("sg_ott"), vals.get("sg_app"),
                                 vals.get("sg_arg"), vals.get("sg_putt"), vals.get("sg_tot"), now))
            if rows:
                con.executemany("INSERT OR REPLACE INTO sg_rounds VALUES (?,?,?,?,?,?,?,?,?,?)",
                                rows)
                con.commit()
                wrote += len(rows)
            if verbose and done % 100 == 0:
                print("   ... %d/%d pairs, %d round-rows, %d errors"
                      % (done, total_pairs - len(have), wrote, errs), flush=True)
            time.sleep(sleep)

    print("sg_rounds: fetched %d pairs, wrote %d round-rows, %d errors -> %s"
          % (done, wrote, errs, DB), flush=True)
    con.close()
    return wrote


if __name__ == "__main__":
    yr = int(sys.argv[1]) if len(sys.argv) > 1 else None
    sys.exit(0 if harvest(season=yr) >= 0 else 1)
