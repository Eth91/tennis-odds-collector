"""Dedupe matchup markets before pricing, and record the probabilities validation will need.

FIX 1 — THE DEDUPE. `by_m[mkt].append((run, od))` collected RAW rows, then `if len(rr) != 2:
continue` skipped anything that was not exactly two. But `golf_lines` stores every (market, runner)
~6x per snapshot, so 12 of 14 matchup markets arrive with 4 rows and are silently dropped. Measured
live: the code priced 2 of 14.

The damage is not only coverage. The 2 that survived were the ones whose duplicate copy happened to
be MISSING from that snapshot — so the matchup stream was sampling markets by a property of the
collector's completeness, not at random. Any prospective matchup record built on that would be a
biased sample of the book.

The top-N path already solved this (`groups[mt][run] = min(od)`); this applies the same rule, so
both streams now dedupe identically: one price per runner, the shortest posted.

Note for anyone measuring coverage later: dedupe BEFORE counting. A diagnostic that dedupes and
then reports "14 markets priced" describes what the code COULD see, not what it does.

FIX 2 — INSTRUMENTATION FOR THE FROZEN-MODEL VALIDATION. The ledger recorded only `odds` and the
edge (in `d_wind`). Calibration, Brier, log loss, reliability slope and market-relative scoring all
need the two probabilities AS THEY STOOD AT BET TIME:

    p_bet  — what the model actually bet (post-recalibration, post-blend)
    p_fair — the devigged market price it was bet against

Without them a settled bet is just a win or a loss, which answers ROI very slowly and calibration
never. Adding two columns is instrumentation, not a model change: no probability, gate or constant
moves. It is done now, before the freeze, because a frozen model that cannot be measured is not
worth freezing.

Columns are added by ALTER TABLE so the existing ledger survives, and the INSERT switches to named
columns so future additions cannot silently shift a positional value into the wrong field.
"""
import ast
import io

p = "pga_e3.py"
s = io.open(p, encoding="utf-8").read()
lines = s.split("\n")

# ---------------------------------------------------------------- 1. dedupe matchups
if "by_m = defaultdict(dict)" in s:
    print("  = matchup dedupe already applied")
else:
    i = next(k for k, l in enumerate(lines) if "by_m = defaultdict(list)" in l)
    assert "by_m[mkt].append((run, od))" in lines[i + 3], "matchup collect block moved"
    assert "if len(rr) != 2:" in lines[i + 5], "matchup skip block moved"
    lines = lines[:i] + [
        "    # DEDUPE FIRST (2026-07-30). golf_lines stores every (market, runner) ~6x per",
        "    # snapshot, so 12 of 14 matchup markets arrived with 4 rows and were dropped by the",
        "    # len(rr) != 2 test below — and the 2 survivors were whichever markets happened to be",
        "    # MISSING their duplicate copy, i.e. a sample selected by collector completeness.",
        "    # Same rule the top-N path already uses: one price per runner, the shortest posted.",
        "    by_m = defaultdict(dict)",
        "    for mkt, mt, run, od in rows:",
        '        if "Matchbet" in mkt and od and od > 1.0:',
        "            cur = by_m[mkt].get(run)",
        "            if cur is None or od < cur:",
        "                by_m[mkt][run] = od",
        "    for mkt, _dd in by_m.items():",
        "        rr = list(_dd.items())",
        "        if len(rr) != 2:",
        "            continue",
    ] + lines[i + 7:]
    print("  + matchup markets deduped to one price per runner before the 2-runner test")

s = "\n".join(lines)

# ---------------------------------------------------------------- 2. record p_bet / p_fair
if "p_fair" in s:
    print("  = p_bet/p_fair already recorded")
else:
    # top-N preview already carries p_bet; add p_fair alongside it
    s = s.replace('''                                "p_raw": round(ours, 4), "p_bet": round(_pb, 4),
                                "ev": round(_pb * od - 1.0, 4)})''',
                  '''                                "p_raw": round(ours, 4), "p_bet": round(_pb, 4),
                                "p_fair": round(fair, 6),
                                "ev": round(_pb * od - 1.0, 4)})''', 1)
    s = s.replace('''                            "p_raw": round(_ours_side, 4), "p_bet": round(_bet, 4),
                            "ev": round(_bet * odds - 1.0, 4)})''',
                  '''                            "p_raw": round(_ours_side, 4), "p_bet": round(_bet, 4),
                            "p_fair": round(_fair_side, 6),
                            "ev": round(_bet * odds - 1.0, 4)})''', 1)
    # birdies are priced against the RAW offered price, so that IS their fair reference
    s = s.replace('''                                      "market": mkt[:60], "odds": od,
                                      "edge": round(edge, 3)})''',
                  '''                                      "market": mkt[:60], "odds": od,
                                      "p_bet": round(ours, 4), "p_fair": round(1.0 / od, 6),
                                      "edge": round(edge, 3)})''', 1)
    old_ins = (
        '            cur = con.execute(\n'
        '                "INSERT OR IGNORE INTO flags VALUES '
        '(?,?,?,?,?,?,?,?,?,?,?,NULL,NULL,NULL)",\n'
        '                (key, now, evn, pv["market"], pv["stream"], pv["runner"], "",\n'
        '                 pv["odds"], pv["edge"], "", ""))'
    )
    new_ins = (
        '            cur = con.execute(\n'
        '                "INSERT OR IGNORE INTO flags(key,flagged_at,event,market,stream,"\n'
        '                "runner,opp,odds,d_wind,tee_r,tee_o,p_bet,p_fair) "\n'
        '                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",\n'
        '                (key, now, evn, pv["market"], pv["stream"], pv["runner"], "",\n'
        '                 pv["odds"], pv["edge"], "", "",\n'
        '                 pv.get("p_bet"), pv.get("p_fair")))'
    )
    assert old_ins in s, "flags INSERT moved"
    s = s.replace(old_ins, new_ins, 1)
    old_open = "        con = sqlite3.connect(PAPER)\n        con.execute(E1.DDL)"
    new_open = (
        "        con = sqlite3.connect(PAPER)\n"
        "        con.execute(E1.DDL)\n"
        "        # migrate an existing ledger in place; pure instrumentation for the\n"
        "        # frozen-model validation - changes no probability, gate or constant\n"
        '        for _c in ("p_bet", "p_fair"):\n'
        "            try:\n"
        '                con.execute("ALTER TABLE flags ADD COLUMN %s REAL" % _c)\n'
        "            except sqlite3.OperationalError:\n"
        "                pass"
    )
    assert old_open in s, "ledger open block moved"
    s = s.replace(old_open, new_open, 1)
    print("  + p_bet/p_fair captured on all three streams and persisted to the ledger")

ast.parse(s)
io.open(p, "w", encoding="utf-8").write(s)
print("  + pga_e3.py written")
