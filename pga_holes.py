"""⛳ pga_holes — REAL hole-level course data, and a measured green-difficulty index.

Green speed (stimpmeter) is not published anywhere I can access, so the usual move is to infer
"this course rewards putting" from scoring residuals. That is circular — it estimates the course
characteristic from the same residuals the interaction is then tested on, which is why every
course-fit test so far has died in noise.

courseHolesStats gives the real thing, free: per hole, the par, the yardage, the scoring average,
and the full outcome distribution (eagles/birdies/pars/bogeys/doubles).

GREEN PENALTY INDEX. Par 3s are the cleanest window onto the green complex: no driving, one
approach, then putting. On a par 3 a bogey is overwhelmingly a missed green not saved, or a
three-putt — both functions of green speed and severity. So:

    green_penalty = (bogeys + doubles) / (birdies + bogeys + doubles)   on par 3s only

controlling for yardage, since a 240-yard par 3 is hard for reasons that have nothing to do with
the greens. High index = penal green complex.
"""
import json
import sqlite3
import sys
from pathlib import Path

import pga_birdies as B

HERE = Path(__file__).resolve().parent
DB = HERE / "pga_model.sqlite"
D = chr(36)

DDL = """CREATE TABLE IF NOT EXISTS course_holes(
    tid TEXT, tname TEXT, course_id TEXT, hole INTEGER, par INTEGER, yards INTEGER,
    scoring_avg REAL, eagles INTEGER, birdies INTEGER, pars INTEGER, bogeys INTEGER,
    doubles INTEGER, PRIMARY KEY(tid, course_id, hole))"""

Q = ('query H(%st: ID!, %sc: ID!) {courseHolesStats(tournamentId: %st, courseId: %sc) '
     '{... on HoleStatSummary {courseHoleNum parValue yards scoringAverage eagles birdies '
     'pars bogeys doubleBogey}}}' % (D, D, D, D))


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


def course_ids(tid):
    """[(courseId, courseName)] for a tournament."""
    q = ('query C(%st: ID!) {courseStats(tournamentId: %st) {courses {courseId courseName '
         'hostCourse}}}' % (D, D))
    try:
        d = B.gql(q, {"t": tid})
        cs = ((d.get("data") or {}).get("courseStats") or {}).get("courses") or []
        return [(c.get("courseId"), c.get("courseName")) for c in cs if c.get("courseId")]
    except Exception:                                               # noqa: BLE001
        return []


def harvest(tids=None, verbose=True):
    con = sqlite3.connect(DB)
    con.execute(DDL)
    con.commit()
    if tids is None:
        tids = [r for r in con.execute("SELECT DISTINCT tid, tname FROM birdie_rounds").fetchall()]
    have = {r[0] for r in con.execute("SELECT DISTINCT tid FROM course_holes").fetchall()}
    new = 0
    for tid, tname in tids:
        if tid in have:
            continue
        for cid, _cn in course_ids(tid):
            try:
                d = B.gql(Q, {"t": tid, "c": str(cid)})
            except Exception:                                       # noqa: BLE001
                continue
            if d.get("errors"):
                continue
            rows = []
            for h in (d.get("data") or {}).get("courseHolesStats") or []:
                hn, par = _i(h.get("courseHoleNum")), _i(h.get("parValue"))
                if not hn or not par:
                    continue
                rows.append((tid, tname, str(cid), hn, par, _i(h.get("yards")),
                             _f(h.get("scoringAverage")), _i(h.get("eagles")),
                             _i(h.get("birdies")), _i(h.get("pars")), _i(h.get("bogeys")),
                             _i(h.get("doubleBogey"))))
            if rows:
                con.executemany("INSERT OR REPLACE INTO course_holes VALUES "
                                "(?,?,?,?,?,?,?,?,?,?,?,?)", rows)
                con.commit()
                new += 1
                if verbose:
                    print("   %-10s %-28s %2d holes" % (tid, str(tname)[:28], len(rows)))
    n = con.execute("SELECT COUNT(*), COUNT(DISTINCT tid) FROM course_holes").fetchone()
    con.close()
    if verbose:
        print("  course_holes: %d rows over %d events (+%d)" % (n[0], n[1], new))
    return n


def _ckey(t):
    return " ".join(sorted(w for w in str(t or "").lower().split() if len(w) > 3))


def course_features():
    """{course_key: {...}} — measured course characteristics, not inferred ones."""
    con = sqlite3.connect(DB)
    con.execute(DDL)
    rows = con.execute("SELECT tname, par, yards, scoring_avg, eagles, birdies, pars, bogeys, "
                       "doubles FROM course_holes").fetchall()
    con.close()
    agg = {}
    for tname, par, yards, sa, e, b, p, bo, db in rows:
        k = _ckey(tname)
        a = agg.setdefault(k, {"p3_bad": 0, "p3_good": 0, "p3_yards": [], "len": [],
                               "bad": 0, "good": 0, "n": 0})
        e, b, p, bo, db = (x or 0 for x in (e, b, p, bo, db))
        a["n"] += 1
        if yards:
            a["len"].append(yards)
        a["good"] += e + b
        a["bad"] += bo + db
        if par == 3:
            a["p3_good"] += e + b
            a["p3_bad"] += bo + db
            if yards:
                a["p3_yards"].append(yards)
    out = {}
    for k, a in agg.items():
        if a["n"] < 9:
            continue
        p3tot = a["p3_good"] + a["p3_bad"]
        tot = a["good"] + a["bad"]
        out[k] = {
            # the green-penalty index: how punishing the green complex is, par 3s only
            "green_penalty": (a["p3_bad"] / p3tot) if p3tot >= 50 else None,
            "p3_yards": (sum(a["p3_yards"]) / len(a["p3_yards"])) if a["p3_yards"] else None,
            "overall_penalty": (a["bad"] / tot) if tot >= 200 else None,
            "course_yards": sum(a["len"]) if len(a["len"]) >= 15 else None,
            "holes": a["n"],
        }
    return out


if __name__ == "__main__":
    harvest()
    f = course_features()
    ok = {k: v for k, v in f.items() if v["green_penalty"] is not None}
    print()
    print("  courses with a green-penalty index: %d" % len(ok))
    srt = sorted(ok.items(), key=lambda kv: -kv[1]["green_penalty"])
    print("  MOST penal greens (par-3 bogey share):")
    for k, v in srt[:6]:
        print("     %-34s %.3f  (par-3 avg %s yds, course %s yds)"
              % (k[:34], v["green_penalty"],
                 int(v["p3_yards"]) if v["p3_yards"] else "?",
                 v["course_yards"] or "?"))
    print("  LEAST penal:")
    for k, v in srt[-4:]:
        print("     %-34s %.3f  (par-3 avg %s yds)"
              % (k[:34], v["green_penalty"], int(v["p3_yards"]) if v["p3_yards"] else "?"))
