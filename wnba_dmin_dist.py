#!/usr/bin/env python3
"""Where did the big-minutes-bump bets go? Compare the replay's d_min distribution to the
live ledger's. If the replay has none above 8, every parameter test run through it has been
measuring a narrower universe than the live model actually sees."""
import sys, sqlite3, statistics as st
from collections import Counter, defaultdict
sys.path.insert(0, "/home/ubuntu")
_a = list(sys.argv); sys.argv = ["x"]
import wnba_replay as R
import wnba_tonight as T, wnba_wowy as W, wnba_slip as S
sys.argv = _a


def band(d):
    if d is None:
        return "unknown"
    return "<1" if d < 1 else "1-3" if d < 3 else "3-8" if d < 8 else "8+"


# --- live ledger ---
c = sqlite3.connect("file:/home/ubuntu/wnba_data/wnba_ledger.sqlite?mode=ro", uri=True)
led = Counter(band(r[0]) for r in c.execute("SELECT d_min FROM predictions"))
c.close()

# --- replay: every beneficiary the replay CONSIDERS, and every bet it produces ---
con = sqlite3.connect(f"file:{R.HIST}?mode=ro", uri=True)
days = [d for (d,) in con.execute(
    "SELECT DISTINCT game_date FROM props WHERE game_date BETWEEN '2026-05-10' "
    "AND '2026-08-05' ORDER BY 1")]
con.close()
players = W.players()

considered = Counter()
haslines = Counter()
priced = Counter()
for day in days:
    R._ASOF["day"] = day
    lines = R._load_date(day)
    if not lines:
        continue
    logs, played = {}, defaultdict(set)
    for n, v in players.items():
        lg = R.full_log(v["id"]); logs[n] = lg
        if R.on(lg, day):
            played[v["team"]].add(n)
    byt = defaultdict(dict)
    for n, v in players.items():
        byt[v["team"]][n] = v
    for team, roster in byt.items():
        if not played[team]:
            continue
        outs = []
        for o in roster:
            if o in played[team]:
                continue
            ol = R.before(logs[o], day)
            reg = [g for g in ol if (g.get("min") or 0) > 0]
            if len(reg) < 5 or st.mean(g["min"] for g in reg[-10:]) < 20:
                continue
            outs.append(ol)
        if not outs:
            continue
        outs = outs[:3]
        for n, v in roster.items():
            blog = R.before(logs[n], day)
            if len(blog) < 4:
                continue
            try:
                w = W.wowy_multi(blog, outs)
                if w["n_without"] < 2 and len(outs) > 1:
                    w = max([W.wowy(blog, ol) for ol in outs], key=lambda x: x["n_without"])
            except Exception:
                continue
            if w["n_without"] < 1:
                continue
            d = w["without"]["min"]["mean"] - w["with"]["min"]["mean"]
            b = band(d)
            considered[b] += 1
            if n in lines:
                haslines[b] += 1
                if (lines[n].get("points") or lines[n].get("rebounds")):
                    priced[b] += 1

print(f"{'band':<10}{'LIVE ledger':>13}{'replay: seen':>14}{'has archive line':>18}")
for b in ("<1", "1-3", "3-8", "8+"):
    print(f"{b:<10}{led.get(b,0):>13}{considered.get(b,0):>14}{haslines.get(b,0):>18}")
tot_c = sum(considered.values()); tot_h = sum(haslines.values())
print(f"{'TOTAL':<10}{sum(led.values()):>13}{tot_c:>14}{tot_h:>18}")
if tot_c:
    print(f"\nshare of 8+ band: live {100*led.get('8+',0)/max(sum(led.values()),1):.1f}%  "
          f"replay-seen {100*considered.get('8+',0)/tot_c:.1f}%  "
          f"replay-with-line {100*haslines.get('8+',0)/max(tot_h,1):.1f}%")
    print("\nIf 'seen' has plenty of 8+ but 'has archive line' does not, the main-line-only")
    print("archive is what removes them -- the same gap that hid Puoch.")
