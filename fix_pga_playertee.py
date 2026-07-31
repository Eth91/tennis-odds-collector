"""Capture rule: last snapshot before THAT PLAYER tees, not before the round's first tee.

WHY THE OLD RULE WAS WRONG. It kept, per event, the last snapshot strictly before the first R1 tee.
In golf that is not the moment a bet stops being available: waves run ~7 hours, so a player teeing
at 16:54 can be bet all morning while the round has been under way since 11:00. Worse, `first_tee`
is only ever R1's, so a ROUND 2 market was tested against Thursday's tee and could never qualify.

Measured on the 37 logged Rocket Classic flags: the old rule admits 0. Zero, not few — the model
would have accumulated flags forever and the SPRT would never have received a single scorable bet.
Under a per-player rule, 11 qualify (every R2 market, flagged 04:30 against tees of 11:33-16:54) and
26 are correctly excluded because that player was already away (R1 markets flagged 20:30-22:00
against tees of 16:43-18:00). Tee-sheet name matching resolved all 37 — no silent drops.

WHY THIS MAY BE CHANGED AT ALL. The capture rule is PRE-REGISTERED, and re-cutting one after seeing
results is exactly what pre-registration forbids. It is defensible here only because the rule has
admitted NOTHING: zero scorable bets exist, so no outcome can be influencing the choice. That
window shuts the moment the first bet scores, and the report says so.

WHAT IS PRESERVED. The discipline the rule existed for — one price per bet, chosen deterministically
rather than by whichever cron pass happened to fire, since these lines move 40-50% within hours. The
old rule took ONE snapshot per EVENT; this takes the last snapshot per MARKET+RUNNER strictly before
that market's own deadline. Same principle, correct clock.

Reference deadline by market kind:
  single player      -> that player's tee for the round named in the market
  matchbet (A vs B)  -> the EARLIER of the two tees; once either is away the price is in-play
  field-wide outright-> the field's R1 first tee, since a 72-hole market goes live at the first ball

Nothing in the MODEL changes; pga_validate.py is not in the frozen set (pga_ruler / pga_e3 /
pga_birdies / pga_context). This only decides which already-logged rows count as validly captured.
"""
import ast
import io
import shutil

P = "pga_validate.py"
s = io.open(P, encoding="utf-8").read()

if "_player_deadline" in s:
    print("  = per-player capture already applied")
    raise SystemExit(0)

HELPER = '''
_TEES = None


def _tee_index():
    """{(tid_round, normalised player): tee datetime} from pga_tees.sqlite, plus each round's first
    tee. Loaded once; a missing tee sheet degrades to {} and every row is then reported as
    unresolvable rather than silently kept or dropped."""
    global _TEES
    if _TEES is not None:
        return _TEES
    import datetime as _dt
    import re as _re
    import sqlite3 as _sq
    import unicodedata as _ud
    idx, first = {}, {}
    f = HERE / "pga_tees.sqlite"
    if f.exists():
        try:
            c = _sq.connect(str(f))
            for tn, rnd, pl, ms in c.execute(
                    "SELECT tname, rnd, player, tee_ms FROM tee_sheet WHERE tee_ms IS NOT NULL"):
                n = _ud.normalize("NFKD", str(pl or "")).encode("ascii", "ignore").decode()
                n = _re.sub(r"[^a-z ]", "", n.lower()).strip()
                t = _dt.datetime.utcfromtimestamp(ms / 1000)
                idx[(str(tn), int(rnd or 0), n)] = t
                k = (str(tn), int(rnd or 0))
                if k not in first or t < first[k]:
                    first[k] = t
            c.close()
        except Exception:                                            # noqa: BLE001
            pass
    _TEES = (idx, first)
    return _TEES


def _norm_name(x):
    import re as _re
    import unicodedata as _ud
    n = _ud.normalize("NFKD", str(x or "")).encode("ascii", "ignore").decode()
    return _re.sub(r"[^a-z ]", "", n.lower()).strip()


def _player_deadline(event, market):
    """The last moment this bet could honestly have been placed.

    Golf waves span ~7 hours, so the round's first tee is not the deadline for a late-wave player —
    their own tee is. Returns (deadline, reason) with deadline None when it cannot be resolved, so
    the caller can EXCLUDE and report rather than guess."""
    import re as _re
    idx, first = _tee_index()
    if not idx:
        return None, "no tee sheet available"
    m = str(market or "")
    g = _re.search(r"Round (\\d)", m)
    rnd = int(g.group(1)) if g else 1
    ev = str(event or "")
    keys = [k for k in {kk[0] for kk in idx} if k and (k in ev or ev in k)]
    tname = sorted(keys, key=len)[-1] if keys else None
    if tname is None:
        return None, "event not on the tee sheet"
    if m.upper().startswith("TOP_") or "FINISH" in m.upper():
        # a 72-hole outright is live from the first ball struck, so R1's first tee is the deadline
        return first.get((tname, 1)), "field outright -> R1 first tee"
    mm = _re.search(r"Matchbet\\s+(.+?)\\s+vs\\.?\\s+(.+?)$", m, _re.I)
    if mm:
        ts = [idx.get((tname, rnd, _norm_name(mm.group(i)))) for i in (1, 2)]
        ts = [t for t in ts if t]
        if not ts:
            return None, "matchbet players not on the tee sheet"
        return min(ts), "matchbet -> earlier of the two tees"
    name = _re.sub(r"\\s+(Total Birdies or Better|Round \\d Score).*$", "", m, flags=_re.I)
    name = _re.sub(r"\\s+Round \\d.*$", "", name).strip()
    t = idx.get((tname, rnd, _norm_name(name)))
    if t is None:
        return None, "player %r not on the R%d tee sheet" % (name[:28], rnd)
    return t, "player tee"

'''

anchor = "def _rows("
assert anchor in s, "anchor for helper missing"
s = s.replace(anchor, HELPER.lstrip("\n") + "\n" + anchor, 1)

OLD = '''    keep, excluded = [], {}
    for ev, rs in by_ev.items():
        tee = next((r[11] for r in rs if r[11]), None)
        if not tee:
            excluded[ev] = "no first_tee recorded — capture undefined"
            continue
        pre = [r[10] for r in rs if r[10] and str(r[10]) < str(tee)]
        if not pre:
            excluded[ev] = "no snapshot before first tee"
            continue
        S = max(pre)
        keep.extend(r for r in rs if r[10] == S)
    return keep, graded, excluded'''
NEW = '''    # PER-PLAYER CAPTURE (revised 2026-07-31, while zero bets were scored — see the module
    # docstring). The deadline for a bet is when THAT PLAYER tees, not when the round's first group
    # does: waves span ~7 hours, and `first_tee` only ever held R1's, so every Round 2+ market was
    # tested against the wrong day and the rule admitted 0 of 37 flags. One price per bet is still
    # enforced — the last snapshot before that market's own deadline — because these lines move
    # 40-50% within hours and otherwise whichever cron pass fired would decide the record.
    keep, excluded = [], {}
    per = {}                                    # (market, runner) -> [rows], deadline
    unresolved = {}
    for ev, rs in by_ev.items():
        for r in rs:
            dl, why = _player_deadline(ev, r[2])
            if dl is None:
                unresolved.setdefault(ev, {}).setdefault(why, 0)
                unresolved[ev][why] += 1
                continue
            per.setdefault((ev, r[2], r[3]), [dl, []])[1].append(r)
    for (ev, _mk, _rn), (dl, rs) in per.items():
        pre = [r for r in rs if r[10] and _dt_lt(str(r[10]), dl)]
        if not pre:
            continue                            # player was already away at every snapshot
        S = max(str(r[10]) for r in pre)
        keep.extend(r for r in pre if str(r[10]) == S)
    for ev, whys in unresolved.items():
        excluded[ev] = "; ".join("%s (%d rows)" % (w, n) for w, n in sorted(whys.items()))
    for ev in by_ev:
        if ev not in excluded and not any(k[0] == ev for k in per):
            excluded[ev] = "no resolvable tee deadline for any flag"
    return keep, graded, excluded


def _dt_lt(snap_iso, deadline):
    """snapshot < deadline, tolerant of the ledger's ISO-string form."""
    import datetime as _dt
    try:
        return _dt.datetime.fromisoformat(str(snap_iso).replace("Z", "")) < deadline
    except (TypeError, ValueError):
        return False'''
assert OLD in s, "capture-rule anchor missing"
s = s.replace(OLD, NEW, 1)

# keep the documented rule honest
s = s.replace(
    "    For each event, the bet set is every flag whose `snapshot_ts` equals S, where\n"
    "        S = max(snapshot_ts) over that event's flags with snapshot_ts < first R1 tee time.\n"
    "    An event with no known `first_tee` is EXCLUDED and reported as excluded — never scored on a\n"
    "    guessed capture, never silently dropped.",
    "    For each MARKET+RUNNER, the bet is the flag whose `snapshot_ts` is the last one strictly\n"
    "    before that PLAYER's tee time for the round the market names (a matchbet uses the earlier\n"
    "    of the two; a field-wide outright uses the R1 first tee, being live from the first ball).\n"
    "    A flag whose deadline cannot be resolved is EXCLUDED and reported — never scored on a\n"
    "    guessed capture, never silently dropped.\n"
    "    REVISED 2026-07-31: the original used the round's first tee, which is not when a bet stops\n"
    "    being available — waves span ~7 hours — and `first_tee` only ever held R1's, so Round 2+\n"
    "    markets were tested against the wrong day and the rule admitted 0 of 37 flags. Changed only\n"
    "    because ZERO bets were scored under it, so no outcome could inform the choice; that\n"
    "    latitude ends with the first scored bet.", 1)

ast.parse(s)
shutil.copyfile(P, "/tmp/pga_validate.pretee.py")
io.open(P, "w", encoding="utf-8").write(s)
print("  + capture rule is now per-player-tee, one price per market+runner")
