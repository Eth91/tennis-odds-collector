import wnba_wowy as W
ps = W.players()
A, R, S, M = "Julie Allemand", "Kiki Rice", "Brittney Sykes", "Aneesah Morrow"
team = [n for n, d in ps.items() if d.get("team") == "TOR"]
logs = {n: W.game_log(ps[n]["id"]) for n in team}
pos_of = lambda n: (ps.get(n) or {}).get("pos")
outs = [S, M]
plays = lambda n: n not in outs          # Rice is NOT on the out list -> she plays tonight

print("=== does peer_regime fire for Allemand with Rice as the peer? ===")
out_ids = {g["game_id"] for o in outs for g in (logs.get(o) or []) if (g.get("min") or 0) > 0}
w = W.peer_regime(logs[A], logs[R], plays(R), out_ids, min_gap=3.0)
print("  peer_regime(Allemand, Rice, plays_tonight=True) ->")
print("   ", w)

print("\n=== and what does the full scan surface (worst peer)? ===")
sc = W.peer_regime_scan(A, team, outs, logs, pos_of, plays, min_gap=3.0)
print("   ", sc)

print("\n=== is the warning actually SHOWN / used anywhere? ===")
import subprocess
for pat in ("peer_regime_scan", "regime"):
    r = subprocess.run(["grep","-rn",pat,"wnba_alert.py","dashboard.py","wnba_slip.py"],
                       capture_output=True, text=True).stdout.strip().splitlines()
    for line in r[:6]:
        print("   ", line[:150])
