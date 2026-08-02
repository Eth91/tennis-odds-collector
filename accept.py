"""Acceptance: does ramp_state fire on the real Rice case, and does the chain persist?"""
import sys, sqlite3; sys.path.insert(0, ".")
import wnba_wowy as W
ps = W.players()
R = "Kiki Rice"
st = W.ramp_state(W.game_log(ps[R]["id"]), "2026-08-02")
print("=== ramp_state(Kiki Rice, as of 2026-08-02) ===")
print("   ", st)
if st:
    print("    -> back %d games after a %d-day absence; %s min since return vs a %s norm,"
          % (st["games_back"], st["gap_days"], st["since"], st["norm"]))
    print("       still %.1f min under it and trending %+.1f. Tonight is game %d."
          % (st["deficit"], st["trend"], st["games_back"] + 1))
print("\n=== ledger migration ===")
import wnba_ledger as L
c = L._con(); cols = [d[1] for d in c.execute("PRAGMA table_info(predictions)")]
print("    peer_regime column:", "peer_regime" in cols)
print("    peer_ramp column:  ", "peer_ramp" in cols)
c.close()
