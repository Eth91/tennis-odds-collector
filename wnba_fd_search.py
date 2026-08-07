#!/usr/bin/env python3
"""wnba_fd_search — recover the main lines FanDuel's event page does not carry.

THE GAP. FanDuel posts "Nyadiew Puoch - Points" at O 5.5 -106 / U 5.5 -122, but that market
is referenced by NO card in any of the 16 event-page tabs, on either the NY or the Alberta
book. Verified exhaustively 2026-08-06. So the collector banks only her legs of the shared
"To Score 5+/10+ Points" markets -> rungs [4.5, 9.5], over-only. prop_edges then anchors
4.5 @ 1.5618 (64% implied), which cannot clear the +10% over bar arithmetically, and reports
"no edge" for a bet it never saw. A data gap wearing a model verdict.

THE FIX. The site's own search DOES return it, from a DIFFERENT HOST than every other call
this repo makes -- api.sportsbook.fanduel.com, not sbapi.*. It needs two headers the rest of
the API does not:  x-sportsbook-region  and  x-app-version.  Both are discoverable: the 400
body names the missing one, so _headers() below negotiates them rather than hardcoding a
guess that rots. No geo-block from Oracle (unlike DraftKings), so this runs on the VM.

SCOPE. Only players wnba_ladder_guard flags as milestone-only -- typically ~28 of ~80. This
is a search endpoint on a book we bet with, so it is deliberately NOT run every 25s hot-window
pass: MIN_GAP_S throttles it and results land in the same fd_lines table posted_props reads.

Parsing is fd_collect.extract() unchanged -- the search payload's marketName ("Nyadiew Puoch
- Points") is byte-identical in shape to the event page's ("Carla Leite - Points"), so there
is no second parser to drift.
"""
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import datetime as dt
from collections import Counter

sys.path.insert(0, "/home/ubuntu/tennis-odds-collector")
os.chdir("/home/ubuntu/tennis-odds-collector")

import fd_collect as FD
import wnba_ladder_guard as GUARD

SEARCH = "https://api.sportsbook.fanduel.com/search/tabs"
REGION = os.environ.get("FD_REGION", "AB")          # the book the user actually bets
APPVER = os.environ.get("FD_APP_VERSION", "6.32.0")
STAMP = "/home/ubuntu/tennis-odds-collector/.fd_search_last"
MIN_GAP_S = int(os.environ.get("FD_SEARCH_GAP", "600"))   # never hammer the book
PACE_S = 1.2                                        # between players
MAX_PLAYERS = 40

# the 400 body names whichever header is missing, so negotiate instead of guessing
_GUESS = {"x-sportsbook-region": REGION, "x-app-version": APPVER,
          "x-sportsbook-platform": "web", "x-brand": "fanduel"}


def _url(q):
    return (f"{SEARCH}?q={urllib.parse.quote(q)}&startIndex=0&_ak={FD.AK}"
            f"&isDesktop=true&timezone=America%2FEdmonton"
            f"&withMarkets=true&includeMarketResults=true&includeMarketBlurbs=true")


def _headers(probe_q="Puoch"):
    """Ask the API which headers it wants rather than pinning a list that silently rots."""
    h = {"User-Agent": FD.UA, "Accept": "application/json"}
    for _ in range(6):
        try:
            urllib.request.urlopen(
                urllib.request.Request(_url(probe_q), headers=h), timeout=25).read(1)
            return h
        except urllib.error.HTTPError as e:
            if e.code != 400:
                raise
            m = re.search(r"property .([a-z0-9-]+).", e.read().decode()[:300])
            if not m:
                raise
            k = m.group(1)
            if k in h:                              # named a header we already sent -> value is wrong
                raise RuntimeError(f"FD rejected header {k}={h[k]!r}; region/app-version drifted")
            h[k] = _GUESS.get(k, "web")
    raise RuntimeError("could not negotiate FanDuel search headers")


def _markets(j):
    """Yield every market dict in the payload, wherever it is nested."""
    if isinstance(j, dict):
        if j.get("marketName") and "runners" in j:
            yield j
        for v in j.values():
            yield from _markets(v)
    elif isinstance(j, list):
        for v in j:
            yield from _markets(v)


def fetch(name, headers):
    req = urllib.request.Request(_url(name), headers=headers)
    j = json.load(urllib.request.urlopen(req, timeout=25))
    rows, ev = [], ""
    for m in _markets(j):
        mn = m.get("marketName") or ""
        if name.split()[-1] not in mn:              # this market belongs to another player
            continue
        for (pl, st, ln, sd, od) in FD.extract(m, "wnba", ev):
            rows.append(("wnba", ev, pl, st, ln, sd, od, 0))
    return rows


def main():
    force = "--force" in sys.argv
    if not force and os.path.exists(STAMP):
        age = time.time() - os.path.getmtime(STAMP)
        if age < MIN_GAP_S:
            print(f"fd_search: skipped ({age:.0f}s < {MIN_GAP_S}s since last)")
            return 0

    bad = GUARD.scan()
    names = sorted(bad)[:MAX_PLAYERS]
    if not names:
        print("fd_search: no milestone-only ladders — nothing to recover")
        open(STAMP, "w").write("")
        return 0

    try:
        headers = _headers()
    except Exception as e:
        # FAIL LOUD. A header change must not read as "no lines found".
        print(f"fd_search: HEADER NEGOTIATION FAILED ({e}) — recovered NOTHING this pass",
              flush=True)
        return 1

    rows, hit, err = [], [], 0
    for i, n in enumerate(names):
        try:
            got = fetch(n, headers)
        except Exception as e:
            err += 1
            print(f"  fd_search {n}: {type(e).__name__} {str(e)[:60]}")
            got = []
        if got:
            two = {ln for _, _, _, _, ln, sd, _, _ in
                   [(None, None, None, None, r[4], r[5], None, None) for r in got]}
            hit.append((n, len(got)))
            rows += got
        if i + 1 < len(names):
            time.sleep(PACE_S)

    if rows:
        ts = dt.datetime.now(dt.timezone.utc).replace(microsecond=0, tzinfo=None).isoformat()
        con = sqlite3.connect(FD.DB)
        con.executemany("INSERT OR REPLACE INTO fd_lines "
                        "(collected_at,sport,event,player,stat,line,side,odds,live) "
                        "VALUES (?,?,?,?,?,?,?,?,?)",
                        [(ts, *r) for r in rows])
        con.commit()
        con.close()
    open(STAMP, "w").write("")
    by = Counter(r[3] for r in rows)
    print(f"fd_search: recovered {len(rows)} lines for {len(hit)}/{len(names)} players "
          f"{dict(by)} (errors {err}) -> {FD.DB}", flush=True)
    for n, c in hit[:12]:
        print(f"    {n:<24} +{c} lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
