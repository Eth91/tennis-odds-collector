"""NBA port · P1 — injury feed (ESPN), the fast layer.

Mirrors the WNBA system's proven feed (same endpoint family that caught 38/38 outs):
ESPN's NBA injuries API -> nba_injuries.json {player: {status, team, detail, date}}.
Runs every collect-odds cycle; in the offseason it's stale season-enders (harmless) —
the point is the plumbing is live and tested long before opening night.

P2 ADD-ON (October, when reports resume): the OFFICIAL NBA injury report — published on
a fixed clock (5:30pm ET + hourly near tip) as a structured PDF. That's the scheduled-
edge-window upgrade over anything WNBA had; parse it when live PDFs exist to test against.

    python nba_injuries.py           # fetch + write nba_injuries.json + print summary
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
OUT = HERE / "nba_injuries.json"
URL = "https://site.web.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}


def fetch():
    """{player: {team, status, detail, date}} — team is the NBA tricode, never blank.

    ⚠️ THE TRICODE IS ON THE ATHLETE, NOT THE GROUP. The outer group carries only
    {id, displayName, injuries} — there is no `team` key on it, so the original
    `(team.get("team") or {}).get("abbreviation")` evaluated to "" for EVERY row.
    A blank tricode is a SILENT ZERO downstream: nba_flags scopes the WOWY pair
    lookup by team, so 40 real OUTs matched 0 pairs and the engine printed
    "0 flags" — indistinguishable from a quiet night. Verified 2026-10-22: the
    abbreviation lives at injuries[].injuries[].athlete.team.abbreviation.

    Group displayName ("Atlanta Hawks") is the fallback so a payload reshuffle
    degrades to a name we can map, not to "". Rows we cannot resolve to a tricode
    are COUNTED and reported — never silently dropped.
    """
    j = requests.get(URL, headers=UA, timeout=25).json()
    groups = j.get("injuries", [])
    # Pass 1: learn group displayName -> tricode from whichever athletes do carry it.
    # Derived from the same payload rather than a static table, so it cannot go stale.
    by_group = {}
    for grp in groups:
        gname = grp.get("displayName") or ""
        for inj in grp.get("injuries", []):
            tri = (((inj.get("athlete") or {}).get("team") or {})
                   .get("abbreviation") or "").upper()
            if gname and tri:
                by_group.setdefault(gname, tri)
                break
    out, unresolved = {}, []
    for grp in groups:
        gname = grp.get("displayName") or ""
        for inj in grp.get("injuries", []):
            ath = inj.get("athlete") or {}
            name = ath.get("displayName") or ""
            if not name:
                continue
            tri = ((ath.get("team") or {}).get("abbreviation") or "").upper()
            if not tri:
                tri = by_group.get(gname, "")
            if not tri:
                unresolved.append(name)
            out[name] = {
                "team": tri,
                "status": (inj.get("status") or ""),                  # Out / Day-To-Day / ...
                "detail": ((inj.get("details") or {}).get("type") or ""),
                "date": (inj.get("date") or "")[:10],
            }
    if unresolved:
        print(f"  !! {len(unresolved)} row(s) with NO tricode: {unresolved[:5]}")
    return out


def main():
    inj = fetch()
    from collections import Counter
    by = Counter(v["status"] for v in inj.values())
    outs = {k: v for k, v in inj.items() if (v["status"] or "").lower() == "out"}
    no_tri = [k for k, v in outs.items() if not v["team"]]

    # FAIL LOUD, DON'T WRITE. A blank tricode on an OUT player is not a cosmetic
    # defect: nba_flags scopes its WOWY pair lookup by team, so these rows match
    # nothing and the engine reports a clean "0 flags". Refuse to publish a feed
    # that would read as a quiet night. (The bug this guards shipped 2026-08 and
    # went unnoticed for 10 weeks precisely because it failed silently.)
    if outs and len(no_tri) > 0.10 * len(outs):
        raise SystemExit(
            f"REFUSING TO WRITE {OUT.name}: {len(no_tri)}/{len(outs)} OUT players have no "
            f"tricode (>10%). The ESPN payload shape likely changed — the abbreviation is at "
            f"injuries[].injuries[].athlete.team.abbreviation. Examples: {no_tri[:5]}")

    OUT.write_text(json.dumps(
        {"fetched_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
         "injuries": inj}, indent=1))
    print(f"nba injuries: {len(inj)} players {dict(by)} -> {OUT.name}")
    print(f"  OUT={len(outs)}  with tricode={len(outs) - len(no_tri)}  teams={len({v['team'] for v in outs.values() if v['team']})}")


if __name__ == "__main__":
    main()
