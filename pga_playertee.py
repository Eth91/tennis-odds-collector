"""Capture rule by PLAYER tee time, not round first-tee. Measure what it admits before building it.

The current rule excludes a flag unless the snapshot precedes the ROUND's first tee, which is wrong
for golf: waves are spread over ~7 hours, so a player in the late wave has not teed off even though
the round has been running since morning. You can bet that player's round market right up until
they start. The correct test is per PLAYER.

Reference tee, by market kind:
  * single-player market  -> that player's tee for the round named in the market
  * matchbet (A vs B)     -> the EARLIER of the two tees; once either is away the price is in-play
  * field-wide outright   -> the field's R1 first tee, since a 72-hole market goes live when the
                             tournament starts

Name matching is the risk here: tee_sheet stores lowercase names and the market strings carry
suffixes and accents, so unmatched names are counted and shown rather than silently dropped.
"""
import datetime as dt
import re
import sqlite3
import unicodedata

TID_LIKE = "%Rocket%"


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", "", s.lower()).strip()


tt = sqlite3.connect("pga_tees.sqlite")
tids = [r[0] for r in tt.execute("SELECT DISTINCT tid FROM tee_sheet WHERE tname LIKE ?", (TID_LIKE,))]
tid = sorted(tids)[-1]
tee = {}                                    # (round, normalised player) -> datetime
for rnd, pl, ms in tt.execute("SELECT rnd, player, tee_ms FROM tee_sheet WHERE tid=?", (tid,)):
    if ms:
        tee[(rnd, norm(pl))] = dt.datetime.utcfromtimestamp(ms / 1000)
r1_first = min([v for (r, _), v in tee.items() if r == 1] or [None])
print("  event %s | %d tee rows | R1 first tee %s" % (tid, len(tee), r1_first))
tt.close()

SUFFIX = re.compile(r"\s+(Total Birdies or Better|Round \d Score|To Finish|Top \d+).*$", re.I)


def players_and_round(market):
    m = str(market or "")
    g = re.search(r"Round (\d)", m)
    rnd = int(g.group(1)) if g else 1
    if m.upper().startswith("TOP_"):
        return [], rnd, "field"
    mm = re.search(r"Matchbet\s+(.+?)\s+vs\.?\s+(.+?)$", m, re.I)
    if mm:
        return [norm(mm.group(1)), norm(mm.group(2))], rnd, "matchbet"
    name = SUFFIX.sub("", m)
    name = re.sub(r"\s+Round \d.*$", "", name).strip()
    return [norm(name)], rnd, "single"


c = sqlite3.connect("pga_paper.sqlite")
c.row_factory = sqlite3.Row
rows = list(c.execute("SELECT market, stream, snapshot_ts, first_tee, result FROM flags"))
c.close()

stats = {"pass": 0, "late": 0, "unmatched": 0, "field": 0}
detail = []
for r in rows:
    snap = dt.datetime.fromisoformat(r["snapshot_ts"]) if r["snapshot_ts"] else None
    pls, rnd, kind = players_and_round(r["market"])
    if kind == "field":
        ref, why = r1_first, "field -> R1 first tee"
    else:
        ts = [tee.get((rnd, p)) for p in pls]
        miss = [p for p, t in zip(pls, ts) if t is None]
        ts = [t for t in ts if t]
        if miss:
            stats["unmatched"] += 1
            detail.append((r["market"], "NO TEE MATCH for %s" % ", ".join(miss), None, snap))
            continue
        ref, why = (min(ts), "earliest of %d" % len(ts)) if len(ts) > 1 else (ts[0], "player tee")
    ok = bool(snap and ref and snap < ref)
    stats["pass" if ok else "late"] += 1
    if kind == "field":
        stats["field"] += 1
    detail.append((r["market"], why, ref, snap))

print("\n  %-52s %-22s %-21s %s" % ("market", "reference tee", "snapshot", "verdict"))
for m, why, ref, snap in detail:
    v = "-" if ref is None else ("BETTABLE" if snap and snap < ref else "already teed off")
    print("  %-52s %-22s %-21s %s"
          % (str(m)[:52], (ref.isoformat() if ref else why)[:22],
             snap.isoformat() if snap else "?", v))

print("\n  === under a PER-PLAYER tee rule ===")
print("    scorable (snapshot before that player teed): %d of %d" % (stats["pass"], len(rows)))
print("    excluded, player already away              : %d" % stats["late"])
print("    excluded, no tee-sheet name match          : %d   <- fix before trusting the count"
      % stats["unmatched"])
print("    (field-wide outrights judged on R1 first tee: %d)" % stats["field"])
print("\n  for comparison: current rule (round first-tee) admits 0 of %d" % len(rows))
