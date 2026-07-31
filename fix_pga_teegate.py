"""Stop flagging a market once THAT PLAYER has teed off, and share one deadline resolver.

THE PROBLEM. pga_e3 runs on a */30 cron and prices whatever FanDuel has posted. FanDuel keeps a
Round 1 market up while Round 1 is live, so the scan flagged R1 birdies 150-750 minutes after those
players teed off (median +257). Those flags:

  * can NEVER be scored — the pre-registered capture rule requires a pre-tee snapshot, so they are
    logged, graded, and then discarded by the validator. 26 of 37 flags this week were exactly that;
  * are bets against a BETTER-INFORMED price. Measured on the 7 that settled: the market's p_fair
    was already 0.620 for eventual winners vs 0.538 for losers — the book had absorbed the round.
    The model disagreed hardest exactly where it was wrong (Højgaard: model 0.853 vs market 0.561,
    224 minutes in, lost). Record 3-4, -2.10u;
  * appear on the BOARD as plays, so the dashboard advertises bets the validation can never count.

THE GATE. One check at the single funnel point where previews become logged flags: skip anything
whose player is already away. Field-wide outrights use the R1 first tee, matchbets the earlier of
the two. UNRESOLVED deadlines are treated as CLOSED, because an unknown deadline is not evidence a
market is open — that permissive reading is what produced the bug.

ONE IMPLEMENTATION, NOT TWO. Both this gate and the validator's capture rule answer the same
question, and tonight already produced three separate bugs from exactly that duplication
(tt_board's filter vs check_today's gate; the correlation cap's band vs selection's band; and this
file's first_tee vs the validator's). So the resolver lives in pga_tee_gate.py and both import it.

THIS IS A MODEL CHANGE and pga_e3.py is frozen — it needs a deliberate re-freeze. It is affordable
because the model has ZERO scored bets: nothing accrued under the old behaviour, so nothing is lost
by correcting it, and no outcome informed the decision.
"""
import ast
import io
import shutil

# ── 1. the validator uses the shared resolver instead of its own copy ─────────
P = "pga_validate.py"
s = io.open(P, encoding="utf-8").read()
if "pga_tee_gate" not in s:
    old_start = s.index("_TEES = None")
    old_end = s.index("def _rows(")
    body = s[old_start:old_end]
    assert "_player_deadline" in body, "unexpected validator layout"
    new = ('''# The deadline resolver lives in pga_tee_gate so the MODEL and the VALIDATOR cannot answer
# "is this market still open?" differently. They did, and that is the whole bug this fixes.
import pga_tee_gate as _TG


def _player_deadline(event, market):
    """(deadline, reason) — delegated, so there is exactly one implementation."""
    return _TG.deadline(event, market)


''')
    s = s[:old_start] + new + s[old_end:]
    ast.parse(s)
    shutil.copyfile(P, "/tmp/pga_validate.preshared.py")
    io.open(P, "w", encoding="utf-8").write(s)
    print("  + pga_validate now delegates to pga_tee_gate")
else:
    print("  = pga_validate already delegates")

# ── 2. pga_e3 refuses to flag a market whose player is away ───────────────────
P2 = "pga_e3.py"
s2 = io.open(P2, encoding="utf-8").read()
if "pga_tee_gate" in s2:
    print("  = pga_e3 already gated")
    raise SystemExit(0)

old = """        _n_shadow = 0
        for pv in preview:
            _is_shadow = bool(pv.get("shadow")) or not armed"""
new = """        _n_shadow = 0
        _n_teed = 0
        for pv in preview:
            # TEE GATE (2026-07-31). FanDuel keeps a round's markets up while that round is live,
            # so the */30 scan was flagging R1 birdies up to 750 min AFTER those players teed off
            # (median +257). Such a flag can never be scored — the pre-registered capture rule
            # needs a pre-tee snapshot — and it is a bet into a price that has already absorbed the
            # round: on the 7 that settled, market p_fair was 0.620 for eventual winners vs 0.538
            # for losers, and the model disagreed hardest where it was wrong (3-4, -2.10u).
            # Resolver is SHARED with the validator (pga_tee_gate) so the two cannot diverge.
            # An UNRESOLVED deadline counts as closed: not knowing is not permission.
            if not _TEEGATE.is_open(evn, pv["market"]):
                _n_teed += 1
                continue
            _is_shadow = bool(pv.get("shadow")) or not armed"""
assert old in s2, "flag loop anchor missing"
s2 = s2.replace(old, new, 1)

old_p = ('        print(f"  E3 logged: {len(flags)} armed + {_n_shadow} shadow "\n'
         '              f"(G2 {\'PASS\' if armed else \'not passed — everything logs as shadow\'})")')
new_p = ('        print(f"  E3 logged: {len(flags)} armed + {_n_shadow} shadow, "\n'
         '              f"{_n_teed} skipped (player already teed off) "\n'
         '              f"(G2 {\'PASS\' if armed else \'not passed — everything logs as shadow\'})")')
assert old_p in s2, "print anchor missing"
s2 = s2.replace(old_p, new_p, 1)

anchor = "def latest_event_rows("
assert anchor in s2, "import anchor missing"
s2 = s2.replace(anchor, "import pga_tee_gate as _TEEGATE\n\n\n" + anchor, 1)

ast.parse(s2)
shutil.copyfile(P2, "/tmp/pga_e3.pretee.py")
io.open(P2, "w", encoding="utf-8").write(s2)
print("  + pga_e3 skips any market whose player has already teed off")
