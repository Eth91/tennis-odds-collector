"""⛳ E3 — RULER RESIDUAL meter (matchups, top-N, outrights) — GATED BEHIND G2, by code.

Runs every golf cron pass: refreshes results (which also feeds the G2 gate), refits the
ruler, prices the live FanDuel board, and computes residuals vs the devigged prices.

THE GATE IS IN THE CODE, NOT IN A PROMISE: until g2_gate() returns PASS on >=15 real closed
matchups, residuals are PREVIEW-ONLY (rendered on the board, clearly labeled, never logged
as paper flags) — a ruler that hasn't proven it can track the close cannot be allowed to
accumulate a paper record that looks like evidence. The week G2 goes green, flags start
logging themselves (stream E3-*) into the same paper ledger + tripwire as E1.

Devig conventions: matchbets = two-way normalization. Top-N/outrights are one-sided books:
fair p_i = (1/odds_i) * N / sum_j(1/odds_j) — the field-wide overround scaled to N expected
winners. Pre-registered flag knobs (constitution law 7 — set BEFORE any result is seen):
matchups |edge| >= 0.06; top-N edge >= 0.04 & odds >= 1.5; outrights EV >= +15% & our
p >= 1.3x fair. These do not move after launch except by a written decision.
"""
import datetime as dt
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

import pga_ruler as RU
import pga_e1 as E1
import pga_field as F

HERE = Path(__file__).resolve().parent
LINES = HERE / "golf_lines.sqlite"
PAPER = HERE / "pga_paper.sqlite"

M_EDGE = 0.06
TN_EDGE = 0.04
TN_MIN_ODDS = 1.5
OUT_EV = 0.15
OUT_RATIO = 1.3


def latest_event_rows():
    con = sqlite3.connect(LINES)
    ev = con.execute("SELECT event, COUNT(*) c FROM golf_lines WHERE collected_at >= "
                     "datetime('now','-1 day') AND event LIKE '%PGA%' AND event NOT LIKE "
                     "'%202_'||'7%' GROUP BY event ORDER BY c DESC LIMIT 1").fetchone()
    if not ev:
        con.close()
        return None, []
    evn = ev[0]
    ts = con.execute("SELECT MAX(collected_at) FROM golf_lines WHERE event=?", (evn,)).fetchone()[0]
    rows = con.execute("SELECT market, mtype, runner, odds FROM golf_lines "
                       "WHERE event=? AND collected_at=?", (evn, ts)).fetchall()
    con.close()
    return evn.strip(), rows


def main():
    RU.crawl((2026,))                       # fresh results -> ratings AND the G2 sample
    R_raw, _ = RU.fit()
    R = {RU.norm(k): v for k, v in R_raw.items()}
    passed, n_g2 = RU.g2_gate(verbose=True)
    armed = bool(passed)

    evn, rows = latest_event_rows()
    if not evn:
        print("e3: no active PGA event in the collector — nothing to price")
        return
    print(f"e3: pricing {evn}  (G2 {'PASS — flags ARMED' if armed else 'pending n=%d — preview only' % n_g2})")

    preview, flags = [], []
    now = dt.datetime.utcnow().replace(microsecond=0).isoformat()

    # ---- matchbets (two-way) ----
    by_m = defaultdict(list)
    for mkt, mt, run, od in rows:
        if "Matchbet" in mkt and od and od > 1.0:
            by_m[mkt].append((run, od))
    for mkt, rr in by_m.items():
        if len(rr) != 2:
            continue
        (a, oa), (b, ob) = rr
        nrounds = 1 if ("Round" in mkt or "1st" in mkt) else 4
        p = RU.matchup_prob(R, a, b, rounds=nrounds)
        if p is None:
            continue
        fair = (1 / oa) / (1 / oa + 1 / ob)
        edge = p - fair
        side, odds, pe = (a, oa, edge) if edge > 0 else (b, ob, -edge)
        if pe >= M_EDGE:
            preview.append({"stream": "E3-match", "runner": side, "market": mkt[:60],
                            "odds": odds, "edge": round(pe, 3)})

    # ---- top-N + outrights (one-sided) ----
    field = [(c.get("athlete") or {}).get("displayName") for c in F.competitors()]
    field = [f for f in field if f]
    sim = RU.simulate(R, field) if field else {}
    groups = defaultdict(list)
    for mkt, mt, run, od in rows:
        if od and od > 1.0 and mt and ("TOP_" in mt and "FINISH" in mt or mt == "OUTRIGHT_BETTING"):
            groups[mt].append((run, od))
    NMAP = {"TOP_5": 5, "TOP_10": 10, "TOP_20": 20, "OUTRIGHT": 1}
    for mt, rr in groups.items():
        N = next((v for k, v in NMAP.items() if mt.startswith(k)), None)
        if not N or len(rr) < 25 or not sim:
            continue
        inv = sum(1 / od for _, od in rr)
        key = {1: "win", 5: "top5", 10: "top10", 20: "top20"}[N]
        for run, od in rr:
            fair = (1 / od) * N / inv
            ours = (sim.get(run) or sim.get(RU.norm(run)) or {}).get(key)
            if ours is None:
                continue
            if N == 1:
                if ours >= OUT_RATIO * fair and ours * od - 1 >= OUT_EV:
                    preview.append({"stream": "E3-outright", "runner": run, "market": mt,
                                    "odds": od, "edge": round(ours - fair, 3)})
            elif ours - fair >= TN_EDGE and od >= TN_MIN_ODDS:
                preview.append({"stream": "E3-top%d" % N, "runner": run, "market": mt,
                                "odds": od, "edge": round(ours - fair, 3)})

    # ---- birdies-or-better (Poisson-binomial; its own gate — currently zero captured
    # FD rows, so structurally preview-only until the trap catches the market) ----
    try:
        import pga_birdies as B
        b_armed, _bn = B.birdie_gate()
        brows = [(mkt, mt, run, od, hc) for mkt, mt, run, od in rows
                 for hc in [None]] if False else []
        brows = [(mkt, mt, run, od) for mkt, mt, run, od in rows
                 if "BIRD" in (mt or "").upper() or "irdie" in (mkt or "")]
        if brows:
            BR, _fr = B.rates()
            BRn = {RU.norm(k): v for k, v in BR.items()}
            con_h = sqlite3.connect(HERE / "golf_lines.sqlite")
            for mkt, mt, run, od in brows:
                rr = BRn.get(RU.norm(run))
                if not rr or not od or od < 1.3:
                    continue
                hc = con_h.execute("SELECT handicap FROM golf_lines WHERE market=? AND "
                                   "runner=? ORDER BY collected_at DESC LIMIT 1",
                                   (mkt, run)).fetchone()
                import re as _re
                k_t = None
                if hc and hc[0] is not None:
                    k_t = int(float(hc[0]) + 0.5)             # o3.5 -> P(4+)
                else:
                    m_ = _re.search(r"(\d+)\+", str(run) + " " + str(mkt))
                    if m_:
                        k_t = int(m_.group(1))
                if not k_t:
                    continue
                ours = B.p_x_or_more(rr, k_t)
                fair = 1 / od                                  # one-sided; vig-uncorrected v1
                if ours - fair >= 0.05:
                    preview.append({"stream": "E3-birdies", "runner": run,
                                    "market": mkt[:60], "odds": od,
                                    "edge": round(ours - fair, 3)})
            con_h.close()
    except Exception as _be:
        print(f"  birdie pricing skipped: {str(_be)[:60]}")

    preview.sort(key=lambda x: -x["edge"])
    preview = preview[:15]
    if armed and preview:
        con = sqlite3.connect(PAPER)
        con.execute(E1.DDL)
        for pv in preview:
            key = f"{evn}|{pv['market']}|{pv['runner']}|{pv['stream']}"
            cur = con.execute(
                "INSERT OR IGNORE INTO flags VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,NULL,NULL)",
                (key, now, evn, pv["market"], pv["stream"], pv["runner"], "",
                 pv["odds"], pv["edge"], "", ""))
            flags.append(pv) if cur.rowcount else None
        con.commit()
        con.close()
        print(f"  E3 flags logged: {len(flags)}")
    else:
        print(f"  E3 preview rows: {len(preview)} (not logged — gate not passed)")

    # board: fold into pga_board.json via E1's writer, with the preview attached
    E1._write_board(evn)
    try:
        b = json.loads(E1.BOARD.read_text())
        b["e3"] = {"armed": armed, "g2_n": n_g2, "rows": preview[:8]}
        tmp = E1.BOARD.with_suffix(".tmp")
        tmp.write_text(json.dumps(b))
        tmp.replace(E1.BOARD)
    except (OSError, ValueError) as e:
        print(f"  board merge skipped: {e}")


if __name__ == "__main__":
    main()
