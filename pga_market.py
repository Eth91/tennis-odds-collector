#!/usr/bin/env python3
"""⚖️ pga_market — fair-probability layer. Every market declares HOW it is priced.

Built after EXP-001, where a field-wide market with a 31.5% overround was being compared against
model probabilities that sum to 1.0. Nothing in the codebase said what a given market's implied
probabilities are supposed to SUM to, so every consumer guessed — and a wrong guess does not
error, it just produces a plausible fair price and a fake edge.

THE MEASURED TAXONOMY (golf_moves closes, 2026-08-14). Overround is sum(1/odds) over the runners
a market quotes:

    two-way (matchbet, single O/U line)   2 runners     ~1.05-1.08   -> normalise to 1
    ladder / ALTERNATE LINES              4 or 6 runners ~2.11, 3.18 -> NOT a 52% hold
    Top-N                                 ~69 runners   5.9-22.5     -> normalise to N
    field win / round leader              ~69 runners   1.39-1.47    -> normalise to 1

⚠️ THE LADDER CASE IS THE ONE THAT LOOKS LIKE A DISASTER AND IS NOT. "Jordan Spieth Round 2 Score"
with 6 runners shows overround 3.18 — a 68% hold, which no book charges. It is THREE two-way
lines (over/under 68.5, 69.5, 70.5) pooled into one market name. 3 x 1.06 = 3.18. Devigging that
as one market would put every selection at a third of its true price. Lines must be grouped by
handicap and devigged INDIVIDUALLY.

⚠️ TOP-N IS NOT AN N-RUNNER WIN MARKET. Twenty players finish top-20 simultaneously, so the
implied probabilities sum to ~N, not 1. Normalising to 1 would divide every top-20 price by 20.

WHAT THIS MODULE DOES NOT DO: it does not decide whether a bet is good. It returns a fair
probability and the overround it removed, and it REFUSES markets it cannot classify rather than
guessing — an unclassified market silently normalised to 1 is exactly the EXP-001 failure.
"""
import re
from collections import defaultdict

TWO_WAY = "two_way"
LADDER = "ladder"
TOP_N = "top_n"
FIELD_WIN = "field_win"
GROUP = "group"
UNKNOWN = "unknown"

_TOPN = re.compile(r"^top\s+(\d+)\b", re.I)
_MATCH = re.compile(r"matchbet", re.I)
_LADDERISH = re.compile(r"(round\s+\d\s+score|total birdies or better|birdies or better)", re.I)
_FIELDWIN = re.compile(r"^(win only|winner|outright|\d+(st|nd|rd|th) round leader|"
                       r"winner w/o|to win)", re.I)
_GROUPY = re.compile(r"(chances to win|top region|top group|top (usa|european|"
                     r"north american|rest of))", re.I)


def classify(market, n_runners=None):
    """(kind, target_sum) for a market name. target_sum is what implied probs should total.

    n_runners disambiguates only where the NAME genuinely cannot: a matchbet is two-way whatever
    it looks like, but "Round 2 Score" is one line at 2 runners and a ladder at 4 or 6.
    """
    m = " ".join(str(market or "").split())
    if not m:
        return UNKNOWN, None
    if _MATCH.search(m):
        return TWO_WAY, 1.0
    t = _TOPN.match(m)
    if t:
        return TOP_N, float(int(t.group(1)))
    if _FIELDWIN.match(m):
        return FIELD_WIN, 1.0
    if _GROUPY.search(m):
        return GROUP, None                      # priced against a subset; no clean target
    if _LADDERISH.search(m):
        if n_runners is None:
            return UNKNOWN, None
        return (TWO_WAY, 1.0) if n_runners <= 2 else (LADDER, 1.0)
    return UNKNOWN, None


def _line_of(runner):
    """Handicap embedded in a selection name, e.g. 'X Over 3.5' -> 3.5. None if absent."""
    mm = re.search(r"\b(over|under)\s+([\d.]+)\s*$", str(runner or "").strip(), re.I)
    return float(mm.group(2)) if mm else None


def fair(market, quotes, n_runners=None):
    """{runner: fair_prob} plus diagnostics, or None if the market cannot be priced.

    `quotes` is {runner: decimal_odds}. Returns (fair_dict, info). info carries the kind, the
    overround actually removed, and — for ladders — the per-line breakdown, because a single
    pooled overround for a ladder is a meaningless number and reporting one invites the very
    mistake this module exists to prevent.
    """
    q = {r: float(o) for r, o in quotes.items() if o and float(o) > 1.0}
    if len(q) < 2:
        return None, {"kind": UNKNOWN, "why": "fewer than 2 usable prices"}
    kind, target = classify(market, n_runners if n_runners is not None else len(q))
    imp = {r: 1.0 / o for r, o in q.items()}
    tot = sum(imp.values())

    if kind == LADDER:
        # group by handicap; each line is its own two-way market
        by_line = defaultdict(dict)
        for r, v in imp.items():
            by_line[_line_of(r)][r] = v
        if any(k is None for k in by_line) or not all(len(v) == 2 for v in by_line.values()):
            return None, {"kind": LADDER, "why": "cannot split into two-sided lines",
                          "lines": {str(k): len(v) for k, v in by_line.items()}}
        out, per = {}, {}
        for ln, side in by_line.items():
            s = sum(side.values())
            per[ln] = s
            for r, v in side.items():
                out[r] = v / s
        return out, {"kind": LADDER, "n_lines": len(per), "overround_per_line": per,
                     "pooled_overround_IGNORE": tot}

    if kind in (TWO_WAY, FIELD_WIN, TOP_N):
        if target is None or tot <= 0:
            return None, {"kind": kind, "why": "no target sum"}
        if kind == TOP_N and len(q) < target + 5:
            return None, {"kind": TOP_N, "why": "field smaller than the top-N target"}
        return ({r: v * (target / tot) for r, v in imp.items()},
                {"kind": kind, "target_sum": target, "overround": tot / target,
                 "hold_pct": 100.0 * (tot / target - 1) / (tot / target)})

    return None, {"kind": kind, "why": "unclassified — refusing to guess a normaliser"}


def ev(p_model, decimal_odds):
    """Expected value per unit staked at the OFFERED price. Vig is in the price, correctly."""
    return p_model * float(decimal_odds) - 1.0


# ── self-test: every claim above, checked ───────────────────────────────────────────────────
if __name__ == "__main__":
    fails = []

    def chk(name, cond, detail=""):
        print("   %-52s %s %s" % (name, "ok" if cond else "FAIL", detail))
        if not cond:
            fails.append(name)

    print("classification")
    chk("matchbet -> two_way", classify("18 Hole Matchbet (Round 1) A vs B", 2)[0] == TWO_WAY)
    chk("Top 20 -> top_n, target 20", classify("Top 20", 69) == (TOP_N, 20.0))
    chk("Top 10 Finish (Incl. Ties) -> top_n", classify("Top 10 Finish (Incl. Ties)", 69)[0] == TOP_N)
    chk("Win Only -> field_win", classify("Win Only", 69) == (FIELD_WIN, 1.0))
    chk("1st Round Leader -> field_win", classify("1st Round Leader", 69) == (FIELD_WIN, 1.0))
    chk("Round 2 Score @2 runners -> two_way", classify("X Round 2 Score", 2)[0] == TWO_WAY)
    chk("Round 2 Score @6 runners -> ladder", classify("X Round 2 Score", 6)[0] == LADDER)
    chk("Three Chances to Win -> group", classify("Three Chances to Win", 84)[0] == GROUP)
    chk("nonsense -> unknown", classify("Hole Match Betting", 5)[0] == UNKNOWN)

    print("\ntwo-way: a 1.06 book must devig to sum 1.0")
    # real observed FanDuel matchbet pricing (inventory 2026-08-14: overround 1.048-1.082).
    # The first fixture was 1.90/2.05 = a 1.4% book, which no sportsbook offers — the test
    # expectation was right and the fixture was wrong.
    f, i = fair("18 Hole Matchbet (Round 1) A vs B", {"A": 1.87, "B": 1.87})
    chk("sums to 1", abs(sum(f.values()) - 1.0) < 1e-9, "%.6f" % sum(f.values()))
    chk("hold reported ~5-6%", 4 < i["hold_pct"] < 8, "%.1f%%" % i["hold_pct"])

    print("\nladder: 3 stacked lines must NOT read as a 68%% hold")
    lad = {"X Over 68.5": 1.90, "X Under 68.5": 2.00,
           "X Over 69.5": 1.55, "X Under 69.5": 2.55,
           "X Over 70.5": 1.30, "X Under 70.5": 3.60}
    f, i = fair("X Round 2 Score", lad, n_runners=6)
    chk("split into 3 lines", i.get("n_lines") == 3)
    chk("each line sums to 1", all(abs(sum(v for r, v in f.items()
                                           if _line_of(r) == ln) - 1.0) < 1e-9
                                   for ln in (68.5, 69.5, 70.5)))
    chk("pooled overround flagged as IGNORE", "pooled_overround_IGNORE" in i,
        "%.2f" % i["pooled_overround_IGNORE"])

    print("\ntop-N: implied must normalise to N, not to 1")
    tn = {"p%d" % k: 6.0 for k in range(69)}          # 69 runners at 6.0 -> sum 11.5
    f, i = fair("Top 10", tn, n_runners=69)
    chk("sums to 10", abs(sum(f.values()) - 10.0) < 1e-6, "%.4f" % sum(f.values()))
    chk("hold ~13-16%", 10 < i["hold_pct"] < 20, "%.1f%%" % i["hold_pct"])

    print("\nfield win: 69 runners, 32%% overround -> sum 1.0")
    fw = {"p%d" % k: 46.0 for k in range(69)}
    f, i = fair("1st Round Leader", fw, n_runners=69)
    chk("sums to 1", abs(sum(f.values()) - 1.0) < 1e-9, "%.6f" % sum(f.values()))

    print("\nrefusals (a guessed normaliser is the bug this prevents)")
    chk("unclassified refuses", fair("Hole Match Betting", {"a": 2.0, "b": 2.0})[0] is None)
    chk("group refuses", fair("Three Chances to Win", {"a": 5.0, "b": 5.0})[0] is None)
    chk("broken ladder refuses",
        fair("X Round 2 Score", {"X Over 68.5": 1.9, "Y": 2.0, "Z": 3.0, "W": 4.0},
             n_runners=4)[0] is None)

    print("\nEV uses the OFFERED price, vig included")
    chk("p=0.5 @2.10 -> +5%", abs(ev(0.5, 2.10) - 0.05) < 1e-12)

    print("\n%s" % ("ALL PASS" if not fails else "FAILED: %s" % fails))
    raise SystemExit(1 if fails else 0)
