"""The side-by-side rules (NBA_SXS_PREREG.md). A replay rule is a function of nba_replay.View only; a logged rule reads
its own live log. REGISTRY pins each rule's fingerprint and registration time: editing a rule (or the helpers and View
it reads) without registering it again fails test_nba_sxs, and a new registration restarts its forward record."""
from __future__ import annotations

import hashlib
import inspect
import json

import nba_proj_data as PD
import nba_replay as RP
import nba_research as R

REG_MIN, REG_APPS = 20.0, 3
NEWS_MARKETS = ("points", "rebounds", "assists", "pra")
NULL_MARKETS = ("points", "rebounds", "assists")
FLAG_MARKET = {"pts": "points", "reb": "rebounds", "ast": "assists", "fg3m": "threes"}


class Rule:
    name, kind = None, "replay"

    def start_day(self, v):
        pass

    def on_obs(self, v, book, seen):
        return ()

    def on_report(self, v, t, rows, prev, seen_before):
        return ()

    def on_tick(self, v, gid, minutes):
        return ()


def sig(gid, pid, market, side, line, book, odds, note=""):
    return {"gid": gid, "pid": pid, "market": market, "side": side, "line": line, "book": book, "odds": odds, "note": note}


def newly_out(v, t, rows, seen_before, prev):
    """[(x, team, gid)]: regulars newly Out/Doubtful on this report (their team on an earlier report today, they were
    not Out/Doubtful on it), for a game at least 30 minutes after the report."""
    out = []
    for team, pid, st in rows:
        if st not in RP.OUTS or team not in seen_before or prev.get(pid) in RP.OUTS:
            continue
        mn, n = v.last10_min(pid)
        if n < REG_APPS or mn < REG_MIN or v.team_of(pid) != team:
            continue
        g = v.game_of(team)
        if g is not None and RP.minus(v.games()[g]["tip"], 30) >= t:
            out.append((pid, team, g))
    return out


def teammates(v, gid, team, x, book, markets):
    return [(p, mk) for p, mk in v.props(gid, book)
            if mk in markets and p != x and v.team_of(p) == team and v.status(p) not in RP.OUTS]


def fd_vs_dk(v, gid, pid, mk, edge, strict):
    """Signals at DraftKings wherever FanDuel is two-sided at a line and FanDuel's no-vig x DraftKings' price - 1 clears
    `edge` (>= edge, or > edge when strict)."""
    fd, dk, out = v.board(gid, pid, mk, "fd"), v.board(gid, pid, mk, "dk"), []
    for (ln, sd), fo in fd.items():
        fu = fd.get((ln, "under"))
        if sd != "over" or not fo or not fu:
            continue
        q = R.no_vig(fo, fu)
        for side, qs in (("over", q), ("under", 1 - q)):
            o = dk.get((ln, side))
            if o and (qs * o - 1 > edge if strict else qs * o - 1 >= edge):
                out.append(sig(gid, pid, mk, side, ln, "dk", o, note=f"ev_fd={qs * o - 1:.3f}"))
    return out


class NULL_TIP30(Rule):
    """Control: every FanDuel main-line over in points, rebounds and assists at tip - 30."""
    name = "NULL_TIP30"

    def on_tick(self, v, gid, minutes):
        if minutes != 30:
            return ()
        out = []
        for p, mk in v.props(gid, "fd"):
            m = RP.main_of(v.board(gid, p, mk, "fd")) if mk in NULL_MARKETS else None
            if m:
                out.append(sig(gid, p, mk, "over", m[0], "fd", m[1]))
        return out


class _News(Rule):
    """A regular newly Out/Doubtful: his teammates' main-line overs at the book's first observation after the report
    (within `window` minutes), only where that main line and over price are unchanged from before the report."""
    book, window = None, None

    def start_day(self, v):
        self.pending = []                                # (report time, gid, absent pid, {(pid, market): (line, over)})

    def on_report(self, v, t, rows, prev, seen_before):
        for x, team, g in newly_out(v, t, rows, seen_before, prev):
            before = {}
            for p, mk in teammates(v, g, team, x, self.book, NEWS_MARKETS):
                m = RP.main_of(v.board(g, p, mk, self.book))
                if m:
                    before[(p, mk)] = (m[0], m[1])
            if before:
                self.pending.append((t, g, x, before))
        return ()

    def on_obs(self, v, book, seen):
        if book != self.book:
            return ()
        out, keep = [], []
        for P, g, x, before in self.pending:
            if RP.minus(v.t, self.window) > P:
                continue                                 # no observation in the window: no signal
            if g not in seen:
                keep.append((P, g, x, before))
                continue
            for (p, mk), (line, over) in before.items():  # the first observation after the report, once
                m = RP.main_of(v.board(g, p, mk, self.book))
                if m and m[0] == line and m[1] == over:
                    out.append(sig(g, p, mk, "over", line, self.book, over, note=f"x={x}"))
        self.pending = keep
        return out


class NEWS_FD(_News):
    name, book, window = "NEWS_FD", "fd", 10


class NEWS_DK(_News):
    name, book, window = "NEWS_DK", "dk", 15


class DK_LAGS_FD(Rule):
    """At every FanDuel observation up to tip - 5: DraftKings' price against FanDuel's no-vig at the same line, EV >= 3%."""
    name, EDGE = "DK_LAGS_FD", 0.03

    def start_day(self, v):
        self.dirty = set()

    def _note(self, v):
        self.dirty |= {k[:3] for k in v.changed}

    def on_report(self, v, t, rows, prev, seen_before):
        self._note(v)
        return ()

    def on_tick(self, v, gid, minutes):
        self._note(v)
        return ()

    def on_obs(self, v, book, seen):
        self._note(v)
        if book != "fd":
            return ()
        games, out, left = v.games(), [], set()
        for g, p, mk in self.dirty:
            if g not in seen:
                left.add((g, p, mk))
            elif v.t <= RP.minus(games[g]["tip"], 5):
                out += fd_vs_dk(v, g, p, mk, self.EDGE, strict=False)
        self.dirty = left
        return out


class T4_TIP30(Rule):
    """T4 as registered (NBA_T4_LIVE_PREREG.md): the boards at tip - 30, DraftKings vs FanDuel's fair, EV > 2%."""
    name, EDGE = "T4_TIP30", 0.02

    def on_tick(self, v, gid, minutes):
        if minutes != 30:
            return ()
        return [s for p, mk in v.props(gid, "fd") for s in fd_vs_dk(v, gid, p, mk, self.EDGE, strict=True)]


class ENGINE_CARD(Rule):
    """Logged: the live flag engine's carded plays, the earliest carded row per play (a tip-card play at its decision)."""
    name, kind = "ENGINE_CARD", "logged"

    def logged(self, day, stores):
        sh = PD._ro(stores["shadow"])
        if sh is None or not day.games:
            return []
        marks = ",".join("?" * len(day.games))
        tip = {f: (at, ln, o) for f, at, ln, o in sh.execute("SELECT flag_id, decided_at, line, odds FROM tipcard WHERE card = 1")} \
            if sh.execute("SELECT 1 FROM sqlite_master WHERE name = 'tipcard'").fetchone() else {}
        out, seen = [], set()
        for fid, at, g, p, stat, line, odds, why in sh.execute(
                f"SELECT flag_id, logged_at, gid, pid, stat, line, odds, card_why FROM flags WHERE card = 1 AND void_reason IS NULL "
                f"AND gid IN ({marks}) ORDER BY logged_at", list(day.games)):
            mk = FLAG_MARKET.get(stat, stat)
            if (g, p, mk) in seen or mk not in PD.MARKET_PARTS or not p:
                continue
            seen.add((g, p, mk))
            if why == "TIP CARD" and fid in tip:
                at, line, odds = tip[fid]
            out.append(dict(sig(g, p, mk, "over", float(line), "best", float(odds), note=fid), t=RP.iso(at)))
        return out


class S1(Rule):
    """Logged: S1's news-window signals (NBA_S1_PREREG.md) at their observation time, line and over price."""
    name, kind = "S1", "logged"

    def logged(self, day, stores):
        lg = PD._ro(stores["proj_log"])
        if lg is None or not day.games or not lg.execute("SELECT 1 FROM sqlite_master WHERE name = 'news_signals'").fetchone():
            return []
        marks = ",".join("?" * len(day.games))
        out, seen = [], set()
        for obs, g, p, mk, line, over in lg.execute(f"SELECT observed_at, gid, pid, market, line, over FROM news_signals "
                                                    f"WHERE gid IN ({marks}) ORDER BY observed_at", list(day.games)):
            if (g, p, mk) not in seen:
                seen.add((g, p, mk))
                out.append(dict(sig(g, p, mk, "over", float(line), "fd", float(over)), t=RP.iso(obs)))
        return out


RULES = (NULL_TIP30, NEWS_FD, NEWS_DK, DK_LAGS_FD, T4_TIP30, ENGINE_CARD, S1)


def fingerprint(cls):
    """A hash of the rule's source (with its bases here), the shared helpers and constants, and the View it reads."""
    parts = [inspect.getsource(c) for c in cls.__mro__ if c is not object and c.__module__ == __name__]
    parts += [inspect.getsource(f) for f in (newly_out, teammates, fd_vs_dk, sig)] + [inspect.getsource(RP.View)]
    parts.append(json.dumps([REG_MIN, REG_APPS, NEWS_MARKETS, NULL_MARKETS, FLAG_MARKET, RP.OUTS, RP.TICKS], sort_keys=True))
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:10]


REGISTERED_AT = "2026-10-27T12:00:00"
REGISTRY = {                                             # name -> (registered at, UTC; fingerprint)
    "NULL_TIP30": (REGISTERED_AT, "145ab4d182"),
    "NEWS_FD": (REGISTERED_AT, "21cdeebfb8"),
    "NEWS_DK": (REGISTERED_AT, "083ae77732"),
    "DK_LAGS_FD": (REGISTERED_AT, "f257d04432"),
    "T4_TIP30": (REGISTERED_AT, "b57ce355df"),
    "ENGINE_CARD": (REGISTERED_AT, "ef893ad2bd"),
    "S1": (REGISTERED_AT, "063cde0069"),
}
