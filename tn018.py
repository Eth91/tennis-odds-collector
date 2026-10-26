#!/usr/bin/env python3
"""TN-018 — is the +EV moneyline tail REAL, or a stale-line artifact? And fix total games.

TN-017: FanDuel's mean moneyline EV against Pinnacle's fair number is -0.0347, essentially its own
4.3% hold - Pinnacle plus margin. But 10.5% of quotes paid MORE than sharp-fair, best +13.6%, and
the effect concentrated in longshots. That tail is either

  REAL DISAGREEMENT   FanDuel's number genuinely differs and stays different, which is takeable
  STALE LINE          FanDuel simply had not moved yet. Also takeable in principle, but only for
                      as long as the lag lasts, and it is a SPEED play not a pricing play
  NOISE               the pair was not simultaneous and I am measuring line movement

The three are separable by asking whether a quote that is +EV at one snapshot is STILL +EV at the
next. Genuine disagreement persists; a stale line converges; noise flips sign at random.

TOTAL GAMES returned zero pairs, which is a join failure rather than an absence: FanDuel stores the
handicap on the runner while Pinnacle stores one games_line per row, and the two only meet when
FanDuel happens to quote the identical number. Both sides are printed here before matching, so the
failure is diagnosed rather than assumed.
"""
import re
import sqlite3
import statistics as st
import unicodedata
from collections import defaultdict
from datetime import datetime as D
from pathlib import Path

HERE = Path(__file__).resolve().parent


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", " ", s.lower()).strip()


def surn(n):
    p = [x for x in norm(n).split() if x]
    return p[-1] if p else ""


def pk(a, b):
    return tuple(sorted([surn(a), surn(b)]))


def tsd(a, b):
    try:
        return abs((D.fromisoformat(a[:19]) - D.fromisoformat(b[:19])).total_seconds()) / 60.0
    except Exception:                                                   # noqa: BLE001
        return 1e9


fd = sqlite3.connect("file:%s?mode=ro" % (HERE / "tennis_fd.sqlite"), uri=True, timeout=60)
pn = sqlite3.connect("file:%s?mode=ro" % (HERE / "odds.sqlite"), uri=True, timeout=60)

print("=" * 88)
print("TOTAL GAMES — why the join found nothing")
print("=" * 88)
fl = [r[0] for r in fd.execute("SELECT DISTINCT handicap FROM fd_tennis WHERE market_type IN "
                               "('MATCH_TOTAL_GAMES','ALTERNATIVE_MATCH_TOTAL_GAMES') "
                               "AND handicap IS NOT NULL ORDER BY 1")]
pl = [r[0] for r in pn.execute("SELECT DISTINCT games_line FROM odds WHERE games_line IS NOT NULL "
                               "AND collected_at >= '2026-08-30' ORDER BY 1")]
print("   FanDuel game lines : %s" % (fl[:14] if fl else "NONE"))
print("   Pinnacle game lines: %s" % (pl[:14] if pl else "NONE"))
print("   overlap: %s" % (sorted(set(fl) & set(pl))[:12] or "EMPTY"))

# ---- moneyline pairs at EVERY snapshot, so persistence can be measured ----------------------
fdrows = fd.execute("""SELECT event_name, tour, start_time, runner_name, odds, collected_at
                       FROM fd_tennis WHERE market_type='MATCH_BETTING'""").fetchall()
pnrows = pn.execute("""SELECT p1, p2, start_time, collected_at, ml1, ml2 FROM odds
                       WHERE collected_at >= '2026-08-30' AND ml1 IS NOT NULL""").fetchall()
fd.close()
pn.close()

P = defaultdict(list)
for p1, p2, stt, ts, a, b in pnrows:
    P[(pk(p1, p2), str(stt)[:10])].append((str(ts), p1, a, b))

series = defaultdict(list)          # (match, runner) -> [(ts, ev)]
for ev, tour, stt, rn, od, ts in fdrows:
    parts = str(ev).split(" v ")
    if len(parts) != 2:
        continue
    cand = P.get((pk(parts[0], parts[1]), str(stt)[:10]))
    if not cand:
        continue
    c = min(cand, key=lambda x: tsd(x[0], ts))
    if tsd(c[0], ts) > 20:
        continue
    same = surn(rn) == surn(c[1])
    po, qo = (c[2], c[3]) if same else (c[3], c[2])
    if not po or not qo:
        continue
    fair = (1 / po) / ((1 / po) + (1 / qo))
    series[(ev, rn, tour)].append((ts, fair * od - 1, fair, od))

print()
print("=" * 88)
print("IS THE +EV TAIL PERSISTENT? tracking each quote across snapshots")
print("=" * 88)
multi = {k: sorted(v) for k, v in series.items() if len(v) >= 2}
print("   quotes observed at 2+ snapshots: %d (of %d total quotes)" % (len(multi), len(series)))
stay, flip, conv = 0, 0, 0
firsts = []
for k, v in multi.items():
    e0 = v[0][1]
    e1 = v[-1][1]
    if e0 > 0:
        firsts.append((e0, e1))
        if e1 > 0:
            stay += 1
        elif e1 > e0 - 0.005:
            flip += 1
        else:
            conv += 1
if firsts:
    print("   quotes that started +EV: %d" % len(firsts))
    print("      still +EV at the last snapshot : %d (%.0f%%)"
          % (stay, 100.0 * stay / len(firsts)))
    print("      decayed toward/below zero      : %d" % (conv + flip))
    print("      mean EV first %+.4f -> last %+.4f"
          % (st.mean([a for a, _ in firsts]), st.mean([b for _, b in firsts])))
    print()
    if stay >= 0.6 * len(firsts):
        print("   -> the tail PERSISTS: FanDuel genuinely disagrees rather than lagging.")
    elif stay <= 0.3 * len(firsts):
        print("   -> the tail DECAYS: it is a stale line converging, i.e. a SPEED play, not a")
        print("      pricing edge. Only takeable if you are faster than FanDuel's own update.")
    else:
        print("   -> mixed: some genuine disagreement, some convergence.")

print()
print("=" * 88)
print("THE +EV QUOTES THEMSELVES (latest snapshot per quote)")
print("=" * 88)
last = [(k, v[-1]) for k, v in series.items()]
pos = [(k, x) for k, x in last if x[1] > 0]
print("   %d of %d quotes are +EV right now (%.1f%%)" % (len(pos), len(last),
                                                         100.0 * len(pos) / max(len(last), 1)))
if pos:
    evs = [x[1] for _k, x in pos]
    print("   mean +EV %.4f | median %.4f | max %.4f" % (st.mean(evs), st.median(evs), max(evs)))
    print("   mean sharp-fair probability of these: %.3f  (low = longshots)"
          % st.mean([x[2] for _k, x in pos]))
    print()
    for k, x in sorted(pos, key=lambda z: -z[1][1])[:8]:
        print("      %-40s %-22s FD %6.2f  fair %.3f  EV %+.3f"
              % (k[0][:40], k[1][:22], x[3], x[2], x[1]))
