"""Bugs #8 and #9, both inside the devig path I "fixed" yesterday.

#8 TWO DIFFERENT PRODUCTS POOLED. "Top 20" and "Top 20 Finish (Incl. Ties)" are separate
   markets with different payouts, and the dedupe collapsed them into one family keeping the
   SHORTEST price per runner. Measured on the live board: 1,620 rows implying 343 qualifiers
   plus 253 rows implying 45, merged into a pool implying 29.2 against a target of 20.
   Since `fair = (1/od) * N / inv`, an inflated inv DEFLATES every fair probability — here by
   about 28% — and the top-N flag is `ours - fair >= TN_EDGE`. So a player whose true fair
   top-20 is 0.30 gets a fair of 0.216 and an edge of +8.4 points of pure artifact. This is the
   same fake-edge mechanism as the original +20-27% bug; the 0.4N-3N guard waves 29.2 through.

   I had seen this number and rationalised it in the audit as "FD's top-N books run ~1.5x
   overround, so our edges are understated, the safe direction." That was wrong in both parts:
   it is not an overround, and the direction is not safe.

#9 `event LIKE '%PGA%'` MATCHES "LPGA". The audit's devig sanity check — the check whose whole
   job is to catch this class of bug — could pool a women's event into the men's pool.

Fixes: keep the full mtype as the family key so distinct products devig separately; restrict a
pool to runners in the current field; and match the tour with a word boundary.
"""
import ast
import io

# ------------------------------------------------------- #8 separate the products
p = "pga_e3.py"
s = io.open(p, encoding="utf-8").read()

old = '''    groups = defaultdict(dict)
    for mkt, mt, run, od in rows:
        if od and od > 1.0 and mt and ("TOP_" in mt and "FINISH" in mt or mt == "OUTRIGHT_BETTING"):
            fam = ("OUTRIGHT" if mt == "OUTRIGHT_BETTING"
                   else "TOP_%s" % "".join(ch for ch in mt.split("_FINISH")[0] if ch.isdigit()))
            cur = groups[fam].get(run)
            if cur is None or od < cur:
                groups[fam][run] = od
    groups = {k: list(v.items()) for k, v in groups.items()}
    NMAP = {"TOP_5": 5, "TOP_10": 10, "TOP_20": 20, "OUTRIGHT": 1}
    for mt, rr in groups.items():
        N = NMAP.get(mt)
        if not N or len(rr) < 25 or not sim:
            continue'''
new = '''    # SEPARATE PRODUCTS DEVIG SEPARATELY (2026-07-30, bug #8). "Top 20" and "Top 20 Finish
    # (Incl. Ties)" are DIFFERENT markets with different payouts. Collapsing them into one
    # family and keeping the shortest price per runner inflated the normaliser: measured live,
    # 1,620 rows implying 343 qualifiers plus 253 implying 45, merged to imply 29.2 against a
    # target of 20. Because fair = (1/od) * N / inv, that DEFLATED every fair probability ~28%
    # and the flag is `ours - fair >= TN_EDGE` — so a true fair of 0.30 read 0.216 and handed
    # out +8.4 points of edge that did not exist. Same mechanism as the original +20-27% bug;
    # the 0.4N-3N guard passes 29.2. Keying on the FULL mtype keeps the products apart.
    # Also restrict each pool to runners actually in this event's field: a pool with more
    # entrants than the field is pooling something foreign.
    field_norm = {RU.norm(f) for f in field} if field else set()
    groups = defaultdict(dict)
    for mkt, mt, run, od in rows:
        if od and od > 1.0 and mt and ("TOP_" in mt and "FINISH" in mt or mt == "OUTRIGHT_BETTING"):
            if field_norm and RU.norm(run) not in field_norm:
                continue
            cur = groups[mt].get(run)
            if cur is None or od < cur:
                groups[mt][run] = od
    groups = {k: list(v.items()) for k, v in groups.items()}

    def _n_for(mt_):
        if mt_ == "OUTRIGHT_BETTING":
            return 1
        d = "".join(ch for ch in str(mt_).split("_FINISH")[0] if ch.isdigit())
        return int(d) if d in ("5", "10", "20") else None

    for mt, rr in groups.items():
        N = _n_for(mt)
        if not N or len(rr) < 25 or not sim:
            continue'''
if "SEPARATE PRODUCTS DEVIG SEPARATELY" in s:
    print("  = e3 already separates products")
else:
    assert old in s, "e3 devig anchor missing"
    s = s.replace(old, new, 1)
    # the stream label used `mt` which is now a full mtype; keep the label readable
    s = s.replace('''            elif ours - fair >= TN_EDGE and od >= TN_MIN_ODDS:
                preview.append({"stream": "E3-top%d" % N, "runner": run, "market": mt,''',
                  '''            elif ours - fair >= TN_EDGE and od >= TN_MIN_ODDS:
                preview.append({"stream": "E3-top%d" % N, "runner": run, "market": mt[:40],''', 1)
    s = s.replace('''            print(f"  skip {mt}: pool implies {inv:.1f} qualifiers, expected ~{N}")''',
                  '''            print(f"  skip {mt}: pool implies {inv:.1f} qualifiers, expected ~{N} "
                      f"({len(rr)} runners)")''', 1)
    ast.parse(s)
    io.open(p, "w", encoding="utf-8").write(s)
    print("  + pga_e3: distinct top-N products devig separately, pools limited to the field")

# --------------------------------------------------- #9 LIKE '%PGA%' matches LPGA
p2 = "pga_audit.py"
a = io.open(p2, encoding="utf-8").read()
old_a = '''ev_fd = con.execute("SELECT event, COUNT(*) c FROM golf_lines WHERE collected_at=? AND "
                    "event LIKE '%PGA%' GROUP BY event ORDER BY c DESC LIMIT 1", (ts2,)).fetchone()'''
new_a = '''# BUG #9: LIKE '%PGA%' also matches "LPGA AIG Women's Open" — so this check, whose entire
# job is to catch pooling errors, could itself pool a women's event into the men's pool.
ev_fd = con.execute("SELECT event, COUNT(*) c FROM golf_lines WHERE collected_at=? AND "
                    "TRIM(event) LIKE 'PGA %' GROUP BY event ORDER BY c DESC LIMIT 1",
                    (ts2,)).fetchone()'''
if "BUG #9" in a:
    print("  = audit already excludes LPGA")
else:
    assert old_a in a, "audit event filter anchor missing"
    a = a.replace(old_a, new_a, 1)
    # and report per-PRODUCT rather than per-family, matching e3
    a = a.replace('''    if od and od > 1 and mt and (("TOP_" in mt and "FINISH" in mt) or mt == "OUTRIGHT_BETTING"):
        f = ("OUTRIGHT" if mt == "OUTRIGHT_BETTING"
             else "TOP_%s" % "".join(ch for ch in mt.split("_FINISH")[0] if ch.isdigit()))
        d = fam.setdefault(f, {})''',
                  '''    if od and od > 1 and mt and (("TOP_" in mt and "FINISH" in mt) or mt == "OUTRIGHT_BETTING"):
        # key on the FULL mtype: "Top 20" and "Top 20 Finish (Incl. Ties)" are different
        # products and pooling them is bug #8
        f = mt
        d = fam.setdefault(f, {})''', 1)
    a = a.replace('''NM = {"TOP_5": 5, "TOP_10": 10, "TOP_20": 20, "OUTRIGHT": 1}
for f, d in sorted(fam.items()):
    N = NM.get(f)
    if not N:
        continue''',
                  '''def _nfor(f):
    if f == "OUTRIGHT_BETTING":
        return 1
    dd = "".join(ch for ch in str(f).split("_FINISH")[0] if ch.isdigit())
    return int(dd) if dd in ("5", "10", "20") else None


for f, d in sorted(fam.items()):
    N = _nfor(f)
    if not N:
        continue''', 1)
    a = a.replace('''    print("    %-9s %3d runners  implies %6.1f qualifiers  target %2d  %s"
          % (f, len(d), inv, N, "OK" if 0.4 * N <= inv <= 3 * N else "SKIPPED by guard"))''',
                  '''    print("    %-30s %4d runners  implies %6.1f  target %2d  %s"
          % (str(f)[:30], len(d), inv, N,
             "OK" if 0.4 * N <= inv <= 3 * N else "SKIPPED by guard"))''', 1)
    ast.parse(a)
    io.open(p2, "w", encoding="utf-8").write(a)
    print("  + pga_audit: LPGA excluded, pools reported per product")
