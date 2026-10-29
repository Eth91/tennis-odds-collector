"""Does the bias affect the projections we ACTUALLY BET? The +0.64 is concentrated in `bench`
(+1.62), and the 7/29 role gate removed bench from the bet path. If confirmed+likely are
unbiased, there is nothing here to correct."""
import sqlite3, statistics as st, math
p = sqlite3.connect("file:/home/ubuntu/tennis-odds-collector/wnba_proj_log.sqlite?mode=ro", uri=True, timeout=30)
p.row_factory = sqlite3.Row
led = sqlite3.connect("file:/home/ubuntu/tennis-odds-collector/wnba_ledger.sqlite?mode=ro", uri=True, timeout=30)
rows = [dict(r) for r in p.execute("SELECT * FROM projections WHERE graded=1")]
bet_keys = {(str(r[0]), str(r[1])) for r in
            led.execute("SELECT pred_date, player FROM predictions")}
def b(sel, pk, ak):
    v = [float(r[pk]) - float(r[ak]) for r in sel if r.get(pk) is not None and r.get(ak) is not None]
    if len(v) < 15: return None
    se = st.pstdev(v)/math.sqrt(len(v)) or 1e-9
    return st.mean(v), st.mean(v)/se, len(v)
print("=== BIAS RESTRICTED TO THE TIERS WE ACTUALLY BET ===")
betable = [r for r in rows if str(r.get("confidence")) in ("confirmed", "likely")]
print(f"  confirmed+likely rows: {len(betable)} of {len(rows)}")
for lab, pk, ak in (("points","proj_pts","actual_pts"), ("rebounds","proj_reb","actual_reb"),
                    ("assists","proj_ast","actual_ast"), ("MINUTES","proj_min","actual_min")):
    r_ = b(betable, pk, ak)
    if r_: print(f"    {lab:9s} bias {r_[0]:+6.2f}  t={r_[1]:+6.2f}  n={r_[2]}")
print("\n=== BIAS ON ROWS THAT BECAME ACTUAL LEDGER BETS ===")
actual_bets = [r for r in rows if (str(r["date"]), str(r["player"])) in bet_keys]
print(f"  projection rows that became bets: {len(actual_bets)}")
for lab, pk, ak in (("points","proj_pts","actual_pts"), ("rebounds","proj_reb","actual_reb"),
                    ("MINUTES","proj_min","actual_min")):
    r_ = b(actual_bets, pk, ak)
    if r_: print(f"    {lab:9s} bias {r_[0]:+6.2f}  t={r_[1]:+6.2f}  n={r_[2]}")
print("\n=== for contrast, the cohort we DON'T bet ===")
notbet = [r for r in rows if str(r.get("confidence")) in ("bench", "projected")]
for lab, pk, ak in (("points","proj_pts","actual_pts"), ("MINUTES","proj_min","actual_min")):
    r_ = b(notbet, pk, ak)
    if r_: print(f"    {lab:9s} bias {r_[0]:+6.2f}  t={r_[1]:+6.2f}  n={r_[2]}")
print("\n=== are bench/projected rows still reaching the LEDGER at all? ===")
for r in led.execute("SELECT confidence, COUNT(*), MAX(pred_date) FROM predictions GROUP BY confidence"):
    print(f"    {str(r[0]):12s} n={r[1]:4d}  last seen {r[2]}")
