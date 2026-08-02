"""Apply the price floor to the Round 4 flags that are already in the ledger.

TIMING IS WHAT MAKES THIS LEGITIMATE. The R4 field tees 15:17-16:45 UTC and it is 10:07 UTC. Not one
of these bets has an outcome, and the rule being applied was derived entirely from rounds that
finished before R4 existed. This is a filter running before the event, not a bet being removed after
seeing how it went — the distinction that separates a filter from a rewritten record.

THE KEY MUST MOVE WITH THE STREAM. `key` is "event|market|runner|stream", so retagging the stream
alone would leave the old key in place; the next pga_e3 cycle would then INSERT a second row under
the new key and the same bet would exist twice, once on each side of the filter. The stream suffix
lands where the generator puts it (`-lowprice` before the `-shadow` suffix e3 appends) so the two
agree byte-for-byte.

WHAT GOES, AND WHY IT IS THE SAME BET THAT ALREADY LOST. All three rejects are plus-money unders on
4.5 birdies — and the graded book already contains Cameron Young under 4.5 @2.14 (lost) and Xander
Schauffele under 4.5 @2.10 (lost). The model is re-flagging the identical players at the identical
line at a slightly worse price. That is not a coincidence the floor happens to catch; it is the
pattern the floor was measured on.
"""
import sqlite3

FLOOR = 0.50
DB = "/Users/ethandown/tennis-odds-collector/pga_paper.sqlite"

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
rows = [dict(r) for r in con.execute(
    "SELECT key, event, market, runner, stream, odds, p_bet, p_fair FROM flags "
    "WHERE result IS NULL")]

moved = 0
for r in rows:
    st = r["stream"] or ""
    base = st[:-len("-shadow")] if st.endswith("-shadow") else st
    if not (base.startswith("E3-birdies") or base.startswith("E3-rscore")):
        continue                       # top-N is structurally longshot; matchups have no evidence
    if "lowprice" in st or (r["p_fair"] or 0.0) >= FLOOR:
        continue
    new_stream = base + "-lowprice" + ("-shadow" if st.endswith("-shadow") else "")
    new_key = f"{r['event']}|{r['market']}|{r['runner']}|{new_stream}"
    con.execute("UPDATE flags SET stream=?, key=? WHERE key=?", (new_stream, new_key, r["key"]))
    print("  filtered  %-32s @%.3f  p_fair %.3f  ->  %s"
          % (r["runner"][:32], r["odds"], r["p_fair"], new_stream))
    moved += 1

con.commit()
print("\n  %d flag(s) retagged; still logged, still graded, off the board." % moved)

print("\n  what remains on the board for Round 4:")
for r in con.execute("SELECT runner, odds, p_bet, p_fair, stream FROM flags "
                     "WHERE result IS NULL AND stream NOT LIKE '%lowprice%' "
                     "AND market LIKE '%Round 4%' ORDER BY odds"):
    print("    KEEP    %-32s @%.3f  model %.3f vs market %.3f"
          % (r["runner"][:32], r["odds"], r["p_bet"] or 0, r["p_fair"] or 0))
con.close()
