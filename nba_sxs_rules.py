"""The side-by-side rules (NBA_SXS_PREREG.md). A replay rule is a function of nba_replay.View only; a logged rule reads
its own live log. REGISTRY pins each rule's fingerprint and registration time: editing a rule (or the helpers and View
it reads) without registering it again fails test_nba_sxs, and a new registration restarts its forward record."""
from __future__ import annotations

import hashlib
import inspect
import json
import sys
import traceback

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


# ── AMENDMENT 3: the user's volume-to-line ratios (NBA_RATIO_PREREG.md) ───────────────────────────────────────
import nba_ratio as RATIO                                # noqa: E402

TRACKING_DB = RP.HERE / "nba_tracking.sqlite"
_RT = {}


def ratio_data(season):
    key = (str(MATCHUP_DB), str(TRACKING_DB), season)
    if key not in _RT:
        _RT.clear()
        _RT[key] = RATIO.RatioData(MATCHUP_DB, TRACKING_DB, season)
    return _RT[key]


RATIO_DEPS = (ratio_data, RATIO.RatioData, RATIO.ratio_eval, ROLE.season_of)


class _RatioOpen(Rule):
    """At a book's opener (first two-sided main), the over when this season's volume clears the rule's multiple of the line.
    Each rule carries its own spec (market, volume, multiple), so the fingerprint covers the threshold."""
    deps, spec = RATIO_DEPS, None

    def start_day(self, v):
        self.opened = set()

    def on_obs(self, v, book, seen):
        mk, out = self.spec[0], []
        for k in sorted(v.changed):
            g, p, m_, b = k
            if b != book or g not in seen or m_ != mk or k in self.opened:
                continue
            m = RP.main_of(v.board(*k))
            if not m:
                continue
            self.opened.add(k)
            if v.t <= RP.minus(v.games()[g]["tip"], 5) and RATIO.ratio_eval(ratio_data(ROLE.season_of(v.date)), self.spec, p, v.date, mk, m[0]):
                out.append(sig(g, p, mk, "over", m[0], b, m[1], note=self.name))
        return out


class RATIO_FGA(_RatioOpen):
    name, spec = "RATIO_FGA", RATIO.FORWARD["RATIO_FGA"]


class RATIO_PA(_RatioOpen):
    name, spec = "RATIO_PA", RATIO.FORWARD["RATIO_PA"]


class RATIO_RC(_RatioOpen):
    name, spec = "RATIO_RC", RATIO.FORWARD["RATIO_RC"]


_DV = {}


def dvp_data(season):
    key = (str(MATCHUP_DB), str(ROLE_GAMELOGS_DB), season)
    if key not in _DV:
        _DV.clear()
        _DV[key] = RATIO.DvpData(MATCHUP_DB, ROLE_GAMELOGS_DB, season)
    return _DV[key]


class PTS_DVP(Rule):
    """Amendment 5: at the opener, the points over when FGA >= the line, 20+ minutes, and the opponent gives his position
    group more points than the 2023-24 median (DvP > 1.0036, the opponent with >= 10 games)."""
    name, spec = "PTS_DVP", ("points", "fga", 1.0, 20.0, 1.0036)
    deps = RATIO_DEPS + (RATIO.DvpData, dvp_data)

    def start_day(self, v):
        self.opened = set()

    def on_obs(self, v, book, seen):
        mk, k, mpg, cut = self.spec[0], self.spec[2], self.spec[3], self.spec[4]
        out = []
        for key in sorted(v.changed):
            g, p, m_, b = key
            if b != book or g not in seen or m_ != mk or key in self.opened:
                continue
            m = RP.main_of(v.board(*key))
            if not m:
                continue
            self.opened.add(key)
            if v.t > RP.minus(v.games()[g]["tip"], 5):
                continue
            season = ROLE.season_of(v.date)
            vol = ratio_data(season).volume(p, v.date)
            if not vol or vol["fga"] < k * m[0] or vol["mpg"] < mpg:
                continue
            team, gm = v.team_of(p), v.games()[g]
            opp = gm["away"] if team == gm["home"] else gm["home"] if team == gm["away"] else None
            dv = dvp_data(season)
            d = dv.dvp(opp, dv.groups.get(p), v.date) if opp else None
            if d is not None and d > cut:
                out.append(sig(g, p, mk, "over", m[0], b, m[1], note=f"dvp={d:.3f}"))
        return out


class RATIO_PA28(_RatioOpen):
    """Amendment 4: potential assists >= 2.8x the assists line at the opener (in-sample threshold; pinged, SHADOW)."""
    name, spec = "RATIO_PA28", RATIO.FORWARD["RATIO_PA28"]


# ── AMENDMENT 6: the six ideas' forward rules (NBA_IDEAS_PREREG.md) ─────────────────────────────────────────────
import nba_ideas as IDEAS                                # noqa: E402

NEWS_DB = RP.HERE / "nba_news.sqlite"
_FD = {}


def foul_data(season):
    key = (str(MATCHUP_DB), season)
    if key not in _FD:
        _FD.clear()
        _FD[key] = IDEAS.FoulData(MATCHUP_DB, season)
    return _FD[key]


def cleared_returners(rd, vd, team, date, t, listed):
    """Absent rotation players not listed Out/Doubtful (and Active in the lineup when one is posted for the team)."""
    lu = vd.lineup(date, t).get(team)
    out = set()
    history = [b for _d, _g, b in rd.season.before(team, date)]
    seen = {p for b in history for p in b}
    for x in seen:
        if history and x in history[-1] and history[-1][x]["min"]:
            continue                                     # played the team's last game: not returning
        st = listed.get(x, (None, None))[1]
        if st in RP.OUTS or (lu and x not in lu["active"]):
            continue
        out.add(x)
    return out


IDEA_DEPS = (role_data, ROLE.RoleData, ROLE.Season, volume_data, VolumeData, IDEAS.return_bets, IDEAS._returning,
             cleared_returners, foul_data, IDEAS.FoulData, IDEAS.foul_bet, IDEAS.restricted, ROLE.season_of)


class RETURN_UNDER(Rule):
    """Idea 4: at tip - 30, a rotation player who missed >= 2 straight games is cleared -> unders on the teammates whose
    minutes rose >= 4 while he was out (points, rebounds, assists, PRA at FanDuel's main)."""
    name, deps = "RETURN_UNDER", IDEA_DEPS

    def start_day(self, v):
        self.listed = {}

    def on_report(self, v, t, rows, prev, seen_before):
        for team, pid, st in rows:
            self.listed[pid] = (team, st)
        return ()

    def on_tick(self, v, gid, minutes):
        if minutes != 30:
            return ()
        rd, vd, g, out = role_data(ROLE.season_of(v.date)), volume_data(), v.games()[gid], []
        for team in (g["home"], g["away"]):
            boards = {p for p, mk in v.props(gid, "fd") if v.team_of(p) == team}
            history = [{p: r["min"] for p, r in b.items() if r["min"]} for _d, _g, b in rd.season.before(team, v.date)]
            cleared = cleared_returners(rd, vd, team, v.date, v.t, self.listed)
            for b in sorted(IDEAS.return_bets(history, cleared, boards)):
                out += side_bets(v, gid, b, "under", note="teammate returns")
        return out


class FOUL_BIG(Rule):
    """Idea 2: at tip - 30, an F/C fouling >= 4.5 per 36 vs a team drawing > 23.5 FTA a game -> points and rebounds unders."""
    name, deps = "FOUL_BIG", IDEA_DEPS

    def on_tick(self, v, gid, minutes):
        if minutes != 30:
            return ()
        season = ROLE.season_of(v.date)
        fd, dv, vd, g, out = foul_data(season), dvp_data(season), volume_data(), v.games()[gid], []
        for p in sorted({p for p, mk in v.props(gid, "fd")}):
            team = v.team_of(p)
            opp = g["away"] if team == g["home"] else g["home"] if team == g["away"] else None
            if IDEAS.foul_bet(fd, dv.groups.get(p) or vd.group(p), p, opp, v.date):
                for mk in ("points", "rebounds"):
                    m = RP.main_of(v.board(gid, p, mk, "fd"))
                    if m and m[2]:
                        out.append(sig(gid, p, mk, "under", m[0], "fd", m[2], note="foul-prone big"))
        return out


class MIN_RESTRICT(Rule):
    """Idea 5: an X/Bluesky item says he is on a minutes restriction -> at FanDuel's next look (within 15 min), unders in
    points, rebounds, assists and PRA."""
    name, deps, window = "MIN_RESTRICT", IDEA_DEPS, 15

    def start_day(self, v):
        n = PD._ro(NEWS_DB)
        self.items = sorted((RP.iso(at), int(pid)) for at, pid, h, b in (n.execute(
            "SELECT detected_at, pid, headline, body FROM news_items WHERE game_date = ? AND pid IS NOT NULL", (v.date,))
            if n is not None and n.execute("SELECT 1 FROM sqlite_master WHERE name = 'news_items'").fetchone() else ())
            if IDEAS.restricted(f"{h} {b}"))
        self.done = set()

    def on_obs(self, v, book, seen):
        if book != "fd":
            return ()
        out, games = [], v.games()
        for at, pid in self.items:
            if at > v.t or pid in self.done or RP.minus(v.t, self.window) > at:
                continue
            g = next((g_ for g_ in seen if g_ in games and any(p == pid for p, _mk in v.props(g_, "fd"))), None)
            if g is None or v.t > RP.minus(games[g]["tip"], 5):
                continue
            self.done.add(pid)
            out += side_bets(v, g, pid, "under", note="minutes restriction")
        return out


# ── AMENDMENT 7: EARLY_SURGE (NBA_EARLY_PREREG.md) ─────────────────────────────────────────────────────────────
import nba_early as EARLY                                # noqa: E402

_ED = {}


def early_data(season):
    key = (str(MATCHUP_DB), str(ROLE_GAMELOGS_DB), season)
    if key not in _ED:
        _ED.clear()
        _ED[key] = EARLY.EarlyData(MATCHUP_DB, ROLE_GAMELOGS_DB, season)
    return _ED[key]


class EARLY_SURGE(Rule):
    """In a player's games 2-5, at the points opener: the over when his FGA/g is >= 1.2x last season's, he plays 20+ minutes,
    and his FGA/g is >= 0.8x the line (the books' lines lag a new role early in the season)."""
    name, deps, spec = "EARLY_SURGE", (early_data, EARLY.EarlyData, EARLY.early_surge, ROLE.season_of), (1.2, 20.0, 0.8, 1, 4)

    def start_day(self, v):
        self.opened = set()

    def on_obs(self, v, book, seen):
        out = []
        for k in sorted(v.changed):
            g, p, mk, b = k
            if b != book or g not in seen or mk != "points" or k in self.opened:
                continue
            m = RP.main_of(v.board(*k))
            if not m:
                continue
            self.opened.add(k)
            if v.t <= RP.minus(v.games()[g]["tip"], 5) and EARLY.early_surge(early_data(ROLE.season_of(v.date)), p, v.date, m[0]):
                out.append(sig(g, p, mk, "over", m[0], b, m[1], note="early volume surge"))
        return out


# ── AMENDMENT 9: BOOST and BOOST_NH (NBA_BOOST_PREREG.md) ──────────────────────────────────────────────────────
import nba_boost as BOOST_M                               # noqa: E402

_BD = {}


def boost_data(season):
    key = (str(MATCHUP_DB), str(ROLE_GAMELOGS_DB), season)
    if key not in _BD:
        _BD.clear()
        _BD[key] = BOOST_M.live_data(MATCHUP_DB, ROLE_GAMELOGS_DB, season)
    return _BD[key]


BOOST_DEPS = (boost_data, role_data, BOOST_M.live_data, BOOST_M.BoostData, BOOST_M.boost_eval, BOOST_M.step_eval,
              BOOST_M.pickup_eval, BOOST_M.step_minutes, BOOST_M.minutes_features, BOOST_M.v3_minutes, BOOST_M.rates,
              BOOST_M.Trees, BOOST_M.rank, BOOST_M.kind_of, BOOST_M.stat_of, BOOST_M.group, BOOST_M.posted_fives,
              ROLE.season_of) + ROLE_DEPS
BOOST_SPEC = [BOOST_M.STARTER_MIN, BOOST_M.BASE_THIS, BOOST_M.BASE_LAST, BOOST_M.SPOT_MAX, BOOST_M.MIN_H,
              BOOST_M.MIN_H_IRRELEVANT, BOOST_M.HIT_AT, BOOST_M.MIN_AVG_MIN, BOOST_M.PROJ_AT, BOOST_M.BASE_N,
              BOOST_M.BASE_MIN_GAMES, BOOST_M.SAME_W, BOOST_M.PRICE_MIN, BOOST_M.TOP, BOOST_M.PARTS, BOOST_M.USUAL_GAMES,
              BOOST_M.USUAL_MIN, BOOST_M.STEP_K, BOOST_M.STEP_STARTS, BOOST_M.K_RATE, BOOST_M.PICK_SPLIT,
              BOOST_M.MIN_FEATURES, BOOST_M.STEP_FLOOR]
if BOOST_M.TREES_B.exists():                             # the fitted bench-pickup model is part of BOOST_PICKUP
    BOOST_SPEC.append(hashlib.sha256(BOOST_M.TREES_B.read_bytes()).hexdigest()[:16])


class BOOST(Rule):
    """A usual starter out, absence game 1-3: at a book's opener, a teammate's over (-150 or better) when 80%+ of his
    past games without that starter but with tonight's other starters beat the line (3+ games, 6+ when the starter's
    own numbers make him irrelevant to the market; 20+ minutes on average)."""
    name, deps, spec, flag_kind = "BOOST", BOOST_DEPS, BOOST_SPEC, "history"

    def start_day(self, v):
        self.listed, self.opened, self.step_seen = {}, {}, set()   # pid -> (team, status); key -> opened at; (pid, book)

    def on_report(self, v, t, rows, prev, seen_before):
        for team, pid, st in rows:
            self.listed[pid] = (team, st)
        return ()

    def judge(self, bd, date, team, p, mk, m, out_now, five):
        """This rule's flag for one prop, or None (NBA_BOOST_PREREG.md amendments 1-6)."""
        if self.flag_kind in ("history", "no history"):
            f = BOOST_M.boost_eval(bd, date, team, p, mk, m[0], m[1], out_now)
            return f if f and BOOST_M.kind_of(f) == self.flag_kind else None
        rd = role_data(ROLE.season_of(date))
        if self.flag_kind == "step":
            return BOOST_M.step_eval(bd, rd, date, team, p, mk, m[0], m[1], out_now, five)
        return BOOST_M.pickup_eval(bd, rd, date, team, p, mk, m[0], m[1], out_now, five)

    def on_obs(self, v, book, seen):
        out, bd = [], None
        at, fives = BOOST_M.posted_fives(LINEUPS_DB, v.date, v.t)   # amendment 4: NBA.com's lineup as of t
        for k in sorted(v.changed):
            g, p, mk, b = k
            if b != book or g not in seen or mk not in BOOST_M.PARTS or k in self.opened:
                continue
            m = RP.main_of(v.board(*k))
            if not m:
                continue
            self.opened[k] = v.t                         # the opener: the first observation with a two-sided main
            if v.t > RP.minus(v.games()[g]["tip"], 5):
                continue
            bd = bd or boost_data(ROLE.season_of(v.date))
            team = bd.team_now(p, v.date)
            out_now = {x for x, (tm, st) in self.listed.items() if tm == team and st in RP.OUTS}
            if not team or not out_now:
                continue
            f = self.judge(bd, v.date, team, p, mk, m, out_now, fives.get(team))
            if f:
                why = f"{f['hits']}/{f['h']}" if f["kind"] == "history" else f"proj={f['proj']:.1f} min={f.get('proj_min', 0):.1f}"
                out.append(sig(g, p, mk, "over", m[0], b, m[1], note=f"x={f['x']} n={f['n']} {why}"))
        if self.flag_kind in ("step", "pickup") and fives:   # amendment 4: at this book's next look after NBA.com's
            bd = bd or boost_data(ROLE.season_of(v.date))   # lineup, the new starter's (or pickup's) earlier props
            for team, five in sorted(fives.items()):
                g = v.game_of(team)
                if bd.usual_five(team, v.date) is None or g not in seen or v.t > RP.minus(v.games()[g]["tip"], 5):
                    continue
                out_now = {x for x, (tm, st) in self.listed.items() if tm == team and st in RP.OUTS}
                tfive, pairs = bd.tonight(team, v.date, out_now, five)
                who = sorted(pairs) if self.flag_kind == "step" else \
                    sorted({pk[0] for s_ in pairs if (pk := bd.pickup(team, v.date, s_, tfive, out_now))})
                for p in who:
                    if (p, book) in self.step_seen:
                        continue
                    self.step_seen.add((p, book))
                    for p2, mk in sorted(v.props(g, book)):
                        k = (g, p, mk, book)
                        m = RP.main_of(v.board(*k)) if p2 == p and mk in BOOST_M.PARTS and self.opened.get(k, at) < at else None
                        f = m and self.judge(bd, v.date, team, p, mk, m, out_now, five)
                        if f:
                            out.append(sig(g, p, mk, "over", m[0], book, m[1], note=f"x={f['x']} n={f['n']} lineup"))
        return out


class BOOST_STEP(BOOST):
    """The new starter for an out usual starter: his minutes from the MINUTES blend (his last 10 starts and ROLE1 v3)
    x his rates, 15%+ over the line (NBA_BOOST_PREREG.md amendment 6). Pinged."""
    name, flag_kind = "BOOST_STEP", "step"


class BOOST_PICKUP(BOOST):
    """The bench pickup for that new starter, once NBA.com's lineup is posted: the fitted minutes model x his rates,
    15%+ over the line (amendment 6). Silent."""
    name, flag_kind = "BOOST_PICKUP", "pickup"


class BOOST_NH(BOOST):
    """BOOST's no-history flags (fewer than 3 such games): the position rules alone put him 15%+ over the line."""
    name, flag_kind = "BOOST_NH", "no history"


# ── AMENDMENT 10: UNDER20 and UNDERML (NBA_UNDER_PREREG.md) ────────────────────────────────────────────────────────
import nba_under as UNDER_M                               # noqa: E402

UNDER_DEPS = (boost_data, role_data, UNDER_M.projection, UNDER_M.under20, UNDER_M.features, UNDER_M.predict,
              UNDER_M.underml, UNDER_M.eligible, UNDER_M.pings, UNDER_M.strong, BOOST_M.v3_minutes, BOOST_M.rates, BOOST_M.live_data, BOOST_M.BoostData, ROLE.season_of) + ROLE_DEPS
UNDER_SPEC = [UNDER_M.RATIO_AT, UNDER_M.EV_AT, list(UNDER_M.FEATURES), UNDER_M.PING_PRICE_MIN, list(UNDER_M.PING_SKIP), UNDER_M.STRONG_AT, UNDER_M.PING_FLOOR]
if UNDER_M.MODEL_PY.exists():                            # the fitted model is part of UNDERML
    UNDER_SPEC.append(hashlib.sha256(UNDER_M.MODEL_PY.read_bytes()).hexdigest()[:16])


class UNDER20(Rule):
    """At tip - 30, FanDuel's main: the under when our projection (ROLE1 v3 minutes x his rates) is under 80% of the line."""
    name, deps, spec = "UNDER20", UNDER_DEPS, UNDER_SPEC

    def start_day(self, v):
        self.listed = {}

    def on_report(self, v, t, rows, prev, seen_before):
        for team, pid, st in rows:
            self.listed[pid] = (team, st)
        return ()

    def judge(self, bd, rd, date, team, p, mk, m, out_now):
        return UNDER_M.under20(bd, rd, date, team, p, mk, m[0], m[2], out_now)

    def on_tick(self, v, gid, minutes):
        if minutes != 30:
            return ()
        season = ROLE.season_of(v.date)
        bd, rd, out = boost_data(season), role_data(season), []
        for p, mk in sorted(set(v.props(gid, "fd"))):
            m = RP.main_of(v.board(gid, p, mk, "fd")) if mk in BOOST_M.PARTS else None
            team = bd.team_now(p, v.date) if m else None
            if not team:
                continue
            out_now = {x for x, (tm, st) in self.listed.items() if tm == team and st in RP.OUTS}
            f = self.judge(bd, rd, v.date, team, p, mk, m, out_now)
            if f:
                out.append(sig(gid, p, mk, f["side"], m[0], "fd", f["price"],
                               note=f"proj={f['proj']:.1f}" if "proj" in f else f"p={f['p']:.3f}"))
        return out


class UNDER20P(UNDER20):
    """UNDER20's pinged subset (NBA_UNDER_PREREG.md amendment 1): the under priced -150 or better, not threes."""
    name = "UNDER20P"

    def judge(self, bd, rd, date, team, p, mk, m, out_now):
        f = UNDER_M.under20(bd, rd, date, team, p, mk, m[0], m[2], out_now)
        return f if f and UNDER_M.eligible(f, mk) else None


class UNDER30P(UNDER20):
    """UNDER20P's flags under 70% of the line, the starred pings (NBA_UNDER_PREREG.md amendment 3)."""
    name = "UNDER30P"

    def judge(self, bd, rd, date, team, p, mk, m, out_now):
        f = UNDER_M.under20(bd, rd, date, team, p, mk, m[0], m[2], out_now)
        return f if f and UNDER_M.eligible(f, mk) and UNDER_M.strong(f) else None


class UNDER3050(UNDER20):
    """UNDER20's pinged flags (NBA_UNDER_PREREG.md amendment 4): eligible and 30-50% below the line."""
    name = "UNDER3050"

    def judge(self, bd, rd, date, team, p, mk, m, out_now):
        f = UNDER_M.under20(bd, rd, date, team, p, mk, m[0], m[2], out_now)
        return f if f and UNDER_M.pings(f, mk) else None


class UNDER3050L(UNDER20):
    """The pings from NBA_UNDER_PREREG.md amendment 9: UNDER3050 less the flags whose line is 6-42% over his last-5
    average."""
    name = "UNDER3050L"
    deps, spec = UNDER_DEPS + (UNDER_M.last5_ratio, UNDER_M.pings_l5), UNDER_SPEC + [list(UNDER_M.L5_ZONE)]

    def judge(self, bd, rd, date, team, p, mk, m, out_now):
        f = UNDER_M.under20(bd, rd, date, team, p, mk, m[0], m[2], out_now)
        return f if f and UNDER_M.pings_l5(f, mk, UNDER_M.last5_ratio(bd, p, date, mk, m[0])) else None


class UNDER3050L_E60(UNDER3050L):
    """NBA_UNDER_PREREG.md amendment 10: UNDER3050L judged at FanDuel's first observation at or after tip - k minutes
    (and before tip - k + 30), not at the tip - 30 tick: flagging earlier. Silent."""
    name, early = "UNDER3050L_E60", 60
    deps = UNDER3050L.deps + (RP.minus,)

    def start_day(self, v):
        super().start_day(v)
        self.done = set()

    def on_obs(self, v, book, seen):
        if book != "fd":
            return ()
        out, games = [], v.games()
        for gid in sorted(seen):
            g = games.get(gid)
            if g and gid not in self.done and RP.minus(g["tip"], self.early) <= v.t < RP.minus(g["tip"], self.early - 30):
                self.done.add(gid)
                out += UNDER20.on_tick(self, v, gid, 30)          # the board and report as of this observation
        return out

    def on_tick(self, v, gid, minutes):
        return ()


class UNDER3050L_E120(UNDER3050L_E60):
    name, early = "UNDER3050L_E120", 120


class UNDER3050L_E180(UNDER3050L_E60):
    name, early = "UNDER3050L_E180", 180


class UNDER3050L_E240(UNDER3050L_E60):
    name, early = "UNDER3050L_E240", 240


class UNDER3050L_E300(UNDER3050L_E60):
    name, early = "UNDER3050L_E300", 300


class UNDERML(UNDER20):
    """At tip - 30, FanDuel's main: T2's logistic model (no hindsight outs features, fit on 2023-24), either side at EV
    >= 5%. Silent."""
    name = "UNDERML"

    def judge(self, bd, rd, date, team, p, mk, m, out_now):
        return UNDER_M.underml(bd, rd, date, team, p, mk, m[0], m[1], m[2], out_now)


# ── AMENDMENT 11: Q15_LR10 and Q15_LR8 (NBA_Q15_LOG.md, TEST B) ─────────────────────────────────────────────────────
import nba_q15 as Q15_Q                                   # noqa: E402
import nba_q15_live as Q15                                # noqa: E402
import nba_q15_model as Q15_M                             # noqa: E402

_Q15 = {}


def q15_candidates(bd, v, gid, team):
    """Everyone who might play for the team tonight: anyone in its earlier games still on it, and anyone with a
    FanDuel or DraftKings prop in the game whose last team it is."""
    have = {p for bk in ("fd", "dk") for p, _mk in v.props(gid, bk) if bd.team_now(p, v.date) == team}
    return set(bd.on_team_tonight(team, v.date)) | have


def q15_night(v, season, bd):
    """nba_q15_live.Night for the date: box scores before it (this season and last, nba_matchup), every candidate in
    the date's games. Built at the day's first tip - 30, when every earlier game is final; later finals are today's.
    None when there are no box scores."""
    if v.date not in _Q15:
        _Q15.clear()
        b, t = Q15.box_from_matchup(MATCHUP_DB, (season, BOOST_M.PREV.get(season, "")), v.date)
        cands = [(p, team, opp, gid) for gid, g in sorted(v.games().items())
                 for team, opp in ((g["home"], g["away"]), (g["away"], g["home"])) for p in sorted(q15_candidates(bd, v, gid, team))]
        _Q15[v.date] = Q15.Night(b, t, v.date, cands, season) if b is not None and len(b) else None
    return _Q15[v.date]


Q15_DEPS = (q15_candidates, q15_night, boost_data, role_data, UNDER_M.projection, BOOST_M.v3_minutes, BOOST_M.rates,
            BOOST_M.live_data, BOOST_M.BoostData, ROLE.season_of, Q15.box_from_matchup, Q15.Night, Q15.placeholders,
            Q15.props_frame, Q15.score, Q15.picks, Q15_M.with_engine, Q15_M.fd_dk_market, Q15_M.under_bets,
            Q15_M.predict, Q15_Q.features, Q15_Q.player_features, Q15_Q.team_features, Q15_Q.team_totals, Q15_Q.team_league,
            Q15_Q.with_allowed, Q15_Q.vacated, Q15_Q.bets, Q15_Q.price_at, Q15_Q.grade, Q15_Q.logit) + ROLE_DEPS
Q15_SPEC = [Q15_M.MIN_AT, list(Q15_Q.PARTS), Q15_Q.RATE_K, Q15_Q.ROT_MIN, list(Q15.BOX_COLS),
            hashlib.sha256((RP.HERE / "nba_q15_lr_model.py").read_bytes()).hexdigest()[:16]]


class Q15_LR10(UNDER20):
    """At tip - 30: the frozen Q15_LR model (NBA_Q15_LOG.md TEST B) on FanDuel's and DraftKings' main lines; the under
    at EV >= 10%, 12+ projected minutes, at the better of the two books at FanDuel's main line (else DraftKings').
    Tonight's absences from the injury report. Silent."""
    name, tau, deps = "Q15_LR10", 0.10, Q15_DEPS
    spec = Q15_SPEC + [0.10]

    def start_day(self, v):
        super().start_day(v)
        _Q15.clear()

    def on_tick(self, v, gid, minutes):
        if minutes != 30:
            return ()
        try:
            return self.judge_game(v, gid)
        except Exception:                                 # amendment 11: a failure skips the game, never the other rules
            traceback.print_exc()
            print(f"{self.name}: {v.date} {gid} skipped", file=sys.stderr)
            return ()

    def judge_game(self, v, gid):
        season = ROLE.season_of(v.date)
        bd, rd = boost_data(season), role_data(season)
        g = v.games()[gid]
        night = q15_night(v, season, bd)
        if night is None:
            return ()
        outs = {tm: {x for x, (t2, st) in self.listed.items() if t2 == tm and st in RP.OUTS} for tm in (g["home"], g["away"])}
        key = ("scored", gid, v.t, frozenset(outs[g["home"]]), frozenset(outs[g["away"]]))
        if key not in _Q15:                               # Q15_LR10 and Q15_LR8 score the same game at the same moment
            players = [(p, team, opp, gid) for team, opp in ((g["home"], g["away"]), (g["away"], g["home"]))
                       for p in sorted(q15_candidates(bd, v, gid, team) - outs[team])]
            pf = night.frame(players)
            props, proj = [], {}
            for p, mk in sorted(set(v.props(gid, "fd")) | set(v.props(gid, "dk"))):
                if p not in pf or mk not in Q15_Q.PARTS:
                    continue
                pr = UNDER_M.projection(bd, rd, p, pf[p]["team"], v.date, outs[pf[p]["team"]], mk)
                if pr:
                    proj[(v.date, p, mk)] = (pr[1], pr[0])
                props.append((p, mk, RP.main_of(v.board(gid, p, mk, "fd")), RP.main_of(v.board(gid, p, mk, "dk"))))
            _Q15[key] = Q15.score(Q15.props_frame(pf, props, {gid: g["home"]}, v.date), proj)
        d, prob = _Q15[key]
        return [sig(gid, p, mk, "under", ln, bk, price, note=f"p_under={pu:.3f} ev={ev:.3f}")
                for p, mk, ln, bk, price, pu, ev in Q15.picks(d, prob, self.tau)]


class Q15_LR8(Q15_LR10):
    """Q15_LR10 at EV >= 8% (NBA_Q15_LOG.md TEST A slot 4). Silent."""
    name, tau = "Q15_LR8", 0.08
    spec = Q15_SPEC + [0.08]


# Amendment 8: the stores of box scores and tracking that the replay hands the rules as of each moment
# (nba_replay.RuleStores). ROLE_GAMELOGS_DB holds past seasons only. Not part of any fingerprint: no rule changes.
PIT_STORES = {"MATCHUP_DB": "matchup", "TRACKING_DB": "tracking"}

RULES = (NULL_TIP30, NEWS_FD, NEWS_DK, DK_LAGS_FD, T4_TIP30, ENGINE_CARD, S1, DEPTH_NEXT, DEPTH_NEXT_TIP30, NEW_STARTER,
         LOST_START, ROLE_OPEN, RATIO_FGA, RATIO_PA, RATIO_RC, RATIO_PA28, PTS_DVP, RETURN_UNDER, FOUL_BIG, MIN_RESTRICT, EARLY_SURGE,
         BOOST, BOOST_STEP, BOOST_PICKUP, BOOST_NH, UNDER20, UNDER20P, UNDER30P, UNDER3050, UNDER3050L, UNDER3050L_E60, UNDER3050L_E120,
         UNDER3050L_E180, UNDER3050L_E240, UNDER3050L_E300, UNDERML, Q15_LR10, Q15_LR8)


def fingerprint(cls):
    """A hash of the rule's source (with its bases here), the shared helpers and constants, and the View it reads."""
    parts = [inspect.getsource(c) for c in cls.__mro__ if c is not object and c.__module__ == __name__]
    parts += [inspect.getsource(f) for f in (newly_out, teammates, fd_vs_dk, sig)] + [inspect.getsource(RP.View)]
    parts += [inspect.getsource(f) for f in getattr(cls, "deps", ())]
    if getattr(cls, "spec", None) is not None:           # a rule's own threshold, wherever it is defined
        parts.append(json.dumps(cls.spec))
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
    "ROLE_OPEN": ("2026-10-27T13:00:00", "fce63818bc"),           # amendment 2 (NBA_ROLE1_PREREG.md)
    "RATIO_FGA": ("2026-10-27T13:00:00", "7931edb259"),           # amendment 3 (NBA_RATIO_PREREG.md)
    "RATIO_PA": ("2026-10-27T13:00:00", "738f3b6032"),
    "EARLY_SURGE": ("2026-10-27T13:00:00", "4fe0ca2d33"),         # amendment 7 (NBA_EARLY_PREREG.md)
    "RETURN_UNDER": ("2026-10-27T13:00:00", "c099fdf615"),        # amendment 6 (NBA_IDEAS_PREREG.md)
    "FOUL_BIG": ("2026-10-27T13:00:00", "08df997f93"),
    "MIN_RESTRICT": ("2026-10-27T13:00:00", "4ee15c815c"),
    "PTS_DVP": ("2026-10-27T13:00:00", "fc8387835f"),             # amendment 5
    "RATIO_PA28": ("2026-10-27T13:00:00", "2404e38806"),          # amendment 4
    "RATIO_RC": ("2026-10-27T13:00:00", "17e2e5ea3f"),
    "BOOST": ("2026-10-28T23:00:00", "ba59b8228e"),               # amendment 9 (NBA_BOOST_PREREG.md amendments 2-7)
    "BOOST_STEP": ("2026-10-28T23:00:00", "5ed40c5557"),
    "BOOST_PICKUP": ("2026-10-28T23:00:00", "4356b2332b"),
    "BOOST_NH": ("2026-10-28T23:00:00", "8c7915ffdb"),
    "UNDER20": ("2026-10-29T00:00:00", "e2e43773b0"),             # amendment 10 (NBA_UNDER_PREREG.md)
    "UNDER20P": ("2026-10-29T00:00:00", "352fb78046"),            # -150 or better, not threes (amendment 1)
    "UNDER30P": ("2026-10-29T00:00:00", "231aeea8d3"),            # ... and 30%+ below (amendment 3)
    "UNDER3050": ("2026-10-29T00:00:00", "7ec3b3d6b7"),           # ... and 30-50% below: the pings (amendment 4)
    "UNDER3050L": ("2026-10-29T07:00:00", "4fdf132a53"),          # ... less line 6-42% over his last 5: the pings (amendment 9)
    "UNDER3050L_E60": ("2026-10-29T22:30:00", "e76088b673"),      # UNDER3050L judged at tip - 60 ... tip - 300 (amendment 10)
    "UNDER3050L_E120": ("2026-10-29T22:30:00", "ac25356b54"),
    "UNDER3050L_E180": ("2026-10-29T22:30:00", "b9a1fb53f8"),
    "UNDER3050L_E240": ("2026-10-29T22:30:00", "1328805737"),
    "UNDER3050L_E300": ("2026-10-29T22:30:00", "3382790997"),
    "UNDERML": ("2026-10-29T00:00:00", "420fd8c7cf"),
    "Q15_LR10": ("2026-10-31T16:00:00", "b8f3015b9e"),            # NBA_Q15 TEST B: the frozen Q15_LR model (amendment 11)
    "Q15_LR8": ("2026-10-31T16:00:00", "890b018e3c"),
}
