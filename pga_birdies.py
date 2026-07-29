"""⛳ BIRDIES-OR-BETTER pricer — orchestrator hole-by-hole data -> par-split rates -> exact
Poisson-binomial round distributions.

DATA: pgatour orchestrator GraphQL (public x-api-key), verified from this box:
schedule -> leaderboardV2 -> scorecardV3(tournamentId, playerId) gives every hole's par and
score. Harvest is resumable ((tid, player) primary key), polite (4 workers, throttled), and
cached forever in pga_model.sqlite — a season is ~4.5k queries once, then only new events.

MODEL: per-player per-hole birdie-or-better rate SPLIT BY PAR (par-5s birdie ~3x par-4s, so
course mix matters), shrunk empirical-Bayes toward the field rate by K_H pseudo-holes.
A round is 18 independent Bernoulli holes at the course's par mix -> the birdie-count
distribution comes from an exact DP (no normal approximation at n=18).

GATE, stated plainly: FanDuel's birdies market has produced ZERO rows in our collector so
far (the $2,880-limit market the user sees in-app is not on the pages we sweep — a
discovery trap in golf_collect now hunts it). With no captured closes there is NOTHING to
calibrate against, so this pricer is PREVIEW-ONLY BY CONSTRUCTION: birdie_gate() returns
not-armed until >=15 settled FD birdie closes grade within 2pts logloss — same law as G2.
"""
import datetime as dt
import json
import sqlite3
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "pga_model.sqlite"
KEY = "da2-gsrx5bibzbb4njvhl7t37wqyl4"
K_H = 60.0                      # pseudo-holes of shrinkage toward the field rate
DEFAULT_MIX = {3: 4, 4: 10, 5: 4}

DDL = """CREATE TABLE IF NOT EXISTS birdie_rounds(
    tid TEXT, tname TEXT, player TEXT, rnd INTEGER,
    p3h INTEGER, p3b INTEGER, p4h INTEGER, p4b INTEGER, p5h INTEGER, p5b INTEGER,
    PRIMARY KEY(tid, player, rnd))"""


def gql(query, variables=None, tries=3):
    for a in range(tries):
        try:
            req = urllib.request.Request(
                "https://orchestrator.pgatour.com/graphql",
                data=json.dumps({"query": query, "variables": variables or {}}).encode(),
                headers={"Content-Type": "application/json", "x-api-key": KEY,
                         "User-Agent": "Mozilla/5.0"})
            return json.load(urllib.request.urlopen(req, timeout=30))
        except Exception:                                     # noqa: BLE001
            time.sleep(0.6 * (a + 1))
    return {}


def completed_tournaments():
    d = gql('{schedule(tourCode: "R") {completed {tournaments {id tournamentName}}}}')
    out = []
    for grp in (d.get("data", {}).get("schedule", {}) or {}).get("completed") or []:
        for t in grp.get("tournaments") or []:
            if str(t.get("id", "")).startswith("R2026"):
                out.append((t["id"], t["tournamentName"]))
    return out


def players_of(tid):
    d = gql('query L($id: ID!) {leaderboardV2(id: $id) {players '
            '{... on PlayerRowV2 {player {id displayName}}}}}', {"id": tid})
    return [(p["player"]["id"], p["player"]["displayName"])
            for p in (d.get("data", {}).get("leaderboardV2", {}) or {}).get("players") or []
            if p and p.get("player")]


def scorecard_rows(tid, tname, pid, pname):
    d = gql('query S($t: ID!, $p: ID!) {scorecardV3(tournamentId: $t, playerId: $p) '
            '{roundScores {roundNumber ... on RoundScore {firstNine {holes {par score}} '
            'secondNine {holes {par score}}}}}}', {"t": tid, "p": pid})
    rows = []
    for rs in (d.get("data", {}).get("scorecardV3", {}) or {}).get("roundScores") or []:
        holes = (((rs.get("firstNine") or {}).get("holes") or []) +
                 ((rs.get("secondNine") or {}).get("holes") or []))
        agg = {3: [0, 0], 4: [0, 0], 5: [0, 0]}
        for h in holes:
            par = h.get("par")
            try:
                sc = int(h.get("score"))
            except (TypeError, ValueError):
                continue
            if par in agg and sc > 0:
                agg[par][0] += 1
                if sc < par:
                    agg[par][1] += 1
        if sum(v[0] for v in agg.values()) >= 15:              # a real completed round
            rows.append((tid, tname, pname, rs.get("roundNumber") or 0,
                         agg[3][0], agg[3][1], agg[4][0], agg[4][1], agg[5][0], agg[5][1]))
    return rows


def harvest(max_events=None):
    con = sqlite3.connect(DB)
    con.execute(DDL)
    done = {r[0] for r in con.execute("SELECT DISTINCT tid FROM birdie_rounds")}
    evs = [e for e in completed_tournaments() if e[0] not in done]
    if max_events:
        evs = evs[:max_events]
    print(f"harvest: {len(evs)} new events (of {len(completed_tournaments())} completed 2026)")
    for tid, tname in evs:
        ps = players_of(tid)
        rows = []

        def one(a):
            time.sleep(0.12)                                   # politeness
            return scorecard_rows(tid, tname, *a)
        with ThreadPoolExecutor(max_workers=4) as ex:
            for rr in ex.map(one, ps):
                rows += rr
        con.executemany("INSERT OR REPLACE INTO birdie_rounds VALUES (?,?,?,?,?,?,?,?,?,?)",
                        rows)
        con.commit()
        print(f"  {tname}: {len(ps)} players, {len(rows)} rounds", flush=True)
    n = con.execute("SELECT COUNT(*), COUNT(DISTINCT player) FROM birdie_rounds").fetchone()
    print(f"birdie_rounds: {n[0]} rows, {n[1]} players")
    con.close()


def rates():
    """{player: {par: shrunk_rate}} + field rates. Recency not weighted in v1 — birdie
    ability is stabler than form, and 2026-only data is already a form window."""
    con = sqlite3.connect(DB)
    field = {3: [0, 0], 4: [0, 0], 5: [0, 0]}
    per = {}
    for pl, p3h, p3b, p4h, p4b, p5h, p5b in con.execute(
            "SELECT player, SUM(p3h), SUM(p3b), SUM(p4h), SUM(p4b), SUM(p5h), SUM(p5b) "
            "FROM birdie_rounds GROUP BY player"):
        per[pl] = {3: (p3h, p3b), 4: (p4h, p4b), 5: (p5h, p5b)}
        for par, (h, b) in per[pl].items():
            field[par][0] += h
            field[par][1] += b
    con.close()
    frate = {par: (b / h if h else 0.15) for par, (h, b) in field.items()}
    out = {}
    for pl, agg in per.items():
        out[pl] = {par: (b + K_H * frate[par]) / (h + K_H) for par, (h, b) in agg.items()}
    return out, frate


def p_x_or_more(player_rates, k_target, mix=None):
    """Exact P(birdies-or-better >= k) in one round via DP over the course's par mix."""
    mix = mix or DEFAULT_MIX
    probs = []
    for par, cnt in mix.items():
        probs += [player_rates.get(par, 0.15)] * cnt
    dist = [1.0]
    for p in probs:
        nxt = [0.0] * (len(dist) + 1)
        for i, v in enumerate(dist):
            nxt[i] += v * (1 - p)
            nxt[i + 1] += v * p
        dist = nxt
    return sum(dist[int(k_target):])


def birdie_gate():
    """Armed only after >=15 SETTLED FanDuel birdie closes grade within 2pts logloss of the
    devig. Zero birdie rows have ever been captured, so: not armed, and says why."""
    con = sqlite3.connect(HERE / "golf_lines.sqlite")
    n = con.execute("SELECT COUNT(*) FROM golf_lines WHERE mtype LIKE '%BIRD%' "
                    "OR market LIKE '%irdie%'").fetchone()[0]
    con.close()
    return False, n


if __name__ == "__main__":
    import sys
    if "--harvest" in sys.argv:
        harvest()
    R, fr = rates()
    if R:
        print(f"rates: {len(R)} players | field per-hole birdie-or-better: "
              f"p3 {fr[3]:.3f}  p4 {fr[4]:.3f}  p5 {fr[5]:.3f}")
        best = sorted(R.items(),
                      key=lambda kv: -(4 * kv[1][3] + 10 * kv[1][4] + 4 * kv[1][5]))[:5]
        for pl, rr in best:
            exp = 4 * rr[3] + 10 * rr[4] + 4 * rr[5]
            print(f"   {pl:<24} E[birdies/round] {exp:.2f}   "
                  f"P(4+) {p_x_or_more(rr, 4):.1%}   P(5+) {p_x_or_more(rr, 5):.1%}")
    armed, n_mkt = birdie_gate()
    print(f"gate: {'ARMED' if armed else 'NOT armed'} — FD birdie rows captured ever: {n_mkt}")
