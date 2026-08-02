"""Split every logged flag into PRE-TEE and POST-TEE and report each record separately.

The user's point is worth taking seriously: a post-tee flag is not necessarily leakage. Our model
prices from its own ruler, not from the scoreboard, so it did not "look at the results". But the
BOOK's price at that moment does reflect the round so far, and p_fair is derived from that price —
so the comparison p_bet vs p_fair is contaminated even if p_bet is not, and it is contaminated in a
direction that flatters us whenever the market has already moved toward the outcome.

So: report both records, and for the post-tee rows also report how far into that player's round the
flag was placed, since a flag 10 minutes after the tee is a very different thing from one 4 hours in.
"""
import datetime as dt
import re
import sqlite3

import pga_validate as V

c = sqlite3.connect("pga_paper.sqlite")
c.row_factory = sqlite3.Row
rows = list(c.execute("SELECT event, market, stream, runner, odds, p_bet, p_fair, result, pnl, "
                      "snapshot_ts FROM flags"))
c.close()


def rnd_of(m):
    g = re.search(r"Round (\d)", str(m or ""))
    return int(g.group(1)) if g else None


pre, post = [], []
for r in rows:
    dl, _why = V._player_deadline(r["event"], r["market"])
    if dl is None:
        continue
    d = dict(r)
    d["_dl"] = dl
    d["_rnd"] = rnd_of(r["market"])
    try:
        snap = dt.datetime.fromisoformat(str(r["snapshot_ts"]).replace("Z", ""))
    except (TypeError, ValueError):
        continue
    d["_mins_after"] = (snap - dl).total_seconds() / 60.0
    (pre if snap < dl else post).append(d)


def rec(rs, lab):
    s = [x for x in rs if x["result"] in ("W", "L")]
    if not s:
        print("  %-40s %3d flags, %d settled — no record yet" % (lab, len(rs), 0))
        return
    w = sum(1 for x in s if x["result"] == "W")
    u = sum(float(x["pnl"] or 0) for x in s)
    print("  %-40s %3d flags, %2d settled  %d-%d  %+.2fu" % (lab, len(rs), len(s), w, len(s) - w, u))


print("=== PRE-TEE (flagged before that player started) ===")
rec(pre, "all pre-tee")
for rn in (1, 2):
    rec([x for x in pre if x["_rnd"] == rn], "  Round %d" % rn)
rec([x for x in pre if x["_rnd"] is None], "  event-long (outrights/matchbets)")

print("\n=== POST-TEE (player already away) ===")
rec(post, "all post-tee")
for rn in (1, 2):
    rec([x for x in post if x["_rnd"] == rn], "  Round %d" % rn)
rec([x for x in post if x["_rnd"] is None], "  event-long")

print("\n=== how deep into the round were the POST-TEE flags? ===")
s = sorted(post, key=lambda x: x["_mins_after"])
for x in s:
    if x["result"] in ("W", "L"):
        print("   +%5.0f min  %-46s %s  p_bet=%.3f p_fair=%.3f"
              % (x["_mins_after"], str(x["market"])[:46], x["result"],
                 x["p_bet"] or 0, x["p_fair"] or 0))
mins = [x["_mins_after"] for x in post]
if mins:
    print("   range +%.0f to +%.0f min after tee (median +%.0f)"
          % (min(mins), max(mins), sorted(mins)[len(mins) // 2]))

print("\n=== is the MARKET price already reflecting the round? ===")
st = [x for x in post if x["result"] in ("W", "L")]
if st:
    ww = [x for x in st if x["result"] == "W"]
    ll = [x for x in st if x["result"] == "L"]
    for lab, g in (("winners", ww), ("losers", ll)):
        if g:
            print("   %-8s mean p_fair %.3f | mean p_bet %.3f  (n=%d)"
                  % (lab, sum(x["p_fair"] or 0 for x in g) / len(g),
                     sum(x["p_bet"] or 0 for x in g) / len(g), len(g)))
    print("   If p_fair is already much higher for eventual winners, the book had absorbed the")
    print("   round and the p_bet-vs-p_fair comparison is not a clean test of the model.")
