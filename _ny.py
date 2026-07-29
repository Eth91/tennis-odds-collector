"""Is the Liberty cascade being wrongly skipped, and does the ABSENCE COMBINATION matter?

User's thesis: {Johannes, Sabally, Fiebich} out is a different animal from {Sabally,
Fiebich} out -- the market has priced 25 days of Fiebich-less Liberty, but it has NOT priced
the trio. The stale-vacancy gate asks "is any ONE out fresh?"; it never asks "has this team
ever played THIS combination?"
"""
import datetime as dt
import json

import wnba_injury_report as IR
import wnba_tonight as T
import wnba_wowy as W

pl = W.players()
inj = T.injuries()
today = dt.datetime.now(T.ET).date().isoformat()

print("=" * 76)
print("MARINE JOHANNES — what each source says (precedence: Underdog > report > RW)")
print("=" * 76)
off = IR.confirmed_by_date().get(today, {})
print("  official report      :", off.get("Marine Johannes"))
rw = []
for t in T.rw_lineups() or []:
    if t.get("team") == "NY":
        rw = t.get("out") or []
print("  rotowire NY out-list :", rw)
ud = []
for ln in open("underdog_log.jsonl", encoding="utf-8"):
    if not ln.strip():
        continue
    e = json.loads(ln)
    if "Johannes" in (e.get("text") or ""):
        ud.append((e["t"][:19], e.get("st"), e.get("text")))
print("  underdog rulings     :")
for u in ud:
    print("       %s  st=%-4s %s" % u)
print("  => injuries() final  :", inj.get("Marine Johannes"))
print("  => in CONFIRMED_OUT  :", "Marine Johannes" in T.CONFIRMED_OUT_TODAY)

print()
print("=" * 76)
print("NY ABSENCE COMBINATIONS — how many games has the team played with each set?")
print("=" * 76)
names = ["Leonie Fiebich", "Satou Sabally", "Marine Johannes"]
logs = {n: W.game_log(pl[n]["id"]) for n in names if n in pl}
played = {n: {g["date"][:10] for g in lg if (g.get("min") or 0) > 0} for n, lg in logs.items()}
for n in names:
    lg = logs.get(n) or []
    last = lg[0]["date"][:10] if lg else "n/a"
    age = (dt.date.fromisoformat(today) - dt.date.fromisoformat(last)).days if lg else 999
    print("  %-18s last played %s (%d days ago)  %s" % (
        n, last, age, "STALE" if age > 21 else "FRESH"))

# team game dates = union of any NY player's logged games
ny = [n for n, v in pl.items() if v.get("team") == "NY"]
alldates = set()
for n in ny:
    for g in W.game_log(pl[n]["id"]):
        alldates.add(g["date"][:10])
alldates = sorted(alldates)
print("\n  NY games logged: %d" % len(alldates))


def combo_games(outset):
    return [d for d in alldates if all(d not in played.get(n, set()) for n in outset)]


for combo in (["Satou Sabally"], ["Leonie Fiebich"],
              ["Leonie Fiebich", "Satou Sabally"],
              ["Leonie Fiebich", "Satou Sabally", "Marine Johannes"]):
    g = combo_games(combo)
    print("  without %-52s n=%-3d %s" % (
        " + ".join(x.split()[-1] for x in combo), len(g),
        ("most recent: " + g[-1]) if g else "NEVER HAPPENED"))

print()
print("=" * 76)
print("THE GATE, as it stands")
print("=" * 76)
print("  all_stale = every out player last appeared >21 days ago -> skip whole cascade")
print("  NY outs the model currently sees:",
      [n for n in names if inj.get(n) in ("Out", "Doubtful")])
print("  => the gate is COMBINATION-BLIND: it scores each out player's own recency,")
print("     never whether THIS SET of absences is one the market has seen before.")
