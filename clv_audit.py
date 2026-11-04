#!/usr/bin/env python3
"""CLV_AUDIT_PREREG.md (commit 7d2f5b2379): one CLV yardstick across the paper-betting systems. Read-only, Mac only.

Copies of the VM's stores live in .projdata (vm_backup_20261103 = the 11/3 nightly backup; clv_vm_20261104 = read-only
snapshots streamed on 11/4 03:35-03:42 UTC). The Mac's own live collectors are read in place through read-only
connections, cut at CUTOFF, so a re-run sees the same rows.

    python3 clv_audit.py                # writes audit/clv_audit/ and CLV_AUDIT_TABLES.md
"""
from __future__ import annotations

import argparse
import bisect
import csv
import datetime as dt
import hashlib
import json
import math
import re
import sqlite3
import unicodedata
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy import stats

import nba_injury_reaction as R
import nba_injury_step2a as S

HERE = Path(__file__).resolve().parent
ET = R.ET
CONV_JSON = HERE / "audit/inj_step2a/result.20261103.json"
NBA_DIR = HERE / ".projdata/vm_backup_20261103"
VM_DIR = HERE / ".projdata/clv_vm_20261104"
HOME = Path.home()
STORES = {
    "nba_lines": NBA_DIR / "nba_lines.20261103.sqlite",
    "nba_matchup": NBA_DIR / "nba_matchup.20261103.sqlite",
    "nba_news": NBA_DIR / "nba_news.20261103.sqlite",
    "nba_shadow": NBA_DIR / "nba_shadow.20261103.sqlite",
    "nba_sxs": NBA_DIR / "nba_sxs.20261103T1257.sqlite",
    "ncaaf_p2": HOME / "dev/cfl-engine/data/ncaaf/ncaaf_p2_ledger.sqlite",
    "ncaaf_fd_mac": HOME / "tennis-odds-collector/collectors/ncaaf_fd_prices.sqlite",
    "ncaaf_rec": VM_DIR / "live_ledger.sqlite",
    "ncaaf_fd_vm": VM_DIR / "ncaaf_fd_prices_vm.sqlite",
    "nfl_v2": HOME / "tennis-odds-collector/nfl_v2_ledger.sqlite",
    "nfl_fd": HOME / "tennis-odds-collector/nfl_prekick_prices.sqlite",
    "tennis_ml": VM_DIR / "ml_ledger.sqlite",
    "tennis_fd": VM_DIR / "tennis_fd.sqlite",
    "golf_paper": VM_DIR / "pga_paper.sqlite",
    "golf_moves": VM_DIR / "golf_moves.sqlite",
    "bet_ledger": VM_DIR / "bet_ledger.sqlite",
    "wnba_clv": VM_DIR / "wnba_clv.sqlite",
    "k_compass": VM_DIR / "k_compass.sqlite",
}
LIVE = ("ncaaf_p2", "ncaaf_fd_mac", "nfl_v2", "nfl_fd")      # Mac collectors: read in place, cut at CUTOFF
CUTOFF = dt.datetime(2026, 11, 4, 3, 0, tzinfo=dt.timezone.utc)
LEVEL = {"nba_sxs": "A", "nba_shadow": "A", "ncaaf_p2": "A", "ncaaf_totals": "A", "ncaaf_rec": "A",
         "tennis_ml": "B", "tennis_pin": "B", "nfl_v2": "C", "golf": "C"}
FLAG_MARKET = {"pts": "points", "reb": "rebounds", "ast": "assists", "fg3m": "threes", "pra": "pra", "pts_reb": "pts_reb",
               "pts_ast": "pts_ast", "reb_ast": "reb_ast", "threes": "threes", "points": "points", "rebounds": "rebounds",
               "assists": "assists"}
NFL_MARKET = {"pass_yds": "player_pass_yds_alternate", "rec_yds": "player_reception_yds_alternate",
              "rush_yds": "player_rush_yds_alternate"}
NCAAF_MARKETS = ("player_pass_yds", "player_reception_yds", "player_rush_yds", "game_total")
CLOSE_MAX = 30.0
MIN_N, MIN_DATES, STRONG_N, STRONG_DATES = 50, 5, 200, 10
COVER_MIN = 0.70
BOOT, SEED = 4000, 7
HORIZONS = ((0, 30, "<30 min"), (30, 180, "30 min-3 h"), (180, 10 ** 7, "3 h+"))
NAME_TOL_H = 12.0                                     # tennis: the same pairing within 12 h is the same match

_FRAC = re.compile(r"(\.\d{6})\d+")
_SUFFIX = {"jr", "sr", "ii", "iii", "iv", "v"}


# ---- small helpers --------------------------------------------------------------------------------------------------
def t_(s):
    """An aware UTC datetime from any of the stores' spellings (naive = UTC; a space for the T; 7-digit fractions)."""
    if s is None or s == "":
        return None
    return R.t_(_FRAC.sub(r"\1", str(s).strip().replace(" ", "T", 1)))


def iso(t):
    return t.astimezone(dt.timezone.utc).isoformat()


def et_date(t):
    return t.astimezone(ET).date().isoformat()


def utc_date(t):
    return t.astimezone(dt.timezone.utc).date().isoformat()


def nv(o, u):
    return (1 / o) / (1 / o + 1 / u)


def norm(name):
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[.'`]", "", s)
    return " ".join(w for w in re.split(r"[^a-z0-9]+", s) if w and w not in _SUFFIX)


def horizon(mins):
    for lo, hi, lab in HORIZONS:
        if lo <= mins < hi:
            return lab
    return "after the start"


def ro(path):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def convs():
    j = json.loads(CONV_JSON.read_text())
    return {m: S.Conv(v["a"], v["b"]) for m, v in j["conversion"].items()}


def bet(system, strategy, t, start, game, player, market, side, line, book, odds, phase="forward", result=None,
        profit=None, src_id=None, src_clv=None, note=None):
    return {"system": system, "strategy": strategy, "level": LEVEL[system], "phase": phase, "t": t, "start": start,
            "game": str(game), "player": player, "market": market, "side": side,
            "line": None if line is None else float(line), "book": book, "odds": float(odds), "result": result,
            "profit": profit, "src_id": src_id, "src_clv": src_clv, "note": note, "clv": None, "why": None,
            "clv2": None, "null": None, "null_n": 0, "excess": None, "move": None, "eligible": False, "date": None}


def finish(b, date, eligible, why=None):
    b["date"], b["eligible"] = date, eligible
    if why:
        b["why"] = why
    if b["start"] is not None and b["t"] is not None:
        b["horizon"] = horizon(R.mins(b["t"], b["start"]))
    return b


def dedupe(bets):
    """The earliest bet per (system, strategy, game, player, market, side, book); (kept, duplicates dropped)."""
    best = {}
    for b in sorted(bets, key=lambda x: x["t"]):
        k = (b["system"], b["strategy"], b["game"], b["player"], b["market"], b["side"], b["book"])
        best.setdefault(k, b)
    return list(best.values()), len(bets) - len(best)


# ---- the NBA close --------------------------------------------------------------------------------------------------
class NBA:
    """Boards (from nba_injury_reaction), each book's close per game, and the canonical CLV of a prop bet."""

    def __init__(self, lines_db, conv):
        self.b = R.Boards(lines_db)
        self.conv = conv
        self._close = {}
        self.games_by_date = defaultdict(list)
        for g, tip in self.b.tip.items():
            self.games_by_date[et_date(tip)].append(g)
        self.end = min(v[-1] for v in self.b.ok.values() if v)          # both books' last full cycle

    def close_t(self, book, gid):
        k = (book, gid)
        if k not in self._close:
            obs, tip = self.b.obs(book, gid), self.b.tip.get(gid)
            self._close[k] = obs[-1] if obs and tip and R.mins(obs[-1], tip) <= CLOSE_MAX else None
        return self._close[k]

    def q(self, book, gid, pid, market, side, line):
        """(no-vig closing probability of the side at the line, why-missing). The same rung's own no-vig when the close
        has it two-sided, else the Step 2a conversion from the close main line (NBA's 8 markets only)."""
        ct = self.close_t(book, gid)
        if ct is None:
            return None, "no close"
        st = self.b.state(book, gid, pid, market, ct)
        if st is None:
            return None, "pulled at the close"
        rung = {ln: (o, u) for ln, o, u in st[4]}.get(line)
        if rung:
            p = R.nv(*rung)
        elif market in self.conv:
            p = self.conv[market].p_at(st[0], st[1], line)
            if p is None:
                return None, "outside the conversion grid"
        else:
            return None, "line not at the close (no conversion)"
        return (p if side == "over" else 1 - p), None

    def clv(self, book, gid, pid, market, side, line, odds):
        q, why = self.q(book, gid, pid, market, side, line)
        return (None, why) if q is None else (q * odds - 1, None)

    def obs_at(self, book, gid, t):
        obs = self.b.obs(book, gid)
        i = bisect.bisect_right(obs, t) - 1
        return obs[i] if i >= 0 else None

    def move(self, book, gid, pid, market, side, line):
        ct = self.close_t(book, gid)
        st = self.b.state(book, gid, pid, market, ct) if ct else None
        if st is None:
            return None
        return (st[0] - line) if side == "over" else (line - st[0])


def nba_null(nba, book, market, side, t, date, cache):
    """Matched null: at the book's observation at or before t, every prop on that book, market and side for games on
    `date` not yet started, at its main line and price, scored with the canonical CLV. (mean, n) or (None, 0)."""
    gids = [g for g in nba.games_by_date.get(date, ()) if nba.b.tip[g] > t]
    key = (book, market, side, date, tuple(sorted((g, nba.obs_at(book, g, t)) for g in gids)))
    if key in cache:
        return cache[key]
    vals = []
    for g in gids:
        tau = nba.obs_at(book, g, t)
        if tau is None:
            continue
        for pid, stat in nba.b.props(book, g):
            if stat != market:
                continue
            st = nba.b.state(book, g, pid, stat, tau)
            if st is None:
                continue
            c, _ = nba.clv(book, g, pid, market, side, st[0], st[2] if side == "over" else st[3])
            if c is not None:
                vals.append(c)
    cache[key] = (sum(vals) / len(vals), len(vals)) if vals else (None, 0)
    return cache[key]


def infer_book(nba, gid, pid, market, line, odds, t):
    """The book whose over at this line matched the logged best-of-two price at the flag time (FanDuel on a tie)."""
    hit = []
    for book in ("fd", "dk"):
        tau = nba.obs_at(book, gid, t)
        st = nba.b.state(book, gid, pid, market, tau) if tau else None
        if st and any(ln == line and abs(o - odds) < 1e-6 for ln, o, _u in st[4]):
            hit.append(book)
    return hit[0] if hit else None


def sxs_bets(path):
    """The side-by-side's signals (every registered rule; its own phase)."""
    con = ro(path)
    out = []
    for rid, rule, phase, t, gid, pid, market, side, line, book, odds, result, clv in con.execute(
            "SELECT rowid, rule, phase, t, gid, pid, market, side, line, book, odds, result, clv FROM signals"):
        out.append(bet("nba_sxs", rule, t_(t), None, gid, pid, market, side, line, book, odds,
                       phase="forward" if phase == "forward" else "development", result=result, src_id=rid,
                       src_clv=clv))
    return out


def shadow_bets(path):
    """The live flag engine: every flag by tier, the carded ones, the pinged ones and the tip card (overs; the logged
    best-of-two price, its book inferred later). Flags the engine itself voided (void_reason) are dropped and counted."""
    con = ro(path)
    pinged = {f for (f,) in con.execute("SELECT flag_id FROM pings WHERE flag_id IS NOT NULL AND ok = 1")}
    out, info = [], defaultdict(int)
    for fid, logged, tier, stat, line, odds, gid, pid, card, void in con.execute(
            "SELECT flag_id, logged_at, tier, stat, line, odds, gid, pid, card, void_reason FROM flags"):
        if void:
            info["voided by the engine"] += 1
            continue
        if odds is None or line is None or gid is None or pid is None or stat not in FLAG_MARKET:
            info["no price, line, game or player"] += 1
            continue
        m = FLAG_MARKET[stat]
        for strat, keep in ((f"flags_{tier}", True), ("flags_carded", card == 1), ("flags_pinged", fid in pinged)):
            if keep:
                out.append(bet("nba_shadow", strat, t_(logged), None, gid, pid, m, "over", line, "best", odds,
                               src_id=fid))
    for fid, gid, pid, stat, line, odds, decided in con.execute(
            "SELECT flag_id, gid, pid, stat, line, odds, decided_at FROM tipcard WHERE card = 1"):
        if odds is None or stat not in FLAG_MARKET:
            info["tip card: no price"] += 1
            continue
        out.append(bet("nba_shadow", "tipcard", t_(decided), None, gid, pid, FLAG_MARKET[stat], "over", line, "best",
                       odds, src_id=fid))
    return out, dict(info)


def nba_box(matchup_db):
    con = ro(matchup_db)
    return {(g, p): (mn, {"pts": a, "reb": b, "ast": c, "fg3m": d}) for g, p, mn, a, b, c, d in
            con.execute("SELECT gid, pid, min, pts, reb, ast, fg3m FROM player_games")}


def score_nba(bets, nba, box, cache):
    """Attach the canonical CLV (same book), FanDuel-close CLV, matched null, excess, grade and horizon."""
    for b in bets:
        gid, pid = b["game"], int(b["player"])
        tip = nba.b.tip.get(gid)
        b["start"] = tip
        if tip is None:
            finish(b, None, False, "game not in the line log")
            continue
        date = et_date(tip)
        if tip > nba.end:
            finish(b, date, False, "not closed at the snapshot")
            continue
        if b["book"] == "best":
            bk = infer_book(nba, gid, pid, b["market"], b["line"], b["odds"], b["t"])
            b["book"] = bk or "fd"
            if bk is None:
                b["note"] = "book unknown: scored on FanDuel"
        mn, st = box.get((gid, pid), (None, None))
        if (gid, pid) in box and not mn or b["result"] == "void":
            finish(b, date, False, "void (did not play)")
            continue
        if st is not None:
            actual = sum(st[c] for c in S.PARTS[b["market"]])
            b["result"] = ("push" if actual == b["line"] else
                           "win" if (actual > b["line"]) == (b["side"] == "over") else "loss")
            b["profit"] = {"push": 0.0, "win": b["odds"] - 1, "loss": -1.0}[b["result"]]
        finish(b, date, True)
        b["clv"], b["why"] = nba.clv(b["book"], gid, pid, b["market"], b["side"], b["line"], b["odds"])
        b["clv2"], _ = nba.clv("fd", gid, pid, b["market"], b["side"], b["line"], b["odds"])
        b["move"] = nba.move(b["book"], gid, pid, b["market"], b["side"], b["line"])
        if b["clv"] is not None:
            b["null"], b["null_n"] = nba_null(nba, b["book"], b["market"], b["side"], b["t"], date, cache)
            b["excess"] = None if b["null"] is None else b["clv"] - b["null"]
    return bets


# ---- FanDuel snapshot stores (NCAAF, NFL) ---------------------------------------------------------------------------
def main_of(lad):
    """(line, over, under) of the two-sided rung with no-vig closest to 50%, or None."""
    two = [(ln, r["over"], r["under"]) for ln, r in lad.items() if "over" in r and "under" in r]
    if not two:
        return None
    return min(two, key=lambda x: (abs(nv(x[1], x[2]) - 0.5), x[0]))


class Snap:
    """A FanDuel snapshot store (fd_quotes: one row per runner per fetch). Per event and market: the fetches that
    carried the market before the start, and each player's ladder {line: {side: best price}} at each fetch."""

    def __init__(self, path, markets, cutoff=CUTOFF):
        self.con = ro(path)
        self.markets = tuple(markets)
        self.cutoff = cutoff
        self.ev = {}
        self._obs = {}

    def load(self, ev, lo=None):
        if ev in self.ev:
            return self.ev[ev]
        q = ("SELECT fetched_at, commence, market, player, side, line, price FROM fd_quotes WHERE event_id = ? AND "
             f"market IN ({','.join('?' * len(self.markets))}) AND fetched_at <= ?")
        args = [ev, *self.markets, iso(self.cutoff)]
        if lo is not None:
            q += " AND fetched_at >= ?"
            args.append(iso(lo))
        d = {"kick": None, "fetch": defaultdict(set), "lad": defaultdict(dict)}
        last = None
        for f, com, mk, pl, side, line, price in self.con.execute(q, args):
            if price is None or line is None or side not in ("over", "under"):
                continue
            ft = t_(f)
            if last is None or ft >= last[0]:
                last = (ft, com)
            d["fetch"][mk].add(ft)
            lad = d["lad"][(mk, ft)].setdefault(norm(pl), {}).setdefault(float(line), {})
            lad[side] = max(lad.get(side, 0.0), float(price))
        d["kick"] = t_(last[1]) if last else None
        d["fetch"] = {m: sorted(v) for m, v in d["fetch"].items()}
        self.ev[ev] = d
        return d

    def kick(self, ev):
        return self.load(ev)["kick"]

    def obs(self, ev, market):
        k = (ev, market)
        if k not in self._obs:
            d = self.load(ev)
            self._obs[k] = [f for f in d["fetch"].get(market, []) if d["kick"] and f < d["kick"]]
        return self._obs[k]

    def obs_at(self, ev, market, t):
        o = self.obs(ev, market)
        i = bisect.bisect_right(o, t) - 1
        return o[i] if i >= 0 else None

    def close_t(self, ev, market):
        o = self.obs(ev, market)
        return o[-1] if o and R.mins(o[-1], self.kick(ev)) <= CLOSE_MAX else None

    def board(self, ev, market, f):
        return self.load(ev)["lad"].get((market, f), {})


def snap_clv(snap, ev, market, player, side, line, odds):
    """Canonical CLV at the same line (no conversion outside NBA): (clv, why-missing, line move toward the bet)."""
    ct = snap.close_t(ev, market)
    if ct is None:
        return None, "no close", None
    lad = snap.board(ev, market, ct).get(player)
    if not lad:
        return None, "pulled at the close", None
    m = main_of(lad)
    mv = None if m is None else ((m[0] - line) if side == "over" else (line - m[0]))
    r = lad.get(line)
    if not r or "over" not in r or "under" not in r:
        return None, "line not at the close (no conversion)", mv
    p = nv(r["over"], r["under"])
    return (p if side == "over" else 1 - p) * odds - 1, None, mv


def snap_null(snap, events, market, side, t, date, cache):
    """Matched null: at each not-yet-started same-date game's last fetch at or before t, every player's main rung on
    the same market and side, scored canonically. (mean, n) or (None, 0)."""
    evs = [e for e, k in events.get(date, ()) if k > t]
    key = (market, side, date, tuple(sorted((e, snap.obs_at(e, market, t)) for e in evs)))
    if key in cache:
        return cache[key]
    vals = []
    for e in evs:
        f = snap.obs_at(e, market, t)
        if f is None:
            continue
        for pl, lad in snap.board(e, market, f).items():
            m = main_of(lad)
            if m is None:
                continue
            c, _, _ = snap_clv(snap, e, market, pl, side, m[0], m[1] if side == "over" else m[2])
            if c is not None:
                vals.append(c)
    cache[key] = (sum(vals) / len(vals), len(vals)) if vals else (None, 0)
    return cache[key]


def snap_events(snap, lo, market):
    """{ET date: [(event, kick)]} for events with `market` fetched between lo and the cutoff."""
    q = "SELECT event_id, MAX(commence) FROM fd_quotes WHERE market = ? AND fetched_at >= ? AND fetched_at <= ? GROUP BY event_id"
    out = defaultdict(list)
    for e, com in snap.con.execute(q, [market, iso(lo), iso(snap.cutoff)]):
        k = t_(com)
        if k:
            out[et_date(k)].append((e, k))
    return out


def ncaaf_bets(p2_path, rec_path):
    """NCAAF P2 unders (two arms), the totals arm, and the receiving-yards overs; (props, totals, rec)."""
    con = ro(p2_path)
    props, totals = [], []
    for fl, arm, ev, gid, ko, player, mk, line, price, side, won, pnl, note in con.execute(
            "SELECT flagged_at, arm, fd_event_id, gid, kickoff, player, market, line, price, side, won, pnl, note "
            "FROM paper_bets WHERE flagged_at <= ?", (iso(CUTOFF),)):
        if price is None or line is None or not ev:
            continue
        res = "void" if note and "void" in note.lower() else ({1: "win", 0: "loss"}.get(won))
        props.append(bet("ncaaf_p2", arm, t_(fl), t_(ko), ev, norm(player), mk, side, line, "fd", price, result=res,
                         profit=pnl if res in ("win", "loss") else None, note=note))
    for fl, arm, ev, ko, line, side, price, won, pnl, note in con.execute(
            "SELECT flagged_at, arm, fd_event_id, kickoff, line, side, price, won, pnl, note FROM paper_totals "
            "WHERE flagged_at <= ?", (iso(CUTOFF),)):
        if price is None or line is None or not ev:
            continue
        res = "void" if note and "void" in note.lower() else ({1: "win", 0: "loss"}.get(won))
        totals.append(bet("ncaaf_totals", arm, t_(fl), t_(ko), ev, "total points", "game_total", side, line, "fd",
                          price, result=res, profit=pnl if res in ("win", "loss") else None, note=note))
    rec = []
    for fl, arm, ev, ko, player, line, op, outcome, pnl in ro(rec_path).execute(
            "SELECT flagged_at, arm, fd_event_id, kickoff, player, line, over_price, outcome, pnl FROM picks"):
        if op is None or line is None or not ev or t_(fl) > CUTOFF:
            continue
        res = (outcome or "").lower() or None
        res = {"w": "win", "l": "loss", "won": "win", "lost": "loss"}.get(res, res)
        rec.append(bet("ncaaf_rec", arm, t_(fl), t_(ko), ev, norm(player), "player_reception_yds", "over", line, "fd",
                       op, result=res, profit=pnl if res in ("win", "loss", "push") else None))
    return props, totals, rec


def score_snap(bets, snap, events, cache):
    for b in bets:
        ev = b["game"]
        d = snap.load(ev, lo=(b["start"] - dt.timedelta(hours=26)) if b["start"] else None)
        kick = d["kick"] or b["start"]
        b["start"] = kick
        date = et_date(kick) if kick else None
        if kick is None or not d["fetch"]:
            finish(b, date, kick is not None and kick <= CUTOFF and b["result"] != "void", "event not in the price store")
            continue
        if kick > CUTOFF:
            finish(b, date, False, "not started at the cutoff")
            continue
        if b["result"] == "void":
            finish(b, date, False, "void")
            continue
        finish(b, date, True)
        b["clv"], b["why"], b["move"] = snap_clv(snap, ev, b["market"], b["player"], b["side"], b["line"], b["odds"])
        if b["clv"] is not None:
            b["null"], b["null_n"] = snap_null(snap, events, b["market"], b["side"], b["t"], date, cache)
            b["excess"] = None if b["null"] is None else b["clv"] - b["null"]
    return bets


def preload(snap, events, dates):
    for d in dates:
        for e, k in events.get(d, ()):
            snap.load(e, lo=k - dt.timedelta(hours=26))


# ---- NFL alt tails: one-sided price CLV ------------------------------------------------------------------------------
def nfl_bets(path):
    con = ro(path)
    out = []
    for pid, strat, arm, ev, com, player, mk, line, side, ts, book, price in con.execute(
            "SELECT p.id, strategy, arm, event_id, commence, player, market, line, side, prediction_ts, book, price "
            "FROM predictions p WHERE bet = 1 AND prediction_ts <= ?", (iso(CUTOFF),)):
        g = con.execute("SELECT won, void, pnl FROM grades WHERE prediction_id = ?", (pid,)).fetchone()
        res = None if g is None else ("void" if g[1] else {1: "win", 0: "loss"}.get(g[0]))
        out.append(bet("nfl_v2", f"{strat}:{arm}", t_(ts), t_(com), ev, norm(player), NFL_MARKET[mk], side, line,
                       "fd", price, result=res, profit=g[2] if g and res in ("win", "loss") else None, src_id=pid))
    return out


def price_clv(snap, ev, market, player, line, odds):
    ct = snap.close_t(ev, market)
    if ct is None:
        return None, "no close"
    lad = snap.board(ev, market, ct).get(player)
    if not lad:
        return None, "pulled at the close"
    oc = (lad.get(line) or {}).get("over")
    if not oc:
        return None, "rung not at the close"
    return odds / oc - 1, None


def rung_null(snap, ev, market, t, cache):
    """Every over rung in the market at the event's fetch at or before t, priced there and at the close:
    {(player, line): price CLV}."""
    f = snap.obs_at(ev, market, t)
    key = (ev, market, f)
    if key not in cache:
        out = {}
        if f is not None:
            for pl, lad in snap.board(ev, market, f).items():
                for ln, r in lad.items():
                    if "over" in r:
                        c, _ = price_clv(snap, ev, market, pl, ln, r["over"])
                        if c is not None:
                            out[(pl, ln)] = c
        cache[key] = out
    return cache[key]


def score_nfl(bets, snap, cache):
    for b in bets:
        ev = b["game"]
        d = snap.load(ev, lo=b["start"] - dt.timedelta(hours=4))
        kick = d["kick"] or b["start"]
        b["start"] = kick
        date = et_date(kick)
        if kick > CUTOFF:
            finish(b, date, False, "not started at the cutoff")
            continue
        if b["result"] == "void":
            finish(b, date, False, "void")
            continue
        finish(b, date, True)
        if not d["fetch"]:
            b["why"] = "event not in the price store"
            continue
        b["clv"], b["why"] = price_clv(snap, ev, b["market"], b["player"], b["line"], b["odds"])
        if b["clv"] is not None:
            rungs = rung_null(snap, ev, b["market"], b["t"], cache)
            others = [v for k, v in rungs.items() if k != (b["player"], b["line"])]
            if others:
                b["null"], b["null_n"] = sum(others) / len(others), len(others)
                b["excess"] = b["clv"] - b["null"]
            own = rungs.get((b["player"], b["line"]))
            b["clv2"] = own                     # the bet rung's own FanDuel-scrape price at that fetch, priced the same way
    return bets


# ---- golf: one-sided price CLV, no null -----------------------------------------------------------------------------
def golf_bets(paper_path, moves_path):
    mv = ro(moves_path)
    by_name, by_type = {}, {}
    for ev, mk, mt, runner, tee, close_ts, close_od, pre_ts, pre_od in mv.execute(
            "SELECT event, market, mtype, runner, tee_utc, close_ts, close_odds, pre_ts, pre_odds FROM moves"):
        row = (tee, close_ts, close_od, pre_ts, pre_od)
        by_name[(ev.strip(), (mk or "").strip(), runner.strip().lower())] = row
        by_type[(ev.strip(), mt, runner.strip().lower())] = row
    out = []
    for key, fl, ev, mk, stream, runner, odds, tee_f, result, pnl in ro(paper_path).execute(
            "SELECT key, flagged_at, event, market, stream, runner, odds, first_tee, result, pnl FROM flags"):
        k = (ev.strip(), mk.strip(), runner.strip().lower())
        row = by_name.get(k) or by_type.get(k)
        res = {"W": "win", "L": "loss", "V": "void", "P": "push"}.get(result, result)
        b = bet("golf", stream, t_(fl), None, ev.strip(), runner.strip().lower(), mk.strip(), "back", None, "fd", odds,
                result=res, profit=pnl if res in ("win", "loss", "push") else None, src_id=key)
        b["_row"] = row
        b["_opp"] = None
        m = re.match(r"(.*) (over|under) ([0-9.]+)$", runner.strip().lower())
        if m:                                   # a two-sided golf market: the other side's close (information)
            b["_opp"] = by_name.get((ev.strip(), mk.strip(), f"{m.group(1)} {'under' if m.group(2) == 'over' else 'over'} {m.group(3)}"))
        out.append(b)
    return out


def score_golf(bets):
    for b in bets:
        row, date = b.pop("_row"), utc_date(b["t"])
        opp = b.pop("_opp")
        if b["result"] == "void":
            finish(b, date, False, "void")
            continue
        if row is None:
            finish(b, date, True, "market not in the move log")
            continue
        tee, cts, cod = t_(row[0]), t_(row[1]), row[2]
        b["start"] = tee
        if tee is None:
            finish(b, date, True, "no tee time")
            continue
        if b["t"] >= tee:
            finish(b, date, False, "flagged after the start")
            continue
        finish(b, date, True)
        if cts is None or not cod:
            b["why"] = "no close"
        elif cts < b["t"]:
            b["why"] = "close before the bet"
        elif R.mins(cts, tee) > CLOSE_MAX or cts > tee:
            b["why"] = "no close"
        else:
            b["clv"] = b["odds"] / cod - 1
            if opp and opp[2] and t_(opp[1]) and R.mins(t_(opp[1]), tee) <= CLOSE_MAX:
                b["clv2"] = nv(cod, opp[2]) * b["odds"] - 1      # two-way no-vig CLV where both sides closed (info)
    return bets


# ---- tennis moneylines ----------------------------------------------------------------------------------------------
class ML:
    """One book's change-only moneyline history: per event its start and each runner's [(time, odds)], the book's run
    times, and an index of events by the pair of names."""

    def __init__(self, rows, runs):
        self.runs = sorted(set(runs))
        self.hist = defaultdict(lambda: defaultdict(list))
        self.start = {}
        names = defaultdict(set)
        for t, eid, start, runner, odds in sorted(rows, key=lambda r: r[0]):
            if odds is None or odds <= 1:
                continue
            self.hist[eid][norm(runner)].append((t, float(odds)))
            self.start[eid] = start or self.start.get(eid)          # the latest listed start
            names[eid].add(norm(runner))
        self.by_pair = defaultdict(list)
        for eid, ns in names.items():
            for a in ns:
                for b in ns:
                    if a < b:
                        self.by_pair[(a, b)].append(eid)
        for eid in self.hist:
            for r in self.hist[eid]:
                self.hist[eid][r].sort()

    def find(self, a, b, start):
        cands = [e for e in self.by_pair.get(tuple(sorted((norm(a), norm(b)))), ())
                 if self.start[e] and abs(R.mins(self.start[e], start)) <= NAME_TOL_H * 60]
        return min(cands, key=lambda e: abs(R.mins(self.start[e], start))) if cands else None

    def price(self, eid, runner, t):
        h = self.hist[eid].get(norm(runner), [])
        i = bisect.bisect_right(h, (t, float("inf"))) - 1
        return h[i][1] if i >= 0 else None

    def q_at(self, eid, pick, opp, t):
        op, oo = self.price(eid, pick, t), self.price(eid, opp, t)
        return None if op is None or oo is None else nv(op, oo)

    def close_any(self, eid, pick, opp):
        """Sensitivity for change-only stores: the last stored price before the start, at any age."""
        q = self.q_at(eid, pick, opp, self.start[eid] - dt.timedelta(seconds=1))
        return (None, "no price before the start") if q is None else (q, None)

    def close(self, eid, pick, opp):
        start = self.start[eid]
        i = bisect.bisect_left(self.runs, start) - 1
        if i < 0 or R.mins(self.runs[i], start) > CLOSE_MAX:
            return None, "no close"
        q = self.q_at(eid, pick, opp, self.runs[i])
        return (None, "pulled at the close") if q is None else (q, None)


def tennis_books(path):
    con = ro(path)
    fd_rows = [(t_(c), e, t_(s), r, o) for c, e, s, r, o in con.execute(
        "SELECT collected_at, event_id, start_time, runner_name, odds FROM fd_tennis WHERE market_type = 'MATCH_BETTING'")]
    fd_runs = [t_(c) for (c,) in con.execute("SELECT DISTINCT collected_at FROM fd_tennis")]
    dk_rows = [(t_(c), f"{n}|{s}", t_(s), r, o) for c, n, s, r, o in con.execute(
        "SELECT collected_at, event_name, start_time, runner_name, odds FROM dk_tennis")]
    dk_runs = [t_(c) for (c,) in con.execute("SELECT DISTINCT collected_at FROM dk_tennis")]
    pin_rows, pin_runs = [], [t_(c) for (c,) in con.execute("SELECT ran_at FROM pin_runs")]
    for c, mid, s, p1, p2, des, price in con.execute(
            "SELECT collected_at, matchup_id, start_time, p1, p2, designation, price_dec FROM pin_tennis "
            "WHERE market_key = 's;0;m'"):
        pin_rows.append((t_(c), mid, t_(s), p1 if des == "home" else p2, price))
    return {"fd": ML(fd_rows, fd_runs), "dk": ML(dk_rows, dk_runs), "pin": ML(pin_rows, pin_runs)}


def tennis_bets(path):
    con = ro(path)
    out = []
    for logged, start, ev, pick, opp, odds, result, pnl in con.execute(
            "SELECT logged_at, start_time, event, pick, opp, odds, result, pnl FROM bets"):
        res = {"W": "win", "L": "loss"}.get(result, result)
        b = bet("tennis_ml", "forward", t_(logged), t_(start), ev, pick, "moneyline", "back", None, "fd", odds,
                result=res, profit=pnl if res in ("win", "loss") else None)
        b["opp"], b["t_price"] = opp, t_(logged)
        out.append(b)
    for logged, book, cap, start, ev, pick, opp, odds, result, pnl in con.execute(
            "SELECT logged_at, book, fd_captured_at, start_time, event, pick, opp, fd_odds, result, pnl FROM pin_bets"):
        res = {"W": "win", "L": "loss"}.get(result, result)
        b = bet("tennis_pin", "pinnacle_ref", t_(logged), t_(start), ev, pick, "moneyline", "back", None, book.lower(),
                odds, result=res, profit=pnl if res in ("win", "loss") else None)
        b["opp"], b["t_price"] = opp, t_(cap) or t_(logged)
        out.append(b)
    return out


def score_tennis(bets, books, any_age=False):
    for b in bets:
        bk = books[b["book"]]
        date = utc_date(b["start"])
        eid = bk.find(b["player"], b["opp"], b["start"])
        if eid is None:
            finish(b, date, True, "match not found in the book's log")
            continue
        b["start"] = bk.start[eid] or b["start"]
        b["date"] = date = utc_date(b["start"])
        if b["t"] >= b["start"]:
            finish(b, date, False, "logged after the start")
            continue
        finish(b, date, True)
        q, b["why"] = (bk.close_any if any_age else bk.close)(eid, b["player"], b["opp"])
        if q is None:
            continue
        b["clv"] = q * b["odds"] - 1
        q0 = bk.q_at(eid, b["player"], b["opp"], b["t_price"])
        if q0 is not None:
            b["null"], b["null_n"] = q0 * b["odds"] - 1, 1
            b["excess"] = b["clv"] - b["null"]
        pe = books["pin"].find(b["player"], b["opp"], b["start"])
        if pe is not None:
            qp, _ = books["pin"].close(pe, b["player"], b["opp"])
            b["clv2"] = None if qp is None else qp * b["odds"] - 1
    return bets


# ---- statistics -----------------------------------------------------------------------------------------------------
def boot(values, dates, reps=BOOT, seed=SEED):
    """(mean, lo, hi, one-sided p of mean <= 0) with dates resampled."""
    v, d = np.asarray(values, float), np.asarray(dates)
    ud, inv = np.unique(d, return_inverse=True)
    s, n = np.bincount(inv, weights=v), np.bincount(inv).astype(float)
    rng = np.random.default_rng(seed)
    pick = rng.integers(0, len(ud), size=(reps, len(ud)))
    m = s[pick].sum(1) / n[pick].sum(1)
    p = max(float(np.mean(m <= 0)), 1 / reps)
    return float(v.mean()), float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5)), p


def holm(ps):
    """Holm-adjusted p-values, same order as given."""
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    adj, run = [0.0] * len(ps), 0.0
    for r, i in enumerate(order):
        run = max(run, min(1.0, (len(ps) - r) * ps[i]))
        adj[i] = run
    return adj


def shrink(means, ses):
    """Empirical-Bayes normal-normal shrink toward the precision-weighted mean; tau^2 by the method of moments."""
    m, s2 = np.asarray(means, float), np.asarray(ses, float) ** 2
    if len(m) < 3:
        return list(m), 0.0
    w = 1 / s2
    mu = float(np.sum(w * m) / np.sum(w))
    tau2 = max(0.0, float(np.var(m, ddof=1) - np.mean(s2)))
    b = tau2 / (tau2 + s2)
    return [float(x) for x in b * m + (1 - b) * mu], tau2


def tier(s):
    """The pre-registered tier of a forward strategy summary."""
    n, nd = s["n"], s["dates"]
    if n < MIN_N or nd < MIN_DATES:
        return "Insufficient"
    c, e = s["clv"], s.get("excess")
    if c[2] < 0:
        return "Loses to the close"
    if e is None:                                   # no baseline: capped at Promising, judged on CLV itself
        return "Promising" if c[0] > 0 and c[1] > 0 else "No evidence"
    promising = c[0] > 0 and e[0] > 0 and e[1] > 0
    strong = (promising and s["level"] in ("A", "B") and n >= STRONG_N and nd >= STRONG_DATES and c[1] > 0
              and s.get("holm_p") is not None and s["holm_p"] < 0.05 and s["coverage"] >= COVER_MIN)
    return "Strong" if strong else "Promising" if promising else "No evidence"


def summarize(rows):
    """Eligible, CLV-scored, coverage, dates, CLV / excess / secondary CLV / ROI with date-clustered intervals."""
    el = [r for r in rows if r["eligible"]]
    sc = [r for r in el if r["clv"] is not None]
    out = {"bets": len(rows), "eligible": len(el), "n": len(sc), "coverage": len(sc) / len(el) if el else 0.0,
           "dates": len({r["date"] for r in sc}), "level": rows[0]["level"] if rows else None}
    why = defaultdict(int)
    for r in rows:
        if r["clv"] is None:
            why[r["why"] or "unscored"] += 1
    out["missing"] = dict(why)
    if sc:
        out["clv"] = boot([r["clv"] for r in sc], [r["date"] for r in sc])
        ex = [r for r in sc if r["excess"] is not None]
        if ex:
            out["excess"] = boot([r["excess"] for r in ex], [r["date"] for r in ex])
            out["null_mean"] = float(np.mean([r["null"] for r in ex]))
            out["excess_n"] = len(ex)
        c2 = [r for r in sc if r["clv2"] is not None]
        if c2:
            out["clv2"] = boot([r["clv2"] for r in c2], [r["date"] for r in c2])
            out["clv2_n"] = len(c2)
        out["beat_share"] = float(np.mean([r["clv"] > 0 for r in sc]))
        mv = [r["move"] for r in sc if r.get("move") is not None]
        if mv:
            out["move_mean"] = float(np.mean(mv))
    pr = [r for r in el if r["profit"] is not None]
    if pr:
        out["roi"] = boot([r["profit"] for r in pr], [r["date"] for r in pr])
        out["roi_n"] = len(pr)
    return out


def breakdowns(rows):
    out = {}
    for dim in ("book", "market", "side", "horizon"):
        cells = defaultdict(list)
        for r in rows:
            if r["eligible"] and r["clv"] is not None:
                cells[r.get(dim) or "?"].append(r)
        out[dim] = {k: {"n": len(v), "clv": float(np.mean([r["clv"] for r in v])),
                        "excess": (float(np.mean([r["excess"] for r in v if r["excess"] is not None]))
                                   if any(r["excess"] is not None for r in v) else None),
                        "dates": len({r["date"] for r in v})} for k, v in sorted(cells.items())}
    return out


# ---- the audit of existing calculations -----------------------------------------------------------------------------
def agree(a, b):
    """Rank correlation, mean difference, sign agreement and n over pairs where both exist."""
    pairs = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    if len(pairs) < 3:
        return {"n": len(pairs)}
    x, y = np.array(pairs, float).T
    return {"n": len(pairs), "spearman": float(stats.spearmanr(x, y)[0]), "mean_diff": float(np.mean(x - y)),
            "sign_agree": float(np.mean((x > 0) == (y > 0)))}


def audit_sxs(rows):
    el = [r for r in rows if r["system"] == "nba_sxs" and r["eligible"]]
    return {"definition": "sxs grade(): q_close x odds - 1; q from FanDuel's board at its last observation before tip "
                          "(no time window); the bet line's two-sided no-vig, else an over-only alt rung de-vigged at "
                          "the main rung's overround; otherwise missing. DraftKings bets scored on FanDuel's close.",
            "stored_vs_canonical_same_book": agree([r["src_clv"] for r in el], [r["clv"] for r in el]),
            "stored_vs_canonical_fanduel_close": agree([r["src_clv"] for r in el], [r["clv2"] for r in el]),
            "coverage_stored": float(np.mean([r["src_clv"] is not None for r in el])) if el else None,
            "coverage_canonical": float(np.mean([r["clv"] is not None for r in el])) if el else None,
            "n_eligible": len(el)}


def audit_nba_clv(rows):
    """nba_clv.py's beat-the-close on the same flags (its own close and dedupe), run on the backup copies."""
    import nba_clv as C
    C.SHADOW, C.LINES, C.NEWS = STORES["nba_shadow"], STORES["nba_lines"], STORES["nba_news"]
    got = {r["flag_id"]: r for r in C.collect()}
    mine = {r["src_id"]: r for r in rows if r["system"] == "nba_shadow" and r["strategy"].startswith("flags_")
            and r["strategy"] not in ("flags_carded", "flags_pinged") and r["eligible"]}
    keys = [k for k in mine if k in got]
    beat = [None if got[k].get("beat") is None else (1.0 if got[k]["beat"] else -1.0) for k in keys]
    fdb = [None if got[k].get("fd_beat") is None else (1.0 if got[k]["fd_beat"] else -1.0) for k in keys]
    return {"definition": "nba_clv.py: beat = the closing main line (best of FanDuel+DraftKings, the two-sided rung "
                          "whose best over is nearest 1.9091, board at tip from the change log) rose above the flagged "
                          "line, or stayed and its best over shortened; fd_beat = the same on FanDuel alone, flag time "
                          "vs tip (amendment 4 primary). Binary; no price value.",
            "beat_vs_canonical": agree(beat, [mine[k]["clv"] for k in keys]),
            "fd_beat_vs_canonical_fd": agree(fdb, [mine[k]["clv2"] for k in keys]),
            "move_vs_canonical": agree([got[k].get("move") for k in keys], [mine[k]["clv"] for k in keys]),
            "beat_rate": (float(np.mean([x > 0 for x in beat if x is not None])) if any(x is not None for x in beat)
                          else None),
            "canonical_beat_rate": float(np.mean([mine[k]["clv"] > 0 for k in keys if mine[k]["clv"] is not None])),
            "n_flags": len(keys)}


def level_d():
    """Stored CLV as stored, with its definition. Never tiered."""
    out = {}
    con = ro(STORES["bet_ledger"])
    rows = con.execute("SELECT sport, src, start_time, clv_pct FROM bets WHERE clv_pct IS NOT NULL").fetchall()
    cells = defaultdict(list)
    for sport, src, start, c in rows:
        cells[f"{sport}/{src}"].append((c / 100, utc_date(t_(start))))
    out["bet_ledger"] = {
        "definition": "bet_ledger.py: (closing_fair x odds_taken - 1); closing_fair = Pinnacle's de-vigged (Shin) "
                      "probability of the side at the bet line when the game starts. A different reference book "
                      "(Pinnacle) from the book bet.",
        "all": _stored(sum(cells.values(), [])), "cells": {k: _stored(v) for k, v in sorted(cells.items())},
        "rows": con.execute("SELECT COUNT(*), MIN(placed_at), MAX(placed_at) FROM bets").fetchone()}
    con = ro(STORES["wnba_clv"])
    rows = con.execute("SELECT date, tier, proj, flag_line, close_line, flag_over, close_over FROM clv "
                       "WHERE closed = 1 AND close_line IS NOT NULL AND flag_line IS NOT NULL").fetchall()
    cells = defaultdict(list)
    for d, tr, proj, fl, cl, fo, co in rows:
        sgn = 1 if (proj or fl) >= fl else -1
        cells[tr or "?"].append(((cl - fl) * sgn, d, cl == fl and fo and co and co < fo))
    out["wnba_clv"] = {
        "definition": "wnba_clv.py: line points the close moved toward the projection, (close_line - flag_line) x "
                      "sign(proj - flag_line); FanDuel main line; no price value and no de-vig.",
        "cells": {k: {"n": len(v), "mean_points": float(np.mean([x[0] for x in v])),
                      "share_moved_toward": float(np.mean([x[0] > 0 for x in v])),
                      "share_moved_away": float(np.mean([x[0] < 0 for x in v])),
                      "dates": len({x[1] for x in v})} for k, v in sorted(cells.items())}}
    con = ro(STORES["k_compass"])
    cells = {}
    for tbl in ("compass", "outs_compass", "opener_k", "route_a", "route_b", "ethan_k"):
        rows = con.execute(f"SELECT game_date, clv_dir, clv_pct FROM {tbl} WHERE clv_dir IS NOT NULL").fetchall()
        cells[tbl] = {"n": len(rows), "share_dir_up": float(np.mean([r[1] > 0 for r in rows])) if rows else None,
                      "n_pct": sum(r[2] is not None for r in rows),
                      "mean_pct": (float(np.mean([r[2] / 100 for r in rows if r[2] is not None]))
                                   if any(r[2] is not None for r in rows) else None)}
    out["k_live"] = {
        "definition": "k_live.py: per book, the last snapshot in a 10:00 to next-day 08:00 window (no first-pitch "
                      "cap, so it can be an in-game price); main = the two-sided rung whose over is nearest 1.9; the "
                      "best price across books for the side; clv_dir = line direction; clv_pct = odds / close odds - 1 "
                      "only when the line is unchanged.",
        "cells": cells}
    return out


def _stored(v):
    if not v:
        return {"n": 0}
    m = boot([x[0] for x in v], [x[1] for x in v])
    return {"n": len(v), "mean": m[0], "lo": m[1], "hi": m[2], "beat_share": float(np.mean([x[0] > 0 for x in v])),
            "dates": len({x[1] for x in v})}


# ---- provenance -----------------------------------------------------------------------------------------------------
def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def provenance():
    out = {}
    for k, p in STORES.items():
        st_ = p.stat()
        rec = {"path": str(p).replace(str(HOME), "~"), "bytes": st_.st_size,
               "mtime_utc": dt.datetime.fromtimestamp(st_.st_mtime, dt.timezone.utc).isoformat()}
        if k in LIVE:
            rec["read"] = f"in place, read-only connection, rows up to {iso(CUTOFF)}"
        else:
            rec["sha256"] = sha(p)
            wal = Path(str(p) + "-wal")
            if wal.exists() and wal.stat().st_size:
                rec["wal_sha256"] = sha(wal)
        out[k] = rec
    return out


# ---- main -----------------------------------------------------------------------------------------------------------
def run(stamp, out_dir):
    conv = convs()
    info, rows = {}, []
    # NBA
    nba = NBA(STORES["nba_lines"], conv)
    box = nba_box(STORES["nba_matchup"])
    sh, info["nba_shadow_dropped"] = shadow_bets(STORES["nba_shadow"])
    nb, info["nba_duplicates"] = dedupe(sxs_bets(STORES["nba_sxs"]) + sh)
    rows += score_nba(nb, nba, box, {})
    info["nba_snapshot_end"] = iso(nba.end)
    print("nba", len(nb), flush=True)
    # NCAAF (Mac store for P2 and totals, the VM copy for receiving-yards overs)
    props, totals, rec = ncaaf_bets(STORES["ncaaf_p2"], STORES["ncaaf_rec"])
    (props, d1), (totals, d2), (rec, d3) = dedupe(props), dedupe(totals), dedupe(rec)
    info["ncaaf_duplicates"] = d1 + d2 + d3
    lo = min(b["t"] for b in props + totals) - dt.timedelta(days=2)
    mac = Snap(STORES["ncaaf_fd_mac"], NCAAF_MARKETS)
    ev_mac = snap_events(mac, lo, "game_total")
    preload(mac, ev_mac, {et_date(b["start"]) for b in props + totals if b["start"]})
    cache = {}
    rows += score_snap(props, mac, ev_mac, cache) + score_snap(totals, mac, ev_mac, cache)
    vm = Snap(STORES["ncaaf_fd_vm"], ("player_reception_yds",))
    ev_vm = snap_events(vm, min(b["t"] for b in rec) - dt.timedelta(days=2), "player_reception_yds")
    preload(vm, ev_vm, {et_date(b["start"]) for b in rec if b["start"]})
    rows += score_snap(rec, vm, ev_vm, {})
    print("ncaaf", len(props), len(totals), len(rec), flush=True)
    # NFL alt tails
    nf, info["nfl_duplicates"] = dedupe(nfl_bets(STORES["nfl_v2"]))
    rows += score_nfl(nf, Snap(STORES["nfl_fd"], tuple(NFL_MARKET.values())), {})
    print("nfl", len(nf), flush=True)
    # golf
    gb, info["golf_duplicates"] = dedupe(golf_bets(STORES["golf_paper"], STORES["golf_moves"]))
    rows += score_golf(gb)
    # tennis
    books = tennis_books(STORES["tennis_fd"])
    tb, info["tennis_duplicates"] = dedupe(tennis_bets(STORES["tennis_ml"]))
    rows += score_tennis(tb, books)
    print("tennis/golf", len(tb), len(gb), flush=True)

    # summaries, Holm, tiers, shrinkage
    groups = defaultdict(list)
    for r in rows:
        groups[(r["system"], r["strategy"], r["phase"])].append(r)
    summ = {}
    for (sysm, strat, phase), rs in sorted(groups.items()):
        s = summarize(rs)
        s.update(system=sysm, strategy=strat, phase=phase, breakdown=breakdowns(rs))
        summ[f"{sysm}|{strat}|{phase}"] = s
    fam = [k for k, s in summ.items() if s["phase"] == "forward" and s["n"] >= MIN_N and s["dates"] >= MIN_DATES]
    ps = [summ[k]["excess"][3] if "excess" in summ[k] else summ[k]["clv"][3] for k in fam]
    for k, p in zip(fam, holm(ps)):
        summ[k]["holm_p"] = p
        summ[k]["holm_on"] = "excess" if "excess" in summ[k] else "clv (no baseline)"
    for k, s in summ.items():
        s["tier"] = tier(s) if s["phase"] == "forward" else "development (never evidence)"
    sh_keys = [k for k in fam if "excess" in summ[k]]
    if sh_keys:
        means = [summ[k]["excess"][0] for k in sh_keys]
        ses = [max((summ[k]["excess"][2] - summ[k]["excess"][1]) / 3.92, 1e-6) for k in sh_keys]
        shr, tau2 = shrink(means, ses)
        for k, v in zip(sh_keys, shr):
            summ[k]["excess_shrunk"] = v
        info["shrink_tau"] = math.sqrt(tau2)

    audits = {"nba_sxs": audit_sxs(rows), "nba_clv": audit_nba_clv(rows)}
    res = {"stamp": stamp, "cutoff": iso(CUTOFF), "prereg": "CLV_AUDIT_PREREG.md @ 7d2f5b2379", "info": info,
           "family_size": len(fam), "strategies": summ, "audit_existing": audits, "level_d": level_d(),
           "stores": provenance()}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"result.{stamp}.json").write_text(json.dumps(res, indent=1, default=str))
    cols = ["system", "strategy", "level", "phase", "t", "start", "date", "horizon", "game", "player", "market",
            "side", "line", "book", "odds", "eligible", "clv", "why", "clv2", "null", "null_n", "excess", "move",
            "result", "profit", "src_id", "src_clv", "note"]
    with open(out_dir / f"bets.{stamp}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in sorted(rows, key=lambda x: (x["system"], x["strategy"], x["t"])):
            w.writerow({k: (iso(v) if isinstance(v, dt.datetime) else v) for k, v in r.items()})
    write_tables(res, HERE / "CLV_AUDIT_TABLES.md")
    return res


def pct(x, d=1):
    return "n/a" if x is None else f"{x * 100:+.{d}f}%"


def ci(t):
    return "n/a" if t is None else f"{pct(t[0])} [{pct(t[1])}, {pct(t[2])}]"


def hp(p):
    return "" if p is None else f"{p:.3f}"


def write_tables(res, path):
    L = ["# CLV audit tables (generated by clv_audit.py; do not edit)", "",
         f"Cutoff {res['cutoff']}. Pre-registration {res['prereg']}. Holm family: {res['family_size']} forward "
         "strategies with 50+ CLV-scored bets on 5+ dates.", "",
         "## Every strategy", "",
         "| System | Strategy | Phase | Lvl | Eligible | Scored (cov.) | Dates | Mean CLV [95%] | Null | Excess [95%] | "
         "Holm p | 2nd CLV | ROI (info) | Tier |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    order = sorted(res["strategies"].values(), key=lambda s: (s["phase"] != "forward", s["system"], -s["n"]))
    for s in order:
        L.append(f"| {s['system']} | {s['strategy']} | {s['phase']} | {s['level']} | {s['eligible']} | "
                 f"{s['n']} ({s['coverage'] * 100:.0f}%) | {s['dates']} | {ci(s.get('clv'))} | "
                 f"{pct(s.get('null_mean'))} | {ci(s.get('excess'))} | "
                 f"{hp(s.get('holm_p'))} | "
                 f"{ci(s.get('clv2'))} | {ci(s.get('roi'))} | {s['tier']} |")
    L += ["", "## Why bets weren't scored", "", "| System | Strategy | Phase | Reasons |", "|---|---|---|---|"]
    for s in order:
        if s["missing"]:
            L.append(f"| {s['system']} | {s['strategy']} | {s['phase']} | "
                     + "; ".join(f"{k} {v}" for k, v in sorted(s["missing"].items(), key=lambda x: -x[1])) + " |")
    L += ["", "## Breakdowns (forward strategies with 50+ scored bets; never tiered)", ""]
    for s in order:
        if s["phase"] != "forward" or s["n"] < MIN_N:
            continue
        L.append(f"**{s['system']} / {s['strategy']}**")
        L.append("")
        L.append("| Cut | Cell | n | Dates | Mean CLV | Mean excess |")
        L.append("|---|---|---|---|---|---|")
        for dim, cells in s["breakdown"].items():
            for k, c in cells.items():
                L.append(f"| {dim} | {k} | {c['n']} | {c['dates']} | {pct(c['clv'])} | {pct(c['excess'])} |")
        L.append("")
    path.write_text("\n".join(L) + "\n")


def sens(stamp, out_dir):
    """Sensitivity reads, information only (never tiered): tennis closes read as change-only (the last stored price
    before the start at any age); NFL with every rung kept (the unit dedupes rungs of one player); NCAAF and NBA line
    moves of every eligible bet with a close, scored or not."""
    out = {}
    books = tennis_books(STORES["tennis_fd"])
    tb, _ = dedupe(tennis_bets(STORES["tennis_ml"]))
    rows = score_tennis(tb, books, any_age=True)
    for sysm in ("tennis_ml", "tennis_pin"):
        out[f"{sysm} change-only close"] = summarize([r for r in rows if r["system"] == sysm])
    nf = score_nfl(nfl_bets(STORES["nfl_v2"]), Snap(STORES["nfl_fd"], tuple(NFL_MARKET.values())), {})
    out["nfl_v2 every rung"] = summarize(nf)
    moves = defaultdict(list)
    with open(out_dir / f"bets.{stamp}.csv") as f:
        for r in csv.DictReader(f):
            if r["eligible"] == "True" and r["phase"] == "forward" and r["move"] not in ("", None):
                moves[f"{r['system']}|{r['strategy']}"].append((float(r["move"]), r["clv"] != ""))
    out["line moves"] = {k: {"n": len(v), "toward": float(np.mean([m > 0 for m, _ in v])),
                             "away": float(np.mean([m < 0 for m, _ in v])),
                             "unchanged": float(np.mean([m == 0 for m, _ in v])),
                             "mean_toward": float(np.mean([m for m, _ in v])),
                             "unscored_n": sum(not s_ for _, s_ in v)} for k, v in sorted(moves.items()) if len(v) >= 20}
    (out_dir / f"sens.{stamp}.json").write_text(json.dumps(out, indent=1, default=str))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stamp", default="20261104")
    ap.add_argument("--out", default=str(HERE / "audit/clv_audit"))
    ap.add_argument("--sens", action="store_true", help="only the sensitivity reads (after a full run)")
    a = ap.parse_args()
    if a.sens:
        for k, v in sens(a.stamp, Path(a.out)).items():
            print(k, {x: v[x] for x in ("n", "coverage", "dates", "clv", "excess") if x in v} if "n" in v and "clv" in v else v)
        return
    res = run(a.stamp, Path(a.out))
    for s in sorted(res["strategies"].values(), key=lambda s: (s["phase"] != "forward", s["system"], -s["n"])):
        if s["phase"] == "forward":
            print(f"{s['system']:12} {s['strategy']:28} n={s['n']:5} d={s['dates']:3} cov={s['coverage']:.2f} "
                  f"clv={ci(s.get('clv'))} ex={ci(s.get('excess'))} {s['tier']}")


if __name__ == "__main__":
    main()
