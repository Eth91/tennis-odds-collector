#!/usr/bin/env python3
"""Player-name resolution between the odds archive and the stat substrates.

Books and stat sites disagree in SYSTEMATIC ways (measured on NFL 2023-24, 476 names,
88.7% exact): punctuation ("AJ Brown" / "A.J. Brown"), suffixes ("Brian Robinson Jr"),
team tags ("Craig Reynolds (DET)"), and pure initials ("A. Erickson"). One resolver for
every sport's backtest, so no model layer ever re-invents (or half-invents) this join.

    from prop_names import build_map
    m = build_map(odds_names, stat_names)     # odds name -> stat name (unmatched absent)
"""
from __future__ import annotations

import re
import unicodedata

_SUFFIX = re.compile(r"\s+(jr|sr|ii|iii|iv|v)\.?$")
_PAREN = re.compile(r"\s*\([^)]*\)")


def norm(s):
    """Canonical form: ascii-fold, drop periods/apostrophes, team tags, suffixes, case."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    s = _PAREN.sub("", s).replace(".", "").replace("'", "").replace("-", " ")
    s = " ".join(s.lower().split())
    return _SUFFIX.sub("", s)


def build_map(odds_names, stat_names):
    """{odds_name: stat_name}. Tiers: exact -> normalized -> unique initial+lastname.
    Ambiguous initial matches are DROPPED (the WNBA name-collision lesson: a wrong join
    silently grades the wrong player; absent is safer than wrong)."""
    out = {}
    stat = set(stat_names)
    by_norm = {}
    for n in stat:
        by_norm.setdefault(norm(n), n)
    by_init = {}
    for n in stat:
        p = norm(n).split()
        if len(p) >= 2:
            by_init.setdefault((p[0][0], " ".join(p[1:])), []).append(n)
    for o in odds_names:
        if o in stat:
            out[o] = o
            continue
        c = by_norm.get(norm(o))
        if c:
            out[o] = c
            continue
        p = norm(o).split()
        if len(p) >= 2 and len(p[0]) <= 2:            # "A. Erickson" style
            cands = by_init.get((p[0][0], " ".join(p[1:])), [])
            if len(cands) == 1:
                out[o] = cands[0]
    return out


if __name__ == "__main__":                             # measured self-check on live data
    import sqlite3
    for sport, odb, mkt, sdb, q in (
        ("NFL", "americanfootball_nfl_odds_hist.sqlite", "player_reception_yds",
         "nfl_stats.sqlite", "select distinct player_display_name from player_weeks"),
        ("NHL", "icehockey_nhl_odds_hist.sqlite", "player_shots_on_goal",
         "nhl_stats.sqlite", "select distinct full_name from players"),
    ):
        try:
            o = sqlite3.connect(f"file:{odb}?mode=ro", uri=True)
            s = sqlite3.connect(f"file:{sdb}?mode=ro", uri=True)
            on = {r[0] for r in o.execute(
                "select distinct player from props where market=?", (mkt,))}
            sn = {r[0] for r in s.execute(q)}
            m = build_map(on, sn)
            print(f"{sport}: {len(on)} odds names -> {len(m)} mapped "
                  f"({100*len(m)/max(1,len(on)):.1f}%), {len(on)-len(m)} unresolved")
        except Exception as e:
            print(f"{sport}: skipped ({str(e)[:60]})")
