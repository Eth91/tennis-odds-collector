"""TN-002b - does FanDuel price sets iid-from-moneyline? BEST-OF handled correctly.

The FanDuel side is format-agnostic: P(A wins 0 sets) = 1 - P(A wins at least 1 set) is a sweep in
either format, so P(straights) = 2 - pA - pB regardless. The iid side is NOT. Best-of-3 inverts
M = p^2(3-2p) with straights p^2+(1-p)^2; best-of-5 inverts M = p^3(6p^2-15p+10) with straights
p^3+(1-p)^3. Applying the bo3 formula to Men's Grand Slam matches manufactured the negative gaps
in the first run - the ATP/WTA split in those numbers was my bug, not a finding.
"""
import json, urllib.request, time, statistics as st
from collections import defaultdict

AK = "FhMFpcPWXMeyZxOx"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
B = "https://sbapi.ny.sportsbook.fanduel.com/api"
TZ = "&timezone=America%2FNew_York"


def get(u):
    r = urllib.request.Request(u, headers={"User-Agent": UA, "Accept": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=30))


def od(r):
    t = (r.get("winRunnerOdds") or {}).get("trueOdds")
    return (t.get("decimalOdds") or {}).get("decimalOdds") if isinstance(t, dict) else None


d = get("%s/content-managed-page?page=SPORT&eventTypeId=2&pbHorizontal=false&_ak=%s%s" % (B, AK, TZ))
att = d.get("attachments") or {}
evs = att.get("events") or {}
comps = att.get("competitions") or {}
cname = {str(k): str(v.get("name")) for k, v in comps.items()}
matches = [v for v in evs.values() if " v " in str(v.get("name", ""))]
print("head-to-head matches: %d" % len(matches))

SLAM = ("us open", "australian open", "wimbledon", "french open", "roland")


def is_bo5(v):
    c = cname.get(str(v.get("competitionId")), "").lower()
    if "women" in c:
        return False
    return ("men" in c) and any(s in c for s in SLAM)


def solve(M, five):
    f = (lambda p: p ** 3 * (6 * p * p - 15 * p + 10)) if five else (lambda p: p * p * (3 - 2 * p))
    lo, hi = 0.5, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if f(mid) < M:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def two(m):
    y = n = None
    for r in (m.get("runners") or []):
        nm = str(r.get("runnerName"))
        if nm.endswith(" Yes"):
            y = od(r)
        elif nm.endswith(" No"):
            n = od(r)
    return y, n


rows = []
for v in matches:
    eid = v.get("eventId")
    try:
        e = get("%s/event-page?eventId=%s&_ak=%s%s" % (B, eid, AK, TZ))
    except Exception:
        continue
    mk = (e.get("attachments") or {}).get("markets") or {}
    A = Bm = ML = None
    for m in mk.values():
        mt = str(m.get("marketType"))
        if mt == "PLAYER_A_TO_WIN_AT_LEAST_1_SET":
            A = m
        elif mt == "PLAYER_B_TO_WIN_AT_LEAST_1_SET":
            Bm = m
        elif mt == "MATCH_BETTING":
            ML = m
    if not (A and Bm and ML):
        continue
    ay, an = two(A)
    by, bn = two(Bm)
    mls = [od(r) for r in (ML.get("runners") or [])]
    if not all([ay, an, by, bn]) or len(mls) != 2 or not all(mls):
        continue
    pA = (1 / ay) / ((1 / ay) + (1 / an))
    pB = (1 / by) / ((1 / by) + (1 / bn))
    fdst = 2 - pA - pB
    tot = 1 / mls[0] + 1 / mls[1]
    M = max(1 / mls[0], 1 / mls[1]) / tot
    five = is_bo5(v)
    p = solve(M, five)
    iid = (p ** 3 + (1 - p) ** 3) if five else (p * p + (1 - p) * (1 - p))
    if 0 < fdst < 1:
        rows.append(("BO5" if five else "BO3", str(v.get("name"))[:34], M, iid, fdst, fdst - iid,
                     cname.get(str(v.get("competitionId")), "")))
    time.sleep(0.25)

print("matches priced: %d" % len(rows))
by = defaultdict(list)
for r in rows:
    by[r[0]].append(r)
print()
print("=" * 90)
print("TN-002b - FanDuel implied P(straight sets) vs its OWN iid value, by format")
print("=" * 90)
for fmt in ("BO3", "BO5"):
    v = by.get(fmt)
    if not v:
        continue
    g = sorted(x[5] for x in v)
    print("   %s  n=%3d   iid %.4f   FanDuel %.4f   gap %+.4f (median %+.4f)"
          % (fmt, len(v), st.mean([x[3] for x in v]), st.mean([x[4] for x in v]),
             st.mean([x[5] for x in v]), g[len(g) // 2]))
print()
print("   Pinnacle, same market, n=8375 (TN-001):  gap vs iid  +0.1116")
print()
print("   sample rows:")
for r in sorted(rows, key=lambda x: -x[2])[:10]:
    print("      %s %-34s M %.3f  iid %.4f  FD %.4f  gap %+.4f"
          % (r[0], r[1], r[2], r[3], r[4], r[5]))
b3 = by.get("BO3") or []
if b3:
    gm = st.mean([x[5] for x in b3])
    print()
    print("   VERDICT on best-of-3 (all of WTA and most of ATP):")
    if gm > 0.07:
        print("     FanDuel gap %+.4f against Pinnacle's +0.1116 -> FanDuel prices sets ABOUT AS" % gm)
        print("     SHARPLY as Pinnacle. It does NOT use iid, so the Phase 4a premise is FALSE here.")
    else:
        print("     FanDuel gap %+.4f -> near the iid value, the edge would be live." % gm)
