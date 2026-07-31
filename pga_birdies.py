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
import math
import sqlite3
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "pga_model.sqlite"
KEY = "da2-gsrx5bibzbb4njvhl7t37wqyl4"
DISPERSION = 0.552              # MEASURED 2026-07-30 out of sample. The model separated
                                # players 1.81x more than reality: reliability slope of
                                # realized on predicted = 0.552 over 19,942 leak-free
                                # player-rounds (early-half rates -> late-half rounds), and
                                # independently our sd of P(over) was 1.81x the devigged
                                # market's with r=0.664. 1/0.552 = 1.81 — the two agree, so
                                # the spread was noise and the market's was right. Applied to
                                # the per-par rate DEVIATION from the field, because K_H
                                # shrinks the rate under a binomial-noise assumption while
                                # birdie counts are over-dispersed (correlated holes) AND
                                # P(>=k) over 18 holes amplifies small rate gaps.
K_H = 106.0                     # MEASURED 2026-07-29 (was 60.0 flat). Per-par, because
                                # birdie skill separates players very differently by par:
K_H_PAR = {3: 593.0, 4: 106.0, 5: 162.0}
# Empirical Bayes on binomial noise p(1-p) over true between-player variance, players with
# >=40 holes of that par:
#   par 3: field p=0.133, true between-player var 0.0002 (sd 1.4 percentage points) -> k=593
#   par 4: field p=0.175, true var 0.0014 -> k=106
#   par 5: field p=0.470, true var 0.0015 -> k=162
# Par-3 birdie ability is almost entirely luck — nearly a tenth of what 60 assumed — while
# par 4s carry most of the real signal. A flat 60 over-trusted par 3s badly.
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


def completed_tournaments(year=None):
    """Completed events for a season. `schedule` takes a year argument, which is what makes
    the 2024-25 backfill possible — v1 hard-coded the R2026 prefix and could only ever see
    the current season, so every course birdie factor had to come through the bridge."""
    q = ('{schedule(tourCode: "R"%s) {completed {tournaments {id tournamentName}}}}'
         % ((', year: "%d"' % int(year)) if year else ""))
    d = gql(q)
    pref = "R%d" % int(year) if year else "R2026"
    out = []
    for grp in (d.get("data", {}).get("schedule", {}) or {}).get("completed") or []:
        for t in grp.get("tournaments") or []:
            if str(t.get("id", "")).startswith(pref):
                out.append((t["id"], t["tournamentName"]))
    return out


def upcoming_tournaments(year=None):
    """Upcoming events — the bettable ones, and the tee sheets worth polling."""
    q = ('{schedule(tourCode: "R"%s) {upcoming {tournaments {id tournamentName}}}}'
         % ((', year: "%d"' % int(year)) if year else ""))
    d = gql(q)
    out = []
    for grp in (d.get("data", {}).get("schedule", {}) or {}).get("upcoming") or []:
        for t in grp.get("tournaments") or []:
            if t.get("id"):
                out.append((t["id"], t.get("tournamentName") or ""))
    return out


def players_of(tid):
    """[] for any event without a modelled leaderboard (team formats, abandoned events) —
    a skip, not a crash: one odd event must not cost an entire season backfill."""
    d = gql('query L($id: ID!) {leaderboardV2(id: $id) {players '
            '{... on PlayerRowV2 {player {id displayName}}}}}', {"id": tid})
    lb = (d.get("data") or {}).get("leaderboardV2") or {}
    return [(p["player"]["id"], p["player"]["displayName"])
            for p in (lb.get("players") or [])
            if p and p.get("player") and p["player"].get("id")]


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


def harvest(max_events=None, years=(2026,)):
    """Default stays 2026 so the loop's behaviour is unchanged; pass years=(2024, 2025) for
    the backfill. Idempotent by tid, so re-running only fetches what is missing."""
    con = sqlite3.connect(DB)
    con.execute(DDL)
    done = {r[0] for r in con.execute("SELECT DISTINCT tid FROM birdie_rounds")}
    allev = []
    for yr in years:
        allev += completed_tournaments(year=yr)
    evs = [e for e in allev if e[0] not in done]
    if max_events:
        evs = evs[:max_events]
    print(f"harvest: {len(evs)} new events (of {len(allev)} completed in {list(years)})")
    for tid, tname in evs:
        try:
            ps = players_of(tid)
        except Exception as e:                                      # noqa: BLE001
            print(f"  {tname}: leaderboard unavailable ({str(e)[:40]}) - skipped", flush=True)
            continue
        if not ps:
            print(f"  {tname}: no player rows - skipped", flush=True)
            continue
        rows = []

        def one(a):
            time.sleep(0.12)                                   # politeness
            return scorecard_rows(tid, tname, *a)
        with ThreadPoolExecutor(max_workers=4) as ex:
            for rr in ex.map(one, ps):
                rows += rr
        for attempt in range(6):
            try:
                con.executemany(
                    "INSERT OR REPLACE INTO birdie_rounds VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
                con.commit()
                break
            except sqlite3.OperationalError as e:
                # the loop's `git reset --hard` briefly swaps this tracked DB under us and
                # sqlite reports it readonly. Reconnect and retry rather than losing an
                # entire backfill run to a one-second window.
                if attempt == 5:
                    raise
                print(f"  write retry {attempt + 1} ({str(e)[:40]})", flush=True)
                time.sleep(2.0 * (attempt + 1))
                try:
                    con.close()
                except Exception:                                  # noqa: BLE001
                    pass
                con = sqlite3.connect(DB, timeout=30)
                con.execute(DDL)
        print(f"  {tname}: {len(ps)} players, {len(rows)} rounds", flush=True)
    n = con.execute("SELECT COUNT(*), COUNT(DISTINCT player) FROM birdie_rounds").fetchone()
    print(f"birdie_rounds: {n[0]} rows, {n[1]} players")
    con.close()


# ── H-P1: within-tournament form (2026-07-31) ───────────────────────────────────────────────
# A player's residual in one round carries to the next at r=+0.152, measured on 42,557
# player-rounds / 114 events after removing round-level conditions, with leave-one-event-out
# baselines and a cross-event null of -0.005 (R1->R2 +0.150, R2->R3 +0.156, R3->R4 +0.156).
# Residual sd is 1.79 birdies per 18, so this moves a projection ~0.27 birdies.
# ⚠️ REFUTED 2026-07-31, hours after it shipped. Set to 0.0 — H-P1 is DISABLED.
# The +0.152 that justified it was de-conditioned at the ROUND level only. Event factors range
# 0.81-1.24, so a week playing easy against a player's history lifts ALL their residuals that week
# and R1 "predicts" R2 for reasons unrelated to form. Removing the EVENT level too:
#     round-only de-conditioning : r=+0.152, within-event null +0.145   <- the null gives it away
#     round + event (correct)    : r=+0.012, within-event null +0.006   <- 0.019 birdies per 18
# The original cross-event null (-0.005) could not catch it: pairing across DIFFERENT events breaks
# the shared week level as well as player identity, so it tested a weaker claim than it looked like.
# The correct null shuffles WITHIN an event — identity dies, the week survives.
# Machinery kept rather than deleted: this idea is intuitive and WILL be proposed again, and the
# refutation belongs where the next person looks. Re-enabling must be a deliberate act.
FORM_R = 0.0            # was 0.152; see above. 0.0 disables the H-P1 shift entirely
FORM_MIN_HOLES = 15     # need a real completed round before trusting a residual


def live_rounds(tid, tname, cache={}):
    """This event's COMPLETED rounds, fetched live — the weekly harvest does not have them.

    Returns {player: (holes, birdies)} aggregated over every completed round so far. Cached per
    tid+round-count so a */30 cron does not re-pull 148 scorecards every pass. Any failure returns
    {} and H-P1 simply does not fire: a missing fetch must never change a price silently.
    """
    key = str(tid)
    if key in cache:
        return cache[key]
    out = {}
    try:
        for pid, pname in players_of(tid):
            try:
                for row in scorecard_rows(tid, tname, pid, pname):
                    _, _, pn, _rnd, p3h, p3b, p4h, p4b, p5h, p5b = row
                    h, b = out.get(pn, (0, 0))
                    out[pn] = (h + p3h + p4h + p5h, b + p3b + p4b + p5b)
            except Exception:                                       # noqa: BLE001
                continue
    except Exception:                                               # noqa: BLE001
        out = {}
    cache[key] = out
    return out


def rates(course_factor=1.0, wind_kmh=None, half_life_d=120.0, course_name=None,
          live_tid=None, live_tname=None):
    """{player: {par: rate}} + field rates, with RECENCY WEIGHTING and context.

    course_factor  multiplies every rate (1.0 = neutral). Comes from pga_context, which
                   measured a 0.78x-1.29x spread between courses BEYOND their par mix —
                   larger than any player edge, so pricing a course as average was the
                   single biggest error in the v1 birdie model.
    wind_kmh       shades rates by pga_context.wind_factor for the player's exposure.
    half_life_d    recency weight on rounds. v1 was unweighted on the theory that birdie
                   ability is stabler than form; that is a claim, not a finding, and the
                   ruler already weights, so the two now agree.
    """
    con = sqlite3.connect(DB)
    field = {3: [0.0, 0.0], 4: [0.0, 0.0], 5: [0.0, 0.0]}
    per = {}
    # recency weight per event = 0.5 ** (age_days / half_life); event date via rounds table
    ed = {}
    try:
        for tid, tn in con.execute("SELECT DISTINCT tid, tname FROM birdie_rounds"):
            r = con.execute("SELECT MIN(date) FROM rounds WHERE LOWER(event) LIKE ?",
                            ("%" + str(tn or "")[:14].lower() + "%",)).fetchone()
            ed[tid] = (r or [None])[0]
    except Exception:                                              # noqa: BLE001
        pass
    today = dt.date.today()
    acc = {}
    for tid, pl, p3h, p3b, p4h, p4b, p5h, p5b in con.execute(
            "SELECT tid, player, SUM(p3h), SUM(p3b), SUM(p4h), SUM(p4b), SUM(p5h), SUM(p5b) "
            "FROM birdie_rounds GROUP BY tid, player"):
        # H-P1: the current event must never inform its own baseline, or the residual is measured
        # against a number that already contains it and shrinks toward zero (the same
        # leave-one-event-out discipline the measurement used).
        if live_tid and str(tid) == str(live_tid):
            continue
        w = 1.0
        d = ed.get(tid)
        if d:
            try:
                w = 0.5 ** (max((today - dt.date.fromisoformat(d)).days, 0) / half_life_d)
            except ValueError:
                w = 1.0
        a = acc.setdefault(pl, {3: [0.0, 0.0], 4: [0.0, 0.0], 5: [0.0, 0.0]})
        for par, (h, b) in ((3, (p3h, p3b)), (4, (p4h, p4b)), (5, (p5h, p5b))):
            a[par][0] += (h or 0) * w
            a[par][1] += (b or 0) * w
            field[par][0] += (h or 0) * w
            field[par][1] += (b or 0) * w
    for pl, a in acc.items():
        per[pl] = {par: (v[0], v[1]) for par, v in a.items()}
    con.close()
    frate = {par: (b / h if h else 0.15) for par, (h, b) in field.items()}
    ctx = float(course_factor or 1.0)
    if wind_kmh is not None:
        try:
            import pga_context as _C
            ctx *= _C.wind_factor(wind_kmh)
        except Exception:                                          # noqa: BLE001
            pass
    # COURSE BASELINE (2026-07-30). Par-class difficulty is strongly course-specific (par-5
    # .325-.624 across 56 courses vs a global .470), and using the global rate made P(>=k)
    # over-respond to par mix — the whole reason the birdie reliability slope sat at 0.617.
    # With the course's own baseline it measures 1.059. Player skill is applied MULTIPLICATIVELY
    # so the baseline carries the mix.
    base = frate
    if course_name:
        cr = course_par_rates()
        ck = _ckey(course_name)
        if ck in cr:
            base = cr[ck]
    out = {}
    for pl, agg in per.items():
        row = {}
        for par, (h, b) in agg.items():
            kh = K_H_PAR.get(par, K_H)
            r_ = (b + kh * frate[par]) / (h + kh)
            # DISPERSION CORRECTION: pull the deviation from the field toward the field by the
            # measured out-of-sample factor. Without this the model separated players 1.81x
            # more than reality and every flagged birdie edge was a tail artefact.
            r_ = frate[par] + DISPERSION * (r_ - frate[par])
            # express the player as a multiplier on THIS course's rate, not an absolute rate
            mult = (r_ / frate[par]) if frate[par] > 0 else 1.0
            row[par] = min(base[par] * mult * ctx, 0.95)
        out[pl] = row

    # ── H-P1 FORM SHIFT (2026-07-31) ────────────────────────────────────────────────────────
    # A player's residual in one round carries to the next at r=+0.152 (42,557 player-rounds /
    # 114 events, round-level conditions removed, leave-one-event-out baselines, cross-event null
    # -0.005). The baseline above already excludes live_tid, so `actual - expected` here is a
    # clean residual rather than one measured against a number containing itself.
    #
    # The field's OWN rate this week carries the conditions (wind, pins, setup) — the same
    # de-conditioning the measurement used — so expected() is the player's multiplier applied to
    # what the field actually did, not to a historical average.
    #
    # Fully guarded: any failure leaves `out` untouched. A missing fetch must never move a price.
    if live_tid and FORM_R:
        try:
            live = live_rounds(live_tid, live_tname or "")
            usable = {p: (h, b) for p, (h, b) in live.items() if h >= FORM_MIN_HOLES}
            th = sum(h for h, _ in usable.values())
            tb = sum(b for _, b in usable.values())
            if th >= FORM_MIN_HOLES * 10 and tb > 0:
                field_now = tb / th                      # conditions, straight from the field
                field_hist = sum(frate.values()) / len(frate) if frate else field_now
                n_shift = 0
                for pl, (h, b) in usable.items():
                    row = out.get(pl)
                    if not row:
                        continue
                    mult = ((sum(row.values()) / len(row)) / field_hist) if field_hist > 0 else 1.0
                    expected = mult * field_now
                    resid = (b / h) - expected
                    shift = FORM_R * resid
                    if abs(shift) < 1e-6:
                        continue
                    out[pl] = {par: max(min(v + shift, 0.95), 0.01) for par, v in row.items()}
                    n_shift += 1
                print(f"  H-P1 form: {n_shift} players shifted "
                      f"(field {field_now:.4f}/hole over {th} holes, r={FORM_R})")
        except Exception as _fe:                                    # noqa: BLE001
            print(f"  H-P1 form: skipped ({str(_fe)[:60]})")

    return out, {par: min(base[par] * ctx, 0.95) for par in frate}


# ---------------------------------------------------------------------------
# COURSE STRUCTURE (2026-07-29). v1 priced EVERY course as par-72 4/10/4, which
# over-counted par-5s (47% birdie rate each) at every shorter venue — Detroit GC is
# par 70, so v1 handed players two phantom par-5s and ran +11.3pts hot on every Over.
# The par->mix rule is VALIDATED against the harvest's own hole counts:
#     par 72 -> 4/10/4 (8/8 events)   par 71 -> 4/11/3 (4/5)   par 70 -> 4/12/2
# Exact hole pars are used whenever the event is in our harvest; the rule is the
# fallback for an UPCOMING course (which is the case that matters for betting).
PAR_MIX_RULE = {70: {3: 4, 4: 12, 5: 2}, 71: {3: 4, 4: 11, 5: 3},
                72: {3: 4, 4: 10, 5: 4}, 73: {3: 3, 4: 11, 5: 4}}
# RE-VALIDATED 2026-07-29 on 114 harvested events (the rule was set on 8 and 5):
#   par 70 -> (4,12,2) in 21/27 events (78%)
#   par 71 -> (4,11,3) in 35/41 (85%)
#   par 72 -> (4,10,4) in 42/44 (95%)
#   par 73 -> (3,11,4) in 2/2  <- CORRECTED from the assumed (4,9,5). n=2 is thin, but an
#             observed mix beats an invented one, and this is only the fallback for a course
#             with no hole data at all — rare now that 114 events are harvested.


PHI_ROUND = 0.0233              # MEASURED 2026-07-30 on 39,722 player-rounds: per-round shared
                                # day factor, Var(theta)=PHI (theta sd 15.3%). Rounds are NOT
                                # independent hole-by-hole — a soft calm day lifts every hole.
                                # Secondary to the course-par fix (0.608->0.644 on its own) but
                                # real, and it widens the count distribution correctly.
CPAR_K = 400.0                  # holes of shrinkage of a course's par rates toward global. Keeps a
                                # thin course, or one that was RECONFIGURED (Detroit 2026 moved
                                # courseId 876->947, par 72->70), from being trusted outright.


def _ckey(tname):
    """Course key: sorted distinctive tokens, so editions of one venue pool together."""
    return " ".join(sorted(w for w in str(tname or "").lower().split() if len(w) > 3))


def course_par_rates(cache={}):
    """{course_key: {par: birdie rate}} measured per COURSE, shrunk toward the global rate.

    Par-class difficulty is strongly course-specific (par-5 ranges .325-.624 across 56 courses vs
    a global .470). Using the global rate made P(>=k) over-respond to par mix and was the whole
    reason the birdie reliability slope sat at 0.617 instead of ~1.0.
    """
    if cache:
        return cache
    con = sqlite3.connect(DB)
    rows = con.execute("SELECT tname, SUM(p3h), SUM(p3b), SUM(p4h), SUM(p4b), SUM(p5h), "
                       "SUM(p5b) FROM birdie_rounds GROUP BY tname").fetchall()
    con.close()
    tot = {3: [0.0, 0.0], 4: [0.0, 0.0], 5: [0.0, 0.0]}
    per = {}
    for tn, a3, b3, a4, b4, a5, b5 in rows:
        k = _ckey(tn)
        d = per.setdefault(k, {3: [0.0, 0.0], 4: [0.0, 0.0], 5: [0.0, 0.0]})
        for par, (h, b) in ((3, (a3, b3)), (4, (a4, b4)), (5, (a5, b5))):
            d[par][0] += h or 0
            d[par][1] += b or 0
            tot[par][0] += h or 0
            tot[par][1] += b or 0
    g = {par: (v[1] / v[0] if v[0] else 0.15) for par, v in tot.items()}
    out = {"__global__": g}
    for k, d in per.items():
        out[k] = {par: (((d[par][1] + CPAR_K * g[par]) / (d[par][0] + CPAR_K))
                        if d[par][0] else g[par]) for par in (3, 4, 5)}
    cache.update(out)
    return cache


def _theta_nodes(phi=PHI_ROUND, n=11, cache={}):
    """Equal-weight discretisation of a mean-1, variance-phi day factor."""
    if phi <= 1e-9:
        return [(1.0, 1.0)]
    if n in cache:
        return cache[n]
    import statistics as _st
    k = 1.0 / phi
    nodes = []
    for i in range(n):
        q = (i + 0.5) / n
        z = _st.NormalDist().inv_cdf(q)
        x = (1 - 1 / (9 * k) + z * math.sqrt(1 / (9 * k))) ** 3
        nodes.append((max(x, 1e-6), 1.0 / n))
    m = sum(w * x for x, w in nodes)
    cache[n] = [(x / m, w) for x, w in nodes]
    return cache[n]


def par_mix(par_total):
    return dict(PAR_MIX_RULE.get(int(par_total or 72), PAR_MIX_RULE[72]))


def course_par(tid, cache=HERE / "pga_course_cache.json"):
    """Par total for a tournament's host course via the orchestrator (cached per tid)."""
    try:
        c = json.loads(cache.read_text())
    except Exception:
        c = {}
    if str(tid) in c:
        return c[str(tid)]
    d = gql('query C($t: ID!) {courseStats(tournamentId: $t) '
            '{courses {courseId courseName par hostCourse}}}', {"t": tid})
    cs = ((d.get("data") or {}).get("courseStats") or {}).get("courses") or []
    host = next((x for x in cs if x.get("hostCourse")), cs[0] if cs else None)
    par = (host or {}).get("par")
    if par:
        c[str(tid)] = par
        try:
            cache.write_text(json.dumps(c))
        except OSError:
            pass
    return par


def harvest_mix(tid):
    """Exact mix from our own harvested hole counts (played events only)."""
    con = sqlite3.connect(DB)
    r = con.execute("SELECT AVG(p3h), AVG(p4h), AVG(p5h) FROM birdie_rounds WHERE tid=?",
                    (tid,)).fetchone()
    con.close()
    if not r or r[0] is None:
        return None
    return {3: round(r[0]), 4: round(r[1]), 5: round(r[2])}


def mix_for(tid):
    """Best available par mix: exact from harvest, else inferred from the par total."""
    return harvest_mix(tid) or par_mix(course_par(tid))


def tid_for_name(name, cache=HERE / "pga_tid_cache.json"):
    """Orchestrator tournament id (R2026xxx) for an event NAME.

    ⚠️ ESPN ids (401811960) and orchestrator ids (R2026524) are DIFFERENT NAMESPACES —
    passing the ESPN id into course_par() silently returned None and every course fell
    back to par-72, which is exactly the bug that made the birdie model run hot. Match
    on name tokens against the schedule (upcoming first: that is the bettable one).
    """
    key = " ".join(str(name or "").lower().split())
    try:
        c = json.loads(cache.read_text())
    except Exception:
        c = {}
    if key in c:
        return c[key]
    d = gql('{schedule(tourCode: "R") {upcoming {tournaments {id tournamentName}} '
            'completed {tournaments {id tournamentName}}}}')
    sd = (d.get("data") or {}).get("schedule") or {}
    cands = []
    for grp in (sd.get("upcoming") or []) + (sd.get("completed") or []):
        for t in grp.get("tournaments") or []:
            cands.append((t.get("id"), " ".join(str(t.get("tournamentName") or "").lower().split())))
    toks = [w for w in key.replace("pga", "").split() if len(w) > 3 and not w.isdigit()]
    # REQUIRE A MAJORITY OF TOKENS (2026-07-30). A single hit used to be enough, so an event
    # missing from the schedule would silently resolve to any tournament sharing one word —
    # and this tid drives the par mix, the course factor AND the wave tee sheet. Same
    # contamination class as the course-name and LPGA bugs. Refusing beats guessing: every
    # caller already handles a None tid by falling back to a documented default.
    need = max(1, (len(toks) + 1) // 2) if toks else 0
    best = None
    for tid, tn in cands:
        hits = sum(1 for w in toks if w in tn)
        if hits >= need and (best is None or hits > best[0]):
            best = (hits, tid)
    tid = best[1] if best else None
    if tid:
        c[key] = tid
        try:
            cache.write_text(json.dumps(c))
        except OSError:
            pass
    return tid


def p_x_or_more(player_rates, k_target, mix=None, phi=None):
    """P(at least k birdies-or-better), integrated over the per-round DAY FACTOR.

    Holes are not independent: a soft, calm day lifts every hole at once. Measured
    Var(theta)=0.0233 (sd 15.3%) over 39,722 rounds. Ignoring it made the count
    distribution too narrow. Pass phi=0 for the old independent behaviour.
    """
    ph = PHI_ROUND if phi is None else phi
    if ph <= 1e-9:
        return _p_x_indep(player_rates, k_target, mix)
    tot = 0.0
    for th, w in _theta_nodes(ph):
        r = {p: min(v * th, 0.98) for p, v in player_rates.items()}
        tot += w * _p_x_indep(r, k_target, mix)
    return tot


def _p_x_indep(player_rates, k_target, mix=None):
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


# PRE-REGISTERED BIRDIE CALIBRATION GATE (2026-07-30). Measured out of sample on 19,942
# leak-free player-rounds, the reliability slope of realized on predicted P(>=4 birdies) is
# 0.61 — the model's tail probabilities are systematically too extreme. Solving DISPERSION on
# the probability scale showed the slope peaks at ~0.608 and NEVER reaches 1.0 even when every
# player is collapsed to the field rate, so this is NOT player over-dispersion: p_x_or_more
# assumes 18 INDEPENDENT holes while real birdie counts are correlated within a round. A scalar
# cannot repair a wrong dependence structure — that needs a per-round random effect
# (beta-binomial). Every birdie edge sits in exactly the tails this miscalibrates, so:
BIRDIE_RELIABILITY = 1.06        # MEASURED 2026-07-30 with COURSE-SPECIFIC per-par
                                 # rates (was 0.61 on global rates). Leak-free,
                                 # 19,942 rounds: slope 1.059, pred .5751 vs real
                                 # .5746. Clears the 0.85 bar, so the stream arms.
BIRDIE_RELIABILITY_MIN = 0.85    # the bar to arm this stream


def birdie_stream_armable():
    """(ok, reason) — whether the birdie stream may be bet at all, on calibration grounds.

    Deliberately independent of G2: G2 asks whether the RULER matches the book on matchups and
    says nothing about whether birdie TAIL probabilities are calibrated.
    """
    if BIRDIE_RELIABILITY < BIRDIE_RELIABILITY_MIN:
        return False, ("birdie reliability slope %.2f < %.2f — tail probabilities are too "
                       "extreme (18-hole independence assumption); needs a per-round random "
                       "effect before this stream can be bet"
                       % (BIRDIE_RELIABILITY, BIRDIE_RELIABILITY_MIN))
    return True, "birdie calibration ok"


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
