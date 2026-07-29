"""Keep the new harvests out of the binary-DB blob war.

pga_model.sqlite is TRACKED, and the loop's recovery path does `git reset --hard FETCH_HEAD`
then replays *.sqlite from its own pre-reset commit. Two consequences, both observed live:
  * during the reset window an open handle sees origin's older copy -> sqlite raises
    "attempt to write a readonly database", which is what killed the first backfill run;
  * rows written to the working file after that commit are discarded by the replay.

So the brand-new tee sheet gets its OWN untracked DB (nothing else writes it, so it can
never lose a race), and both harvests retry through the reset window instead of dying.
birdie_rounds stays in pga_model.sqlite — it already lives there and has survived 15 events
— but the harvest is now interruption-tolerant, and it is idempotent by tid anyway.
"""
import ast
import io

# ------------------------------------------------------------------ pga_wave DB
p = "pga_wave.py"
s = io.open(p, encoding="utf-8").read()
old = '''HERE = Path(__file__).resolve().parent
DB = HERE / "pga_model.sqlite"
UA = {"User-Agent": "Mozilla/5.0"}'''
new = '''HERE = Path(__file__).resolve().parent
DB = HERE / "pga_model.sqlite"          # read-only here: rounds / birdie_rounds live in it
TEEDB = HERE / "pga_tees.sqlite"        # our own, gitignored: never in the reset/replay race
UA = {"User-Agent": "Mozilla/5.0"}'''
if "TEEDB" not in s:
    assert old in s
    s = s.replace(old, new, 1)

    # every tee_sheet connection moves to TEEDB
    s = s.replace('''def harvest_tees(tids=None, years=(2024, 2025, 2026), verbose=True):
    """Store tee sheets. Idempotent: an event already stored is skipped, so this is safe to
    call from the loop. Historical sheets are what make fit_wave possible at all."""
    con = sqlite3.connect(DB)''', '''def harvest_tees(tids=None, years=(2024, 2025, 2026), verbose=True):
    """Store tee sheets. Idempotent: an event already stored is skipped, so this is safe to
    call from the loop. Historical sheets are what make fit_wave possible at all."""
    con = sqlite3.connect(TEEDB, timeout=30)''', 1)
    s = s.replace('''    con = sqlite3.connect(DB)
    con.execute(DDL)
    if rnd is None:''', '''    con = sqlite3.connect(TEEDB, timeout=30)
    con.execute(DDL)
    if rnd is None:''', 1)
    s = s.replace('''    con = sqlite3.connect(DB)
    con.execute(DDL)
    sheets = {}''', '''    con = sqlite3.connect(TEEDB, timeout=30)
    con.execute(DDL)
    sheets = {}''', 1)

    # tolerate the reset window rather than dying in it
    s = s.replace('''        con.executemany(
            "INSERT OR REPLACE INTO tee_sheet(tid,tname,rnd,player,tee_ms,start_tee,tz) "
            "VALUES(?,?,?,?,?,?,?)",
            [(tid, tname, rnd, nm, ms, stee, tz) for rnd, nm, ms, stee in rows])
        con.commit()''', '''        payload = [(tid, tname, rnd, nm, ms, stee, tz) for rnd, nm, ms, stee in rows]
        for attempt in range(6):
            try:
                con.executemany(
                    "INSERT OR REPLACE INTO tee_sheet(tid,tname,rnd,player,tee_ms,"
                    "start_tee,tz) VALUES(?,?,?,?,?,?,?)", payload)
                con.commit()
                break
            except sqlite3.OperationalError as e:      # reset window: reconnect and retry
                if attempt == 5:
                    raise
                if verbose:
                    print("   %s write retry %d (%s)" % (tid, attempt + 1, str(e)[:40]))
                time.sleep(2.0 * (attempt + 1))
                try:
                    con.close()
                except Exception:                                   # noqa: BLE001
                    pass
                con = sqlite3.connect(TEEDB, timeout=30)
                con.execute(DDL)''', 1)
    s = s.replace("import sqlite3\nimport statistics as st",
                  "import sqlite3\nimport statistics as st\nimport time", 1)
    ast.parse(s)
    io.open(p, "w", encoding="utf-8").write(s)
    print("  + pga_wave.py  own TEEDB + write retry")
else:
    print("  = pga_wave.py  already on TEEDB")

# ------------------------------------------------------- birdie harvest retry
p = "pga_birdies.py"
s = io.open(p, encoding="utf-8").read()
old_b = '''        con.executemany("INSERT OR REPLACE INTO birdie_rounds VALUES (?,?,?,?,?,?,?,?,?,?)",
                        rows)
        con.commit()'''
new_b = '''        for attempt in range(6):
            try:
                con.executemany(
                    "INSERT OR REPLACE INTO birdie_rounds VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
                con.commit()
                break
            except sqlite3.OperationalError as e:
                # the loop's `git reset --hard` briefly swaps this tracked DB under us and
                # sqlite reports it readonly. Reconnect and retry rather than losing an
                # entire backfill run to a one-second window.
                if attempt == 5:
                    raise
                print(f"  write retry {attempt + 1} ({str(e)[:40]})", flush=True)
                time.sleep(2.0 * (attempt + 1))
                try:
                    con.close()
                except Exception:                                  # noqa: BLE001
                    pass
                con = sqlite3.connect(DB, timeout=30)
                con.execute(DDL)'''
if "write retry" not in s:
    assert old_b in s
    s = s.replace(old_b, new_b, 1)
    ast.parse(s)
    io.open(p, "w", encoding="utf-8").write(s)
    print("  + pga_birdies.py  write retry")
else:
    print("  = pga_birdies.py  already retrying")

# ------------------------------------------------------------------- gitignore
p = ".gitignore"
s = io.open(p, encoding="utf-8").read() if io.open(p, encoding="utf-8") else ""
if "pga_tees.sqlite" not in s:
    if not s.endswith("\n"):
        s += "\n"
    s += "pga_tees.sqlite\n"
    io.open(p, "w", encoding="utf-8").write(s)
    print("  + .gitignore  pga_tees.sqlite")
else:
    print("  = .gitignore  already has pga_tees.sqlite")
print("db-safety patch done")
