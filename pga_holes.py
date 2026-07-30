"""⛳ pga_holes — real hole-level course data, and a MEASURED green-difficulty index.

Green speed (stimpmeter) is published nowhere I can access. The usual substitute is to infer "this
course rewards putting" from scoring residuals, but that is circular — it estimates the course
characteristic from the same residuals the interaction is then tested against, which is why every
course-fit test so far has died in noise. courseHolesStats gives the real outcome distribution per
hole, free.

TWO TRAPS FOUND WHILE BUILDING THIS, both silent:
  * HoleStatSummary carries `holeNum`/`doubleBogeys`, NOT `courseHoleNum`/`doubleBogey`, and has
    no par or yardage at all.
  * `scoringAverage` is a DIFFERENTIAL TO PAR ("-0.178" = 0.178 under par), not an absolute score.
    Inferring par by rounding it would have produced par=0 for all 18 holes and looked plausible
    in aggregate. Par instead comes from scorecardV3, which reports each hole's par directly —
    one player per tournament is enough for all 18.

GREEN PENALTY INDEX. Par 3s are the cleanest window on the green complex: no driving, one approach,
then putting. A bogey there is overwhelmingly a missed green not saved or a three-putt, both
functions of green speed and severity:
    green_penalty = (bogeys + doubles) / (birdies + eagles + bogeys + doubles)   on par 3s
"""
import sqlite3
from pathlib import Path

import pga_birdies as B

HERE = Path(__file__).resolve().parent
DB = HERE / "pga_model.sqlite"
D = chr(36)

DDL = """CREATE TABLE IF NOT EXISTS course_holes(
    tid TEXT, tname TEXT, course_id TEXT, hole INTEGER, par INTEGER,
    score_diff REAL, eagles INTEGER, birdies INTEGER, pars INTEGER, bogeys INTEGER,
    doubles INTEGER, PRIMARY KEY(tid, course_id, hole))"""

Q_HOLES = ('query H(%st: ID!, %sc: ID!) {courseHolesStats(tournamentId: %st, courseId: %sc) '
           '{... on HoleStatSummary {holeNum scoringAverage eagles birdies pars bogeys '
           'doubleBogeys}}}' % (D, D, D, D))
Q_COURSE = ('query C(%st: ID!) {courseStats(tournamentId: %st) {courses {courseId courseName}}}'
            % (D, D))
Q_CARD = ('query S(%st: ID!, %sp: ID!) {scorecardV3(tournamentId: %st, playerId: %sp) '
          '{roundScores {... on RoundScore {firstNine {holes {holeNumber par}} '
          'secondNine {holes {holeNumber par}}}}}}' % (D, D, D, D))


def _i(x):
    try:
        return int(float(str(x).replace(",", "")))
    except (TypeError, ValueError):
        return None


def _f(x):
    try:
        return float(str(x).replace(",", ""))
    except (TypeError, ValueError):
        return None


def hole_pars(tid):
    """{holeNumber: par} — from a scorecard, since HoleStatSummary has no par."""
    try:
        ps = B.players_of(tid)
    except Exception:                                               # noqa: BLE001
        return {}
    for pid, _nm in ps[:4]:
        try:
            d = B.gql(Q_CARD, {"t": tid, "p": pid})
        except Exception:                                           # noqa: BLE001
            continue
        out = {}
        for rs in ((d.get("data") or {}).get("scorecardV3") or {}).get("roundScores") or []:
            for nine in ("firstNine", "secondNine"):
                for h in ((rs.get(nine) or {}).get("holes") or []):
                    hn, par = _i(h.get("holeNumber")), _i(h.get("par"))
                    if hn and par in (3, 4, 5):
                        out[hn] = par
        if len(out) >= 15:
            return out
    return {}


def harvest(verbose=True):
    con = sqlite3.connect(DB)
    con.execute(DDL)
    con.commit()
    tids = con.execute("SELECT DISTINCT tid, tname FROM birdie_rounds").fetchall()
    have = {r[0] for r in con.execute("SELECT DISTINCT tid FROM course_holes").fetchall()}
    new = 0
    for tid, tname in tids:
        if tid in have:
            continue
        pars = hole_pars(tid)
        if not pars:
            continue
        try:
            dc = B.gql(Q_COURSE, {"t": tid})
            courses = ((dc.get("data") or {}).get("courseStats") or {}).get("courses") or []
        except Exception:                                           # noqa: BLE001
            continue
        for c in courses:
            cid = c.get("courseId")
            if not cid:
                continue
            try:
                d = B.gql(Q_HOLES, {"t": tid, "c": str(cid)})
            except Exception:                                       # noqa: BLE001
                continue
            if d.get("errors"):
                continue
            rows = []
            for h in (d.get("data") or {}).get("courseHolesStats") or []:
                hn = _i(h.get("holeNum"))
                if not hn or hn not in pars:
                    continue
                rows.append((tid, tname, str(cid), hn, pars[hn],
                             _f(h.get("scoringAverage")), _i(h.get("eagles")),
                             _i(h.get("birdies")), _i(h.get("pars")), _i(h.get("bogeys")),
                             _i(h.get("doubleBogeys"))))
            if rows:
                con.executemany("INSERT OR REPLACE INTO course_holes VALUES "
                                "(?,?,?,?,?,?,?,?,?,?,?)", rows)
                con.commit()
                new += 1
                if verbose and new % 15 == 1:
                    print("   %-10s %-28s %2d holes" % (tid, str(tname)[:28], len(rows)))
    n = con.execute("SELECT COUNT(*), COUNT(DISTINCT tid) FROM course_holes").fetchone()
    con.close()
    if verbose:
        print("  course_holes: %d rows over %d events (+%d)" % (n[0], n[1], new))
    return n


def _ckey(t):
    return " ".join(sorted(w for w in str(t or "").lower().split() if len(w) > 3))


def course_features():
    con = sqlite3.connect(DB)
    con.execute(DDL)
    rows = con.execute("SELECT tname, par, eagles, birdies, pars, bogeys, doubles, score_diff "
                       "FROM course_holes").fetchall()
    con.close()
    agg = {}
    for tname, par, e, b, p, bo, db, sd in rows:
        k = _ckey(tname)
        a = agg.setdefault(k, {"p3g": 0, "p3b": 0, "g": 0, "b": 0, "n": 0, "diff": []})
        e, b, p, bo, db = (x or 0 for x in (e, b, p, bo, db))
        a["n"] += 1
        a["g"] += e + b
        a["b"] += bo + db
        if sd is not None:
            a["diff"].append(sd)
        if par == 3:
            a["p3g"] += e + b
            a["p3b"] += bo + db
    out = {}
    for k, a in agg.items():
        if a["n"] < 15:
            continue
        p3 = a["p3g"] + a["p3b"]
        tot = a["g"] + a["b"]
        out[k] = {"green_penalty": (a["p3b"] / p3) if p3 >= 80 else None,
                  "overall_penalty": (a["b"] / tot) if tot >= 400 else None,
                  "scoring_diff": (sum(a["diff"]) / len(a["diff"])) if a["diff"] else None,
                  "holes": a["n"]}
    return out


if __name__ == "__main__":
    harvest()
    f = course_features()
    ok = {k: v for k, v in f.items() if v["green_penalty"] is not None}
    print()
    print("  courses with a green-penalty index: %d" % len(ok))
    srt = sorted(ok.items(), key=lambda kv: -kv[1]["green_penalty"])
    print("  MOST penal green complexes (par-3 bogey share of decisive holes):")
    for k, v in srt[:6]:
        print("     %-36s %.3f" % (k[:36], v["green_penalty"]))
    print("  LEAST penal:")
    for k, v in srt[-5:]:
        print("     %-36s %.3f" % (k[:36], v["green_penalty"]))
    import statistics as st
    vals = [v["green_penalty"] for v in ok.values()]
    if vals:
        print("  spread: mean %.3f  sd %.3f  range %.3f..%.3f"
              % (st.mean(vals), st.pstdev(vals), min(vals), max(vals)))
