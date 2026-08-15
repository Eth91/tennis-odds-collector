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


# Latin letters with NO NFKD decomposition. Without this table the ASCII pass DELETES them
# ('Højgaard' -> 'hjgaard') instead of folding them, and the tee sheet already carries BOTH
# 'rasmus hjgaard' and 'rasmus hojgaard' as separate keys because two sources spell him
# differently. Folding a character that is currently dropped can only turn a miss into a hit:
# every comparison runs both sides through this function.
_FOLD = str.maketrans({"ø": "o", "Ø": "O", "đ": "d", "Đ": "D", "ł": "l", "Ł": "L",
                       "æ": "ae", "Æ": "AE", "ß": "ss", "þ": "th", "ð": "d", "Þ": "TH"})


def norm_name(x):
    """Fold accents and punctuation so 'Nicolai Højgaard' matches the sheet's 'nicolai hojgaard'."""
    n = unicodedata.normalize("NFKD", str(x or "").translate(_FOLD))
    n = n.encode("ascii", "ignore").decode()
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


def _norm_ev(x):
    """Event name -> comparable form: lowercase alphanumerics, trailing year dropped.
    'FedEx St. Jude Championship' and 'PGA FedEx St Jude Championship 2026' must compare
    equal -- the period in 'St.' alone was enough to stop them matching."""
    import re as _re
    t = _re.sub(r"(19|20)\d{2}", "", str(x or ""))
    return "".join(ch for ch in t.lower() if ch.isalnum())


def _event_key(event, when=None):
    """The tee_sheet key for `event`, choosing the RIGHT EDITION when a tournament recurs.

    ⚠️ THIS PICKED THE WRONG YEAR AND SILENTLY CLOSED THE WHOLE BOARD. The tee sheet holds a
    row set per edition -- 'FedEx St. Jude Championship' (2024/2025) alongside 'PGA FedEx St
    Jude Championship 2026'. The old rule returned the LONGEST NAME MATCH, which has nothing
    to do with which tournament is being played, and 'St.' vs 'St ' meant the 2026 key did not
    even match. Deadlines resolved to 2024-08-15, every one of them already past, and
    is_open() correctly reported CLOSED for every market -- so the model flagged NOTHING for
    the live event and looked merely quiet rather than broken.
    Ties are now broken by TIME: the edition whose tee times sit nearest `when` wins.
    """
    idx, first = _load()
    evn = _norm_ev(event)
    names = {k[0] for k in idx}
    hits = [n for n in names if n and evn and (_norm_ev(n) in evn or evn in _norm_ev(n))]
    if not hits:
        return None
    if len(hits) == 1:
        return hits[0]
    now = when or dt.datetime.utcnow()

    def _dist(n):
        ts = [t for (nm, _r), t in first.items() if nm == n]
        return min(abs((t - now).total_seconds()) for t in ts) if ts else float("inf")

    return sorted(hits, key=_dist)[0]


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
    mu = m.upper()
    # ROUND LEADER closes at THAT round's first tee. Must be tested BEFORE the outright branch:
    # folding it in would stamp a 2nd-round market with Wednesday's R1 tee, which is precisely the
    # `_first_tee` hard-coded-rnd=1 defect in another file.
    gl = re.search(r"(\d)\s*(?:ST|ND|RD|TH)\s+ROUND\s+LEADER", mu)
    if gl:
        r = int(gl.group(1))
        return first.get((tname, r)), "round-%d leader -> R%d first tee" % (r, r)
    # FIELD-WIDE OUTRIGHT -> R1 first tee (a 72-hole market is live from the first ball).
    # Matches the mtype form (TOP_10_FINISH_IMG) AND the bare names FanDuel actually posts:
    # "Top 5", "Top 10", "Top 20", "Win Only", "Winner", "Winner w/o X", "Top USA",
    # "Top European", "Three Chances to Win". All are field-wide 72-hole markets.
    if (mu.startswith("TOP_") or "FINISH" in mu
            or re.match(r"^TOP\s+\d+\b", mu)
            or re.match(r"^TOP\s+(USA|EUROPEAN|NORTH AMERICAN|REST OF|AUSTRAL|ASIAN|"
                        r"ENGLISH|IRISH|SCOTTISH|SOUTH AFRICAN|CONTINENTAL)", mu)
            or mu in ("WIN ONLY", "WINNER", "OUTRIGHT", "TO WIN", "TOURNAMENT WINNER")
            or mu.startswith("WINNER W/O")
            or re.search(r"\bCHANCES TO WIN\b", mu)):
        return first.get((tname, 1)), "field outright -> R1 first tee"
    # 2-BALL / 3-BALL -> the EARLIEST tee in the group. Same rule as a matchbet and for the same
    # reason: once any player in the group is away, the price is in-play. FanDuel writes the
    # participants abbreviated after a ' - ' ("2 Ball (Round 4) - A. Iwai / Lopez Ramirez"), so
    # match exact, then unique surname, then surname + first initial -- the initial exists
    # precisely to separate the two Fitzpatricks and must not be discarded.
    # ANY unresolved or still-ambiguous participant FAILS CLOSED. Guessing would pick an
    # arbitrary tee, and picking the later one banks an in-play price as a close.
    if re.match(r"^\s*[23]\s*BALL\b", mu):
        tail = m.split(" - ", 1)[1] if " - " in m else ""
        parts = [p.strip() for p in tail.split("/") if p.strip()]
        if not parts:
            return None, "ball market: no parsable participants"
        pool = {}
        for _k, _v in idx.items():
            if _k[0] == tname and _k[1] == rnd:
                pool[_k[2]] = _v
        if not pool:
            return None, "no R%d tee sheet for this event" % rnd
        ts, bad = [], []
        for p in parts:
            n = norm_name(p)
            t = pool.get(n)
            if t is None and n:
                toks = n.split()
                cand = [(kk, vv) for kk, vv in pool.items()
                        if kk.split() and kk.split()[-1] == toks[-1]]
                if len(cand) > 1 and len(toks) > 1:
                    cand = [c for c in cand if c[0].split()[0].startswith(toks[0][:1])]
                if len(cand) == 1:
                    t = cand[0][1]
                elif len(cand) > 1:
                    bad.append("%s ambiguous x%d" % (p[:18], len(cand)))
                    continue
            if t is None:
                bad.append(p[:18])
            else:
                ts.append(t)
        if bad or len(ts) != len(parts):
            return None, "ball participants unresolved: %s" % ("; ".join(bad)[:56] or "none")
        return min(ts), "%d-ball -> earliest of %d tees" % (len(parts), len(parts))
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
