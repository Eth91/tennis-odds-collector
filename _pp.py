"""Injury source precedence, per the user 2026-07-28:

    1. @UnderdogWNBA (X)      2. official WNBA injury report      3. RotoWire

"Got it simple clean easy." So: strict priority, no cleverness.
  * RotoWire only fills players the league report says NOTHING about (it was gated on the
    report being >3h stale -- replaced by a plain "official is silent" test).
  * A news ruling always wins. The time-aware veto I had added is GONE: it let a noon
    "Probable" outrank a 6:53pm "ruled out" (the Aaliyah Edwards miss).
A conflict where the league published AFTER the tweet is only LOGGED, never acted on --
visible without breaking the ranking the user set.
"""
import ast
import io
import sys

p = "wnba_tonight.py"
s = io.open(p, encoding="utf-8").read()


def rep(old, new, tag):
    global s
    if old not in s:
        sys.exit("ANCHOR MISSING: " + tag)
    if s.count(old) != 1:
        sys.exit("ANCHOR AMBIGUOUS (%d): %s" % (s.count(old), tag))
    s = s.replace(old, new)


# --- RotoWire drops to rank 3: fills gaps only ---
rep("""                _off = today_off.get(_nm)
                if _off == "Out":
                    continue                 # already official; nothing to add
                if _off in ("Probable", "Available") and not _stale:
                    continue                 # fresh official clearance beats RW""",
    """                # RANK 3: RotoWire fills only what the league report is SILENT about.
                # Any official status for this player -- Out, Questionable, Probable --
                # outranks RotoWire outright.
                if today_off.get(_nm) is not None:
                    continue""",
    "rw_rank3")

# --- Underdog becomes rank 1: unconditional ---
rep('''            if _e["st"] == "out":
                # TIME-AWARE VETO: an official Probable/Available only outranks a ruling the
                # league published BEFORE. Edwards sat 'Probable' on the 12:00 PM report and
                # was ruled out at 6:53 PM -- vetoing on the stale status is how we stayed
                # blind to a ruling the whole market already had.
                if (_nm in _off_avail and _rep_dt is not None
                        and _e.get("_dt") is not None and _rep_dt > _e["_dt"]):
                    continue''',
    '''            if _e["st"] == "out":
                # RANK 1: a news ruling wins outright. No veto -- the old time-aware one let a
                # noon "Probable" outrank a 6:53pm "ruled out" (the Edwards miss). If the league
                # published AFTER the tweet and disagrees, say so but still trust the news.
                if (_nm in _off_avail and _rep_dt is not None
                        and _e.get("_dt") is not None and _rep_dt > _e["_dt"]):
                    print("CONFLICT: report (%s) later than news, says %s is %s -- "
                          "taking the news OUT anyway (rank 1)"
                          % (_stamp, _nm, today_off.get(_nm)), flush=True)''',
    "ud_rank1")

# --- news "available" also outranks the report now ---
rep('''            else:                              # "available to play"
                if _nm in _off_out:
                    continue                   # official Out outranks a news clearance
                out.pop(_nm, None)
                NEWS_OUTS.discard(_nm)''',
    '''            else:                              # "available to play"
                # RANK 1 both ways: a news clearance also outranks the report. An official Out
                # that a beat reporter later contradicts is a stale row, not a live ruling.
                if _nm in _off_out:
                    print("CONFLICT: report says %s Out, news says available -- "
                          "taking the news (rank 1)" % _nm, flush=True)
                out.pop(_nm, None)
                NEWS_OUTS.discard(_nm)''',
    "ud_in")

# --- retire the now-unused staleness constant's role in gating (keep for reporting) ---
rep("RW_FALLBACK_STALE_HRS = 3.0",
    "RW_FALLBACK_STALE_HRS = 3.0   # report-age reporting only; RotoWire is rank 3 by gap-fill now",
    "const_note")

ast.parse(s)
io.open(p, "w", encoding="utf-8").write(s)
print("precedence set: Underdog(1) > official report(2) > RotoWire(3)")
