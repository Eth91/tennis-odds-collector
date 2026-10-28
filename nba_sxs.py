#!/usr/bin/env python3
"""The side-by-side test (NBA_SXS_PREREG.md): every registered rule over every finished day, graded the same way.
Research only: nothing is bet and nothing is shown as a pick.

    python3 nba_sxs.py --run OUT_JSON           # nightly on the VM, after the box scores
Signals are stored in nba_sxs.sqlite; a day is recomputed when a rule's fingerprint or the APPARATUS changes, or for
the last 3 days.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
from pathlib import Path

import numpy as np

import nba_proj_eval as E
import nba_replay as RP
import nba_sxs_rules as SR

HERE = RP.HERE
SINCE = "2026-10-22"
NEED_CLV, NEED_ROI, RECOMPUTE_DAYS = 200, 500, 3
NEED_CLV_DATES, NEED_ROI_DATES = 10, 20                 # a date-clustered interval needs dates, not just signals
NULL_BAND = (-0.08, 0.0)
APPARATUS = 8                                           # the replay's version (amendment 8: games final by t, tracking stored by t)
COLS = ("rule", "fp", "phase", "date", "t", "gid", "pid", "market", "side", "line", "book", "odds", "note", "result",
        "actual", "profit", "q_close", "clv")
DDL = [f"CREATE TABLE IF NOT EXISTS signals ({', '.join(COLS)})",
       "CREATE TABLE IF NOT EXISTS days (rule TEXT, fp TEXT, date TEXT, ran_at TEXT, PRIMARY KEY (rule, fp, date))"]
STORES = {"lines": HERE / "nba_lines.sqlite", "news": HERE / "nba_news.sqlite", "matchup": HERE / "nba_matchup.sqlite",
          "gamelogs": HERE / "nba_gamelogs.sqlite", "shadow": HERE / "nba_shadow.sqlite", "proj_log": HERE / "nba_proj_log.sqlite"}


def phase(rule, fp, t):
    """'forward' only for a registered fingerprint at or after its registration; 'unregistered' for changed code."""
    at, reg_fp = SR.REGISTRY.get(rule, (None, None))
    if fp != reg_fp:
        return "unregistered"
    return "forward" if t >= at else "development"


def verdict(summary, null_ok):
    c = summary.get("clv") or {}
    n, nd = c.get("n", 0), c.get("dates", 0)
    if n < NEED_CLV or nd < NEED_CLV_DATES:
        v = f"accumulating ({n}/{NEED_CLV} signals, {nd}/{NEED_CLV_DATES} dates)"
    elif c["lo"] > 0:
        v = "BEATS THE CLOSE"
    elif c["hi"] < 0:
        v = "LOSES TO THE CLOSE"
    else:
        v = "NO EDGE SHOWN"
    r = summary.get("roi")
    if r and r["n"] >= NEED_ROI and r.get("dates", 0) >= NEED_ROI_DATES:
        v += "; PROFITABLE" if r["lo"] > 0 else "; ROI interval reaches 0"
    return v if null_ok is not False else "GRADER CHECK FAILED · " + v


def run(out_json=None, db=HERE / "nba_sxs.sqlite", since=SINCE, until=None, stores=None, today=None):
    stores = {**STORES, **(stores or {})}
    today = today or E._et_date(dt.datetime.now(dt.timezone.utc).isoformat())
    until = until or (dt.date.fromisoformat(today) - dt.timedelta(days=1)).isoformat()
    recent = (dt.date.fromisoformat(until) - dt.timedelta(days=RECOMPUTE_DAYS - 1)).isoformat()
    con = sqlite3.connect(db)
    for s in DDL:
        con.execute(s)
    if "apparatus" not in {r[1] for r in con.execute("PRAGMA table_info(days)")}:
        con.execute("ALTER TABLE days ADD COLUMN apparatus INTEGER")       # days run before amendment 8 are redone
    rules = [cls() for cls in SR.RULES]
    fps = {cls.name: SR.fingerprint(cls) for cls in SR.RULES}
    history = None
    for d in RP.dates(stores["matchup"], stores["lines"], since, until):
        todo = [r for r in rules if d >= recent or not con.execute(
            "SELECT 1 FROM days WHERE rule = ? AND fp = ? AND date = ? AND apparatus = ?", (r.name, fps[r.name], d, APPARATUS)).fetchone()]
        if not todo:
            continue
        history = history or RP.History(stores["gamelogs"], stores["matchup"])
        day = RP.Day(d, stores["lines"], stores["news"], stores["matchup"], history)
        sig = RP.run_day(day, [r for r in todo if r.kind == "replay"])
        for r in todo:
            if r.kind == "logged":
                sig += [dict(s, rule=r.name) for s in r.logged(day, stores)]
        for s in sig:
            s["date"] = d
        RP.grade(day, sig, RP.box_of(stores["matchup"], list(day.games)))
        names = [r.name for r in todo]
        con.execute(f"DELETE FROM signals WHERE date = ? AND rule IN ({','.join('?' * len(names))})", [d, *names])
        con.executemany(f"INSERT INTO signals VALUES ({','.join('?' * len(COLS))})",
                        [tuple(dict(s, fp=fps[s["rule"]], phase=phase(s["rule"], fps[s["rule"]], s["t"])).get(c) for c in COLS)
                         for s in sig])
        now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        con.executemany("INSERT OR REPLACE INTO days (rule, fp, date, ran_at, apparatus) VALUES (?, ?, ?, ?, ?)",
                        [(n, fps[n], d, now, APPARATUS) for n in names])
        con.commit()
    return scoreboard(con, fps, out_json)


def scoreboard(con, fps, out_json=None):
    rows = [dict(zip(COLS, r)) for r in con.execute(f"SELECT {', '.join(COLS)} FROM signals")]
    by = lambda name, ph: [r for r in rows if r["rule"] == name and r["fp"] == fps[name] and r["phase"] == ph]
    null = RP.summarize(by("NULL_TIP30", "forward")).get("clv")
    null_ok = None if not null or null["n"] < NEED_CLV or null["dates"] < NEED_CLV_DATES else NULL_BAND[0] <= null["mean"] <= NULL_BAND[1]
    res = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "prereg": "NBA_SXS_PREREG.md",
           "note": "research only; nothing is bet. Verdicts count forward signals only (after registration).",
           "grader_check": {"null_clv": null, "ok": null_ok}, "rules": {}}
    for cls in SR.RULES:
        n = cls.name
        fwd, dev = by(n, "forward"), by(n, "development")
        f = RP.summarize(fwd)
        f["verdict"] = verdict(f, null_ok)
        for key in ("market", "side"):
            f["by_" + key] = {k: RP.summarize([r for r in fwd if r[key] == k]) for k in sorted({r[key] for r in fwd})}
        res["rules"][n] = {"kind": cls.kind, "doc": (cls.__doc__ or "").strip(), "fingerprint": fps[n],
                           "registered": SR.REGISTRY.get(n, (None,))[0],
                           "registered_fingerprint_matches": SR.REGISTRY.get(n, (None, None))[1] == fps[n],
                           "development": RP.summarize(dev), "forward": f}
    if out_json:
        tmp = Path(str(out_json) + ".tmp")
        tmp.write_text(json.dumps(res, indent=1, default=float))
        tmp.replace(out_json)
    return res


def table(res):
    lines = []
    for n, r in res["rules"].items():
        for ph in ("development", "forward"):
            s = r[ph]
            c, o = s.get("clv") or {}, s.get("roi") or {}
            lines.append(f"{n:<12} {ph:<11} signals {s['signals']:5d} graded {s['graded']:5d}  "
                         + (f"CLV {100 * c['mean']:+5.1f}% [{100 * c['lo']:+5.1f}, {100 * c['hi']:+5.1f}] cov {s['clv_coverage']:.0%}  " if c else "CLV n/a  ")
                         + (f"ROI {100 * o['mean']:+6.1f}% ({o['w']}-{o['l']})" if o else "")
                         + (f"  {s['verdict']}" if ph == "forward" else ""))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", metavar="OUT_JSON")
    ap.add_argument("--db", default=str(HERE / "nba_sxs.sqlite"))
    a = ap.parse_args()
    if a.run:
        print(table(run(a.run, db=a.db)))


if __name__ == "__main__":
    main()
