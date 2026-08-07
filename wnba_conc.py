#!/usr/bin/env python3
"""Is the rebound edge a rule, or three players?

72.2% on 36 bets is only meaningful if those bets are spread across many distinct
beneficiary/out-player pairs. If a handful of pairs repeat, the effective sample is far
smaller than 36 and one player's hot stretch is carrying it.

Reports: distinct beneficiaries, distinct pairs, the per-pair breakdown, and the record with
each pair capped at ONE bet (its first chronologically) — the pessimistic read that no single
relationship can dominate.
"""
import sys, sqlite3, statistics as st
from collections import defaultdict, Counter

sys.path.insert(0, "/home/ubuntu/tennis-odds-collector")
sys.path.insert(0, "/home/ubuntu")
_a = list(sys.argv); sys.argv = ["x"]
import wnba_stint3way as S3
import wnba_replay as R
import wnba_wowy as W
sys.argv = _a


def summarize(rows, label):
    if not rows:
        print(f"  {label}: none")
        return
    w = sum(r["hit"] for r in rows); l = len(rows) - w
    u = sum((r["price"] - 1.0) if r["hit"] else -1.0 for r in rows)
    be = st.mean([1.0 / r["price"] for r in rows])
    hit = w / len(rows)
    print(f"  {label:<34} {w}-{l}  hit {100*hit:5.1f}%  be {100*be:5.1f}%  "
          f"edge {100*(hit-be):+6.1f}  {u:+7.2f}u")


def main():
    con = sqlite3.connect(f"file:{R.HIST}?mode=ro", uri=True)
    days = [d for (d,) in con.execute(
        "SELECT DISTINCT game_date FROM props WHERE game_date>='2026-05-10' ORDER BY 1")]
    con.close()
    players = W.players()

    for stat in ("rebounds", "assists"):
        cand = [c for c in S3.run(stat, days, players, samepos=True)
                if c["proj"] - c["line"] >= 0.0]
        print(f"\n=== {stat.upper()} — {len(cand)} bets ===")
        ben = Counter(c["player"] for c in cand)
        pairs = Counter((c["player"], c["out"]) for c in cand)
        print(f"  distinct beneficiaries: {len(ben)}    distinct pairs: {len(pairs)}")
        top = pairs.most_common(6)
        print(f"  most repeated pairs: " +
              ", ".join(f"{a.split()[-1]}/{b.split()[-1]} x{n}" for (a, b), n in top))

        print("\n  per-pair record:")
        bypair = defaultdict(list)
        for c in cand:
            bypair[(c["player"], c["out"])].append(c)
        for (a, b), rs in sorted(bypair.items(), key=lambda kv: -len(kv[1]))[:8]:
            w_ = sum(r["hit"] for r in rs)
            print(f"    {a:<21} w/o {b:<20} {w_}-{len(rs)-w_}")

        print()
        summarize(cand, "ALL bets")
        # one bet per pair (earliest) — no relationship can dominate
        seen, first = set(), []
        for c in sorted(cand, key=lambda x: x["date"]):
            k = (c["player"], c["out"])
            if k in seen:
                continue
            seen.add(k); first.append(c)
        summarize(first, f"ONE per pair (n={len(first)})")
        # one bet per beneficiary
        seen2, firstb = set(), []
        for c in sorted(cand, key=lambda x: x["date"]):
            if c["player"] in seen2:
                continue
            seen2.add(c["player"]); firstb.append(c)
        summarize(firstb, f"ONE per beneficiary (n={len(firstb)})")
        # drop the single most-repeated pair entirely
        if top:
            worst = top[0][0]
            summarize([c for c in cand if (c["player"], c["out"]) != worst],
                      f"excluding {worst[0].split()[-1]}/{worst[1].split()[-1]}")


if __name__ == "__main__":
    main()
