#!/usr/bin/env python3
"""TWO-PASS VALIDATION of the FanDuel search-based main-line recovery.

WHY A SECOND PASS. Both bugs found 2026-08-06 were invisible to a single hand-run:
  1. FD_SEARCH_GAP was 600s == wnba_tonight.FRESH_MIN. posted_props sets
     cutoff = (newest stamp for this player, ANY stat) - FRESH_MIN, and fd_collect rewrites
     the milestone rungs every ~4 min, continuously advancing `latest`. A recovered main line
     went stale the instant it became eligible to refresh -> worked exactly once (now 180s).
  2. fetch() queried the FULL name; FanDuel search does not reliably match one ("Nyadiew
     Puoch" -> nothing, "Puoch" -> her market) -> zero rows for everyone, read as "no line".
Neither shows up until the recovered rung has to SURVIVE the regular collector overwriting
around it. Hence: recover, then wait past FRESH_MIN, then look again.

PASS = a recovered two-sided rung is STILL returned by posted_props after the wait AND
_main_line() is not None. Anything else is a FAIL and the recovery path is not fixed.
"""
import subprocess, sys, time, datetime as dt

sys.path.insert(0, "/home/ubuntu/tennis-odds-collector")
import os
os.chdir("/home/ubuntu/tennis-odds-collector")

WAIT_S = 12 * 60          # > FRESH_MIN (10 min)
OUT = "/home/ubuntu/twopass_report.txt"
log_lines = []


def log(m):
    print(m, flush=True)
    log_lines.append(str(m))


def probe(names):
    """-> {player: (rungs, main_line)} for points, read through the REAL posted_props."""
    import importlib
    import wnba_tonight as T
    importlib.reload(T)                     # fresh module = fresh cache/db handle
    out = {}
    for n in names:
        pp = T.posted_props(n).get("points", {})
        out[n] = (sorted(pp), T._main_line(pp))
    return out


def main():
    log(f"=== TWO-PASS TEST {dt.datetime.now(dt.timezone.utc).isoformat()} ===")

    import wnba_ladder_guard as GUARD
    bad = GUARD.scan()
    milestone = sorted(bad)
    log(f"\n[1] ladder guard: {len(milestone)} player(s) milestone-only")
    log("    " + ", ".join(milestone[:14]) + (" ..." if len(milestone) > 14 else ""))
    if not milestone:
        log("\nNo milestone-only ladders on this slate — nothing to validate. INCONCLUSIVE.")
        return 2

    log("\n[2] running wnba_fd_search.py --force")
    r = subprocess.run([sys.executable, "wnba_fd_search.py", "--force"],
                       capture_output=True, text=True, timeout=900)
    for ln in (r.stdout or "").strip().splitlines():
        log("    " + ln)
    if r.returncode != 0:
        log(f"    !! exit {r.returncode}: {(r.stderr or '')[:200]}")

    before = probe(milestone)
    recovered = [n for n, (rungs, ml) in before.items() if ml is not None]
    log(f"\n[3] immediately after recovery: {len(recovered)} player(s) now have a main line")
    for n in recovered[:10]:
        log(f"    {n:<24} rungs={before[n][0]}  main={before[n][1]}")
    if not recovered:
        log("\nFAIL — recovery produced no two-sided rung for ANY player.")
        log("      (bug 2 class: the search query itself is returning nothing)")
        return 1

    log(f"\n[4] waiting {WAIT_S//60} min for fd_collect to write around it "
        f"(FRESH_MIN=10) ...")
    time.sleep(WAIT_S)

    after = probe(recovered)
    held = [n for n in recovered if after[n][1] is not None]
    lost = [n for n in recovered if after[n][1] is None]
    log(f"\n[5] after the wait: {len(held)}/{len(recovered)} still have a main line")
    for n in recovered[:10]:
        tag = "HELD" if after[n][1] is not None else "LOST -> reverted to milestone-only"
        log(f"    {n:<24} rungs={after[n][0]}  main={after[n][1]}  {tag}")

    verdict = "PASS" if held and not lost else ("PARTIAL" if held else "FAIL")
    log(f"\n=== VERDICT: {verdict} ===")
    if verdict != "PASS":
        log("    the FD_SEARCH_GAP=180s fix did NOT hold; recovered rungs are still aging out")

    # did anything actually flag?
    log("\n[6] does any recovered player FLAG?")
    try:
        import wnba_tonight as T, wnba_wowy as W, statistics as st
        pl = W.players()
        for n in held[:8]:
            v = pl.get(n)
            if not v:
                continue
            blog = W.game_log(v["id"])
            edges = T.prop_edges(n, blog, v["min"], None, None, None) or []
            best = max(edges, key=lambda e: e["ev"]) if edges else None
            if best:
                bar = 0.10 if best["side"] == "over" else 0.04
                log(f"    {n:<24} {best['stat']} {best['side']} {best['line']:g} "
                    f"EV {best['ev']*100:+.1f}% {'** CLEARS **' if best['ev'] >= bar else ''}")
            else:
                log(f"    {n:<24} no qualifying rung")
    except Exception as e:
        log(f"    (flag check skipped: {type(e).__name__} {e})")

    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as e:
        log(f"\nERROR: {type(e).__name__}: {e}")
        rc = 3
    open(OUT, "w").write("\n".join(log_lines) + "\n")
    # fire-and-forget notify; never let a notify failure change the verdict
    try:
        import wnba_tonight as T
        subprocess.run(["curl", "-s", "-d",
                        "WNBA two-pass test: " + ("\n".join(log_lines))[-350:],
                        "ntfy.sh/" + (T._ntfy_topic() if hasattr(T, "_ntfy_topic") else "")],
                       timeout=20)
    except Exception:
        pass
    sys.exit(rc)
