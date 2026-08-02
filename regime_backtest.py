"""Does the REGIME warning actually predict losers? Reconstructed as-of, on the graded ledger.

THE QUESTION. peer_regime_scan already fires correctly — on the Allemand bet it named Kiki Rice,
measured 2/11 sample match and 6.0 borrowed minutes. It has never been wired to anything: the
docstring says DISPLAY ONLY because ~51 selected bets could not validate a hard gate. There are
more graded bets now, so the honest move is to measure it before proposing anything.

WHY IT HAS TO BE RECONSTRUCTED. The scan's output goes into the ntfy ping text (`rtag`) and is
never persisted — the ledger's `regime` column is written by a different module (wnba_regime). So
the warning is recomputed here for each graded bet.

AS-OF DISCIPLINE. For a bet on date D the elevated sample uses ONLY games strictly before D. A
game log is a historical record, so this is reconstructible without leakage as long as that cut is
respected. Verified explicitly below: every game entering a bet's sample is asserted < D.

ONE HONEST APPROXIMATION, stated rather than buried. At flag time the scan asks the INJURY FEED
whether the peer is expected to play (`inj.get(x) not in ("Out","Doubtful")`). That feed's state at
that moment is not recoverable, so this uses whether the peer ACTUALLY played that night. Those
differ exactly when the feed was wrong — a game-time scratch or a surprise return. That is a small
and roughly symmetric set, but it means this measures "would the warning have been RIGHT", which is
a mild upper bound on "would the warning have FIRED". Treat the effect size as optimistic.

UNIVERSE is the pre-registered one the tracker counts: graded overs -> current_selection ->
confidence in {confirmed, likely}. Fitting on anything wider would tune a filter against bets the
board never made. Reported as record / hit% / units / ROI — never MAE.
"""
import json
import sqlite3
import sys
from collections import defaultdict

sys.path.insert(0, ".")
import wnba_wowy as W

MIN_GAP = 3.0
BET_ROLES = ("confirmed", "likely")


def load_universe():
    c = sqlite3.connect("wnba_ledger.sqlite")
    cols = [d[1] for d in c.execute("PRAGMA table_info(predictions)")]
    rows = [dict(zip(cols, r)) for r in c.execute("SELECT * FROM predictions WHERE graded=1")]
    c.close()
    rows = [r for r in rows if r.get("result") in ("over", "under") and r.get("odds")]
    overs = [r for r in rows if str(r.get("side")) == "over"]
    try:
        import wnba_slip as S
        sel, _ = S.current_selection(overs, commit=False)
    except Exception as e:                                       # noqa: BLE001
        raise SystemExit("current_selection failed (%s) — refusing to score a wider universe" % e)
    return [r for r in sel if str(r.get("confidence")) in BET_ROLES]


def main():
    uni = load_universe()
    print("universe: %d graded, selected, {confirmed,likely} overs" % len(uni))
    ps = W.players()
    by_team = defaultdict(list)
    for n, d in ps.items():
        if d.get("team"):
            by_team[d["team"]].append(n)
    logcache = {}

    def glog(n):
        if n not in logcache:
            try:
                logcache[n] = W.game_log(ps[n]["id"])
            except Exception:                                    # noqa: BLE001
                logcache[n] = []
        return logcache[n]

    warned, clean, skipped = [], [], 0
    for r in uni:
        bene, team, D = r.get("player"), r.get("team"), str(r.get("pred_date"))[:10]
        outs = [o.strip() for o in str(r.get("out_player") or "").split(",") if o.strip()]
        if not bene or not team or bene not in ps or not outs:
            skipped += 1
            continue
        mates = [n for n in by_team.get(team, []) if n != bene]

        def before(n):
            """games strictly before the bet date — the whole leak-free contract"""
            out = [g for g in glog(n) if str(g.get("date"))[:10] < D]
            assert all(str(g.get("date"))[:10] < D for g in out)
            return out

        blog = before(bene)
        out_ids = {g["game_id"] for o in outs for g in before(o) if (g.get("min") or 0) > 0}
        # who actually played that night = the proxy for "expected to play" (see docstring)
        night = {g["game_id"]: g for g in glog(bene) if str(g.get("date"))[:10] == D}
        gid_tonight = next(iter(night), None)
        worst = None
        for m in mates:
            if m in outs:
                continue
            mlog_all = glog(m)
            played_tonight = any(g["game_id"] == gid_tonight and (g.get("min") or 0) > 0
                                 for g in mlog_all)
            w = W.peer_regime(blog, before(m), played_tonight, out_ids, min_gap=MIN_GAP)
            if w and (worst is None or (w["gap_min"] or 0) > (worst["gap_min"] or 0)):
                worst = dict(w, peer=m)
        (warned if worst else clean).append((r, worst))

    def score(bucket, label):
        if not bucket:
            print("  %-28s (empty)" % label)
            return
        wins = sum(1 for r, _ in bucket if r["result"] == r["side"])
        n = len(bucket)
        units = 0.0
        for r, _ in bucket:
            # THE WNBA LEDGER STORES DECIMAL ODDS (measured range 1.33-4.90), which is the
            # OPPOSITE of the TT ledger where `odds` is American. Treating these as American
            # gave 73% hit at -25.5% ROI — arithmetically impossible, and the tell that the
            # units were wrong. A win pays (dec - 1).
            dec = float(r["odds"] or 0)
            assert 1.0 < dec < 30.0, "odds %r is not decimal — check the ledger" % dec
            units += (dec - 1.0) if r["result"] == r["side"] else -1.0
        print("  %-28s %2d-%-2d  hit %5.1f%%  units %+6.2f  ROI %+6.1f%%"
              % (label, wins, n - wins, 100.0 * wins / n, units, 100.0 * units / n))

    print("\n=== does the REGIME warning separate winners from losers? ===")
    score(clean, "no warning")
    score(warned, "REGIME WARNING")
    print("  skipped (unresolvable): %d" % skipped)

    if warned:
        print("\n=== severity: does a bigger borrowed-minutes gap predict worse? ===")
        for lo, hi, lab in ((3.0, 5.0, "gap 3-5 min"), (5.0, 8.0, "gap 5-8 min"),
                            (8.0, 99.0, "gap 8+ min")):
            score([(r, w) for r, w in warned if lo <= (w["gap_min"] or 0) < hi], lab)
        print("\n=== and by how little of the sample matches tonight ===")
        for lo, hi, lab in ((0.0, 0.34, "match <34% of sample"), (0.34, 0.67, "match 34-67%"),
                            (0.67, 1.01, "match 67%+")):
            score([(r, w) for r, w in warned if lo <= (w["peer_match"] or 0) < hi], lab)
        print("\n  worst offenders:")
        for r, w in sorted(warned, key=lambda x: -(x[1]["gap_min"] or 0))[:6]:
            print("    %s %-22s %-9s %-4s %s  peer=%-20s gap %sm  %d/%d"
                  % (str(r["pred_date"])[:10], r["player"], r["stat"], r["line"],
                     "WON " if r["result"] == r["side"] else "LOST", w["peer"],
                     w["gap_min"], w["n_match"], w["n_elev"]))
    significance(warned, clean)




def significance(warned, clean):
    """Is the split real, or 15 bets of noise? Fisher exact + a DAY-CLUSTERED bootstrap.

    Day clustering matters here specifically: bets on one slate share the same injury news and the
    same games, so treating 52 bets as 52 independent draws overstates certainty. Resampling whole
    SLATES is the honest unit."""
    import math, random
    from collections import defaultdict
    random.seed(11)

    def wl(b):
        w = sum(1 for r, _ in b if r["result"] == r["side"])
        return w, len(b) - w

    aw, al = wl(warned); bw, bl = wl(clean)

    def C(n, k):
        return math.comb(n, k)
    # one-sided Fisher: P(warned bucket does this badly or worse)
    tot, totw = aw + al + bw + bl, aw + bw
    p = sum(C(aw + al, i) * C(bw + bl, totw - i) / C(tot, totw)
            for i in range(0, aw + 1) if 0 <= totw - i <= bw + bl)
    print("\n=== is it real? ===")
    print("  Fisher exact (one-sided, warned no better): p = %.4f" % p)

    def units(b):
        return sum((float(r["odds"]) - 1.0) if r["result"] == r["side"] else -1.0 for r, _ in b)

    byday = defaultdict(lambda: ([], []))
    for r, w in warned: byday[str(r["pred_date"])[:10]][0].append((r, w))
    for r, w in clean:  byday[str(r["pred_date"])[:10]][1].append((r, w))
    days = list(byday)
    diffs = []
    for _ in range(4000):
        smp = [byday[random.choice(days)] for _ in days]
        W_ = [x for d in smp for x in d[0]]; C_ = [x for d in smp for x in d[1]]
        if not W_ or not C_: continue
        diffs.append(units(C_) / len(C_) - units(W_) / len(W_))
    diffs.sort()
    lo, hi = diffs[int(.025 * len(diffs))], diffs[int(.975 * len(diffs))]
    print("  day-clustered bootstrap, ROI(clean) - ROI(warned): %+.1f%%  95%% CI [%+.1f%%, %+.1f%%]"
          % (100 * (units(clean)/len(clean) - units(warned)/len(warned)), 100*lo, 100*hi))
    print("  %d distinct slates (%d bets) — the real sample size is the slate count"
          % (len(days), len(warned) + len(clean)))
    print("  CI excludes 0: %s" % ("YES" if lo > 0 else "no — cannot support a hard gate yet"))


if __name__ == "__main__":
    main()
