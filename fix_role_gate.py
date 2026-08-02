"""Gate WNBA beneficiary bets on the starter label. Measured, not assumed.

A beneficiary who is NOT confirmed/likely STARTING is not a bet. Split of the 135 graded ledger
predictions by `starter_label`, real odds, 1u flat:

    STARTING (confirmed + likely)     n=111   62-49   55.9%   +11.32u
    NOT STARTING (bench + projected)  n= 23    6-17   26.1%   -11.26u
    ALL                               n=135   69-66   51.1%    +1.03u

z = -2.52 against the odds-implied break-even those bets actually took (52.3% — expected 12 wins,
got 6). Not noise. Per label: confirmed 56.6% (+4.00u), likely 55.2% (+2.80u), bench 36.4%
(-3.40u), projected 16.7% (-8.20u, the worst bucket in the ledger).

MECHANISM: minutes that never arrive. Kaitlyn Chen 7/29 was tagged `bench`, projected 21.5 minutes
off five prior elevated games that were ALL 22-25 minutes, and played 12 for 4 points. Janelle
Salaun, same night, same out player, also `bench`. Mean projected minutes by label — confirmed
29.9, likely 30.0, bench 21.9: the model already knows bench players get fewer minutes and still
over-projects them. It COMPUTED the label and printed it on the board as "NOT STARTING". It simply
never gated on it.

ONE GATE, SHARED BY PING AND RECORD (the ping<->board coherence rule). A blocked play still lands
in `preds`, so the dashboard keeps full coverage and the projection tracker still learns from it —
but it carries `bettable = 0`, so it never enters the ledger, never joins a parlay, and never
pings. That keeps "if it pings it's on the dashboard" true while making "on the dashboard" strictly
wider than "bet".

NOT a change to any projection or edge calculation. Only the decision to act on one.
"""
import ast
import io
import shutil

P = "wnba_alert.py"
s = io.open(P, encoding="utf-8").read()
shutil.copyfile(P, "/tmp/wnba_alert.prerole.py")

if "BET_ROLES" in s:
    print("  = role gate already applied")
    raise SystemExit(0)

# ---------------------------------------------------------------- 1. the gate, defined once
anchor = "def collect():"
gate = '''# -- ROLE GATE (2026-07-30, measured on the ledger). A beneficiary who is NOT confirmed/likely
# STARTING is not a bet:
#     STARTING (confirmed+likely)    n=111  62-49  55.9%  +11.32u
#     NOT STARTING (bench+projected) n= 23   6-17  26.1%  -11.26u
# z = -2.52 vs the odds-implied break-even (52.3%; expected 12 wins, got 6) -- not noise. The
# mechanism is minutes that never arrive: Chen 7/29 was tagged "bench", projected 21.5 min off
# five prior 22-25 min games, and played 12 for 4 pts. The label was already computed and shown
# on the board as "NOT STARTING"; nothing ever gated on it.
#
# ONE gate shared by ping and record. A blocked play stays in `preds` (board coverage, projection
# tracker) but carries bettable=0: no ledger row, no parlay leg, no push.
BET_ROLES = {"confirmed", "likely"}


def role_ok(conf):
    """True when the beneficiary is confirmed or likely STARTING."""
    return str(conf) in BET_ROLES


'''
assert anchor in s, "collect() anchor missing"
s = s.replace(anchor, gate + anchor, 1)

# ---------------------------------------------------------------- 2. n1 tier
n1_old = '''                        alerts.append((e["ev"], f"n1|{slate_date}|{n}|{e['stat']}|{e['line']:g}",
                            f"⚡1G {out_label} OUT -> {_short(n)} {e['stat'][:3]} o{e['line']:g} "
                            f"{T._am(e['dec'])} | proj {e['elev_avg']:g} +{e['ev']*100:.0f}%EV "
                            f"· 1-game sample · STALE line — SPEED PILOT (graded, tier n1)"'''
n1_new = '''                        if not role_ok(_c1):
                            preds[-1]["bettable"] = 0    # board keeps it; no bet, no ping
                        if role_ok(_c1):
                            alerts.append((e["ev"], f"n1|{slate_date}|{n}|{e['stat']}|{e['line']:g}",
                                f"⚡1G {out_label} OUT -> {_short(n)} {e['stat'][:3]} o{e['line']:g} "
                                f"{T._am(e['dec'])} | proj {e['elev_avg']:g} +{e['ev']*100:.0f}%EV "
                                f"· 1-game sample · STALE line — SPEED PILOT (graded, tier n1)"'''
assert n1_old in s, "n1 alerts.append block missing"
s = s.replace(n1_old, n1_new, 1)

# the n1 call's closing lines need one more indent level too
n1_tail_old = '''                            + _n1_warn(e["stat"])))'''
n1_tail_new = '''                                + _n1_warn(e["stat"])))'''
assert n1_tail_old in s, "n1 tail missing"
s = s.replace(n1_tail_old, n1_tail_new, 1)

# ---------------------------------------------------------------- 3. firm tier
firm_old = '''                alerts.append((e["ev"], key,'''
firm_new = '''                if role_ok(conf):
                    alerts.append((e["ev"], key,'''
assert firm_old in s, "firm alerts.append missing"
s = s.replace(firm_old, firm_new, 1)
firm_body_old = '''                    f"{out_label} OUT -> {_short(n)} {e['stat'][:3]} {sd}{e['line']:g} "
                    f"{T._am(e['dec'])}{wo} | {rec} {e['hit']*100:.0f}% "
                    f"| proj {e['elev_avg']:g} +{e['ev']*100:.0f}%EV{ctag}{tag}{env_tag}{rtag}"))'''
firm_body_new = '''                        f"{out_label} OUT -> {_short(n)} {e['stat'][:3]} {sd}{e['line']:g} "
                        f"{T._am(e['dec'])}{wo} | {rec} {e['hit']*100:.0f}% "
                        f"| proj {e['elev_avg']:g} +{e['ev']*100:.0f}%EV{ctag}{tag}{env_tag}{rtag}"))'''
assert firm_body_old in s, "firm message body missing"
s = s.replace(firm_body_old, firm_body_new, 1)

firm_pred_old = '''                preds.append({"pred_date": slate_date, "out_player": out_full, "player": n,
                              "tier": "firm",'''
firm_pred_new = '''                preds.append({"pred_date": slate_date, "out_player": out_full, "player": n,
                              "tier": "firm", "bettable": 1 if role_ok(conf) else 0,'''
assert firm_pred_old in s, "firm preds.append missing"
s = s.replace(firm_pred_old, firm_pred_new, 1)

# ---------------------------------------------------------------- 4. ledger + parlays honour it
log_old = '''    logged = L.log_predictions(preds)                    # feed the learning loop'''
log_new = '''    # ROLE GATE applied ONCE here, so the ledger, the parlays and the pushes cannot disagree
    # about what counted as a bet. Blocked rows stay in `preds` for the board.
    bet_preds = [p for p in preds if p.get("bettable", 1)]
    _blocked = len(preds) - len(bet_preds)
    if _blocked:
        print(f"role gate: {_blocked} play(s) held — beneficiary not confirmed/likely starting")
    logged = L.log_predictions(bet_preds)                # feed the learning loop'''
assert log_old in s, "log_predictions anchor missing"
s = s.replace(log_old, log_new, 1)

slip_old = '''        for p in preds:
            if (p.get("side") or "over") == "over":'''
slip_new = '''        for p in bet_preds:
            if (p.get("side") or "over") == "over":'''
assert slip_old in s, "parlay loop anchor missing"
s = s.replace(slip_old, slip_new, 1)

push_old = "        delivered = push_plays(fresh, preds, topic)"
push_new = "        delivered = push_plays(fresh, bet_preds, topic)"
assert push_old in s, "push_plays anchor missing"
s = s.replace(push_old, push_new, 1)

ast.parse(s)
io.open(P, "w", encoding="utf-8").write(s)
print("  + role gate defined once (BET_ROLES / role_ok)")
print("  + n1 tier: bettable=0 + ping suppressed")
print("  + firm tier: bettable flag + ping suppressed")
print("  + ledger, parlays and pushes all read bet_preds")
