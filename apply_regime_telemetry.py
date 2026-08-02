"""Persist the regime + ramp signals per bet. Telemetry only — no gate, no pricing change.

WHY THIS AND NOT A FILTER. The peer-regime warning already works: on the Julie Allemand over-5.5
assists bet (2026-08-02) it named Kiki Rice unprompted, measured 2/11 sample match and 6.0 borrowed
minutes, and was right — 9 of Allemand's 11 elevated games also had Rice out, and in the one recent
game where Rice approached her pre-absence norm, Allemand fell 32 -> 22 minutes.

So I measured whether to act on it, reconstructing the warning as-of for every graded bet in the
pre-registered universe (52 selected {confirmed,likely} overs):

    no warning        27-10   hit 73.0%   units +18.41   ROI +49.7%
    REGIME WARNING     8-7    hit 53.3%   units  +0.33   ROI  +2.2%

The direction is large and matches the mechanism. It is still NOT enough to gate on:
Fisher exact one-sided p = 0.1490, and a day-clustered bootstrap puts the ROI gap at +47.6% with a
95% CI of [-22.9%, +91.5%] — spanning zero. 52 bets are only 16 distinct slates, and a slate is the
real unit because bets on one night share the same injury news. The original docstring's reasoning
("~51 selected bets can't validate a hard gate") survives at 52. WNBA v1.2 is frozen anyway:
adoption requires a paired SPRT over >= 60 PROSPECTIVE settled bets.

THE BLOCKER IS THAT THE SIGNAL IS THROWN AWAY. peer_regime_scan's output goes into the ntfy ping
text and nowhere else, so evaluating it required reconstructing it from game logs — and a
reconstruction can never be the prospective test, because it is not what the model saw. Logging it
at flag time is the prerequisite for ever adopting it, and it changes nothing about what gets
flagged or how anything is priced.

RAMP is logged alongside it, unproven and labelled as such. peer_regime asks a BINARY question —
did the peer play? — which is right for a stable role and wrong for a returning player, whose
minutes are a moving target. Both of Allemand's two "matching" games had Rice at 17 and 23 minutes
against her own 26.7-minute norm, so even the sub-sample peer_regime says to trust was built from a
lineup that is not tonight's. Measured prevalence on the graded universe: 3 of 52 bets (6%), all
three from ONE slate with ONE peer. That is not a testable effect, it is an anecdote — which is
exactly why it is logged rather than wired to anything.
"""
import ast
import io
import shutil

# ── 1. the ramp detector lives with the other WOWY primitives ───────────────────────────────────
W = "wnba_wowy.py"
s = io.open(W, encoding="utf-8").read()
if "def ramp_state" in s:
    print("  = ramp_state already present")
else:
    RAMP = '''

def ramp_state(peer_log, as_of, missed_days=12, back_max=4, deficit_min=2.0):
    """Is this peer still CLIMBING BACK into their role as of `as_of`? None when not.

    peer_regime asks whether a peer played — a binary. That is the right question for a stable
    role and the wrong one for someone working back from an absence, because their minutes are a
    moving target and every game they take back is a game the beneficiary gives up.

    The case this was built from: Julie Allemand's elevated sample had 11 games, 9 of them with
    Kiki Rice out. peer_regime correctly flagged that. But the 2 games it said to trust were Rice's
    first two back — 17 and 23 minutes against a 26.7-minute pre-absence norm — so the "good"
    sub-sample was itself taken from a lineup that had not settled. Rice climbed 17 -> 23, and the
    game where she came closest to her norm is the game Allemand dropped 32 -> 22 minutes.

    Strictly-prior games only. UNPROVEN: measured at 3 of 52 graded bets (6%), all from one slate
    and one peer, which is too rare to validate. Logged, never gated.
    """
    import datetime as _dt
    gs = sorted([g for g in peer_log if str(g.get("date"))[:10] < as_of],
                key=lambda g: str(g.get("date"))[:10])
    played = [g for g in gs if (g.get("min") or 0) > 0]
    if len(played) < 4:
        return None

    def _d(x):
        return _dt.date.fromisoformat(str(x.get("date"))[:10])

    for nb in range(1, back_max + 1):
        if len(played) < nb + 1:
            return None
        gap = (_d(played[-nb]) - _d(played[-nb - 1])).days
        if gap >= missed_days:                       # found the absence behind this stretch
            cur = played[-nb:]
            pre = played[:-nb][-8:]
            if len(pre) < 3:
                return None
            norm = sum(g["min"] for g in pre) / len(pre)
            mins = [g["min"] for g in cur]
            deficit = norm - (sum(mins) / len(mins))
            if deficit < deficit_min:
                return None                          # role already restored
            return {"games_back": nb, "gap_days": gap, "norm": round(norm, 1),
                    "since": mins, "deficit": round(deficit, 1),
                    "trend": round(mins[-1] - mins[0], 1) if len(mins) > 1 else 0.0}
    return None
'''
    anchor = "\n\ndef top_peer("
    assert anchor in s, "top_peer anchor"
    s = s.replace(anchor, RAMP + "\ndef top_peer(", 1)
    ast.parse(s)
    shutil.copyfile(W, "/tmp/wnba_wowy.preramp.py")
    io.open(W, "w", encoding="utf-8").write(s)
    print("  + wnba_wowy.ramp_state()")

# ── 2. persist both signals on the flag row ─────────────────────────────────────────────────────
A = "wnba_alert.py"
s = io.open(A, encoding="utf-8").read()
if "_regime_json" in s:
    print("  = alert already persists the signals")
    raise SystemExit(0)

OLD = """                    if _rw:
                        rtag = (f" ⚠REGIME({_rw['peer']} plays; sample {_rw['n_match']}/"
                                f"{_rw['n_elev']}, ~{_rw['gap_min']:g}min borrowed)")
                except Exception:
                    rtag = \"\""""
NEW = """                    if _rw:
                        rtag = (f" ⚠REGIME({_rw['peer']} plays; sample {_rw['n_match']}/"
                                f"{_rw['n_elev']}, ~{_rw['gap_min']:g}min borrowed)")
                        # PERSIST IT. Until now this existed only in the ping text, so evaluating
                        # it meant reconstructing it from game logs — and a reconstruction can
                        # never be the prospective test, because it is not what the model saw.
                        # Measured retrospectively at 8-7 / +2.2% ROI against 27-10 / +49.7% for
                        # unwarned bets; direction strong, but p=0.149 and the day-clustered CI
                        # spans zero over 16 slates, so this LOGS and does not gate.
                        _regime_json = json.dumps(_rw)
                    # RAMP: is a peer who plays tonight still climbing back into their role? The
                    # binary "did they play" misses it. Unproven (3/52 bets, one slate) — logged.
                    try:
                        _rmp = None
                        for _pn in [x for x, vv in pl.items() if vv.get("team") == team]:
                            if _pn == n or _pn in [nm for nm, _ in outs]:
                                continue
                            if inj.get(_pn) in ("Out", "Doubtful"):
                                continue
                            _st = W.ramp_state(glog(pl[_pn]["id"]), today)
                            if _st and (_rmp is None or _st["deficit"] > _rmp[1]["deficit"]):
                                _rmp = (_pn, _st)
                        if _rmp:
                            _ramp_json = json.dumps(dict(_rmp[1], peer=_rmp[0]))
                            rtag += (f" ⚠RAMP({_rmp[0]} back {_rmp[1]['games_back']}g, "
                                     f"{_rmp[1]['deficit']:g}min under norm)")
                    except Exception:                                  # noqa: BLE001
                        pass
                except Exception:
                    rtag = \"\""""
assert OLD in s, "rtag anchor"
s = s.replace(OLD, NEW, 1)
ast.parse(s)
shutil.copyfile(A, "/tmp/wnba_alert.pretele.py")
io.open(A, "w", encoding="utf-8").write(s)
print("  + wnba_alert persists regime + ramp (telemetry only; nothing gated)")
