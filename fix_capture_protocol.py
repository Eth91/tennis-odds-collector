"""Record the anchor covariates, and pin WHICH snapshot counts as "the bet".

Both are protocol, not model. No probability, gate or constant changes. They re-stamp the freeze
fingerprint because the source changes, which is the point of hashing the source.

--------------------------------------------------------------------------------------------
WHY A CAPTURE RULE. Measured across six snapshots in one 2.5-hour window on Rocket Classic R1:

    Jake Knapp over 2.5     1.72 -> 1.96 -> 1.59 -> 1.87 -> 2.42   (+40%)
    Russell Henley over 3.5 1.68 -> 1.87 -> 2.52                   (+50%)
    Ben Griffin under 5.5   1.45 -> 2.00 -> 1.77 -> 1.38            (-5%)

e3 runs every cron pass and logs whenever the gates pass, so without a rule "the bet" is whichever
pass happened to fire — and on lines that move 40-50% within hours, snapshot timing would dominate
every other variable in the record. A prospective study whose exposure is set by cron scheduling is
not a study.

PRE-REGISTERED RULE (fixed 2026-07-30, before any settled bet):

    For each event, the bet set is every flag whose `snapshot_ts` equals S, where
        S = max(snapshot_ts) over flags with snapshot_ts < first R1 tee time.
    If `first_tee` is unknown for an event, that event is EXCLUDED from the record and
    reported as excluded — never scored on a guessed capture, never silently dropped.

That is deterministic, has no lookahead, and is the last honest moment a bet could actually have
been placed. Later snapshots are still logged — they are the raw material for the line-volatility
analysis — but they do not enter the SPRT.

--------------------------------------------------------------------------------------------
WHY THE ANCHOR COVARIATES. The birdie stream anchors its course level to the market by bisecting a
multiplier LAM, gated on having >= 8 two-sided lines. Rocket Classic R1 posted 7, so LAM stayed at
1.000 and the stream priced on the model's own course-level estimate.

On that event it turned out not to matter — measured gap 1.7 points, LAM would have solved to 1.029,
and every flag survived anchoring. But that was only knowable AFTER the fact, and course level
genuinely varies 0.78x-1.29x (sd 13%) across venues.

So: record `lam` and `n_lines` and let the bets validate. Excluding them on suspicion would be a
post-hoc selection made by the same judgement the test is supposed to audit — exactly the bias
pre-registration exists to prevent. If an unanchored level is wrong, p_bet will mispredict and the
SPRT will say so. Anchored (n_lines >= 8) vs unanchored is a PRE-REGISTERED SUBGROUP, analysed as a
covariate, not a filter.
"""
import ast
import io

p = "pga_e3.py"
s = io.open(p, encoding="utf-8").read()

# ---------------------------------------------------------------- 1. snapshot ts out of the reader
if "def latest_event_rows():\n    \"\"\"" not in s and "return evn.strip(), rows, ts" not in s:
    old = """    rows = con.execute("SELECT market, mtype, runner, odds FROM golf_lines "
                       "WHERE event=? AND collected_at=?", (evn, ts)).fetchall()
    con.close()
    return evn.strip(), rows"""
    new = """    rows = con.execute("SELECT market, mtype, runner, odds FROM golf_lines "
                       "WHERE event=? AND collected_at=?", (evn, ts)).fetchall()
    con.close()
    # `ts` is returned so every flag can record WHICH price snapshot it was priced on. The
    # pre-registered capture rule selects one snapshot per event; without this the record
    # would silently depend on cron timing.
    return evn.strip(), rows, ts"""
    assert old in s, "latest_event_rows tail moved"
    s = s.replace(old, new, 1)
    assert "evn, rows = latest_event_rows()" in s, "caller moved"
    s = s.replace("evn, rows = latest_event_rows()", "evn, rows, snap_ts = latest_event_rows()", 1)
    print("  + latest_event_rows() returns the snapshot timestamp")
else:
    print("  = snapshot ts already returned")

# ---------------------------------------------------------------- 2. first R1 tee time
if "_first_tee" not in s:
    anchor = "    preview, flags = [], []"
    new = '''    # FIRST R1 TEE TIME — defines the pre-registered capture boundary. Orchestrator sheet
    # first (pga_tees.sqlite, epoch ms), ESPN stamp as fallback. If neither is available the
    # value stays None and the validator EXCLUDES the event rather than guessing a capture.
    _first_tee = None
    try:
        import pga_birdies as _B0
        _tid0 = _B0.tid_for_name(evn)
        if _tid0:
            _c0 = sqlite3.connect(HERE / "pga_tees.sqlite")
            _r0 = _c0.execute("SELECT MIN(tee_ms) FROM tee_sheet WHERE tid=? AND rnd=1",
                              (str(_tid0),)).fetchone()
            _c0.close()
            if _r0 and _r0[0]:
                _first_tee = dt.datetime.utcfromtimestamp(
                    float(_r0[0]) / 1000.0).replace(microsecond=0).isoformat()
    except Exception:                                               # noqa: BLE001
        _first_tee = None
    if _first_tee is None:
        try:
            _tt0 = F.tee_times()
            if _tt0:
                _first_tee = min(_tt0.values())
        except Exception:                                           # noqa: BLE001
            _first_tee = None
    print(f"  capture: snapshot {snap_ts} | first R1 tee {_first_tee or 'UNKNOWN'}")

''' + anchor
    assert anchor in s, "preview init moved"
    s = s.replace(anchor, new, 1)
    print("  + first R1 tee time resolved and printed")
else:
    print("  = first tee already resolved")

# ---------------------------------------------------------------- 3. birdie anchor covariates
if "_bird_lam" not in s:
    a2 = "    # ---- birdies-or-better: MARKET-ANCHORED LEVEL, player-relative edges ----"
    s = s.replace(a2, "    _bird_lam, _bird_nlines = None, 0\n" + a2, 1)
    old_l = '''            LAM = 1.0
            if len(_pairs) >= 8:'''
    new_l = '''            LAM = 1.0
            _bird_nlines = len(_pairs)
            if len(_pairs) >= 8:'''
    assert old_l in s, "LAM init moved"
    s = s.replace(old_l, new_l, 1)
    old_g = '''            _ok_b, _why_b = B.birdie_stream_armable()'''
    new_g = '''            _bird_lam = LAM
            _ok_b, _why_b = B.birdie_stream_armable()'''
    assert old_g in s, "armable check moved"
    s = s.replace(old_g, new_g, 1)
    print("  + birdie LAM and two-sided line count captured")
else:
    print("  = birdie covariates already captured")

# ---------------------------------------------------------------- 4. persist all four
if "snapshot_ts" not in s:
    old_mig = '''        for _c in ("p_bet", "p_fair"):'''
    new_mig = '''        for _c in ("p_bet", "p_fair", "snapshot_ts", "first_tee", "lam", "n_lines"):'''
    assert old_mig in s, "migration loop moved"
    s = s.replace(old_mig, new_mig, 1)
    s = s.replace('con.execute("ALTER TABLE flags ADD COLUMN %s REAL" % _c)',
                  'con.execute("ALTER TABLE flags ADD COLUMN %s %s"\n'
                  '                            % (_c, "TEXT" if _c in ("snapshot_ts", "first_tee")\n'
                  '                               else "REAL"))', 1)
    old_i = ('                "runner,opp,odds,d_wind,tee_r,tee_o,p_bet,p_fair) "\n'
             '                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",\n'
             '                (key, now, evn, pv["market"], pv["stream"], pv["runner"], "",\n'
             '                 pv["odds"], pv["edge"], "", "",\n'
             '                 pv.get("p_bet"), pv.get("p_fair")))')
    new_i = ('                "runner,opp,odds,d_wind,tee_r,tee_o,p_bet,p_fair,"\n'
             '                "snapshot_ts,first_tee,lam,n_lines) "\n'
             '                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",\n'
             '                (key, now, evn, pv["market"], pv["stream"], pv["runner"], "",\n'
             '                 pv["odds"], pv["edge"], "", "",\n'
             '                 pv.get("p_bet"), pv.get("p_fair"),\n'
             '                 snap_ts, _first_tee,\n'
             '                 _bird_lam if pv["stream"] == "E3-birdies" else None,\n'
             '                 _bird_nlines if pv["stream"] == "E3-birdies" else None))')
    assert old_i in s, "INSERT moved"
    s = s.replace(old_i, new_i, 1)
    print("  + snapshot_ts / first_tee / lam / n_lines persisted")
else:
    print("  = capture columns already persisted")

ast.parse(s)
io.open(p, "w", encoding="utf-8").write(s)
print("  + pga_e3.py written")
