"""Did the correlation cap keep the RIGHT leg? Graded, on the breadcrumb built for this question.

wnba_capped_legs.csv logs both sides of every pool contest: the winner the cap kept and the leg it
deleted, with line/odds/ev/d_min. That is the only way to grade a contest the ledger cannot see —
capped legs never log a result, so the ledger alone is blind to the counterfactual.

WNBA is FROZEN (v1.0, validation only), so nothing here ships. This is a hypothesis test against the
frozen baseline, which is what the freeze demands of any proposed change.

The specific hypothesis, from tonight's Carleton/DiLeo inversion: the cap's band term uses the
SHADOW band (d_min<0 or >8) while selection's gkey uses the A-band (3<=d_min<=8). Where both legs
sit inside 0-8 the cap's band term is a no-op and a hair of odds decides. Ranking by the A-band
instead should prefer the leg selection would have wanted.
"""
import csv
import os
import sqlite3
from collections import defaultdict

CAP = "wnba_capped_legs.csv"
if not os.path.exists(CAP):
    raise SystemExit("  no %s — nothing to audit" % CAP)

rows = []
with open(CAP) as f:
    for r in csv.reader(f):
        if len(r) < 9:
            continue
        try:
            rows.append({"date": r[0], "team": r[1], "kept": r[2], "capped": r[3],
                         "stat": r[4], "line": float(r[5]), "odds": float(r[6] or 0),
                         "ev": float(r[7] or 0), "d_min": float(r[8]) if r[8] not in ("", "None") else None})
        except ValueError:
            continue
print("  capped-leg contests logged: %d over %d dates"
      % (len(rows), len({r["date"] for r in rows})))

# grade both sides from the gamelog store
con = sqlite3.connect("wnba_gamelogs.sqlite")
tabs = [t[0] for t in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
print("  gamelog tables:", tabs)


def actual(player, date, stat):
    """Actual stat value for player on date, or None."""
    for t in tabs:
        tc = [d[1] for d in con.execute("PRAGMA table_info(%s)" % t)]
        if "player" not in tc:
            continue
        dc = next((c for c in tc if c in ("date", "game_date")), None)
        if not dc:
            continue
        try:
            r = con.execute("SELECT * FROM %s WHERE player=? AND substr(%s,1,10)=?"
                            % (t, dc), (player, date[:10])).fetchone()
        except sqlite3.Error:
            continue
        if not r:
            continue
        d = dict(zip(tc, r))
        p, rb, a = d.get("pts"), d.get("reb"), d.get("ast")
        if p is None:
            continue
        return {"points": p, "rebounds": rb, "assists": a,
                "pra": (p or 0) + (rb or 0) + (a or 0),
                "pts_reb": (p or 0) + (rb or 0), "pts_ast": (p or 0) + (a or 0),
                "reb_ast": (rb or 0) + (a or 0)}.get(stat)
    return None


# pair each contest: the kept leg's own row is in the ledger; the capped leg's is here
led = sqlite3.connect("wnba_ledger.sqlite")
led.row_factory = sqlite3.Row


def kept_leg(date, team, player):
    r = led.execute("SELECT * FROM predictions WHERE pred_date=? AND team=? AND player=? "
                    "AND side='over' AND graded=1 ORDER BY ev DESC LIMIT 1",
                    (date, team, player)).fetchone()
    return dict(r) if r else None


tally = defaultdict(lambda: [0, 0])       # rule -> [right, wrong]
detail = []
for r in rows:
    kl = kept_leg(r["date"], r["team"], r["kept"])
    if not kl:
        continue
    kept_res = 1 if str(kl.get("result") or "").upper().startswith("W") else 0
    cap_act = actual(r["capped"], r["date"], r["stat"])
    if cap_act is None:
        continue
    cap_res = 1 if cap_act > r["line"] else 0
    if kept_res == cap_res:
        continue                          # contest is non-discriminating
    kdm, cdm = kl.get("d_min"), r["d_min"]

    def aband(x):
        return 0 if (x is not None and 3 <= x <= 8) else 1
    # what the CURRENT cap does: it kept `kept` by construction
    tally["CURRENT (shadow-band, odds, ev)"][0 if kept_res else 1] += 1
    # what an A-BAND-FIRST rule would have picked
    pick_kept = (aband(kdm), float(kl.get("odds") or 99), -(kl.get("ev") or 0)) <= \
                (aband(cdm), r["odds"], -r["ev"])
    win = kept_res if pick_kept else cap_res
    tally["A-BAND FIRST (3-8, then odds, ev)"][0 if win else 1] += 1
    # pure EV, for reference — the metric the codebase says is anti-predictive
    pick_kept_ev = (kl.get("ev") or 0) >= r["ev"]
    win_ev = kept_res if pick_kept_ev else cap_res
    tally["PURE EV"][0 if win_ev else 1] += 1
    detail.append((r["date"], r["team"], r["stat"], r["kept"], kept_res, kdm,
                   r["capped"], cap_res, cdm))

print("\n=== discriminating contests (the two legs disagreed) : %d ===" % len(detail))
print("  %-11s %-5s %-9s %-20s %-6s %-20s %s"
      % ("date", "team", "stat", "KEPT", "res", "CAPPED", "res"))
for d in detail:
    print("  %-11s %-5s %-9s %-20s %-6s %-20s %s"
          % (d[0], d[1], d[2], "%s(dm %s)" % (d[3][:12], d[5]), "W" if d[4] else "L",
             "%s(dm %s)" % (d[6][:12], d[8]), "W" if d[7] else "L"))

print("\n=== which keep-rule picks the winner more often? ===")
print("  %-38s %6s %6s %8s" % ("rule", "right", "wrong", "acc"))
for k, (a, b) in tally.items():
    n = a + b
    print("  %-38s %6d %6d %7.1f%%" % (k, a, b, 100 * a / n if n else 0))
print("\n  n is small — this is a hypothesis for the frozen-model validator, not a shipping decision.")
