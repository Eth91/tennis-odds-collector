"""When does a golf bet stop being available? One implementation, shared by the model and the validator.

Golf waves span ~7 hours, so "the round has started" is NOT the deadline — a player teeing at 16:54
can be bet all morning while the field has been away since 11:00. The deadline is per PLAYER.

This module exists so there is exactly ONE answer to that question. pga_e3 uses it to refuse
flagging a market whose player is already away; pga_validate uses it to decide which logged flags
were validly captured. When those two were separate implementations they disagreed immediately —
the same failure that let tt_board's filter drift from check_today's gate, and the correlation cap
drift from selection's band. A shared function cannot drift from itself.

Deadline by market kind:
    single player       -> that player's tee for the round the market names
    matchbet (A vs B)   -> the EARLIER of the two tees; once either is away the price is in-play
    field-wide outright -> the R1 first tee, since a 72-hole market is live from the first ball

Returns (deadline, reason). A deadline of None means UNRESOLVED — callers must treat that as
"cannot confirm it is still pre-tee" and exclude, never as permission to proceed.
"""
import datetime as dt
import re
import sqlite3
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEES = HERE / "pga_tees.sqlite"

_IDX = None                       # (tname, rnd, normalised player) -> tee datetime
_FIRST = None                     # (tname, rnd) -> earliest tee that round


def norm_name(x):
    """Fold accents and punctuation so 'Nicolai Højgaard' matches the sheet's 'nicolai hojgaard'."""
    n = unicodedata.normalize("NFKD", str(x or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", "", n.lower()).strip()


def _load():
    global _IDX, _FIRST
    if _IDX is not None:
        return _IDX, _FIRST
    idx, first = {}, {}
    if TEES.exists():
        try:
            c = sqlite3.connect(str(TEES))
            for tn, rnd, pl, ms in c.execute(
                    "SELECT tname, rnd, player, tee_ms FROM tee_sheet WHERE tee_ms IS NOT NULL"):
                t = dt.datetime.utcfromtimestamp(float(ms) / 1000.0)
                key = (str(tn), int(rnd or 0))
                idx[(key[0], key[1], norm_name(pl))] = t
                if key not in first or t < first[key]:
                    first[key] = t
            c.close()
        except sqlite3.Error:
            pass
    _IDX, _FIRST = idx, first
    return _IDX, _FIRST


def _event_key(event):
    idx, _ = _load()
    ev = str(event or "")
    names = {k[0] for k in idx}
    hits = [n for n in names if n and (n in ev or ev in n)]
    return sorted(hits, key=len)[-1] if hits else None


def deadline(event, market):
    """(deadline_utc, reason). None deadline = unresolved -> the caller must NOT treat it as open."""
    idx, first = _load()
    if not idx:
        return None, "no tee sheet available"
    tname = _event_key(event)
    if tname is None:
        return None, "event not on the tee sheet"
    m = str(market or "")
    g = re.search(r"Round (\d)", m)
    rnd = int(g.group(1)) if g else 1
    if m.upper().startswith("TOP_") or "FINISH" in m.upper():
        return first.get((tname, 1)), "field outright -> R1 first tee"
    mm = re.search(r"Matchbet\s+(.+?)\s+vs\.?\s+(.+?)$", m, re.I)
    if mm:
        ts = [idx.get((tname, rnd, norm_name(mm.group(i)))) for i in (1, 2)]
        ts = [t for t in ts if t]
        if not ts:
            return None, "matchbet players not on the tee sheet"
        return min(ts), "matchbet -> earlier of the two tees"
    name = re.sub(r"\s+(Total Birdies or Better|Round \d Score).*$", "", m, flags=re.I)
    name = re.sub(r"\s+Round \d.*$", "", name).strip()
    t = idx.get((tname, rnd, norm_name(name)))
    if t is None:
        return None, "player %r not on the R%d tee sheet" % (name[:28], rnd)
    return t, "player tee"


def is_open(event, market, when=None):
    """True only when we can CONFIRM the bet is still pre-tee.

    Unresolved resolves to False on purpose: an unknown deadline is not evidence the market is
    open, and the failure we are fixing came from treating a missing/wrong reference as permission.
    """
    dl, _why = deadline(event, market)
    if dl is None:
        return False
    now = when or dt.datetime.utcnow()
    return now < dl
