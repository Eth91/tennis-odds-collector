"""How many flags would become SCORABLE with a per-round tee reference, and is the file frozen?"""
import json, re, sqlite3, datetime as dt

print("=== what the PGA freeze covers ===")
fz = json.load(open("pga_v1_freeze.json"))
print("  version %s frozen %s" % (fz.get("version"), fz.get("frozen")))
for f, h in (fz.get("source_files") or {}).items():
    print("    %-22s %s" % (f, h))

print("\n=== per-round tee times for the live event ===")
t = sqlite3.connect("pga_tees.sqlite")
rows = list(t.execute("SELECT DISTINCT tid, tname FROM tee_sheet WHERE tname LIKE ?", ("%Rocket%",)))
print("  matching events:", rows[-3:] if rows else "none")
if rows:
    tid = rows[-1][0]
    for r in t.execute("SELECT rnd, COUNT(*), MIN(tee_ms), MAX(tee_ms) FROM tee_sheet "
                       "WHERE tid=? GROUP BY rnd", (tid,)):
        lo = dt.datetime.utcfromtimestamp(r[2] / 1000).isoformat() if r[2] else "?"
        hi = dt.datetime.utcfromtimestamp(r[3] / 1000).isoformat() if r[3] else "?"
        print("    round %s: %4d players  first tee %s  last tee %s" % (r[0], r[1], lo, hi))
t.close()

print("\n=== the 37 logged flags, re-tested against a PER-ROUND tee ===")
c = sqlite3.connect("pga_paper.sqlite"); c.row_factory = sqlite3.Row
tt = sqlite3.connect("pga_tees.sqlite")
tid = rows[-1][0] if rows else None
rnd_first = {}
if tid:
    for r in tt.execute("SELECT rnd, MIN(tee_ms) FROM tee_sheet WHERE tid=? GROUP BY rnd", (tid,)):
        if r[1]:
            rnd_first[r[0]] = dt.datetime.utcfromtimestamp(r[1] / 1000)
tt.close()
ok_now = ok_fix = 0
per = {}
for r in c.execute("SELECT market, stream, snapshot_ts, first_tee FROM flags"):
    snap = dt.datetime.fromisoformat(r["snapshot_ts"]) if r["snapshot_ts"] else None
    ft = dt.datetime.fromisoformat(r["first_tee"]) if r["first_tee"] else None
    if snap and ft and snap < ft:
        ok_now += 1
    g = re.search(r"Round (\d)", str(r["market"]))
    rn = int(g.group(1)) if g else None
    ref = rnd_first.get(rn) if rn else ft          # non-round markets keep the event tee
    good = bool(snap and ref and snap < ref)
    ok_fix += good
    k = "Round %s" % rn if rn else "event-long"
    per.setdefault(k, [0, 0])
    per[k][0] += 1
    per[k][1] += good
print("  scorable under the CURRENT rule (event R1 tee): %d of 37" % ok_now)
print("  scorable with a PER-ROUND tee reference       : %d of 37" % ok_fix)
print("  %-12s %6s %10s" % ("market kind", "rows", "would pass"))
for k, v in sorted(per.items()):
    print("  %-12s %6d %10d" % (k, v[0], v[1]))
c.close()
