"""⛳ EDGE ATTRIBUTION — where do the flagged edges actually come from?

A model can pass every calibration check and still have all its edge sitting on the one thing it
cannot measure. Three failure modes worth catching before any money moves:

  THIN SAMPLE   if flags concentrate on players below MIN_ROUNDS, the "edge" is mostly the
                halved-rating/widened-sigma regime disagreeing with a market that knows more.
  ONE TERM      if the edge evaporates when a single weak term is switched off (wind r=-0.20,
                bridge r=-0.43), we are betting that term, not the model.
  CONCENTRATION if a handful of players carry every flag, the effective n is that handful and
                one bad player read sinks the stream.

Compares flagged players against the FIELD baseline, because "most flags are thin-sample" means
nothing if most of the field is thin-sample too.
"""
import json
import re
import sqlite3
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path

import pga_birdies as B
import pga_field as PF
import pga_ruler as RU

HERE = Path(__file__).resolve().parent
BOARD = HERE / "pga_board.json"

rows = []
try:
    rows = (json.loads(BOARD.read_text()).get("e3") or [])
except Exception as e:                                              # noqa: BLE001
    print("no board: %s" % e)
print("=" * 74)
print("EDGE ATTRIBUTION — %d flagged rows on the board" % len(rows))
print("=" * 74)
if not rows:
    raise SystemExit("nothing flagged; run pga_e3.py first")

R, _ = RU.fit()
Rn = {RU.norm(k): v for k, v in R.items()}
field = [(c.get("athlete") or {}).get("displayName") for c in PF.competitors()]
field = [f for f in field if f]

# birdie sample sizes, in holes
con = sqlite3.connect(B.DB)
holes = {RU.norm(p): (h or 0) for p, h in con.execute(
    "SELECT player, SUM(p3h)+SUM(p4h)+SUM(p5h) FROM birdie_rounds GROUP BY player")}
con.close()


def players_of(row):
    """The player(s) a flag is about."""
    run = str(row.get("runner") or "")
    mkt = str(row.get("market") or "")
    m = re.search(r"Matchbet(?: \(Round \d\))? (.+?) vs (.+)$", mkt)
    if m:
        return [m.group(1).strip(), m.group(2).strip()]
    # birdies arrive as "Name over 3.5"
    m2 = re.match(r"(.+?)\s+(?:over|under)\s+[\d.]+$", run)
    if m2:
        return [m2.group(1).strip()]
    return [run.strip()]


by_stream = defaultdict(list)
for r_ in rows:
    by_stream[str(r_.get("stream") or "?")].append(r_)
print()
print("[1] FLAGS BY STREAM")
for s_, v in sorted(by_stream.items()):
    eg = [float(x.get("edge") or 0) for x in v]
    print("    %-14s %2d flags   edge mean %+.3f  max %+.3f"
          % (s_, len(v), st.mean(eg), max(eg)))

# ------------------------------------------------------------------ thin sample
print()
print("[2] THIN SAMPLE — are flags leaning on players the ruler barely knows?")
MINR = RU.MIN_ROUNDS
field_n = [(Rn.get(RU.norm(p)) or (0, 0, 0))[2] for p in field]
field_n = [n for n in field_n if n]
base_thin = sum(1 for n in field_n if n < MINR) / max(len(field_n), 1)
flag_ns, unrated = [], 0
for r_ in rows:
    for pl in players_of(r_):
        v = Rn.get(RU.norm(pl))
        if v:
            flag_ns.append(v[2])
        else:
            unrated += 1
if flag_ns:
    thin = sum(1 for n in flag_ns if n < MINR) / len(flag_ns)
    print("    flagged players: %d refs, median n=%.0f rounds, %.0f%% below MIN_ROUNDS=%d"
          % (len(flag_ns), st.median(flag_ns), 100 * thin, MINR))
    print("    FIELD baseline : %d rated,  median n=%.0f rounds, %.0f%% below MIN_ROUNDS"
          % (len(field_n), st.median(field_n), 100 * base_thin))
    verdict = ("OK — flags are not concentrated in the thin-sample regime"
               if thin <= base_thin + 0.10 else
               "WARNING — flags over-represent thin-sample players vs the field")
    print("    -> %s" % verdict)
if unrated:
    print("    %d flag references had NO rating at all (should be impossible)" % unrated)

# --------------------------------------------------------------- concentration
print()
print("[3] CONCENTRATION — how many distinct players carry the flags?")
cnt = Counter()
for r_ in rows:
    for pl in players_of(r_):
        cnt[RU.norm(pl)] += 1
print("    %d flags over %d distinct players" % (sum(cnt.values()), len(cnt)))
top = cnt.most_common(4)
share = sum(c for _p, c in top) / max(sum(cnt.values()), 1)
for pl, c in top:
    print("       %-26s %d flags" % (pl, c))
print("    top-4 players carry %.0f%% of all flags -> %s"
      % (100 * share, "acceptable" if share <= 0.6 else
         "WARNING: effective n is a handful of players"))

# ------------------------------------------------------- does one term carry it?
print()
print("[4] ONE-TERM DEPENDENCE — do the birdie edges survive without the context terms?")
bd = by_stream.get("E3-birdies") or []
if not bd:
    print("    no birdie flags to decompose")
else:
    import pga_context as C
    evn = PF.event().get("name") or ""
    cf, _cn = C.course_factor(evn)
    la, lo = PF.coords()
    wind = C.live_wind_stat(la, lo) if la is not None else None
    tid = B.tid_for_name(evn)
    mix = B.mix_for(tid) if tid else B.DEFAULT_MIX
    variants = {
        "as priced (course+wind)": {"course_factor": cf, "wind_kmh": wind},
        "no wind term": {"course_factor": cf},
        "no course factor": {"wind_kmh": wind},
        "neither (raw rates)": {},
    }
    for label, kw in variants.items():
        BR, _fr = B.rates(**kw)
        BRn = {RU.norm(k): v for k, v in BR.items()}
        keep = 0
        moved = []
        for r_ in bd:
            run = str(r_.get("runner") or "")
            m = re.match(r"(.+?)\s+(over|under)\s+([\d.]+)$", run)
            if not m:
                continue
            pl, side, ln = m.group(1).strip(), m.group(2), float(m.group(3))
            rr = BRn.get(RU.norm(pl))
            od = float(r_.get("odds") or 0)
            if not rr or od <= 1:
                continue
            po = B.p_x_or_more(rr, int(ln + 0.5), mix)
            ours = po if side == "over" else 1 - po
            e = ours - 1 / od
            moved.append(e)
            if e >= 0.05:
                keep += 1
        print("    %-26s %2d/%d flags survive   mean edge %+.3f"
              % (label, keep, len(bd), st.mean(moved) if moved else 0))
    print()
    print("    NOTE: these variants drop the market-anchored LAM too, so 'raw rates' is the")
    print("    unanchored model. A large swing there means the LEVEL is doing the work and the")
    print("    edge is player-relative dispersion only — which is what the birdie stream is.")
print()
print("=" * 74)
print("ATTRIBUTION COMPLETE")
