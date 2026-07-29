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

    # ---- birdies-or-better: MARKET-ANCHORED LEVEL, player-relative edges ----
    # Two corrections after v1 ran +11.3pts hot on every Over (one-sided = model error):
    #  1. PAR MIX. v1 priced every course as par-72 4/10/4. Detroit GC is par 70 (4/12/2),
    #     so v1 invented two par-5s at a 47% birdie rate each. Now uses mix_for(tid):
    #     exact hole counts from our harvest, else the par-total rule (validated 8/8 at
    #     par 72 against real hole counts).
    #  2. COURSE LEVEL IS NOT KNOWABLE PRE-TOURNAMENT. Measured on 15 harvested events,
    #     courses vary 0.78x-1.29x in birdie rate BEYOND their par mix (sd 13%) — larger
    #     than any player edge we could carry. The market CAN see this (course history,
    #     setup, agronomy); we cannot. So we solve one multiplier LAM that makes our
    #     field-average P(over) match the market's, and bet only DEVIATIONS from it.
    #     This is the plan's "mispricing detector, not oracle" made literal: we never
    #     claim to know the course level, only who beats it.
    try:
        import pga_birdies as B
        import re as _re
        brows = [(mkt, mt, run, od) for mkt, mt, run, od in rows
                 if ("BIRDIES" in (mt or "").upper() or "irdie" in (mkt or ""))
                 and od and od > 1.0]
        if brows:
            BR, _fr = B.rates()
            BRn = {RU.norm(k): v for k, v in BR.items()}
            try:
                # resolve the ORCHESTRATOR tid from the event name — ESPN ids are a
                # different namespace and silently defaulted every course to par 72.
                _tid = B.tid_for_name(evn)
                _mix = B.mix_for(_tid) if _tid else None
                if _mix:
                    print(f"  birdies: course {_tid} par mix {_mix}")
            except Exception:
                _mix = None
            if not _mix:
                _mix = B.DEFAULT_MIX
            # parse the board once
            parsed = []
            for mkt, mt, run, od in brows:
                pm = _re.match(r"(.+?)\s+Total Birdies or Better", mkt)
                sm = _re.search(r"(Over|Under)\s+([\d.]+)", run)
                if not pm or not sm:
                    continue
                rr = BRn.get(RU.norm(pm.group(1).strip()))
                if not rr:
                    continue
                parsed.append((pm.group(1).strip(), sm.group(1).lower(),
                               float(sm.group(2)), od, mkt, rr))
            overs = [x for x in parsed if x[1] == "over"]
            LAM = 1.0
            if len(overs) >= 8:
                # bisect LAM so mean model P(over) == mean market implied P(over)
                tgt = sum(1 / x[3] for x in overs) / len(overs)
                lo, hi = 0.5, 1.6
                for _ in range(28):
                    LAM = (lo + hi) / 2
                    scaled = {p: min(v * LAM, 0.95) for p, v in ()} if False else None
                    m = 0.0
                    for _pl, _sd, ln, _od, _mk, rr in overs:
                        rs = {k: min(v * LAM, 0.95) for k, v in rr.items()}
                        m += B.p_x_or_more(rs, int(ln + 0.5), _mix)
                    m /= len(overs)
                    if m > tgt:
                        hi = LAM
                    else:
                        lo = LAM
                print(f"  birdies: course-level LAM={LAM:.3f} "
                      f"(market-anchored on {len(overs)} Over lines, mix {_mix})")
            seen_b = set()
            for player, side, line, od, mkt, rr in parsed:
                rs = {k: min(v * LAM, 0.95) for k, v in rr.items()}
                p_over = B.p_x_or_more(rs, int(line + 0.5), _mix)
                ours = p_over if side == "over" else 1 - p_over
                edge = ours - 1 / od
                key = (RU.norm(player), side, line)
                if edge >= 0.05 and key not in seen_b:
                    seen_b.add(key)
                    preview.append({"stream": "E3-birdies",
                                    "runner": f"{player} {side} {line:g}",
                                    "market": mkt[:60], "odds": od,
                                    "edge": round(edge, 3)})
    except Exception as _be:
        print(f"  birdie pricing skipped: {str(_be)[:70]}")

    # DEDUPE (2026-07-29): the same underlying market reaches us under several mtypes
    # (TOP_20_FINISH_IMG vs TOP_20_FINISH_(INCL._TIES)) and again from the competition
    # page, so an un-deduped preview showed the same play eight times and crowded out
    # every other stream. Keep the best-edge instance per (stream, runner, line).
    _best = {}
    for _pv in preview:
        _k = (_pv["stream"], RU.norm(_pv["runner"]), _pv.get("odds"))
        if _k not in _best or _pv["edge"] > _best[_k]["edge"]:
            _best[_k] = _pv
    preview = sorted(_best.values(), key=lambda x: -x["edge"])[:15]
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
