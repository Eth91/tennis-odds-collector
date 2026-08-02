#!/usr/bin/env python3
"""⛳ Golf LINE MOVEMENT — paired open→close per market/runner. The missing half of the collector.

WHY THIS EXISTS. golf_collect.py already snapshots every FanDuel golf price every 30 minutes, so
the movement is technically in golf_lines.sqlite. In practice it is unusable for the one question
that matters — *does the price move, and does it move toward us* — for four reasons:

  1. NO CLOSE. The table has no idea when a bet stopped being available. A golf wave spans ~7
     hours, so "the round started" is not the deadline; the deadline is that PLAYER's tee. Without
     it you cannot separate a pre-tee price from an in-play one, and in-play golf prices move for
     reasons that have nothing to do with the market's opinion.
  2. NO PAIRING. Answering "how far did this line move" means a correlated subquery per runner
     against 90 MB of rows, per analysis. Nobody runs that, so nobody looks.
  3. IT OUTGREW GIT. golf_lines.sqlite reached 89.6 MiB — inside GitHub's 100 MB hard limit but
     past the 50 MB warning — and was dropped from tracking at 2026-08-01T07:32Z. The raw history
     now lives only on the VM. This table is the ~2% of it worth keeping, so the movement record
     survives on the Mac even though the snapshot archive cannot.
  4. DUPLICATES. golf_lines stores each (market, runner) up to ~6x per snapshot from the overlapping
     .com/.ca/competition sweeps. Same rule as pga_e3's dedupe: one price per runner per snapshot,
     the shortest posted.

WHAT "OPEN" HONESTLY MEANS. `open_*` is the FIRST PRICE THIS COLLECTOR SAW, not the book's true
opener. At a 30-minute cadence a market that posts Wednesday morning is caught within 30 minutes,
but a market that posts between passes is not. The column is named open_* for readability and every
report below labels it "first seen". It is not evidence about where FanDuel actually opened.

THE CLOSE IS FROZEN, NEVER OVERWRITTEN. `pre_*` tracks the latest price seen STRICTLY before the
deadline and keeps moving; the instant a pass observes now >= deadline, `pre_*` is copied into
`close_*` and never touched again. Two things follow, and both are the point:
  - a market that VANISHES at the tee (the normal case in golf — FD pulls the round-score O/U when
    the player hits) still gets a close, because the freeze sweep runs over stored keys, not over
    the rows in this pass;
  - an in-play price can never contaminate a close, because close_* is write-once.

DEADLINES COME FROM pga_tee_gate, NOT FROM A SECOND COPY. That module is already the single answer
to "when does this bet stop being available" — single player -> that player's tee, matchbet -> the
earlier of the two, field outright -> the R1 first tee. A second implementation would drift from it
within a week; that has already happened twice in this repo. An UNRESOLVED deadline stays NULL and
the key simply never gets a close, which is the honest outcome — it is not evidence of anything.

    python3 golf_moves.py              # fold the newest golf_lines snapshot in (what cron calls)
    python3 golf_moves.py --backfill    # replay the entire golf_lines history (VM only, ~minutes)
    python3 golf_moves.py --report      # how much do golf lines actually move, by market type
    python3 golf_moves.py --clv         # our flagged price vs the close — the real softness test
"""
import datetime as dt
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LINES = HERE / "golf_lines.sqlite"
MOVES = HERE / "golf_moves.sqlite"
PAPER = HERE / "pga_paper.sqlite"

NO_HCAP = -999.0          # SQLite treats NULLs in a PK as distinct, which would duplicate every
                          # handicap-less market on every pass. Sentinel instead.

DDL = """
CREATE TABLE IF NOT EXISTS moves(
    event TEXT, market TEXT, mtype TEXT, runner TEXT, hcap REAL,
    rnd INTEGER,                      -- parsed from the market name; NULL for 72-hole markets
    tee_utc TEXT, tee_why TEXT,       -- from pga_tee_gate; NULL = unresolved, never guessed
    open_ts TEXT, open_odds REAL,     -- FIRST SEEN by this collector, not the book's opener
    pre_ts TEXT, pre_odds REAL,       -- running: latest price strictly before the deadline
    close_ts TEXT, close_odds REAL,   -- pre_* frozen at the deadline; WRITE ONCE
    last_ts TEXT, last_odds REAL,     -- latest price at all, in-play included
    min_odds REAL, max_odds REAL,
    n_obs INTEGER DEFAULT 0, n_pre INTEGER DEFAULT 0,
    PRIMARY KEY(event, market, runner, hcap));
CREATE INDEX IF NOT EXISTS idx_mv_ev ON moves(event, rnd);
CREATE INDEX IF NOT EXISTS idx_mv_mt ON moves(mtype);
"""

_RND = re.compile(r"Round\s+(\d)", re.I)


def _open_moves(write=True):
    """Open the movement DB. `write=False` NEVER CREATES THE FILE, and that is a safety rail.

    golf_moves.sqlite is written by exactly one machine (the VM's collector) and travels to the Mac
    through git, same as pga_paper.sqlite. A bare sqlite3.connect() creates an empty file, so a Mac
    running `--report` would leave a 0-byte DB behind — and one `git add -A` later, the VM's
    `git reset --hard FETCH_HEAD` would apply that empty file over the real one. That is not
    hypothetical: it is exactly the state golf_lines.sqlite was found in on 2026-08-01. Read paths
    open read-only via URI so they fail loudly on a machine that has no copy instead of minting a
    destructive one.
    """
    if not write:
        if not MOVES.exists():
            return None
        return sqlite3.connect("file:%s?mode=ro" % MOVES, uri=True)
    con = sqlite3.connect(str(MOVES))
    con.executescript(DDL)
    return con


def _snapshot(lc, ts):
    """One price per (event, market, runner, handicap) for this snapshot — the shortest posted.

    Same dedupe rule pga_e3 applies to matchbets. Taking MIN rather than "whichever row came back
    first" matters: the .ca and .com sweeps disagree by a tick often enough that an arbitrary pick
    would inject noise indistinguishable from real movement.
    """
    return lc.execute(
        "SELECT event, market, mtype, runner, COALESCE(handicap, ?) hc, MIN(odds) "
        "FROM golf_lines WHERE collected_at=? AND odds > 1.0 "
        "GROUP BY event, market, runner, hc", (NO_HCAP, ts)).fetchall()


def _deadline(cache, event, market):
    """(iso_utc or None, reason) via the shared gate, memoised per (event, market)."""
    k = (event, market)
    if k in cache:
        return cache[k]
    try:
        import pga_tee_gate as TG
        dl, why = TG.deadline(event, market)
        v = (dl.replace(microsecond=0).isoformat() if dl else None, why)
    except Exception as e:                                          # noqa: BLE001
        v = (None, "gate error: %s" % str(e)[:40])
    cache[k] = v
    return v


def fold(ts, mc=None, lc=None, cache=None):
    """Fold one golf_lines snapshot into the movement table. Returns (n_keys, n_frozen)."""
    own = mc is None
    mc = mc or _open_moves()
    lc = lc or sqlite3.connect(str(LINES))
    cache = {} if cache is None else cache

    rows = _snapshot(lc, ts)
    for ev, mkt, mt, run, hc, od in rows:
        tee, why = _deadline(cache, ev, mkt)
        g = _RND.search(str(mkt or ""))
        rnd = int(g.group(1)) if g else None
        pre_tee = bool(tee) and ts < tee

        mc.execute(
            "INSERT INTO moves(event,market,mtype,runner,hcap,rnd,tee_utc,tee_why,"
            "open_ts,open_odds,pre_ts,pre_odds,last_ts,last_odds,min_odds,max_odds,n_obs,n_pre) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?) "
            "ON CONFLICT(event,market,runner,hcap) DO UPDATE SET "
            "  last_ts=excluded.last_ts, last_odds=excluded.last_odds,"
            "  min_odds=MIN(min_odds,excluded.min_odds),"
            "  max_odds=MAX(max_odds,excluded.max_odds),"
            "  n_obs=n_obs+1,"
            # the deadline can arrive AFTER the market does (FD posts round-score O/Us before the
            # tee sheet drops), so fill it in late — but never overwrite one already resolved.
            "  tee_utc=COALESCE(moves.tee_utc, excluded.tee_utc),"
            "  tee_why=COALESCE(moves.tee_why, excluded.tee_why),"
            # pre_* only advances while we are genuinely pre-deadline AND the close is not yet cut.
            "  pre_ts=CASE WHEN excluded.pre_ts IS NOT NULL AND moves.close_ts IS NULL"
            "              THEN excluded.pre_ts ELSE moves.pre_ts END,"
            "  pre_odds=CASE WHEN excluded.pre_ts IS NOT NULL AND moves.close_ts IS NULL"
            "                THEN excluded.pre_odds ELSE moves.pre_odds END,"
            "  n_pre=n_pre+excluded.n_pre",
            (ev, mkt, mt, run, hc, rnd, tee, why,
             ts, od,
             ts if pre_tee else None, od if pre_tee else None,
             ts, od, od, od, 1 if pre_tee else 0))

    # FREEZE SWEEP — over STORED keys, not this pass's rows. A round-score O/U is pulled from the
    # board the moment the player tees off, so it is absent from exactly the snapshot that proves
    # its deadline passed. Sweeping stored keys is what gets those markets a close at all.
    cur = mc.execute(
        "UPDATE moves SET close_ts=pre_ts, close_odds=pre_odds "
        "WHERE close_ts IS NULL AND pre_ts IS NOT NULL AND tee_utc IS NOT NULL AND tee_utc <= ?",
        (ts,))
    frozen = cur.rowcount
    mc.commit()
    if own:
        mc.close()
        lc.close()
    return len(rows), frozen


def latest_ts(lc):
    """Newest snapshot, or None if there is no archive here.

    A bare `sqlite3.connect` CREATES an empty file, so `LINES.exists()` is not evidence the table
    exists — and on the Mac it never will, because the raw archive is gitignored and VM-only. This
    has to degrade to "nothing to do", not raise.
    """
    try:
        r = lc.execute("SELECT MAX(collected_at) FROM golf_lines").fetchone()
    except sqlite3.Error:
        return None
    return r[0] if r else None


def backfill():
    """Replay every snapshot in golf_lines, oldest first. VM only — the Mac has no raw history."""
    lc = sqlite3.connect(str(LINES))
    mc = _open_moves()
    cache = {}
    try:
        stamps = [r[0] for r in lc.execute(
            "SELECT DISTINCT collected_at FROM golf_lines ORDER BY collected_at")]
    except sqlite3.Error:
        print("backfill: no golf_lines archive on this machine — it is VM-only by design")
        return
    print("backfill: %d snapshots" % len(stamps))
    tot = froz = 0
    for i, ts in enumerate(stamps, 1):
        n, f = fold(ts, mc, lc, cache)
        tot += n
        froz += f
        if i % 25 == 0 or i == len(stamps):
            print("  %4d/%d  %s  obs %d  frozen %d" % (i, len(stamps), ts, tot, froz), flush=True)
    lc.close()
    mc.close()
    print("backfill done: %d observations folded, %d closes frozen" % (tot, froz))


# ── reports ─────────────────────────────────────────────────────────────────────────────────────

def _p(od):
    """Implied probability. Movement in ODDS is not comparable across price ranges — 1.90 -> 2.00
    and 8.0 -> 8.1 are the same 0.1 of decimal odds and wildly different opinions. Probability is."""
    return 1.0 / od if od and od > 1.0 else None


def report():
    mc = _open_moves(write=False)
    if mc is None:
        print("golf_moves: no movement DB here — the VM's collector writes it; git pull first")
        return
    tot = mc.execute("SELECT COUNT(*) FROM moves").fetchone()[0]
    if not tot:
        print("golf_moves: empty — run `python3 golf_moves.py --backfill` on the VM first")
        return
    print("=== COVERAGE ===")
    for lab, q in (("keys tracked", "SELECT COUNT(*) FROM moves"),
                   ("deadline resolved", "SELECT COUNT(*) FROM moves WHERE tee_utc IS NOT NULL"),
                   ("close frozen", "SELECT COUNT(*) FROM moves WHERE close_ts IS NOT NULL"),
                   ("open != close (movable)",
                    "SELECT COUNT(*) FROM moves WHERE close_ts IS NOT NULL AND n_pre >= 2")):
        print("  %-24s %d" % (lab, mc.execute(q).fetchone()[0]))
    why = mc.execute("SELECT tee_why, COUNT(*) c FROM moves WHERE tee_utc IS NULL "
                     "GROUP BY 1 ORDER BY c DESC LIMIT 5").fetchall()
    if why:
        print("  unresolved deadlines:")
        for w, c in why:
            print("    %-46s %d" % (str(w)[:46], c))

    print("\n=== HOW FAR DO GOLF LINES MOVE? first seen -> close, in probability ===")
    print("  %-34s %6s %8s %8s %8s" % ("market type", "n", "mean|d|", "median", "p90"))
    rows = mc.execute(
        "SELECT mtype, open_odds, close_odds FROM moves "
        "WHERE close_ts IS NOT NULL AND n_pre >= 2 AND open_odds > 1 AND close_odds > 1").fetchall()
    byt = {}
    for mt, o, c in rows:
        po, pc = _p(o), _p(c)
        if po and pc:
            byt.setdefault(mt or "?", []).append(abs(pc - po))
    shown, thin = 0, []
    for mt, ds in sorted(byt.items(), key=lambda kv: -len(kv[1])):
        if len(ds) < 10:                       # a mean over <10 markets is not a number
            thin.append((mt, len(ds)))
            continue
        ds.sort()
        n = len(ds)
        shown += 1
        print("  %-34s %6d %8.4f %8.4f %8.4f"
              % (mt[:34], n, sum(ds) / n, ds[n // 2], ds[min(n - 1, int(n * 0.9))]))
    if not byt:
        print("  (no market has both a first-seen and a frozen close yet — needs a full round)")
    # NEVER SILENTLY TRUNCATE. A table that just ends reads as "that is all there was".
    if thin:
        print("  suppressed (n<10, too thin to average): %s"
              % ", ".join("%s:%d" % (m[:26], c) for m, c in sorted(thin, key=lambda x: -x[1])[:6]))
    mc.close()


def clv():
    """Our flagged price vs the close on the SAME market/runner. The actual softness test.

    A market is soft for us only if the price we took beats the price the market settled on. This
    is the one measurement that can support "PGA markets are soft" — and it is measured against the
    book's own close, never against the model's opinion, because model-source CLV lies.
    """
    mc = _open_moves(write=False)
    if mc is None:
        print("golf_moves: no movement DB here — the VM's collector writes it; git pull first")
        return
    try:
        pc = sqlite3.connect(str(PAPER))
        flags = pc.execute("SELECT event, market, runner, odds, stream, result FROM flags").fetchall()
        pc.close()
    except sqlite3.Error as e:
        print("no paper ledger: %s" % e)
        return
    # THE TWO SIDES NAME RUNNERS DIFFERENTLY, and a sloppy join here would quietly measure the
    # wrong leg. The ledger writes "Stefano Mazzoli under 69.5" (player + side + line, because a
    # flag has to stand alone); FanDuel's runnerName on the same market is just "Under 69.5", with
    # the line in `handicap`. So O/U markets join on SIDE + LINE, and only name-runner markets
    # (matchbets, top-N) join on the runner string itself.
    ou = re.compile(r"^(.*?)\s+(over|under)\s+([\d.]+)\s*$", re.I)
    hits, miss = [], 0
    for ev, mkt, run, od, stream, res in flags:
        m = ou.match(str(run or ""))
        if m:
            side, line = m.group(2).lower(), float(m.group(3))
            r = mc.execute(
                "SELECT close_odds FROM moves WHERE event=? AND market=? AND close_odds IS NOT NULL"
                " AND LOWER(runner) LIKE ? AND (hcap=? OR runner LIKE ?)",
                (ev, mkt, side + "%", line, "%%%g" % line)).fetchone()
        else:
            r = mc.execute(
                "SELECT close_odds FROM moves WHERE event=? AND market=? AND close_odds IS NOT NULL"
                " AND LOWER(TRIM(runner))=?", (ev, mkt, str(run or "").strip().lower())).fetchone()
        if not r:
            miss += 1
            continue
        pb, pcl = _p(od), _p(r[0])
        if pb and pcl:
            hits.append((stream, pcl - pb, res))
    print("=== CLV vs the FanDuel close (%d flags matched, %d unmatched) ===" % (len(hits), miss))
    if not hits:
        print("  nothing to measure yet. Needs golf_moves populated across a round the flags "
              "were taken in — the movement table only has history from the day it starts.")
        mc.close()
        return
    by = {}
    for s, d, res in hits:
        by.setdefault((s or "?").replace("-shadow", ""), []).append(d)
    print("  %-18s %5s %9s %9s" % ("stream", "n", "mean CLV", "beat %"))
    for s, ds in sorted(by.items(), key=lambda kv: -len(kv[1])):
        n = len(ds)
        print("  %-18s %5d %+9.4f %8.1f%%"
              % (s, n, sum(ds) / n, 100.0 * sum(1 for d in ds if d > 0) / n))
    print("\n  CLV is in probability. Positive = the close agreed with us (we got the better\n"
          "  price). This is the only number that can say a golf market was soft for US.")
    mc.close()


def main():
    a = sys.argv[1:]
    if "--backfill" in a:
        return backfill()
    if "--report" in a:
        return report()
    if "--clv" in a:
        return clv()
    if not LINES.exists():
        print("golf_moves: no golf_lines.sqlite here (the raw archive lives on the VM) — skipped")
        return
    lc = sqlite3.connect(str(LINES))
    ts = latest_ts(lc)
    if not ts:
        lc.close()
        print("golf_moves: golf_lines has no snapshots")
        return
    n, f = fold(ts, lc=lc)
    lc.close()
    print("golf_moves %s: %d keys folded, %d closes frozen" % (ts, n, f))


if __name__ == "__main__":
    main()
