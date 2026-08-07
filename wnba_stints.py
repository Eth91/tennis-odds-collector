"""Lineup-stint reconstruction from ESPN WNBA play-by-play.

WHY THIS EXISTS
---------------
WOWY has always needed a player to have MISSED A GAME -- the absence IS the signal.
That is why the injury model keeps hitting walls: Diggins+Taylor is n=0 historical
games, the Diggins+Stevens+Taylor trio is n=0, Stevens+Taylor is n=2. A player who
has never sat has NO without-sample at all, so the model goes silent on exactly the
spots that matter most.

ESPN carries ~51 SUBSTITUTION events per game ("X enters the game for Y"). Walking
them reconstructs who is on the floor at every moment, which turns on/off into a
WITHIN-GAME measurement:

  * every game contributes, not just absence games
  * a player who never missed a game still has thousands of off-court possessions
  * lineup combinations are measured directly, not inferred from a coincidence
    of injuries

VALIDATION IS THE WHOLE GAME HERE. A stint reconstructor that silently drifts to
4 or 6 players on the floor produces confident garbage, and nothing downstream can
tell. `reconstruct` therefore returns a health report and REFUSES to be trusted
quietly: callers get `ok=False` and the reason, never a plausible-looking lineup.
"""
from __future__ import annotations

import re
from collections import defaultdict

import requests

SITE = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba"
HEADERS = {"Accept": "application/json"}          # ESPN 403s browser UAs
_S = requests.Session()
_SUB_RE = re.compile(r"^(.*?)\s+enters the game for\s+(.*?)\s*$", re.I)


class PbpUnreadable(RuntimeError):
    """Feed unusable. Never degraded to an empty/partial reconstruction."""


def _get(url, **params):
    try:
        r = _S.get(url, params=params, headers=HEADERS, timeout=25)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        raise PbpUnreadable(f"{type(e).__name__}: {e}") from e
    except ValueError as e:
        raise PbpUnreadable(f"non-JSON: {e}") from e


def _clock_to_sec(period, disp):
    """Elapsed game seconds. WNBA: 4 x 10:00, OT 5:00."""
    # UNDER A MINUTE ESPN DROPS THE MINUTES DIGIT (fixed 2026-08-06): the clock reads
    # "44.7" or "3.2", not "0:44.7". Splitting on ":" raised and returned None, so EVERY
    # scoring play in the last minute of a quarter was silently discarded -- four quarters
    # of clutch-time scoring, gone. That is what left Kelsey Plum at 70% of her points while
    # 92% of her minutes were counted, and it is a big part of why per-minute rates came out
    # scrambled. Seconds may also be fractional, so parse as float.
    d = str(disp).strip()
    try:
        if ":" in d:
            mm, ss = d.split(":")
            rem = int(mm) * 60 + float(ss)
        else:
            rem = float(d)
    except Exception:                                          # noqa: BLE001
        return None
    p = int(period or 1)
    plen = 600 if p <= 4 else 300
    base = 600 * min(p - 1, 4) + max(p - 5, 0) * 300
    return base + (plen - rem)


def starters(summary):
    """{team_id: {player names}} from the boxscore's starter flags."""
    out = defaultdict(set)
    for tm in ((summary.get("boxscore") or {}).get("players") or []):
        tid = str(((tm.get("team") or {}).get("id")) or "?")
        for grp in tm.get("statistics") or []:
            for a in grp.get("athletes") or []:
                if a.get("starter"):
                    nm = ((a.get("athlete") or {}).get("displayName"))
                    if nm:
                        out[tid].add(nm)
    return dict(out)


def reconstruct(event_id):
    """-> {'ok': bool, 'why': str, 'stints': [...], 'health': {...}}

    A stint = (start_sec, end_sec, {team_id: frozenset(on-floor names)}).
    """
    s = _get(f"{SITE}/summary", event=event_id)
    plays = s.get("plays") or []
    if not plays:
        raise PbpUnreadable(f"event {event_id}: no plays")
    on = {k: set(v) for k, v in starters(s).items()}
    if not on:
        return {"ok": False, "why": "no starters in boxscore", "stints": [], "health": {}}
    bad_five = 0
    unknown_out = 0
    stints = []
    cur_start = 0
    for p in plays:
        txt = str(p.get("text") or "")
        per = ((p.get("period") or {}).get("number"))
        sec = _clock_to_sec(per, ((p.get("clock") or {}).get("displayValue")))
        m = _SUB_RE.match(txt)
        if not m:
            continue
        inn, out_ = m.group(1).strip(), m.group(2).strip()
        tid = str(((p.get("team") or {}).get("id")) or "?")
        if tid not in on:
            unknown_out += 1
            continue
        if sec is not None and sec > cur_start:
            stints.append((cur_start, sec, {k: frozenset(v) for k, v in on.items()}))
            cur_start = sec
        if out_ in on[tid]:
            on[tid].discard(out_)
        else:
            unknown_out += 1          # subbing out someone we never had on
        on[tid].add(inn)
        if len(on[tid]) != 5:
            bad_five += 1
    # CLOSE THE FINAL STINT (2026-08-06). It used to be appended with end=None, and every
    # consumer drops a stint without an end -- so the last stretch of EVERY game was thrown
    # away. That would be harmless if it dropped minutes and production together, but it does
    # not: measured on 401857113, players lost ~10% of their minutes and ~37% of their points,
    # or the reverse. The per-minute RATE therefore came out wrong by up to 30% per player, in
    # both directions, which is almost certainly why the stint signal measured rho~0 on 30k+
    # observations -- the measurement was noise. Close it at the last timestamped play.
    _last = 0
    for _p in plays:
        _t = _clock_to_sec(((_p.get("period") or {}).get("number")),
                           ((_p.get("clock") or {}).get("displayValue")))
        if _t is not None and _t > _last:
            _last = _t
    if cur_start is not None:
        # +1 so a basket at the exact final timestamp is inside the window;
        # consumers test a <= t < b, which would otherwise drop the buzzer play.
        _end = (_last + 1) if _last > cur_start else None
        stints.append((cur_start, _end, {k: frozenset(v) for k, v in on.items()}))
    sizes = [len(v) for _, _, d in stints for v in d.values()]
    off_five = sum(1 for x in sizes if x != 5)
    health = {"stints": len(stints), "lineup_slots": len(sizes),
              "not_five": off_five, "bad_five_events": bad_five,
              "unknown_sub_targets": unknown_out}
    # THE LINEUP INVARIANT IS THE HEALTH CHECK (fixed 2026-08-05). The first
    # version also required unknown_sub_targets == 0, and that threw away 17 of
    # 234 games (7.3%) whose reconstruction was PERFECT: every one reported
    # not_five == 0, i.e. exactly five players on the floor in every slot, and
    # failed only because one or two substitution events named an outgoing player
    # missing from the starter flags. Swapping that player still leaves five on
    # the floor, so the set self-corrects and the stints are usable.
    # A LARGE count is different -- that means the parse has desynced from the
    # feed rather than hiccuped -- so it still refuses above a threshold.
    MAX_UNKNOWN = 6
    ok = off_five == 0 and unknown_out <= MAX_UNKNOWN
    why = "" if ok else (
        f"{off_five}/{len(sizes)} lineup slots not 5-on-floor; "
        f"{unknown_out} unresolved sub targets (limit {MAX_UNKNOWN})")
    if ok and unknown_out:
        why = f"WARN {unknown_out} unresolved sub target(s); lineups all valid"
    return {"ok": ok, "why": why, "stints": stints, "health": health}


if __name__ == "__main__":
    import sys, json
    r = reconstruct(sys.argv[1] if len(sys.argv) > 1 else "401857113")
    print(json.dumps(r["health"], indent=1))
    print("ok:", r["ok"], "|", r["why"])
    for st_ in r["stints"][:3]:
        print("  ", st_[0], "->", st_[1], {k: sorted(v)[:3] for k, v in st_[2].items()})
