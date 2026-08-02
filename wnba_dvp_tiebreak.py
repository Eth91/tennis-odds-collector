"""DvP as a TIEBREAKER, not a filter: same number of bets, different choice. Does it win more?

The filter test dropped bets and lost units. This is the other use, and the one the user actually
asked about: when the model must choose ONE of two plays — the correlation cap keeps one player per
team-game prop-family — does picking by DvP beat picking by the current rule?

A swap changes WHICH bet, never HOW MANY, so volume is held constant and the only question is the
record. Scored on every logged cap contest where both legs can be graded, not just the two whose
winner survived into the counted record — a tiebreaker's job is judged on the choices it faces.

Rules compared, all on identical contests:
    CURRENT     (shadow-band, odds, -ev)          — what shipped before tonight
    A-BAND      (shadow, A-band, odds, -ev)       — v1.1, shipped tonight
    DvP-FIRST   (better DvP wins outright)
    A-BAND+DvP  (A-band first, DvP breaks ties inside the band)
    PURE EV                                       — the known-bad control

DvP is refit AS OF each contest's date (dvp_backtest.fit_dvp), so no game after the bet informs it.
"""
import csv
import sqlite3
from collections import defaultdict

import numpy as np

import dvp_backtest as D
import wnba_wowy as W

STAT2K = {"points": "pts", "rebounds": "reb", "assists": "ast",
          "pra": "pts", "pts_reb": "pts", "pts_ast": "pts", "reb_ast": "reb"}

# ── contests ──────────────────────────────────────────────────────────────────
seen = {}
with open("wnba_capped_legs.csv") as f:
    for r in csv.reader(f):
        if len(r) < 9:
            continue
        try:
            k = (r[0], r[1], r[2], r[3], r[4], float(r[5]))
            seen[k] = {"date": r[0], "team": r[1], "kept": r[2], "capped": r[3], "stat": r[4],
                       "line": float(r[5]), "odds": float(r[6] or 0), "ev": float(r[7] or 0),
                       "d_min": float(r[8]) if r[8] not in ("", "None") else None}
        except ValueError:
            continue
contests = list(seen.values())
print("  distinct cap contests: %d" % len(contests))

# ── the kept leg's own row (odds/ev/d_min/opp/result) ─────────────────────────
con = sqlite3.connect("wnba_ledger.sqlite")
con.row_factory = sqlite3.Row
led = {}
for r in con.execute("SELECT * FROM predictions WHERE side='over'"):
    d = dict(r)
    led.setdefault((d["pred_date"], d["player"], d["stat"]), []).append(d)
con.close()

print("  building boxscore history...", flush=True)
hist, allg = D.build(60)
pos = D.positions()
lg_pace = np.mean([x["poss"] for x in allg if x.get("poss")]) if allg else 83.2
_cache = {}


def coef_asof(date, team, position, statk):
    pg = D._PG.get(position, position)
    key = (date, statk, pg)
    if key not in _cache:
        rows = []
        for x in allg:
            if x["date"] >= date or (x.get("min") or 0) < D.MIN_MIN:
                continue
            if D._PG.get(pos.get(x["pid"]), None) != pg:
                continue
            poss = x.get("poss") or lg_pace
            rows.append((x["pid"], x["opp"],
                         (x.get(statk) or 0) / max(x["min"], 1e-9) * (lg_pace / max(poss, 1e-9))))
        adj, _ = D.fit_dvp(rows, lg_pace)
        _cache[key] = adj
    return _cache[key].get(team)


players = W.players() or {}
_gl = {}


def actual(name, date, stat):
    if name not in _gl:
        pid = (players.get(name) or {}).get("id")
        try:
            _gl[name] = W.game_log(pid) if pid else []
        except Exception:                                          # noqa: BLE001
            _gl[name] = []
    for gm in _gl[name]:
        if (gm.get("date") or "")[:10] != date[:10]:
            continue
        p, rb, a = gm.get("pts"), gm.get("reb"), gm.get("ast")
        if p is None:
            return None
        return {"points": p, "rebounds": rb, "assists": a,
                "pra": (p or 0) + (rb or 0) + (a or 0), "pts_reb": (p or 0) + (rb or 0),
                "pts_ast": (p or 0) + (a or 0), "reb_ast": (rb or 0) + (a or 0)}.get(stat)
    return None


def aband(x):
    return 0 if (x is not None and 3 <= x <= 8) else 1


def oob(x):
    return 1 if (x is not None and (x < 0 or x > 8)) else 0


rows = []
for c in contests:
    lk = led.get((c["date"], c["kept"], c["stat"]))
    if not lk:
        continue
    k = sorted(lk, key=lambda r: -(r.get("ev") or 0))[0]
    ka = actual(c["kept"], c["date"], c["stat"])
    ca = actual(c["capped"], c["date"], c["stat"])
    if ka is None or ca is None or k.get("line") is None:
        continue
    kw = 1 if ka > k["line"] else 0
    cw = 1 if ca > c["line"] else 0
    if kw == cw:
        continue                                    # non-discriminating: any rule scores the same
    statk = STAT2K.get(c["stat"])
    opp = k.get("opp")
    kp = (players.get(c["kept"]) or {}).get("position")
    cp = (players.get(c["capped"]) or {}).get("position")
    kd = cd = None
    if statk and opp and kp and cp:
        try:
            kd, cd = (coef_asof(c["date"], opp, kp, statk),
                      coef_asof(c["date"], opp, cp, statk))
        except Exception:                                          # noqa: BLE001
            pass
    rows.append({"c": c, "k": k, "kw": kw, "cw": cw, "kd": kd, "cd": cd})

print("  discriminating contests (the legs disagreed): %d" % len(rows))
print("  ...with DvP resolved for BOTH legs: %d" % sum(1 for r in rows if r["kd"] is not None and r["cd"] is not None))

RULES = {
    # CURRENT is known BY CONSTRUCTION: the CSV's "kept" column IS what the old rule chose.
    # Recomputing it from ledger-vs-CSV odds compares two different snapshots and does NOT
    # reproduce the original decision — that error made the shipped rule look 1-3 instead of 3-1.
    "CURRENT (what the cap actually kept)":
        lambda r: True,
    "A-BAND (v1.1, shipped)":
        lambda r: (oob(r["k"].get("d_min")), aband(r["k"].get("d_min")),
                   float(r["k"].get("odds") or 99), -(r["k"].get("ev") or 0))
                  <= (oob(r["c"]["d_min"]), aband(r["c"]["d_min"]), r["c"]["odds"], -r["c"]["ev"]),
    "DvP-FIRST (higher coef wins)":
        lambda r: (r["kd"] is None or r["cd"] is None) or (r["kd"] >= r["cd"]),
    "A-BAND then DvP":
        lambda r: (aband(r["k"].get("d_min")), -(r["kd"] if r["kd"] is not None else -9))
                  <= (aband(r["c"]["d_min"]), -(r["cd"] if r["cd"] is not None else -9)),
    "PURE EV (known-bad control)":
        lambda r: (r["k"].get("ev") or 0) >= r["c"]["ev"],
}

print("\n  %-32s %6s %6s %8s" % ("tiebreak rule", "right", "wrong", "acc"))
for name, pick_kept in RULES.items():
    a = b = 0
    for r in rows:
        win = r["kw"] if pick_kept(r) else r["cw"]
        a, b = (a + 1, b) if win else (a, b + 1)
    n = a + b
    print("  %-32s %6d %6d %7.1f%%" % (name, a, b, 100 * a / n if n else 0))

print("\n  ⚠ independence check — how many DISTINCT (date, kept player)?")
import collections
_d = collections.Counter((r["c"]["date"], r["c"]["kept"]) for r in rows)
print("     %d contests across %d distinct kept-legs: %s"
      % (len(rows), len(_d), dict(_d)))

print("\n=== the contests, with d_min and both DvP coefficients ===")
print("  %-11s %-8s %-30s %-30s" % ("date", "stat", "KEPT dmin/dvp res", "CAPPED dmin/dvp res"))
for r in rows:
    print("  %-11s %-8s %-30s %-30s"
          % (r["c"]["date"], r["c"]["stat"],
             "%s dm%s %s %s" % (r["c"]["kept"][:11], r["k"].get("d_min"),
                             ("%+.4f" % r["kd"]) if r["kd"] is not None else "n/a",
                             "W" if r["kw"] else "L"),
             "%s dm%s %s %s" % (r["c"]["capped"][:11], r["c"]["d_min"],
                             ("%+.4f" % r["cd"]) if r["cd"] is not None else "n/a",
                             "W" if r["cw"] else "L")))
print("\n  A tiebreaker swaps a bet, never removes one, so volume is identical across every rule")
print("  above. The only thing that moves is the record.")
