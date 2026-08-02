"""Is the projection trustworthy enough to LADDER UP? The load-bearing question, answered first.

THE ASK was to backtest betting a higher alt rung when the projection clears it. That cannot be done
directly: only 4 of the 52 graded selected bets fall inside the window where historical rung PRICES
still exist (wnba_lines prunes at 2 days, fanduel_props at 3). Four bets is an anecdote, and pricing
a strategy off four outcomes is how filters get fit to noise.

But the price question is the SECOND question. The first is whether the projection earns the right
to ladder at all, and that one is answerable on every graded bet with a realized value (144), with
no rung prices needed:

    if the model projects 18.4, how often does the player actually reach 14.5? 15.5? 16.5?

If the projection is well calibrated at those thresholds, laddering has promise and capturing rung
prices becomes worth doing. If it is optimistic — which is the prior here, since elevated roles are
documented to regress and OVER_EV_MIN is already set at 2.5x the under bar for exactly that reason —
then laddering up is fatal at ANY price and the current main-line-only rule is correct.

MEASURED AS: for each graded bet, take the projection (elev_avg) and the realized value (actual),
then ask at each HEADROOM level h — a hypothetical rung h below the projection — whether the player
actually cleared it. Headroom is the honest x-axis because it is what the model would key a ladder
decision on: "project 18.4, so bet the 14.5" is a headroom of 3.9.

The implied break-even is shown beside each clear-rate: an alt rung that far below a projection
would need roughly that price to be worth betting, so the comparison is to a realistic number
rather than to 50%.
"""
import sqlite3
import sys

sys.path.insert(0, ".")


def main():
    c = sqlite3.connect("wnba_ledger.sqlite")
    c.row_factory = sqlite3.Row
    cols = [d[1] for d in c.execute("PRAGMA table_info(predictions)")]
    rows = [dict(r) for r in c.execute("SELECT * FROM predictions WHERE graded=1")]
    c.close()
    rows = [r for r in rows
            if r.get("actual") is not None and r.get("elev_avg") is not None
            and r.get("line") is not None and str(r.get("side")) == "over"]
    print("graded bets with both a projection and a realized value: %d\n" % len(rows))

    # 1) IS THE PROJECTION CALIBRATED AT ALL? A ladder is only as good as the number it keys on.
    over = sum(1 for r in rows if r["actual"] > r["elev_avg"])
    bias = sum(r["actual"] - r["elev_avg"] for r in rows) / len(rows)
    print("=== 1. is the projection itself honest? ===")
    print("   realized ABOVE projection: %d/%d (%.1f%%)  — 50%% would be unbiased"
          % (over, len(rows), 100.0 * over / len(rows)))
    print("   mean(actual - projection): %+.2f  — negative means the model projects too high" % bias)

    # 2) THE ACTUAL LADDER QUESTION, by headroom.
    print("\n=== 2. if the model projects X, how often is a rung H below X actually cleared? ===")
    print("   %-14s %6s %8s   %s" % ("headroom", "n", "cleared", "implied breakeven to profit"))
    for lo, hi in ((0.0, 1.0), (1.0, 2.0), (2.0, 3.0), (3.0, 4.0), (4.0, 6.0), (6.0, 99.0)):
        hits = tot = 0
        for r in rows:
            proj, act = r["elev_avg"], r["actual"]
            # walk hypothetical .5 rungs sitting `h` below the projection
            rung = proj - (lo + hi) / 2.0
            if rung <= 0:
                continue
            rung = round(rung * 2) / 2.0
            if not (lo <= proj - rung < hi):
                continue
            tot += 1
            hits += 1 if act > rung else 0
        if tot < 5:
            print("   %-14s %6d   (too thin to read)" % ("%.0f-%.0f pts" % (lo, min(hi, 9)), tot))
            continue
        rate = hits / tot
        print("   %-14s %6d %7.1f%%   needs ~%.0f%% at a typical alt price"
              % ("%.0f-%.0f pts" % (lo, min(hi, 9)), tot, 100 * rate, 100 * rate))

    # 3) THE DIRECT COMPARISON: main line vs the deepest rung the projection clears.
    print("\n=== 3. head-to-head on the bets we actually made ===")
    main_w = sum(1 for r in rows if r["actual"] > r["line"])
    print("   MAIN LINE as bet:            %d/%d cleared (%.1f%%)"
          % (main_w, len(rows), 100.0 * main_w / len(rows)))
    for step in (1.0, 2.0, 3.0):
        elig = [r for r in rows if r["elev_avg"] - r["line"] >= step + 1.0]
        if len(elig) < 5:
            print("   ladder +%.0f: only %d eligible — too thin" % (step, len(elig)))
            continue
        w = sum(1 for r in elig if r["actual"] > r["line"] + step)
        base = sum(1 for r in elig if r["actual"] > r["line"])
        print("   ladder +%.0f (n=%3d eligible): %.1f%% cleared vs %.1f%% at the main line"
              % (step, len(elig), 100.0 * w / len(elig), 100.0 * base / len(elig)))


if __name__ == "__main__":
    main()
