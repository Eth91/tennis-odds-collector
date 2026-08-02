"""What is the VOLUME path's actual record?

It matters because `use_vol` is the exemption that let Carleton onto the card despite failing the
conviction gate (+0.26 min, +0.80 FGA against a bar of +2 min OR +1 FGA). If the volume path earns
that exemption, fine. If it does not, the exemption is doing the damage.

Measured two ways, because they answer different questions:
  * ALL graded rows — every row the path ever produced.
  * The POST-SELECTION universe — `current_selection` then the role gate, i.e. what the tracker
    actually counts and the bot actually bets. The house rule is to judge filters on this, since
    profiling the raw ledger invents findings about rows that were never carded.

Day-clustered CI throughout: WNBA bets arrive in slates, so bets within a night share conditions and
an i.i.d. interval would overstate precision.

WNBA is FROZEN. This is measurement, which is the one thing the freeze permits.
"""
import random
import sqlite3
from collections import defaultdict

con = sqlite3.connect("wnba_ledger.sqlite")
cols = [d[1] for d in con.execute("PRAGMA table_info(predictions)")]
ALL = [dict(zip(cols, r)) for r in con.execute("SELECT * FROM predictions WHERE graded=1")]
con.close()
ALL = [r for r in ALL if r.get("result") in ("over", "under") and r.get("odds")]
OV = [r for r in ALL if (r.get("side") or "over") == "over"]

try:
    import wnba_slip as S
    SEL, _dropped = S.current_selection(OV, commit=False)
except Exception as e:                                             # noqa: BLE001
    print("  current_selection failed (%r) — falling back to raw overs" % (e,))
    SEL = OV
BET_ROLES = {"confirmed", "likely"}
UNI = [r for r in SEL if str(r.get("confidence")) in BET_ROLES]

print("  graded overs: %d   post-selection: %d   post-role-gate: %d"
      % (len(OV), len(SEL), len(UNI)))
print("  distinct basis values:", sorted({str(r.get("basis")) for r in ALL}))


def day(r):
    return str(r.get("pred_date"))[:10]


def ret(r):
    return (float(r["odds"]) - 1) if r["result"] == "over" else -1.0


def boot(rows, iters=2000):
    byd = defaultdict(list)
    for r in rows:
        byd[day(r)].append(ret(r))
    ks = list(byd)
    if len(ks) < 2:
        return None
    rng = random.Random(7)
    sims = []
    for _ in range(iters):
        s = [x for k in rng.choices(ks, k=len(ks)) for x in byd[k]]
        if s:
            sims.append(sum(s) / len(s))
    sims.sort()
    return sims[int(.025 * len(sims))], sims[int(.975 * len(sims))]


def show(label, rows):
    if not rows:
        print("  %-34s (none)" % label)
        return
    n = len(rows)
    w = sum(1 for r in rows if r["result"] == "over")
    u = sum(ret(r) for r in rows)
    ci = boot(rows)
    print("  %-34s %4d %5d-%-4d %6.1f%% %+8.2fu %+7.1f%%  %s  [%d days]"
          % (label, n, w, n - w, 100 * w / n, u, 100 * u / n,
             ("CI %+.0f%%..%+.0f%%" % (100 * ci[0], 100 * ci[1])) if ci else "CI n/a",
             len({day(r) for r in rows})))


for title, pool in (("ALL graded overs", OV),
                    ("POST-SELECTION + role gate (what the bot bets)", UNI)):
    print("\n=== %s, split by basis ===" % title)
    print("  %-34s %4s %10s %7s %9s %8s" % ("basis", "n", "record", "hit%", "units", "ROI"))
    byb = defaultdict(list)
    for r in pool:
        byb[str(r.get("basis"))].append(r)
    for b in sorted(byb, key=lambda k: -len(byb[k])):
        show(b, byb[b])
    show("-- ALL --", pool)

print("\n=== the specific question: does the volume path earn its exemption? ===")
print("  It skips the conviction gate (an over normally needs d_min>2 OR d_fga>1).")
vol = [r for r in UNI if str(r.get("basis")) == "volume"]
oth = [r for r in UNI if str(r.get("basis")) != "volume"]
show("volume (exempt from the gate)", vol)
show("everything else", oth)
print()
weak = [r for r in vol if (r.get("d_min") or 0) <= 2 and (r.get("d_fga") or 0) <= 1]
strong = [r for r in vol if not ((r.get("d_min") or 0) <= 2 and (r.get("d_fga") or 0) <= 1)]
print("  Splitting the volume rows by whether they WOULD have passed the gate anyway:")
show("volume that FAILS the gate", weak)
show("volume that PASSES anyway", strong)
print("\n  'volume that FAILS the gate' is the Carleton cell — the rows that exist ONLY because")
print("  of the exemption. That is the number that decides whether the exemption is earning.")
