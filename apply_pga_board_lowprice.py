"""Keep price-floored flags out of the board record — but COUNT them, so the filter stays testable.

_write_board tallies every row with a non-null result and lists every row with a null one, with no
notion of stream. So a flag the price floor rejected would still show on the board and still land in
the headline record, which would make the filter cosmetic.

Excluding them silently would be the opposite mistake: a filter that deletes its own evidence can
never be shown to be wrong. So the board gains a `filtered` block carrying the -lowprice stream's
own record. If the floor is a mistake, that block is where it becomes visible — a -lowprice line
running well ahead of the kept bets is the falsification, and it accrues automatically.
"""
import ast
import io
import shutil

P = "pga_e1.py"
s = io.open(P, encoding="utf-8").read()

if "lowprice" in s:
    print("  = already applied")
    raise SystemExit(0)

OLD = '''        for r, in con.execute("SELECT result FROM flags WHERE result IS NOT NULL"):
            rec["w" if r == "W" else ("l" if r == "L" else "p")] += 1
        rec["units"] = round(con.execute(
            "SELECT COALESCE(SUM(pnl),0) FROM flags WHERE pnl IS NOT NULL").fetchone()[0], 2)
        opens = [dict(zip(("market", "runner", "opp", "odds", "d_wind", "flagged_at"), row))
                 for row in con.execute(
                     "SELECT market, runner, opp, odds, d_wind, flagged_at FROM flags "
                     "WHERE result IS NULL ORDER BY flagged_at DESC LIMIT 12")]'''

NEW = '''        # PRICE-FLOOR SPLIT (2026-08-02). Streams carrying `lowprice` were rejected by
        # PRICE_FLOOR before the round started. They still price and still grade, so the filter
        # keeps being tested — but they are not bets we would take, so they belong neither in the
        # headline record nor on the board. Their own record is reported separately below; that
        # line is what would falsify the floor.
        NOTLOW = "COALESCE(stream,'') NOT LIKE '%lowprice%'"
        for r, in con.execute(
                f"SELECT result FROM flags WHERE result IS NOT NULL AND {NOTLOW}"):
            rec["w" if r == "W" else ("l" if r == "L" else "p")] += 1
        rec["units"] = round(con.execute(
            f"SELECT COALESCE(SUM(pnl),0) FROM flags WHERE pnl IS NOT NULL AND {NOTLOW}"
        ).fetchone()[0], 2)
        opens = [dict(zip(("market", "runner", "opp", "odds", "d_wind", "flagged_at"), row))
                 for row in con.execute(
                     "SELECT market, runner, opp, odds, d_wind, flagged_at FROM flags "
                     f"WHERE result IS NULL AND {NOTLOW} ORDER BY flagged_at DESC LIMIT 12")]
        filt = {"w": 0, "l": 0, "p": 0, "units": 0.0, "open": 0}
        for r, in con.execute(
                "SELECT result FROM flags WHERE COALESCE(stream,'') LIKE '%lowprice%'"):
            if r is None:
                filt["open"] += 1
            else:
                filt["w" if r == "W" else ("l" if r == "L" else "p")] += 1
        filt["units"] = round(con.execute(
            "SELECT COALESCE(SUM(pnl),0) FROM flags WHERE pnl IS NOT NULL "
            "AND COALESCE(stream,'') LIKE '%lowprice%'").fetchone()[0], 2)'''
assert OLD in s, "board tally anchor"
s = s.replace(OLD, NEW, 1)

# `filt` is built inside the try; the writer must still work if that block raised.
OLD2 = '''    rec = {"w": 0, "l": 0, "p": 0, "units": 0.0}
    opens = []'''
NEW2 = '''    rec = {"w": 0, "l": 0, "p": 0, "units": 0.0}
    filt = {"w": 0, "l": 0, "p": 0, "units": 0.0, "open": 0}
    opens = []'''
assert OLD2 in s, "board init anchor"
s = s.replace(OLD2, NEW2, 1)

OLD3 = '''"event": event_name, "note": note, "record": rec, "open": opens, "clv": clv}))'''
NEW3 = '''"event": event_name, "note": note, "record": rec, "open": opens,
        "filtered": filt, "clv": clv}))'''
assert OLD3 in s, "board write anchor"
s = s.replace(OLD3, NEW3, 1)

ast.parse(s)
shutil.copyfile(P, "/tmp/pga_e1.prelowprice.py")
io.open(P, "w", encoding="utf-8").write(s)
print("  + board record and open list exclude -lowprice; their own record kept under `filtered`")
