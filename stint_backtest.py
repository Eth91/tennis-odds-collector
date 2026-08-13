"""WALK-FORWARD BACKTEST of the stint-WOWY fallback, on REAL historical lines.

RULES THIS OBEYS
* REAL LINES ONLY — every price comes from `wnba_props_hist` (the archived pre-game
  snapshot). No proxy lines, no reconstructed prices.
* WALK-FORWARD — every stint aggregate for a game on date D uses `game_date < D`. The
  module enforces this; the backtest never passes a date it has already seen.
* IT ONLY FIRES WHERE THE LIVE MODEL IS BLIND — a candidate is skipped unless game-level
  `n_without < 2`, which is precisely the gate `wnba_alert` cannot clear. So this measures
  NEW bets, not a re-run of bets the model already makes.
* ONE IMPLEMENTATION — projections come from `wnba_stint_wowy.project()`, the same
  function the live channel would call. The backtest does not re-derive the math.

The stints DB is copied into an indexed in-memory SQLite so the module's own queries run
unchanged but fast (~150k rows; the file has no useful indexes for these access patterns).
"""
import sqlite3, sys, math
from collections import defaultdict
sys.path.insert(0, ".")
import wnba_stint_wowy as SW

EV_MIN = float(sys.argv[1]) if len(sys.argv) > 1 else 0.10
# SHRINK: a single multiplier on the projected mean, correcting the measured bias that
# off-floor per-36 rates are bench-vs-bench inflated and the minutes bump is too generous.
# ⚠️ FIT ON 2025 ONLY, then applied to 2026 untouched -- otherwise this is just curve-fitting
# an 85-bet sample and the "improvement" is guaranteed and meaningless.
SHRINK = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
BOOK_PREF = ("fanduel", "draftkings", "betrivers", "williamhill_us", "betonlineag")
MARKET = {"points": "player_points", "rebounds": "player_rebounds", "assists": "player_assists"}

# ── load stints into memory, indexed ──────────────────────────────────────────
src = sqlite3.connect("file:wnba_stints.sqlite?mode=ro", uri=True, timeout=30)
mem = sqlite3.connect(":memory:")
src.backup(mem)
src.close()
mem.row_factory = sqlite3.Row
for ddl in ("CREATE INDEX i1 ON onfloor(player, game_date)",
            "CREATE INDEX i2 ON onfloor(event_id)",
            "CREATE INDEX i3 ON pairs(player, mate, game_date)",
            "CREATE INDEX i4 ON pteam(event_id)"):
    mem.execute(ddl)

# ── load real historical lines ────────────────────────────────────────────────
LINES = defaultdict(list)           # (player, market) -> [(date, line, price, book)]
# BOTH archives. wnba_props_hist covers 2026-05-10+ only; the 2025 file carries
# 2024-10-21 -> 2025-10-11. Using just the first gave n=47 bets -- far too thin for any
# split to mean anything, and every "finding" in it was inside the noise.
for _db in ("wnba_props_hist.sqlite", "wnba_props_2025.sqlite"):
    try:
        ph = sqlite3.connect(f"file:{_db}?mode=ro", uri=True, timeout=30)
        ph.row_factory = sqlite3.Row
        k = 0
        for r in ph.execute("SELECT player, market, game_date, line, price, book, side FROM props"):
            LINES[(r["player"], r["market"])].append(
                (r["game_date"], r["line"], r["price"], r["book"], r["side"]))
            k += 1
        ph.close()
        print(f"  {_db}: {k:,} over-quotes")
    except Exception as e:
        print(f"  {_db}: SKIPPED ({e})")
print(f"loaded {sum(len(v) for v in LINES.values()):,} real over-quotes total")

def real_line(player, stat, date):
    """The archived pre-game over quote. props_hist game_date is the UTC date of tip, so a
    US evening game lands on D or D+1 -- accept both, never a wider window."""
    cand = LINES.get((player, MARKET[stat]))
    if not cand:
        return None
    d1 = date
    d2 = (__import__("datetime").date.fromisoformat(date) +
          __import__("datetime").timedelta(days=1)).isoformat()
    hits = [c for c in cand if c[0] in (d1, d2)]
    if not hits:
        return None
    # pair the OVER with its matching UNDER (same book, same line) so the shrink target is
    # the DE-VIGGED market probability. Shrinking toward the raw 1/decimal would drag every
    # estimate toward a number that is deliberately below the book's true belief.
    for b in BOOK_PREF:                       # deterministic book preference, never best-price
        ov = [h for h in hits if h[3] == b and h[4] == "over"]
        if not ov:
            continue
        o = ov[0]
        un = [h for h in hits if h[3] == b and h[4] == "under" and abs(h[1] - o[1]) < 1e-9]
        if un:
            po, pu = 1.0 / o[2], 1.0 / un[0][2]
            return o[1], o[2], b, po / (po + pu)
        return o[1], o[2], b, None            # one-sided: no de-vig possible, no shrink target
    return None

# ── team/game scaffolding ─────────────────────────────────────────────────────
games = [(r["event_id"], r["game_date"]) for r in mem.execute(
    "SELECT DISTINCT event_id, game_date FROM onfloor WHERE game_date >= '2024-05-01' "
    "ORDER BY game_date")]
print(f"{len(games)} games from 2024-01-01")

team_of = defaultdict(dict)
for r in mem.execute("SELECT event_id, player, team FROM pteam"):
    team_of[r["event_id"]][r["player"]] = r["team"]

played_in = defaultdict(dict)
for r in mem.execute("SELECT event_id, player, sec, pts, reb, ast FROM onfloor"):
    played_in[r["event_id"]][r["player"]] = r

# player -> sorted [(date, event_id, sec)] for recent-form lookups
hist = defaultdict(list)
for r in mem.execute("SELECT player, game_date, event_id, sec FROM onfloor ORDER BY game_date"):
    hist[r["player"]].append((r["game_date"], r["event_id"], r["sec"] or 0))

def mpg_before(p, d, window=10):
    h = [x for x in hist[p] if x[0] < d][-window:]
    return (sum(x[2] for x in h) / len(h) / 60.0) if h else 0.0

def recent_roster(team, d, evs):
    """Players who appeared for `team` in its games in the 21 days before d."""
    out = set()
    for ev, gd in evs:
        if gd >= d:
            break
        if (__import__("datetime").date.fromisoformat(d) -
                __import__("datetime").date.fromisoformat(gd)).days > 21:
            continue
        for p, t in team_of.get(ev, {}).items():
            if t == team and p in played_in.get(ev, {}):
                out.add(p)
    return out

# ── the sweep ─────────────────────────────────────────────────────────────────
bets, skipped_noline, skipped_nwo, skipped_proj = [], 0, 0, 0
for gi, (ev, d) in enumerate(games):
    if gi % 120 == 0:
        print(f"  ...{gi}/{len(games)} {d}  bets={len(bets)}", flush=True)
    roster_by_team = defaultdict(set)
    for p, t in team_of.get(ev, {}).items():
        roster_by_team[t].add(p)
    for team, squad in roster_by_team.items():
        pl_now = {p for p in squad if p in played_in.get(ev, {})}
        prior = recent_roster(team, d, games[:gi])
        outs = [p for p in (prior - pl_now) if mpg_before(p, d) >= 15.0]
        if not outs:
            continue
        for out in outs:
            omp = mpg_before(out, d)
            # ── PROJECTED STARTER FILTER (2026-08-12) ──────────────────────────
            # Measured over 9,816 player-games: a projected starter plays 20+ minutes
            # 86% of the time (avg 27.4, only 5% under 15). The 6th-8th man clears 20
            # just 29% of the time and is UNDER 15 in 46%. Letting the whole mpg>=8
            # population in meant most candidates were minutes coin-flips, which is
            # what a marginalised projection correctly prices as ~no edge -- and what
            # an unmarginalised one turns into a phantom edge.
            # The five is recomputed WITHOUT the out player, so the next man up is
            # promoted exactly as a coach would. Pre-tip knowable: recent mpg + the
            # out list, no hindsight about who actually played.
            _avail = [(mpg_before(p, d) or 0, p) for p in (prior - set(outs))]
            _avail.sort(reverse=True)
            _proj_start = {p for _m, p in _avail[:5]}
            for ben in pl_now:
                if ben not in _proj_start:
                    continue
                if mpg_before(ben, d) < 8.0:
                    continue
                nwo, _, _ = SW.game_level_n_without(mem, ben, out, d)
                if nwo >= 2:                    # live model already covers this
                    skipped_nwo += 1
                    continue
                for stat in ("points", "rebounds", "assists"):
                    rl = real_line(ben, stat, d)
                    if not rl:
                        skipped_noline += 1
                        continue
                    line, price, book, p_mkt = rl
                    pr = SW.project(mem, ben, out, stat, line, d, omp,
                                    dispersion=SHRINK, p_market=p_mkt)
                    if not pr:
                        skipped_proj += 1
                        continue
                    ev_bet = pr["p_over"] * price - 1.0
                    if ev_bet < EV_MIN:
                        continue
                    act = played_in[ev][ben]
                    got = act["pts"] if stat == "points" else (
                        act["reb"] if stat == "rebounds" else act["ast"])
                    bets.append({"date": d, "player": ben, "out": out, "stat": stat,
                                 "line": line, "price": price, "book": book,
                                 "p": pr["p_over"], "ev": ev_bet, "proj": pr["proj"],
                                 "actual": got, "min": (act["sec"] or 0) / 60.0,
                                 "won": got > line, "nwo": nwo,
                                 "off_min": pr["off_min"], "rate36": pr["rate36"]})

# ── results ───────────────────────────────────────────────────────────────────
print(f"\nskipped: no real line={skipped_noline:,}  already-covered(n>=2)={skipped_nwo:,}  "
      f"unmeasurable={skipped_proj:,}")
n = len(bets)
if not n:
    print("NO BETS"); sys.exit()
w = sum(1 for b in bets if b["won"])
units = sum((b["price"] - 1.0) if b["won"] else -1.0 for b in bets)
print(f"\n=== STINT-WOWY FALLBACK, EV_MIN={EV_MIN} ===")
print(f"  bets   {n}")
print(f"  record {w}-{n-w} = {w/n*100:.1f}%")
print(f"  units  {units:+.2f}   ROI {units/n*100:+.1f}%")
print(f"  mean modelled p_over {sum(b['p'] for b in bets)/n:.3f}  vs realised {w/n:.3f}"
      f"   (calibration gap {sum(b['p'] for b in bets)/n - w/n:+.3f})")
print(f"  mean implied {sum(1/b['price'] for b in bets)/n:.3f}")

def bucket(name, key):
    print(f"\n  by {name}:")
    g = defaultdict(list)
    for b in bets:
        g[key(b)].append(b)
    for k in sorted(g, key=str):
        v = g[k]
        ww = sum(1 for b in v if b["won"])
        uu = sum((b["price"] - 1.0) if b["won"] else -1.0 for b in v)
        print(f"    {str(k):14s} n={len(v):4d}  {ww}-{len(v)-ww} = {ww/len(v)*100:5.1f}%  "
              f"units {uu:+7.2f}  ROI {uu/len(v)*100:+6.1f}%")

print(f"\n  SHRINK={SHRINK}")
for _s in ("2025", "2026"):
    v = [b for b in bets if b["date"][:4] == _s]
    if not v: continue
    ww = sum(1 for b in v if b["won"])
    uu = sum((b["price"] - 1.0) if b["won"] else -1.0 for b in v)
    mp = sum(b["p"] for b in v) / len(v)
    print(f"    {_s}: n={len(v):3d}  {ww}-{len(v)-ww} = {ww/len(v)*100:5.1f}%  "
          f"units {uu:+7.2f}  ROI {uu/len(v)*100:+6.1f}%   modelled p={mp:.3f} vs real {ww/len(v):.3f}")
bucket("stat", lambda b: b["stat"])
bucket("season", lambda b: b["date"][:4])
bucket("n_without", lambda b: f"n={b['nwo']}")
bucket("EV band", lambda b: "0.10-0.25" if b["ev"] < 0.25 else ("0.25-0.50" if b["ev"] < 0.5 else "0.50+"))
bucket("off-floor sample", lambda b: "120-300m" if b["off_min"] < 300 else
       ("300-800m" if b["off_min"] < 800 else "800m+"))
# ── ERROR DECOMPOSITION ───────────────────────────────────────────────────────
# A 27pp calibration gap is a BIAS, not variance. Two candidates: we assumed minutes the
# player never got, or the off-floor per-36 rate does not survive contact with a bigger
# role. Separating them decides whether the channel is fixable or dead.
print("\n=== ERROR DECOMPOSITION ===")
am = sum(b["min"] for b in bets) / n
pm = sum(b["proj"] / b["rate36"] * 36.0 for b in bets) / n      # minutes implied by proj
print(f"  minutes: assumed {pm:5.1f}  actual {am:5.1f}   ({am - pm:+.1f})")
ap = sum(b["actual"] for b in bets) / n
pp = sum(b["proj"] for b in bets) / n
print(f"  stat:    projected {pp:5.2f}  actual {ap:5.2f}   ({ap - pp:+.2f})")
r_act = [b["actual"] / (b["min"] / 36.0) for b in bets if b["min"] >= 8]
r_prj = [b["rate36"] for b in bets if b["min"] >= 8]
print(f"  per-36:  off-floor rate used {sum(r_prj)/len(r_prj):5.2f}  "
      f"actual achieved {sum(r_act)/len(r_act):5.2f}   "
      f"({sum(r_act)/len(r_act) - sum(r_prj)/len(r_prj):+.2f})")
print("  -> if MINUTES match but per-36 falls short, the off-floor rate is the bias:")
print("     off-floor minutes are disproportionately bench-vs-bench, where per-36 output")
print("     is inflated and does NOT carry into a starter-sized role.")
hi = [b for b in bets if b["min"] >= pm - 2]
if hi:
    hw = sum(1 for b in hi if b["won"])
    print(f"\n  bets where the player DID get the assumed minutes: n={len(hi)} "
          f"{hw}-{len(hi)-hw} = {hw/len(hi)*100:.1f}%")
print("\n  first 10 bets:")
for b in bets[:10]:
    print(f"    {b['date']} {b['player'][:18]:18s} {b['stat'][:4]:4s} o{b['line']:<5g} "
          f"@{b['price']:<5} p={b['p']:.2f} proj={b['proj']:.1f} act={b['actual']:.0f} "
          f"min={b['min']:.0f} {'WIN' if b['won'] else 'loss'}  (out: {b['out'][:16]})")
