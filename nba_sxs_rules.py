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


# ── AMENDMENT 1: the volume rules ────────────────────────────────────────────────────────────────────────────
VOLUME_MARKETS = ("points", "rebounds", "assists", "pra")
LINEUPS_DB, MATCHUP_DB, INDEX_JSON = RP.HERE / "nba_lineups.sqlite", RP.HERE / "nba_matchup.sqlite", RP.HERE / "nba_player_index.json"


class VolumeData:
    """Point-in-time helpers the volume rules read: position groups, starts and appearances before a date, team
    schedules, and the lineup snapshot as of a moment."""

    def __init__(self, lineups_db, matchup_db, index_json):
        from collections import defaultdict
        self.pos = {}
        if index_json.exists():
            for pid, v in json.load(open(index_json))["players"].items():
                if len(v) > 2 and v[2]:
                    self.pos[int(pid)] = v[2][0]
        self.apps, self.team_days = defaultdict(list), defaultdict(set)    # pid -> [(date, started)]; team -> dates
        m = PD._ro(matchup_db)
        if m is not None:
            for d, h, a in m.execute("SELECT date, home, away FROM games"):
                self.team_days[h].add(d)
                self.team_days[a].add(d)
            for d, pid, st in m.execute("SELECT gm.date, p.pid, p.starter FROM player_games p JOIN games gm ON gm.gid = p.gid "
                                        "WHERE p.min > 0"):
                self.apps[pid].append((d, bool(st)))
        for v in self.apps.values():
            v.sort()
        self.lineups_db, self.snaps = lineups_db, {}     # date -> [(fetched_at, {team: {"starters", "active"}})], loaded per date

    def _snaps(self, date):
        import zlib
        if date not in self.snaps:
            self.snaps = {date: []}                      # one date in memory at a time
            lc = PD._ro(self.lineups_db)
            for f, body in (lc.execute("SELECT fetched_at, body FROM snaps WHERE date_et = ? ORDER BY fetched_at", (date,))
                            if lc is not None else ()):
                teams = {}
                for g in json.loads(zlib.decompress(body)).get("games", []):
                    for side in ("homeTeam", "awayTeam"):
                        t = g.get(side) or {}
                        ps = t.get("players") or []
                        teams[t.get("teamAbbreviation")] = {
                            "starters": {p["personId"] for p in ps if p.get("position") and p.get("lineupStatus") in ("Expected", "Confirmed")},
                            "active": {p["personId"] for p in ps if p.get("rosterStatus") == "Active"}}
                self.snaps[date].append((RP.iso(f), teams))
        return self.snaps[date]

    def group(self, pid):
        return self.pos.get(pid)

    def starts(self, pid, date):
        """(starts, appearances) over his last 10 appearances before the date."""
        a = [s for d, s in self.apps.get(pid, ()) if d < date][-10:]
        return sum(a), len(a)

    def recently_active(self, pid, team, date):
        last4 = sorted(d for d in self.team_days.get(team, ()) if d < date)[-4:]
        return bool(last4) and any(d in last4 for d, _s in self.apps.get(pid, ()))

    def lineup(self, date, t):
        """{team: {"starters", "active"}} from the latest snapshot fetched at or before t (or {})."""
        best = {}
        for f, teams in self._snaps(date):
            if f <= t:
                best = teams
        return best


_VD = {}


def volume_data():
    key = (str(LINEUPS_DB), str(MATCHUP_DB), str(INDEX_JSON))
    if key not in _VD:
        _VD.clear()
        _VD[key] = VolumeData(LINEUPS_DB, MATCHUP_DB, INDEX_JSON)
    return _VD[key]


def next_man(v, vd, gid, team, x, taken=()):
    """The next man up behind X: same position group, not Out/Doubtful, a FanDuel board, fewer last-10 minutes than
    X, the most of those (ties: the lower id)."""
    gx, (mx, _n) = vd.group(x), v.last10_min(x)
    if gx is None or mx is None:
        return None
    best = None
    for p in sorted({p for p, _mk in v.props(gid, "fd")}):
        if p == x or p in taken or v.team_of(p) != team or v.status(p) in RP.OUTS or vd.group(p) != gx:
            continue
        mp, _k = v.last10_min(p)
        if mp is not None and mp < mx and (best is None or mp > best[0]):
            best = (mp, p)
    return best[1] if best else None


def side_bets(v, gid, pid, side, note=""):
    out = []
    for mk in VOLUME_MARKETS:
        m = RP.main_of(v.board(gid, pid, mk, "fd"))
        if m and m[1 if side == "over" else 2]:
            out.append(sig(gid, pid, mk, side, m[0], "fd", m[1 if side == "over" else 2], note=note))
    return out


VOL_DEPS = (VolumeData, volume_data, next_man, side_bets)


class DEPTH_NEXT(Rule):
    """A regular newly Out/Doubtful: the next man up behind him, volume overs at FanDuel's first look after the report."""
    name, window, deps = "DEPTH_NEXT", 10, VOL_DEPS

    def start_day(self, v):
        self.pending = []

    def on_report(self, v, t, rows, prev, seen_before):
        self.pending += [(t, g, team, x) for x, team, g in newly_out(v, t, rows, seen_before, prev)]
        return ()

    def on_obs(self, v, book, seen):
        if book != "fd":
            return ()
        vd, out, keep = volume_data(), [], []
        for P, g, team, x in self.pending:
            if RP.minus(v.t, self.window) > P:
                continue
            if g not in seen:
                keep.append((P, g, team, x))
                continue
            b = next_man(v, vd, g, team, x)
            if b is not None:
                out += side_bets(v, g, b, "over", note=f"behind={x}")
        self.pending = keep
        return out


class DEPTH_NEXT_TIP30(Rule):
    """At tip - 30: each recently active regular listed Out/Doubtful -> the next man up behind him, volume overs."""
    name, deps = "DEPTH_NEXT_TIP30", VOL_DEPS

    def start_day(self, v):
        self.listed = {}                                 # pid -> (team, latest status)

    def on_report(self, v, t, rows, prev, seen_before):
        for team, pid, st in rows:
            self.listed[pid] = (team, st)
        return ()

    def on_tick(self, v, gid, minutes):
        if minutes != 30:
            return ()
        vd, g, out = volume_data(), v.games()[gid], []
        for team in (g["home"], g["away"]):
            xs = []
            for pid, (tm, st) in self.listed.items():
                if tm != team or st not in RP.OUTS or v.team_of(pid) != team:
                    continue
                mn, n = v.last10_min(pid)
                if n >= REG_APPS and mn >= REG_MIN and vd.recently_active(pid, team, v.date):
                    xs.append((-mn, pid))
            taken = {x for _m, x in xs}
            for _m, x in sorted(xs):
                b = next_man(v, vd, gid, team, x, taken)
                if b is not None:
                    taken.add(b)
                    out += side_bets(v, gid, b, "over", note=f"behind={x}")
        return out


class NEW_STARTER(Rule):
    """At tip - 30: a starter in tonight's lineup who started <= 30% of his last (up to) 10, with >= 3 appearances: overs."""
    name, deps = "NEW_STARTER", VOL_DEPS

    def on_tick(self, v, gid, minutes):
        if minutes != 30:
            return ()
        vd, g, out = volume_data(), v.games()[gid], []
        lu = vd.lineup(v.date, v.t)
        for team in (g["home"], g["away"]):
            e = lu.get(team)
            if not e or len(e["starters"]) != 5:
                continue
            for p in sorted(e["starters"]):
                st, n = vd.starts(p, v.date)
                if n >= 3 and st <= 0.3 * n:
                    out += side_bets(v, gid, p, "over", note=f"started {st}/{n}")
        return out


class LOST_START(Rule):
    """At tip - 30: a usual starter (>= 8 of his last 10) listed Active but not in tonight's starting five: volume unders."""
    name, deps = "LOST_START", VOL_DEPS

    def on_tick(self, v, gid, minutes):
        if minutes != 30:
            return ()
        vd, g, out = volume_data(), v.games()[gid], []
        lu = vd.lineup(v.date, v.t)
        for team in (g["home"], g["away"]):
            e = lu.get(team)
            if not e or len(e["starters"]) != 5:
                continue
            for p in sorted(e["active"] - e["starters"]):
                st, n = vd.starts(p, v.date)
                if st >= 8 and v.status(p) not in RP.OUTS:
                    out += side_bets(v, gid, p, "under", note=f"started {st}/{n}")
        return out


# ── AMENDMENT 2: ROLE_OPEN (NBA_ROLE1_PREREG.md) ─────────────────────────────────────────────────────────────
import nba_role as ROLE                                  # noqa: E402

ROLE_GAMELOGS_DB = RP.HERE / "nba_gamelogs.sqlite"
_RD = {}


def role_data(season):
    key = (str(MATCHUP_DB), str(ROLE_GAMELOGS_DB), season)
    if key not in _RD:
        _RD.clear()
        _RD[key] = ROLE.RoleData(MATCHUP_DB, ROLE_GAMELOGS_DB, season)
    return _RD[key]


ROLE_DEPS = (role_data, ROLE.RoleData, ROLE.role_eval, ROLE.project, ROLE.Season, ROLE.Priors, ROLE.ewma, ROLE.group,
             ROLE.p_over, ROLE.p_side, ROLE.calibrated, ROLE.logit, ROLE.season_of)


class ROLE_OPEN(Rule):
    """A book's opener for a player whose role is elevated (a rotation teammate out, absence game 1-3): the side whose
    calibrated EV (ROLE1 v2, beta 0.09) is >= 5%, at the opener's price."""
    name, deps = "ROLE_OPEN", ROLE_DEPS

    def start_day(self, v):
        self.listed, self.opened = {}, set()             # pid -> (team, latest status); keys already opened

    def on_report(self, v, t, rows, prev, seen_before):
        for team, pid, st in rows:
            self.listed[pid] = (team, st)
        return ()

    def on_obs(self, v, book, seen):
        out, rd = [], None
        for k in sorted(v.changed):
            g, p, mk, b = k
            if b != book or g not in seen or mk not in ROLE.MARKET_STAT or k in self.opened:
                continue
            m = RP.main_of(v.board(*k))
            if not m:
                continue
            self.opened.add(k)                           # the opener: the first observation with a two-sided main
            if v.t > RP.minus(v.games()[g]["tip"], 5):
                continue
            team = v.team_of(p)
            out_now = {x for x, (tm, st) in self.listed.items() if tm == team and st in RP.OUTS}
            if not team or not out_now:
                continue
            rd = rd or role_data(ROLE.season_of(v.date))
            for e in ROLE.role_eval(rd, v.date, team, p, mk, m[0], m[1], m[2], out_now):
                out.append(sig(g, p, mk, e["side"], m[0], b, e["price"], note=f"ev={e['ev']:.3f} mu={e['mu']:.1f}"))
        return out


RULES = (NULL_TIP30, NEWS_FD, NEWS_DK, DK_LAGS_FD, T4_TIP30, ENGINE_CARD, S1, DEPTH_NEXT, DEPTH_NEXT_TIP30, NEW_STARTER,
         LOST_START, ROLE_OPEN)


def fingerprint(cls):
    """A hash of the rule's source (with its bases here), the shared helpers and constants, and the View it reads."""
    parts = [inspect.getsource(c) for c in cls.__mro__ if c is not object and c.__module__ == __name__]
    parts += [inspect.getsource(f) for f in (newly_out, teammates, fd_vs_dk, sig)] + [inspect.getsource(RP.View)]
    parts += [inspect.getsource(f) for f in getattr(cls, "deps", ())]
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
    "DEPTH_NEXT": (REGISTERED_AT, "80c7346297"),                   # amendment 1 (the volume rules)
    "DEPTH_NEXT_TIP30": (REGISTERED_AT, "726d7f5e54"),
    "NEW_STARTER": (REGISTERED_AT, "5e5996fb1a"),
    "LOST_START": (REGISTERED_AT, "134f9fb1e9"),
    "ROLE_OPEN": ("2026-10-27T13:00:00", "c6b50c9d1a"),           # amendment 2 (NBA_ROLE1_PREREG.md)
}
