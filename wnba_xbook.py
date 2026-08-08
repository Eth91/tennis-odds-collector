#!/usr/bin/env python3
"""CROSS-BOOK DISPERSION on WNBA props. Is this market soft enough to be worth building on?

THE DECISION THIS INFORMS
    A simulation engine is a large build aimed at beating the closing line on the MEAN -- the
    exact thing that failed for the CFL engine (edge not real at n=1,386) and NFL props (close
    beats model, z=+11.79), and the thing the WNBA beneficiary study already found nothing in
    (2 seasons, 2,552 games: "edge must come from PRICE, not thesis").
    So before building anything, ask the cheaper question: DOES THE MARKET DISAGREE WITH ITSELF?
    If 8 books cluster tightly, the market is efficient and a sim will not rescue it. If they
    scatter, the edge is in PRICE and needs no model at all.

WHAT IS MEASURED
    1. LINE dispersion  -- do books post different NUMBERS for the same player/market? This is
       worth far more than price dispersion: a different line is a different bet.
    2. PRICE dispersion -- at the SAME line, how far apart are the prices?
    3. EFFECTIVE HOLD   -- the vig you actually pay at one book, versus the vig if you always
       take the best price across all 8. If best-price hold goes NEGATIVE that is arbitrage.
    4. DOES IT WIN?     -- graded against boxscores. Dispersion is only worth something if the
       outlier price is a MISTAKE rather than the outlier book knowing something.

GRADING: boxscores carry pts/reb/ast, so points, rebounds, assists and PRA can be graded.
`player_threes` CANNOT -- the boxscore has fg3a (attempts), not threes made -- so it is excluded
rather than graded against the wrong column.
"""
import sqlite3, collections, statistics as st

P25 = "/home/ubuntu/tennis-odds-collector/wnba_props_2025.sqlite"
PH = "/home/ubuntu/tennis-odds-collector/wnba_props_hist.sqlite"
BOX = "/home/ubuntu/tennis-odds-collector/wnba_boxscores.sqlite"

MKT = {"player_points": "pts", "player_rebounds": "reb", "player_assists": "ast",
       "player_points_rebounds_assists": "pra"}


def norm(s):
    return " ".join(str(s or "").lower().replace(".", "").replace("'", "").split())


def dec(p):
    if p is None:
        return None
    p = float(p)
    if 1.01 < p < 30:
        return p
    if abs(p) < 1.01:
        return None
    return 1 + (p / 100 if p > 0 else 100 / (-p))


rows = []
for db in (P25, PH):
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    for ev, gd, bk, mk, pl, sd, ln, pr in c.execute(
            "SELECT event_id,game_date,book,market,player,side,line,price FROM props "
            "WHERE line IS NOT NULL AND price IS NOT NULL"):
        d = dec(pr)
        if d is None or mk not in MKT:
            continue
        rows.append((ev, str(gd)[:10], bk, mk, norm(pl), str(sd).lower(), float(ln), d))
    c.close()
print("gradeable prop quotes loaded: %d" % len(rows))
print("  price format check -> min %.2f  median %.2f  max %.2f (decimal)"
      % (min(r[7] for r in rows), st.median([r[7] for r in rows]), max(r[7] for r in rows)))

# results
res = {}
c = sqlite3.connect(f"file:{BOX}?mode=ro", uri=True)
for gd, pl, pts, reb, ast in c.execute(
        "SELECT game_date,player,pts,reb,ast FROM box"):
    if pts is None:
        continue
    res[(norm(pl), str(gd)[:10])] = {"pts": pts, "reb": reb, "ast": ast,
                                     "pra": (pts or 0) + (reb or 0) + (ast or 0)}
c.close()
print("  boxscore player-games available for grading: %d" % len(res))

# group: one entry per (event, market, player, book) keeping that book's line+prices
G = collections.defaultdict(dict)
for ev, gd, bk, mk, pl, sd, ln, d in rows:
    g = G[(ev, gd, mk, pl)]
    e = g.setdefault(bk, {"line": ln})
    if e["line"] != ln:                       # a book quoting two lines: keep the main one
        continue
    e[sd] = max(e.get(sd, 0), d)

print("\n=== 1. LINE DISPERSION -- do books post different numbers? ===")
nb = collections.Counter()
spread = []
for k, g in G.items():
    lines = [v["line"] for v in g.values()]
    nb[len(g)] += 1
    if len(g) >= 2:
        spread.append(max(lines) - min(lines))
multi = [k for k, g in G.items() if len(g) >= 2]
print("  player-game-markets: %d   priced by 2+ books: %d (%.0f%%)"
      % (len(G), len(multi), 100 * len(multi) / max(len(G), 1)))
if spread:
    ident = sum(1 for s in spread if s == 0)
    print("  books post the SAME line: %d of %d (%.0f%%)"
          % (ident, len(spread), 100 * ident / len(spread)))
    print("  line spread when they differ: mean %.2f  median %.2f  p90 %.2f  max %.1f"
          % (st.mean(spread), st.median(spread),
             sorted(spread)[int(0.9 * len(spread))], max(spread)))

print("\n=== 2 & 3. HOLD: one book vs shopping all 8 ===")
single, best, arbs = [], [], 0
for k in multi:
    g = G[k]
    per_line = collections.defaultdict(dict)
    for bk, v in g.items():
        if "over" in v and "under" in v:
            per_line[v["line"]][bk] = (v["over"], v["under"])
    for ln, bks in per_line.items():
        if len(bks) < 2:
            continue
        for o, u in bks.values():
            single.append(1 / o + 1 / u - 1)
        bo = max(x[0] for x in bks.values())
        bu = max(x[1] for x in bks.values())
        h = 1 / bo + 1 / bu - 1
        best.append(h)
        if h < 0:
            arbs += 1
if single:
    print("  two-way quotes compared: %d book-quotes across %d line-groups" % (len(single), len(best)))
    print("  HOLD at a single book      : mean %+.2f%%  median %+.2f%%"
          % (100 * st.mean(single), 100 * st.median(single)))
    print("  HOLD taking the best price : mean %+.2f%%  median %+.2f%%"
          % (100 * st.mean(best), 100 * st.median(best)))
    print("  -> shopping removes %.2fpp of vig" % (100 * (st.mean(single) - st.mean(best))))
    print("  outright ARBITRAGE (best-price hold < 0): %d of %d (%.2f%%)"
          % (arbs, len(best), 100 * arbs / len(best)))

print("\n=== 4. DOES THE OUTLIER WIN? (graded) ===")


def grade(k, side, line):
    ev, gd, mk, pl = k
    r = res.get((pl, gd))
    if not r:
        return None
    v = r[MKT[mk]]
    if v is None or float(v) == float(line):
        return None                                   # push
    return (v > line) if side == "over" else (v < line)


def report(sel, tag):
    if len(sel) < 30:
        print("    %-42s n=%d (thin)" % (tag, len(sel)))
        return
    w = sum(1 for x in sel if x[0]); n = len(sel)
    u = sum((x[1] - 1) if x[0] else -1 for x in sel)
    be = st.mean([1 / x[1] for x in sel])
    print("    %-42s n=%-5d %5.1f%%  vs breakeven %5.1f%%  %+8.1fu  ROI %+6.2f%%"
          % (tag, n, 100 * w / n, 100 * be, u, 100 * u / n))


allbet, bestbet, consensus_side = [], [], []
for k in multi:
    g = G[k]
    for side in ("over", "under"):
        quotes = [(bk, v["line"], v[side]) for bk, v in g.items() if side in v]
        if len(quotes) < 3:
            continue
        # the OUTLIER: the book offering the best deal for this side
        # (for an over, the lowest line at the best price; compare on implied prob)
        best_q = max(quotes, key=lambda q: q[2] if side == "under" else q[2])
        med_line = st.median([q[1] for q in quotes])
        gq = grade(k, side, best_q[1])
        if gq is not None:
            bestbet.append((gq, best_q[2]))
        for bk, ln, d in quotes:
            gg = grade(k, side, ln)
            if gg is not None:
                allbet.append((gg, d))
        # does the outlier LINE (not price) differ from the field?
        if best_q[1] != med_line:
            gc = grade(k, side, best_q[1])
            if gc is not None:
                consensus_side.append((gc, best_q[2]))

report(allbet, "every quote, every book (baseline)")
report(bestbet, "always take the BEST price across books")
report(consensus_side, "  ...restricted to OFF-CONSENSUS lines")
print("\n  a market that is soft shows the best-price bet clearing breakeven.")
print("  a market that is efficient shows shopping only recovering vig, never passing it.")
