#!/usr/bin/env python3
"""NBA pings — an ntfy push the moment a play is flagged, and a VOID push if its premise dies.

User, 2026-10-24: "add a ntfy ping immediately once a play is flagged, i need 0 latency and extreme
speed." This overrides the standing "shadow tiers never ping" rule for the NBA. Every NBA tier is
still SHADOW (nba_flags.LIVE_TIERS is empty: no backtest beat the close), so each ping says `shadow`.
The speed test's measurement does not change: a flag's price is the engine's logged price, never a fill.

FORMAT — the user's spec (feedback_ping_board_coherence, v3), ported to the NBA:
    body   🚨 {TEAM} {Full Name} {STAT} o{line} {american} {tier} shadow
    title  static "Pickz" (an empty title shows the raw topic URL); NO tags (they add an emoji)
    VOID   ⚠ VOID {TEAM} {Full Name} {STAT} o{line} {why}   (urgent: money may already be down)

ONE PING PER PLAY: (game date, player, stat), however many tiers flag it and however often it is
re-flagged at a moved line, deduplicated in nba_shadow.sqlite `pings`. Called in-process by
nba_flags right after the flag rows commit, so the ping costs one HTTPS POST (~0.2-0.5 s), not a
poll. A play whose game has started never pings. A failed send is recorded and retried on the next
flag pass while the game has not started. Never raises: a ping problem must not break the flag pass.
"""
from __future__ import annotations

import datetime as dt
import os
import sqlite3

import requests

PINGS_DDL = """CREATE TABLE IF NOT EXISTS pings (key TEXT PRIMARY KEY, kind TEXT, sent_at TEXT,
    ok INTEGER, body TEXT, flag_id TEXT, gtime TEXT)"""
ABBR = {"points": "PTS", "pts": "PTS", "rebounds": "REB", "reb": "REB", "assists": "AST", "ast": "AST",
        "pra": "PRA", "pts_reb": "PR", "pts_ast": "PA", "reb_ast": "RA", "threes": "3PM"}
CANON = {"pts": "points", "reb": "rebounds", "ast": "assists"}
TIMEOUT_S = 5


def american(dec):
    if not dec or dec <= 1:
        return ""
    return f"+{round((dec - 1) * 100)}" if dec >= 2 else f"-{round(100 / (dec - 1))}"


def play_key(f):
    stat = f.get("raw_stat") or f["stat"]
    return f"play|{f['game_date']}|{f.get('pid') or f['b']}|{CANON.get(stat, stat)}"


def play_body(f):
    return (f"🚨 {f['team']} {f['b']} {ABBR.get(f['stat'], f['stat'].upper())} o{f['line']:g} "
            f"{american(f['odds'])} {f['tier']} shadow")


def void_body(f, why):
    stat = f.get("raw_stat") or f["stat"]
    return f"⚠ VOID {f['team']} {f['b']} {ABBR.get(stat, stat.upper())} o{f['line']:g} {why}"


def send(body, priority="high"):
    """POST to ntfy; True on success. No topic configured -> False, quietly (benched)."""
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        return False
    try:
        r = requests.post(f"https://ntfy.sh/{topic}", data=body.encode("utf-8"), timeout=TIMEOUT_S,
                          headers={"Title": "Pickz", "Priority": priority})
        return r.status_code == 200
    except requests.RequestException:
        return False


def _started(gtime, now):
    try:
        t = dt.datetime.fromisoformat(str(gtime).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    return t <= now


def ping_plays(sh, flags, now=None, sender=send):
    """Ping each new play once. `flags` are dicts as nba_flags writes them (with flag_id)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    sh.execute(PINGS_DDL)
    sent = []
    for f in flags:
        if _started(f.get("gtime"), now):
            continue
        k = play_key(f)
        row = sh.execute("SELECT ok FROM pings WHERE key=?", (k,)).fetchone()
        if row and row[0]:
            continue                                   # already delivered for this play
        body = play_body(f)
        ok = bool(sender(body, "high"))
        sh.execute("INSERT OR REPLACE INTO pings VALUES (?,?,?,?,?,?,?)",
                   (k, "play", now.replace(microsecond=0).isoformat(), int(ok), body,
                    f.get("flag_id"), f.get("gtime")))
        sent.append((body, ok))
    sh.commit()
    return sent


def ping_voids(sh, retracted, now=None, sender=send):
    """A ⚠ VOID once for every PINGED play the board has retracted (nba_board's own rule:
    the player Out/Doubtful, or the absent star Available/Probable, on the newest report)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    sh.execute(PINGS_DDL)
    sent = []
    for f in retracted:
        if _started(f.get("gtime"), now):
            continue
        k = play_key(f)
        pinged = sh.execute("SELECT 1 FROM pings WHERE key=? AND kind='play' AND ok=1", (k,)).fetchone()
        vk = "void|" + k
        done = sh.execute("SELECT ok FROM pings WHERE key=?", (vk,)).fetchone()
        if not pinged or (done and done[0]):
            continue
        body = void_body(f, f["why"])
        ok = bool(sender(body, "urgent"))
        sh.execute("INSERT OR REPLACE INTO pings VALUES (?,?,?,?,?,?,?)",
                   (vk, "void", now.replace(microsecond=0).isoformat(), int(ok), body, None, f.get("gtime")))
        sent.append((body, ok))
    sh.commit()
    return sent


def seed(sh, now=None):
    """Mark every play already in the shadow table as pinged (kind 'seed') so switching pings on
    does not push hours-old plays the next time they re-flag at a moved line. Idempotent."""
    now = now or dt.datetime.now(dt.timezone.utc)
    sh.execute(PINGS_DDL)
    n = 0
    for gd, pid, b, stat, gtime in sh.execute(
            "SELECT game_date, pid, b, stat, gtime FROM flags WHERE void_reason IS NULL").fetchall():
        k = play_key({"game_date": gd, "pid": pid, "b": b, "stat": stat})
        cur = sh.execute("INSERT OR IGNORE INTO pings VALUES (?,?,?,?,?,?,?)",
                         (k, "seed", now.replace(microsecond=0).isoformat(), 1, None, None, gtime))
        n += cur.rowcount
    sh.commit()
    return n


if __name__ == "__main__":
    import sys
    from pathlib import Path
    if "--seed" in sys.argv:
        con = sqlite3.connect(Path(__file__).resolve().parent / "nba_shadow.sqlite")
        print(f"seeded {seed(con)} existing play(s) as already pinged")
