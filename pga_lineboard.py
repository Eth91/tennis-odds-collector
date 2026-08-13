#!/usr/bin/env python3
"""Snapshot the FULL birdie line board, pre-tee, so the base rate is computable later.

WHY THIS EXISTS
The paper record is almost entirely birdie UNDERS, and the only honest way to judge them is
against the rate for players who ACTUALLY CARRIED THAT LINE. That could not be computed for
the Rocket Classic or Wyndham: `golf_lines` is a 2-day rolling buffer and `golf_moves` only
retains markets the mover cared about, so exactly ONE past 4.5-line player could be matched.
Two tournaments of evidence, and the denominator was gone.

⚠️ IT MUST CAPTURE THE WHOLE BOARD, NOT OUR FLAGS. A base rate built only from bets we made is
not a base rate -- it is the same selection we are trying to test. Every player with a posted
line goes in, flagged or not.

WRITE-ONCE per (event, rnd, player, line): the FIRST sighting is kept, because the question is
"what was available before anyone teed off", not "what did it drift to". Re-running is safe and
idempotent; a later run only fills in players whose lines had not yet been posted.
"""
import datetime as dt
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "golf_lines.sqlite"
DB = HERE / "pga_lineboard.sqlite"

DDL = """CREATE TABLE IF NOT EXISTS board(
  event TEXT, rnd INTEGER, player TEXT, line REAL,
  over_odds REAL, under_odds REAL,
  first_seen TEXT, tee_utc TEXT, pre_tee INTEGER,
  PRIMARY KEY(event, rnd, player, line))"""


def _norm(x):
    return "".join(ch for ch in str(x or "").lower() if ch.isalnum())


def capture(event_filter=None):
    if not SRC.exists():
        print(f"pga_lineboard: {SRC.name} missing"); return 0
    src = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True, timeout=30)
    src.row_factory = sqlite3.Row
    rows = src.execute(
        "SELECT event, market, runner, odds, collected_at FROM golf_lines "
        "WHERE mtype='PLAYER_BIRDIES_OR_BETTER'").fetchall()
    src.close()

    # (event, rnd, player, line) -> {"over"/"under": odds, "seen": earliest}
    agg = {}
    for r in rows:
        ev = (r["event"] or "").strip()
        if event_filter and _norm(event_filter) not in _norm(ev):
            continue
        rm = re.search(r"Round\s+(\d)", r["market"] or "")
        mm = re.search(r"^(.*?)\s+(Over|Under)\s+([\d.]+)$", (r["runner"] or "").strip(), re.I)
        if not rm or not mm:
            continue
        k = (ev, int(rm.group(1)), mm.group(1).strip(), float(mm.group(3)))
        d = agg.setdefault(k, {"over": None, "under": None, "seen": r["collected_at"]})
        d[mm.group(2).lower()] = float(r["odds"] or 0) or None
        if r["collected_at"] and r["collected_at"] < d["seen"]:
            d["seen"] = r["collected_at"]

    try:
        import pga_tee_gate as TG
    except Exception:                                                  # noqa: BLE001
        TG = None

    con = sqlite3.connect(DB, timeout=60)
    con.execute("PRAGMA busy_timeout=60000")
    con.execute(DDL)
    n = 0
    for (ev, rnd, player, line), d in sorted(agg.items()):
        tee, pre = None, None
        if TG:
            try:
                t = TG.deadline(ev, f"{player} Total Birdies or Better Round {rnd}")
                t = t[0] if isinstance(t, tuple) else t
                if isinstance(t, dt.datetime):
                    tee = t.isoformat()
                    seen = dt.datetime.fromisoformat(str(d["seen"]).replace("Z", ""))
                    pre = 1 if seen < t else 0
            except Exception:                                          # noqa: BLE001
                pass
        cur = con.execute(
            "INSERT OR IGNORE INTO board(event,rnd,player,line,over_odds,under_odds,"
            "first_seen,tee_utc,pre_tee) VALUES(?,?,?,?,?,?,?,?,?)",
            (ev, rnd, player, line, d["over"], d["under"], d["seen"], tee, pre))
        n += cur.rowcount
    con.commit()
    tot = con.execute("SELECT COUNT(*) FROM board").fetchone()[0]
    pre_n = con.execute("SELECT COUNT(*) FROM board WHERE pre_tee=1").fetchone()[0]
    print(f"pga_lineboard: +{n} new | {tot} rows total | {pre_n} captured PRE-TEE")
    for ev, rnd, c, p in con.execute(
            "SELECT event, rnd, COUNT(*), SUM(COALESCE(pre_tee,0)) FROM board "
            "GROUP BY event, rnd ORDER BY event, rnd"):
        print(f"   {ev[:38]:38s} R{rnd}  {c:3d} players  ({p} pre-tee)")
    con.close()
    return n


if __name__ == "__main__":
    capture(sys.argv[1] if len(sys.argv) > 1 else None)
