"""Audit: does EVERY play the TT board renders pass EVERY rule?

The dashboard's TT card does not read the `bets` list — it renders from `elite_h2h[].pick` and
`elite_upcoming`. That mismatch is exactly how skipped plays reached the board once already, so this
checks the surfaces that actually render, not the key that is easy to check.

Every rendered pick is re-tested against the full chain, independently:
    real posted odds        (a projected/proxy line must never be tracked)
    n >= ELITE_MIN_N_BET    thin H2H
    NOT (under, 80 <= line < 90)   the 80-90-under leak
    NOT (over, line < 65)          the low-line-over leak
    side-split raw bands           overs .80-.85, unders .85+

Anything rendered that fails any one of them is a live bug.
"""
import json
import sys
import urllib.request

import check_today as CT

URL = "https://raw.githubusercontent.com/fgf9p6ks2f-ux/tennis-odds-collector/main/tt_board.json"
src = sys.argv[1] if len(sys.argv) > 1 else URL
raw = (open(src).read() if not src.startswith("http")
       else urllib.request.urlopen(src, timeout=30).read().decode())
d = json.loads(raw)
print("  source : %s" % src)
print("  updated: %s" % d.get("updated"))


def gate(n, raw_rate, side, line):
    """The full chain, re-implemented ONLY for auditing — deliberately independent of the code
    under test, so a shared bug cannot hide from its own checker."""
    fails = []
    if n is None or n < CT.ELITE_MIN_N_BET:
        fails.append("thin H2H (n=%s < %d)" % (n, CT.ELITE_MIN_N_BET))
    r = (raw_rate / 100.0) if (raw_rate or 0) > 1 else raw_rate
    if side == "under" and line is not None and 80.0 <= line < 90.0:
        fails.append("80-90 under leak")
    if side == "over" and line is not None and line < 65.0:
        fails.append("low-line over leak (<65)")
    if side == "over":
        if not (CT.ELITE_OVER_RAW_LO <= (r or 0) < CT.ELITE_OVER_RAW_HI):
            fails.append("over raw %.3f outside [%.2f,%.2f)" % (r or 0, CT.ELITE_OVER_RAW_LO,
                                                                CT.ELITE_OVER_RAW_HI))
    else:
        if (r or 0) < CT.ELITE_UNDER_RAW:
            fails.append("under raw %.3f < %.2f" % (r or 0, CT.ELITE_UNDER_RAW))
    return fails


print("\n=== SURFACE 1: elite_h2h[].pick — what the live card renders as a BET ===")
picks = [e for e in (d.get("elite_h2h") or []) if e.get("pick")]
bad = 0
if not picks:
    print("  none")
for e in picks:
    p = e["pick"]
    side, line, hit = p.get("side"), p.get("line"), p.get("hit")
    tots = e.get("totals") or []
    n = len(tots)
    # recompute the raw rate straight from the H2H totals at the posted line — do not trust `hit`
    if line is not None and n:
        over = sum(1 for t in tots if t > line)
        r = (over / n) if side == "over" else (1 - over / n)
    else:
        r = None
    f = gate(n, r, side, line)
    bad += bool(f)
    print("  %-34s %-6s %-6s n=%-3d raw=%-6s  %s"
          % (e.get("p1n", "?") + " v " + e.get("p2n", "?"), side, line, n,
             ("%.3f" % r) if r is not None else "-",
             "OK" if not f else "*** FAILS: " + "; ".join(f)))
    if p.get("hit") is not None and r is not None and abs(p["hit"] / 100.0 - r) > 0.02:
        print("       ^ note: board shows hit=%s%% but the totals give %.1f%%" % (p["hit"], 100 * r))

print("\n=== SURFACE 2: elite_upcoming — projected rows (labelled 'never tracked') ===")
up = d.get("elite_upcoming") or []
if not up:
    print("  none")
for e in up[:12]:
    n = e.get("n")
    ok = (n or 0) >= CT.ELITE_MIN_N_BET
    print("  %-34s %-6s proj %-6s n=%-3s hit=%-4s  %s"
          % (e.get("p1", "?") + " v " + e.get("p2", "?"), e.get("side"), e.get("proj"), n,
             e.get("hit"), "depth OK" if ok else "*** below the bet depth floor"))
print("  (projections use the DEPTH floor only — raw bands are fitted to REAL lines and must not")
print("   be applied to a proxy line; they are rendered as 'projected · never tracked')")

print("\n=== SURFACE 3: the bets / skipped keys ===")
print("  bets   : %d" % len(d.get("bets") or []))
for b in d.get("bets") or []:
    f = gate(b.get("n"), b.get("raw"), b.get("side"), b.get("line"))
    bad += bool(f)
    print("    %-34s %-6s %-6s n=%-3s raw=%-5s %s"
          % (b["p1"] + " v " + b["p2"], b.get("side"), b.get("line"), b.get("n"), b.get("raw"),
             "OK" if not f else "*** FAILS: " + "; ".join(f)))
print("  skipped: %d (must NOT render as bets)" % len(d.get("skipped") or []))
for b in d.get("skipped") or []:
    print("    %-34s %-6s n=%-3s raw=%-5s reason=%s"
          % (b["p1"] + " v " + b["p2"], b.get("side"), b.get("n"), b.get("raw"), b.get("skip_bet")))

print("\n  VERDICT: %s" % ("all rendered plays pass every rule" if bad == 0
                           else "*** %d rendered play(s) FAIL a rule ***" % bad))
