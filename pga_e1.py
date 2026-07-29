"""⛳ E1 — WAVE/WEATHER TIMING meter (PGA_PLAN.md Phase 3, stream E1; PAPER ONLY).

THE EDGE (the plan's highest-prior thesis, the opener-strike analog): matchup prices post
before the weather picture firms. Thu/Fri waves alternate (AM Thu → PM Fri), so when the
forecast says one wave draws meaningfully more wind, the cross-wave matchup is mispriced
until the book reprices. We flag the LOW-wind side at the current FanDuel price and let the
paper record judge.

CONSTITUTION COMPLIANCE:
  law 1  real FanDuel prices only (golf_lines.sqlite, the running collector)
  law 5  never gated on the book having reacted — we fire on the forecast, period
  law 7  paper meter with the tripwire defined BEFORE launch (in pga_grade.py):
         bench + alarm if <52% of implied-breakeven pace after 25 graded

MECHANICS. 72-hole matchbets carry BOTH waves (the pair flips Fri), so the differential is
summed over R1 (actual tee) + R2 (estimated flipped wave: the other wave's median tee,
+24h). Single-round matchbets use that round alone. 3-balls tee off TOGETHER — no wave
differential exists, so E1 skips them by design (they belong to E3/props, not this meter).

No ntfy anywhere in this file — shadows never ping.
"""
import datetime as dt
import json
import re
import sqlite3
import statistics as st
import urllib.request
from pathlib import Path

import pga_field as F

HERE = Path(__file__).resolve().parent
DB = HERE / "golf_lines.sqlite"
PAPER = HERE / "pga_paper.sqlite"
BOARD = HERE / "pga_board.json"
THRESH_KMH = 6.0        # mean cross-wave wind differential (km/h) worth flagging (~4 mph)
MIN_ODDS = 1.60         # don't meter juiced favorites — clean measurement wants fair prices
WINDOW_H = 5            # hours of exposure per round from the tee time

DDL = """CREATE TABLE IF NOT EXISTS flags(
    key TEXT PRIMARY KEY, flagged_at TEXT, event TEXT, market TEXT, stream TEXT,
    runner TEXT, opp TEXT, odds REAL, d_wind REAL, tee_r TEXT, tee_o TEXT,
    result TEXT, pnl REAL, graded_at TEXT)"""


def wind_hours(lat, lon, days=4):
    """{iso_hour_utc: wind km/h} from open-meteo (free, keyless)."""
    u = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
         "&hourly=wind_speed_10m&forecast_days=%d&timezone=UTC" % (lat, lon, days))
    d = json.load(urllib.request.urlopen(
        urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=25))
    h = d.get("hourly") or {}
    return dict(zip(h.get("time") or [], h.get("wind_speed_10m") or []))


def exposure(w, tee_iso, hours=WINDOW_H):
    """Mean wind over [tee, tee+hours). None if the forecast doesn't cover it."""
    try:
        t0 = dt.datetime.fromisoformat(tee_iso.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None
    vals = []
    for k, v in w.items():
        try:
            tk = dt.datetime.fromisoformat(k)
        except ValueError:
            continue
        if t0 <= tk < t0 + dt.timedelta(hours=hours):
            vals.append(v)
    return st.mean(vals) if vals else None


def latest_matchups(event_like):
    """[(market, runner, opp, odds)] from the newest snapshot of FD matchbets."""
    con = sqlite3.connect(DB)
    ts = con.execute("SELECT MAX(collected_at) FROM golf_lines WHERE event LIKE ?",
                     (event_like,)).fetchone()[0]
    if not ts:
        return [], None
    rows = con.execute(
        "SELECT market, runner, odds FROM golf_lines WHERE collected_at=? AND event LIKE ? "
        "AND market LIKE '%Matchbet%'", (ts, event_like)).fetchall()
    con.close()
    by_mkt = {}
    for mkt, run, od in rows:
        by_mkt.setdefault(mkt, []).append((run, od))
    out = []
    for mkt, rr in by_mkt.items():
        if len(rr) != 2:
            continue
        (r1, o1), (r2, o2) = rr
        out.append((mkt, r1, r2, o1))
        out.append((mkt, r2, r1, o2))
    return out, ts


def norm(n):
    return " ".join(str(n or "").lower().split())


def main():
    ev = F.event()
    name = ev.get("name") or ""
    state, desc = F.status(ev)
    print(f"E1 wave meter — {name} [{desc}]")
    if not name:
        return
    tt = F.tee_times(ev)
    if not tt:
        print("  no tee times posted yet — meter waits (they release Tue/Wed)")
        _write_board(name, [], note="waiting for tee times")
        return
    lat, lon = F.coords(ev)
    if lat is None:
        print("  no course coords — cannot compute wind; skipping")
        return
    w = wind_hours(lat, lon)
    ttn = {norm(k): v for k, v in tt.items()}

    # wave centers from the actual R1 tee sheet — needed to estimate the R2 flip
    tees = sorted(tt.values())
    hrs = []
    for t in tees:
        try:
            hrs.append(dt.datetime.fromisoformat(t.replace("Z", "+00:00")))
        except ValueError:
            pass
    if not hrs:
        print("  unparseable tee times — skipping")
        return
    med = sorted(hrs)[len(hrs) // 2]
    am_c = st.mean([h.timestamp() for h in hrs if h <= med]) if any(h <= med for h in hrs) else None
    pm_c = st.mean([h.timestamp() for h in hrs if h > med]) if any(h > med for h in hrs) else None

    def expo_total(tee_iso):
        """R1 exposure + estimated R2 (flipped wave, +24h). None if forecast can't cover."""
        e1 = exposure(w, tee_iso)
        if e1 is None or am_c is None or pm_c is None:
            return e1, None
        t0 = dt.datetime.fromisoformat(tee_iso.replace("Z", "+00:00"))
        other = pm_c if abs(t0.timestamp() - am_c) < abs(t0.timestamp() - pm_c) else am_c
        r2 = dt.datetime.utcfromtimestamp(other) + dt.timedelta(hours=24)
        e2 = exposure(w, r2.isoformat() + "Z")
        return e1, e2

    mkts, snap_ts = latest_matchups("%" + (name.split()[-2] if len(name.split()) > 1 else name) + "%")
    if not mkts:
        # event-name mismatch between ESPN and FD is common — fall back to the busiest event
        con = sqlite3.connect(DB)
        ev_fd = con.execute("SELECT event, COUNT(*) c FROM golf_lines WHERE collected_at >= "
                            "datetime('now', '-1 day') AND event LIKE '%PGA%' "
                            "GROUP BY event ORDER BY c DESC LIMIT 1").fetchone()
        con.close()
        if ev_fd:
            mkts, snap_ts = latest_matchups(ev_fd[0].strip())
    print(f"  matchbets in snapshot: {len(mkts) // 2}  (ts {snap_ts})")

    con = sqlite3.connect(PAPER)
    con.execute(DDL)
    flags = 0
    for mkt, runner, opp, odds in mkts:
        if not odds or odds < MIN_ODDS:
            continue
        tr, to = ttn.get(norm(runner)), ttn.get(norm(opp))
        if not tr or not to:
            continue
        r1r, r2r = expo_total(tr)
        r1o, r2o = expo_total(to)
        if r1r is None or r1o is None:
            continue
        er = r1r + (r2r or 0)
        eo = r1o + (r2o or 0)
        d = eo - er                       # positive = OPP draws more wind = flag RUNNER
        per_round = d / (2 if (r2r is not None and r2o is not None) else 1)
        if per_round < THRESH_KMH:
            continue
        key = f"{name}|{mkt}|{runner}"
        cur = con.execute(
            "INSERT OR IGNORE INTO flags VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,NULL,NULL)",
            (key, dt.datetime.utcnow().replace(microsecond=0).isoformat(), name, mkt,
             "E1", runner, opp, odds, round(per_round, 1), tr, to))
        if cur.rowcount:
            flags += 1
            print(f"  ⛳E1 FLAG {runner} over {opp} @{odds:.2f}  "
                  f"wind diff {per_round:+.1f} km/h/round  ({mkt[:52]})")
    con.commit()
    con.close()
    print(f"  new flags: {flags}")
    _write_board(name)


def _write_board(event_name, open_rows=None, note=""):
    """pga_board.json — everything the dashboard panel renders. Rewritten by e1 AND grade."""
    rec = {"w": 0, "l": 0, "p": 0, "units": 0.0}
    opens = []
    try:
        con = sqlite3.connect(PAPER)
        con.execute(DDL)
        for r, in con.execute("SELECT result FROM flags WHERE result IS NOT NULL"):
            rec["w" if r == "W" else ("l" if r == "L" else "p")] += 1
        rec["units"] = round(con.execute(
            "SELECT COALESCE(SUM(pnl),0) FROM flags WHERE pnl IS NOT NULL").fetchone()[0], 2)
        opens = [dict(zip(("market", "runner", "opp", "odds", "d_wind", "flagged_at"), row))
                 for row in con.execute(
                     "SELECT market, runner, opp, odds, d_wind, flagged_at FROM flags "
                     "WHERE result IS NULL ORDER BY flagged_at DESC LIMIT 12")]
        con.close()
    except Exception as e:                                    # noqa: BLE001
        note = note or f"board data error: {str(e)[:40]}"
    clv = {}
    try:
        clv = json.loads((HERE / "golf_clv.json").read_text())
    except (OSError, ValueError):
        pass
    tmp = BOARD.with_suffix(".tmp")
    tmp.write_text(json.dumps({
        "ts": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "event": event_name, "note": note, "record": rec, "open": opens, "clv": clv}))
    tmp.replace(BOARD)


if __name__ == "__main__":
    main()
