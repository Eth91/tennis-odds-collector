#!/usr/bin/env python3
"""wnba_premise_sweep — pull plays whose PREMISE has publicly returned, before tip.

THE GAP (2026-08-06). Three LA plays were flagged and PINGED on the premise "Ariel Atkins is
out": Wheeler reb_ast 8.5, Makani points 7.5 and 9.5. At 00:07:19Z RotoWire posted
"Ariel Atkins: Will play Thursday" (class IN) — 1h53m before the 02:00Z tip. The system LOGGED
that news and did nothing with it. Atkins started and played 29 minutes; the rows voided
post-game via wnba_ledger._premise_really_broke().

But that function runs at GRADING time — it is a post-mortem, not a guard. So for two hours the
plays stayed live on the board, stayed pinged on the phone, and kept consuming TOP-2 slots on a
team-game that a real play could have used. A void is not free.

wnba_slip.suppressed() is the ONE gate the board and the slip share, and it drops a play when a
human vetoed it or when its SUBJECT is firm-out. There is no case for "the OUT player came back",
which is this bug. Rather than edit a frozen v1.4 file, this writes the durable veto the gate
ALREADY honours — data, not code — so board, slip and alert all drop the play together, which is
the coherence rule (if it pings it is on the board; one gate, not three).

The ledger row is deliberately left to grade normally. Per suppressed()'s own docstring a wrong
call must surface in the record rather than hide there — this removes the play from tonight's
selection, it does not erase the evidence.

CONSERVATIVE ON MULTI-OUT: if ANY named member of the out-set returns, the play is pulled. The
projection was built on the full vacated pool (vacated = sum over the set), so a member returning
falsifies the price even when others still sit.
"""
import datetime as dt
import io
import json
import os
import re
import sqlite3
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, "/home/ubuntu/tennis-odds-collector")
os.chdir("/home/ubuntu/tennis-odds-collector")

NEWS = "wnba_news_log.jsonl"
VETO = "wnba_vetoed.txt"
LEDGER = "/home/ubuntu/wnba_data/wnba_ledger.sqlite"


def slate_date():
    """ET date — the basis pred_date is written on."""
    return dt.datetime.now(ZoneInfo("America/New_York")).date().isoformat()


def returned_today(slate):
    """{player} that a source has declared IN for this slate."""
    back = {}
    try:
        for ln in io.open(NEWS, encoding="utf-8"):
            ln = ln.strip()
            if not ln:
                continue
            try:
                j = json.loads(ln)
            except ValueError:
                continue
            if (j.get("class") or "").upper() != "IN":
                continue
            ts = str(j.get("ts") or "")
            # news ts is UTC; a slate's news spans the ET day and the UTC morning after
            if ts[:10] not in (slate, (dt.date.fromisoformat(slate)
                                       + dt.timedelta(days=1)).isoformat()):
                continue
            p = (j.get("player") or "").strip()
            if p:
                back[p] = (ts, j.get("src"), j.get("text"))
    except OSError:
        pass
    return back


def _veto_key(date, player, stat, line):
    return f"{date}|{player.split()[-1]}|{stat}|{line:g}"


def existing_vetoes():
    seen = set()
    try:
        for ln in io.open(VETO, encoding="utf-8"):
            ln = ln.strip()
            if ln and not ln.startswith("#"):
                seen.add("|".join(ln.split("|")[:4]))
    except OSError:
        pass
    return seen


def main():
    # --replay <date>: match against ALL rows for that slate (not just unsettled) and WRITE
    # NOTHING. Exists because the live path can only be exercised when a premise actually
    # returns mid-slate; without it the matching logic ships untested, which is how the two
    # fd_search bugs got through on 2026-08-06.
    replay = None
    if "--replay" in sys.argv:
        replay = sys.argv[sys.argv.index("--replay") + 1]
    slate = replay or slate_date()
    back = returned_today(slate)
    if not back:
        print(f"premise sweep: no IN-class news for {slate} — nothing to pull")
        return 0

    con = sqlite3.connect(f"file:{LEDGER}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(
        "SELECT pred_date, player, stat, line, out_player, result FROM predictions "
        "WHERE pred_date=?" + ("" if replay else " AND (result IS NULL OR result='')"),
        (slate,))]
    con.close()
    if not rows:
        print(f"premise sweep: {len(back)} returned ({', '.join(sorted(back))}) "
              f"but no UNSETTLED rows on {slate} — nothing to pull")
        return 0

    seen = existing_vetoes()
    new = []
    for r in rows:
        outs = [x.strip() for x in re.split(r",|;", r.get("out_player") or "") if x.strip()]
        hit = [o for o in outs if o in back]
        if not hit:
            continue
        key = _veto_key(r["pred_date"], r["player"], r["stat"], float(r["line"]))
        if key in seen:
            continue
        seen.add(key)
        who = ", ".join(hit)
        ts, src, text = back[hit[0]]
        new.append((key, r, who, ts, src, text, outs))

    if not new:
        print(f"premise sweep: {len(back)} returned, {len(rows)} unsettled, "
              f"0 newly affected (already vetoed or different premise)")
        return 0

    if replay:
        print(f"REPLAY {slate}: would pull {len(new)} play(s) — writing nothing")
        for _k, r, who, ts, src, _t, outs in new:
            print(f"    {r['player']:<22} {r['stat']:<8} {r['line']:g}  "
                  f"premise [{', '.join(outs)}] -> {who} IN via {src} at {ts}  "
                  f"(row result={r.get('result') or 'unsettled'})")
        return 0

    with io.open(VETO, "a", encoding="utf-8") as f:
        f.write(f"\n# PREMISE RETURNED — auto-swept {dt.datetime.now(dt.timezone.utc).isoformat()}\n")
        for key, r, who, ts, src, text, outs in new:
            reason = (f"PREMISE RETURNED: {who} declared IN by {src} at {ts} "
                      f"({text}). Play was priced on the absence of [{', '.join(outs)}]; "
                      f"a returning member falsifies the vacated pool the projection used. "
                      f"Pulled from board+slip pre-tip; the ledger row still grades.")
            f.write(f"{key}|{reason}\n")
            print(f"  PULLED {r['player']} {r['stat']} {r['line']:g}  <- {who} is IN ({src})")

    print(f"premise sweep: pulled {len(new)} play(s) on {slate}")
    try:
        import wnba_tonight as T
        topic = T._ntfy_topic() if hasattr(T, "_ntfy_topic") else ""
        if topic:
            import subprocess
            body = "PREMISE RETURNED — pulled:\n" + "\n".join(
                f"{r['player']} {r['stat']} {r['line']:g} ({who} IN)"
                for _k, r, who, *_ in new)
            subprocess.run(["curl", "-s", "-H", "Title: WNBA premise pulled",
                            "-d", body, f"ntfy.sh/{topic}"], timeout=20)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
