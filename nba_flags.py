"""NBA port · flag-time engine — injuries × (WOWY priors | cold-start) × live lines -> SHADOW.

  1. The OFFICIAL league injury report (nba_injury_report; every 15 min, game-dated, names
     resolved to person ids within the team's roster) -> who is Out TONIGHT. A trigger X is an
     Out in absence game 1 or 2 of the CURRENT season (the backtests pooled across the summer,
     which hid every October first-absence; see NBA_SPEED_PREREG.md) and carries the time the
     league first published that Out (`news_at`), so flag latency and CLV can be measured.
     nba_watch.py runs this pass the moment a report with a fresh Out publishes.
     ESPN is no longer read here: the WNBA dropped it for over-reporting Out (4 of 22 rows).
  2. Three beneficiary tiers (wowy and cold are disjoint; priced re-prices the wowy population):
       wowy — B has a with/without split vs X ON THIS TEAM (>= 2 games without, >= 3 with),
              computed live from `apps` with the margin test's formulas (amendment 7; it used to
              read nba_wowy.sqlite, frozen at last season's end).
              proj = rate × (base_min + d_min); bet OVER at proj - line >= MARGIN[stat].
       cold — B has NO such split. X's vacated minutes go to the [12, 32]-min rotation in
              proportion to minutes played (nba_coldstart.redistribute — the SAME function
              the real-line test ran); bet OVER at proj - line >= COLD_MARGIN.
       priced — the wowy population, decided the WNBA way: wnba_tonight.prop_edges prices
              every posted rung (elevated sample, minutes-honest rescale, hit rate shrunk toward
              the book, EV >= 0.10, the WNBA's guards), base rung only, then
              wnba_slip.current_selection. Sticky per team-game like the WNBA card: a play that
              enters stays, newcomers only fill an open slot that is P/R/A-disjoint.
  3. Freshest NBA main lines from nba_lines.sqlite (FanDuel + DraftKings, collected on the
     Mac by nba_lines.py), joined on person id; best over price across books.
  4. Pre-game only: the slate is games with status 1 (not started) on today's ET date.

⚠️ NOTHING HERE PLACES A BET. Both tiers failed on real lines on 2026-10-22:
   wowy — nba_margin_refit.py: at the shipped margins pts −2.58%, pra −1.96%, reb −2.55%,
          every CI crosses zero; the always-over null is −6.56%.
   cold — NBA_COLDSTART_PREREG.md, executed by nba_coldstart_realline.py: PRA>=5 KILL
          (−8.61% pooled, −18.19% second half), PTS>=5 THIN (n=33).
   priced — the WNBA pricing machinery (nba_pricing, the code NBA_PRICING_PREREG.md tested):
          KILL at the close, −3.46% pooled over 1,186 bets, CI [−8.80, +1.99]; beats the margin
          rule and the null, loses anyway; overconfident by 10-17 points of probability.
   So every flag goes to the SHADOW table nba_shadow.sqlite, graded by --grade, and only a
   tier listed in LIVE_TIERS may also write a PAPER bet to bet_ledger. Adding one requires a
   new pre-registered test that passes; see NBA_PORT_WHAT_TRANSFERS.md.

⚠️ MAC-ONLY. Slate, rosters and this season's box scores come from cdn.nba.com, which
   403s the Oracle VM even with browser impersonation (2026-10-22). On a host that cannot
   reach it this exits 2 with the reason, rather than printing "0 flags" — which is what it
   did, silently, through four stacked blind inputs before this rewrite.

    python nba_flags.py             # flag -> shadow (and paper, for LIVE_TIERS only)
    python nba_flags.py --dry-run   # print, write nothing
    python nba_flags.py --grade     # settle shadow rows from ESPN box scores
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sqlite3
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

import nba_coldstart as C
import nba_injury_report as I
import nba_news_watch as NW
import nba_pricing as P
import nba_rosters as R

HERE = Path(__file__).resolve().parent
WOWY = HERE / "nba_wowy.sqlite"
LINES_DB = HERE / "nba_lines.sqlite"       # written by nba_lines.py (Mac)
LEDGER = HERE / "bet_ledger.sqlite"
SHADOW = HERE / "nba_shadow.sqlite"
ET = ZoneInfo("America/New_York")

LIVE_TIERS = frozenset()               # tiers allowed to write PAPER bets. EMPTY — see above.
MAX_ABSENCE_GAME = 2                   # trigger only on absence game 1-2 (the tested cell)
HORIZONS = 2                           # flag tonight's games AND tomorrow's (h0, h1)
REPORT_MAX_AGE_MIN = 45                # an official report older than this is a blind input
STATS = ("pra", "pts", "reb")          # ast/fg3m gated off (48.5% Oct-Nov / 53.7%)
K_DMIN, K_MIN = 3.0, 60.0              # == nba_wowy / the margin test: shrink pseudo-games / -minutes
TRACKING = HERE / "nba_tracking.sqlite"  # amendment 9: rebound chances / potential assists per game
OPP_KEYS = {"rebounds": ("reb_chances",), "reb": ("reb_chances",), "assists": ("potential_ast",),
            "ast": ("potential_ast",), "pra": ("reb_chances", "potential_ast"),
            "pts_reb": ("reb_chances",), "pts_ast": ("potential_ast",),
            "reb_ast": ("reb_chances", "potential_ast")}
OPP_CONFIRM = 1.10
MARGIN = {"pra": 5.0, "pts": 3.0, "reb": 2.0}          # wowy tier (measured negative)
LEDGER_STAT = {"pra": "pra", "pts": "points", "reb": "rebounds"}   # fd_lines stat keys
# AMENDMENT 18: P/R/A production pools, for the card's "no shared component" rule (wowy/cold keys)
CARD_COMPONENTS = {"pts": frozenset("p"), "reb": frozenset("r"), "ast": frozenset("a"),
                   "pra": frozenset("pra"), "threes": frozenset("p"), "fg3m": frozenset("p")}
LINE_MAX_AGE_MIN = 90
# A book fed by a pushed SNAPSHOT (DraftKings on the VM, NBA_SPEED_PREREG.md amendment 4) refreshes
# only while its sender is awake, so 90 min would let a stale price into a flag. Its limit is the
# snapshot cadence plus slack. Books collected on this host keep LINE_MAX_AGE_MIN.
BOOK_MAX_AGE_MIN = {"dk": 12} if os.environ.get("NBA_DK_SNAPSHOT") else {}


def _fresh_books(con, now):
    """{book: latest collected_at} for books whose board is within that book's age limit."""
    out = {}
    for b, ts in con.execute("SELECT book, MAX(collected_at) FROM board GROUP BY book"):
        cut = (now - dt.timedelta(minutes=BOOK_MAX_AGE_MIN.get(b, LINE_MAX_AGE_MIN))
               ).replace(tzinfo=None).isoformat()
        if ts >= cut:
            out[b] = ts
    return out
STAR_MIN, ACTIVE_DAYS, MIN_PRIOR_APPS = 28.0, 12, 5    # == nba_wowy / the cold-start test
WOWY_STAR_MIN = 24.0    # AMENDMENT 16: wowy only; flags with X under STAR_MIN score in their own cell


SHADOW_DDL = """CREATE TABLE IF NOT EXISTS flags (
    flag_id TEXT PRIMARY KEY, logged_at TEXT, game_date TEXT, tier TEXT, team TEXT,
    x TEXT, b TEXT, stat TEXT, line REAL, odds REAL, proj REAL, margin REAL,
    gid TEXT, gtime TEXT, matchup TEXT, actual REAL, result TEXT, graded_at TEXT,
    ev REAL, pid INTEGER, news_at TEXT, stale INTEGER, horizon INTEGER, x_pid INTEGER,
    trigger_src TEXT, void_reason TEXT, d_min REAL, opp_cell TEXT, opp_ratio REAL, x_status TEXT,
    x_min REAL, card INTEGER)"""
COMBO = {"pts_reb": ("points", "rebounds"), "pts_ast": ("points", "assists"),
         "reb_ast": ("rebounds", "assists")}


def _shadow(path):
    """Open the shadow table, migrating a pre-`ev` table in place (idempotent)."""
    sh = sqlite3.connect(path)
    sh.execute(SHADOW_DDL)
    have = {r[1] for r in sh.execute("PRAGMA table_info(flags)")}
    for col, typ in (("ev", "REAL"), ("pid", "INTEGER"), ("news_at", "TEXT"),
                     ("stale", "INTEGER"), ("horizon", "INTEGER"), ("x_pid", "INTEGER"),
                     ("trigger_src", "TEXT"), ("void_reason", "TEXT"), ("d_min", "REAL"),
                     ("opp_cell", "TEXT"), ("opp_ratio", "REAL"), ("x_status", "TEXT"),
                     ("x_min", "REAL"), ("card", "INTEGER")):
        if col not in have:
            sh.execute(f"ALTER TABLE flags ADD COLUMN {col} {typ}")
    return sh


def fold(s):
    """ascii-fold + lower + strip punctuation — 'Kristaps Porziņģis' == 'Kristaps Porzingis'."""
    n = unicodedata.normalize("NFKD", s or "")
    n = "".join(c for c in n if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9 ]", "", n.lower()).split())



def slate(sched, today_et):
    """{tricode: (gid, utc, matchup)} for games on today's ET date that have NOT started."""
    games = {}
    for g in sched:
        if g["date_et"] != today_et or g["status"] != 1:
            continue
        mu = f"{g['away']} @ {g['home']}"
        for t in (g["home"], g["away"]):
            games[t] = (g["gid"], g["utc"], mu)
    return games


def latest_lines(now):
    """({(pid, stat): (line, best_over_dec, collected_at)}, status) from nba_lines.board.

    Every book's latest SUCCESSFUL board counts if it is no older than LINE_MAX_AGE_MIN, so
    FanDuel and DraftKings shop against each other even though they are fetched seconds apart
    (the old reader took MAX(collected_at) across all books, which would have kept ONE book).
    Joined on NBA person id, resolved by nba_lines within the game's two rosters — never on a
    name. Main line = the two-sided rung whose best over is nearest even money."""
    if not LINES_DB.exists():
        return {}, f"no {LINES_DB.name} — nba_lines.py has never run"
    con = sqlite3.connect(f"file:{LINES_DB}?mode=ro", uri=True)
    books = dict(con.execute("SELECT book, MAX(collected_at) FROM board GROUP BY book"))
    fresh = sorted(_fresh_books(con, now))
    if not fresh:
        con.close()
        return {}, ("nba_lines board is empty" if not books else
                    f"every book's board is older than {LINE_MAX_AGE_MIN} min {books}")
    rows = con.execute("SELECT pid, stat, line, side, odds, collected_at FROM board "
                       f"WHERE pid IS NOT NULL AND book IN ({','.join('?' * len(fresh))})",
                       fresh).fetchall()
    con.close()
    two = {}
    for pid, stat, line, side, odds, ts in rows:
        two.setdefault((pid, stat, line), {}).setdefault(side, []).append((odds, ts))
    out = {}
    for (pid, stat, line), sides in two.items():
        if "over" not in sides or "under" not in sides:      # milestone X+ rungs are over-only
            continue
        best_over, ts = max(sides["over"])
        cur = out.get((pid, stat))
        if cur is None or abs(best_over - 1.9091) < abs(cur[1] - 1.9091):
            out[(pid, stat)] = (line, best_over, ts)
    stale = sorted(set(books) - set(fresh))
    return out, ("ok" if not stale else f"stale book(s) excluded: {stale}")


def board_ladders(now):
    """{pid: {stat: {line: (best_over, best_under)}}} — every fresh two-sided rung, both books.
    The shape wnba_tonight.prop_edges reads from posted_props()."""
    if not LINES_DB.exists():
        return {}
    con = sqlite3.connect(f"file:{LINES_DB}?mode=ro", uri=True)
    fresh = sorted(_fresh_books(con, now))
    raw = defaultdict(lambda: [0.0, 0.0])
    if fresh:
        for pid, stat, line, side, odds in con.execute(
                "SELECT pid, stat, line, side, odds FROM board WHERE pid IS NOT NULL AND "
                f"book IN ({','.join('?' * len(fresh))})", fresh):
            i = 0 if side == "over" else 1 if side == "under" else None
            if i is not None:
                k = (pid, stat, round(float(line), 1))
                raw[k][i] = max(raw[k][i], float(odds))
    con.close()
    out = defaultdict(lambda: defaultdict(dict))
    for (pid, stat, line), (o, u) in raw.items():
        if o and u and stat in P.PROP_STATS:
            out[pid][stat][line] = (o, u)
    return out


def absence_index(last_app, team_game_dates, season, out_in_tonights_game=False):
    """Which absence tonight's/tomorrow's game is for X: 1 = first game missed.

    Counts the franchise's COMPLETED games after X's last appearance, plus tonight's not-yet-final
    game when the target is tomorrow and X is ruled Out for tonight too. Across the SEASON
    BOUNDARY (amendment 3): games missed at the end of last season are carried over only when
    they are a real streak (> MAX_ABSENCE_GAME). A star who rested the last 1-2 games of April
    starts October fresh (Mitchell 2026-10-22); a player out since February does not — the
    first version reset everyone, and on 2026-10-23 it called all 51 Outs fresh."""
    this = sum(1 for d in team_game_dates if d > last_app and C.season_of(d) == season)
    prev = sum(1 for d in team_game_dates if d > last_app and C.season_of(d) < season)
    carried = prev if prev > MAX_ABSENCE_GAME else 0
    return 1 + carried + this + (1 if out_in_tonights_game else 0)


def _team_apps(apps, pid, tri):
    """The player's appearances FOR THIS TEAM — the cold-start test's played_by was
    team-scoped, so the live rotation must be too, or forward shadow is not comparable."""
    return [a for a in apps.get(pid, []) if a[3] == tri]


def _mean_last10(ap):
    last = ap[-10:]
    return sum(a[1] for a in last) / len(last)


def split(apps, b_id, x_id, tri):
    """B's franchise games since X's first franchise game in the pool: (without X, with X).
    The backtest's out_g / in_g, team-scoped (nba_pricing_realline.walk)."""
    xa = _team_apps(apps, x_id, tri)
    if not xa:
        return [], []
    x_first, x_dates = xa[0][0], {a[0] for a in xa}
    since = [a for a in _team_apps(apps, b_id, tri) if a[0] >= x_first]
    return [a for a in since if a[0] not in x_dates], [a for a in since if a[0] in x_dates]


def load_tracking(pids):
    """{(date, pid): {reb_chances, potential_ast}} for these players, or None if there is no data."""
    if not pids or not TRACKING.exists():
        return None
    con = sqlite3.connect(f"file:{TRACKING}?mode=ro", uri=True)
    out = {(d, p): {"reb_chances": rc, "potential_ast": pa} for d, p, rc, pa in con.execute(
        f"SELECT date, player_id, reb_chances, potential_ast FROM tracking WHERE player_id IN "
        f"({','.join('?' * len(pids))})", sorted(pids))}
    con.close()
    return out


def opp_cell(trk, b_id, b_out, b_in, stat):
    """AMENDMENT 9: does B's role bump show up in OPPORTUNITIES (rebound chances / potential assists
    per game), not just in makes? (label, ratio). b_out / b_in are the split's PRIOR games."""
    keys = OPP_KEYS.get(stat)
    if not keys:
        return "n/a", None
    if trk is None:
        return "NO DATA", None

    def per_game(apps):
        # a game counts when it has a tracking row; a blank component is 0 — the Rebounding feed
        # OMITS players with no rebound chances (nba_tracking.verify: 96-100% zero-rebound games)
        return [sum(row.get(k) or 0.0 for k in keys)
                for row in (trk.get((a[0], b_id)) for a in apps) if row]
    vo, vi = per_game(b_out), per_game(b_in)
    if len(vo) < C.MIN_WOWY or len(vi) < 3 or sum(vi) <= 0:
        return "THIN", None
    ratio = (sum(vo) / len(vo)) / (sum(vi) / len(vi))
    return ("CONFIRMED" if ratio >= OPP_CONFIRM else "NOT CONFIRMED"), round(ratio, 3)


def wowy_live(apps, out_pid, cur_team, games, out_all, why):
    """wowy tier, computed LIVE (NBA_SPEED_PREREG.md amendment 7): the margin test's formulas on the
    same `apps` priced and cold use (400-day pool + this season's box scores). It replaced a lookup
    into nba_wowy.sqlite, frozen at 2026-04-12: Holiday projected on 31.4 min while playing 21 and 27."""
    cands = []
    for x_id, (xname, tri) in out_pid.items():
        if tri not in games:
            continue
        xa = _team_apps(apps, x_id, tri)
        if len(xa) < 10 or _mean_last10(xa) < WOWY_STAR_MIN:
            why["wowy_x_not_a_star_here"] += 1
            continue
        for b_id, t in cur_team.items():
            if t != tri or b_id == x_id or b_id in out_all:
                continue
            ba = _team_apps(apps, b_id, tri)
            if len(ba) < MIN_PRIOR_APPS:
                continue
            b_out, b_in = split(apps, b_id, x_id, tri)
            if len(b_out) < C.MIN_WOWY or len(b_in) < 3:
                continue
            b10 = ba[-10:]
            base_min = sum(a[1] for a in b10) / len(b10)
            m10 = sum(a[1] for a in b10)
            min_out = sum(a[1] for a in b_out)
            d_min = (min_out / len(b_out) - sum(a[1] for a in b_in) / len(b_in))
            d_min *= len(b_out) / (len(b_out) + K_DMIN)
            for stat in STATS:
                base_rate = sum(a[2][stat] for a in b10) / max(1e-9, m10)
                rate = (sum(a[2][stat] for a in b_out) + base_rate * K_MIN) / (min_out + K_MIN)
                cands.append(("wowy", tri, xname, b_id, stat, rate * (base_min + d_min),
                              MARGIN[stat], x_id, d_min))
    return cands


def void_pass(now=None):
    """⚠ VOID pings for pinged plays the board now retracts (nba_board's rule). Never raises."""
    try:
        import nba_board as BRD
        import nba_ping as PING
        sh = _shadow(SHADOW)
        for body, ok in PING.ping_voids(sh, BRD.board(now)["retracted"], now=now):
            print(f"  PING {'sent' if ok else 'NOT SENT'}: {body}")
        sh.close()
    except Exception as e:                                           # noqa: BLE001
        print(f"  !! void-ping error: {type(e).__name__}: {e}")


def amend6_reason(tier, team, x_pid, pid, pair_teams):
    """The amendment-6 void reason for a logged flag, or None. pair_teams: {(x_id, b_id): {team}}."""
    if tier != "wowy" or not x_pid or not pid:
        return None
    teams = pair_teams.get((x_pid, pid), set())
    if not teams or team in teams:
        return None
    return f"amend6: with/without split measured on another team ({'/'.join(sorted(teams))})"


def amend6(dry=False):
    """Apply amendment 6 to every logged flag (idempotent; never touches an already-void flag)."""
    con = sqlite3.connect(f"file:{WOWY}?mode=ro", uri=True)
    pair_teams = defaultdict(set)
    for x, b, t in con.execute("SELECT x_id, b_id, team FROM pairs"):
        pair_teams[(x, b)].add(t)
    con.close()
    sh = _shadow(SHADOW)
    hits = []
    for fid, tier, team, x_pid, pid, b, stat, line, gd in sh.execute(
            "SELECT flag_id, tier, team, x_pid, pid, b, stat, line, game_date FROM flags "
            "WHERE void_reason IS NULL"):
        why = amend6_reason(tier, team, x_pid, pid, pair_teams)
        if why:
            hits.append((fid, why, f"{gd} {b} {stat} o{line:g} ({team})"))
    for fid, why, desc in hits:
        print(f"  void {desc}: {why}")
        if not dry:
            sh.execute("UPDATE flags SET void_reason=? WHERE flag_id=? AND void_reason IS NULL", (why, fid))
    sh.commit()
    print(f"amendment 6: {len(hits)} flag(s) {'would be ' if dry else ''}voided")


def flags(dry=False, game_date=None):
    """One flag pass for the games on `game_date` (ET; default today). Completed-game data
    (appearances, rosters) is always as of NOW; everything about the game — slate, official
    report, absence count, flag ids, card slots — is keyed to game_date. `horizon` = days
    between now and the game: 0 = game day, 1 = a ruling for TOMORROW's game, flagged today
    (NBA_SPEED_PREREG.md, amendment 1: its own cell, never pooled into the primary test)."""
    now = dt.datetime.now(dt.timezone.utc)
    today_et = now.astimezone(ET).date().isoformat()
    gdate = game_date or today_et
    horizon = (dt.date.fromisoformat(gdate) - dt.date.fromisoformat(today_et)).days
    blind, why = [], Counter()

    try:
        sched = R.schedule()
        boxes, n_failed = R.season_boxes(sched)
    except R.Blind as e:
        print(f"nba flags: BLIND — cdn.nba.com unreachable from this host ({e}). "
              f"Slate, rosters and box scores are Mac-only; nothing evaluated.")
        sys.exit(2)
    if n_failed:
        blind.append(f"{n_failed} final box score(s) failed to fetch (retried next run)")
    games = slate(sched, gdate)
    try:
        index, inote = R.player_index(today_et)
    except R.Blind as e:
        print(f"nba flags: BLIND — no current rosters ({e}); nothing evaluated.")
        sys.exit(2)
    if inote:
        blind.append(inote)
    apps, cur_team, name = R.state(today_et, boxes, index=index)
    lines, lstat = latest_lines(now)
    if lstat != "ok":
        blind.append(lstat)

    # ── WHO IS OUT TONIGHT: the official league report, already resolved to person ids ──
    try:
        rep, rep_mark = I.current(gdate)
    except sqlite3.OperationalError:
        rep, rep_mark = {}, None
    if rep_mark is None:
        blind.append(f"no official injury report stored listing {gdate} (nba_injury_report.py)")
    else:
        age = (now - dt.datetime.fromisoformat(rep_mark).replace(tzinfo=ET)).total_seconds() / 60
        if age > REPORT_MAX_AGE_MIN:
            blind.append(f"newest official report is {age:.0f} min old (> {REPORT_MAX_AGE_MIN})")
    # out_all: everyone ruled Out tonight — never a beneficiary. out_pid: the TRIGGERS, i.e. an
    # Out in absence game <= 2 for this franchise, counted the way every backtest counted it.
    team_dates = defaultdict(set)
    for _p, _ap in apps.items():
        for _a in _ap:
            team_dates[_a[3]].add(_a[0])
    # AMENDMENT 15: "Out" here means ABSENT (Out or Doubtful); x_status keeps which, for its own cell.
    out_all = {pid for pid, v in rep.items() if v[2] in I.ABSENT}
    out_pid, news_at, x_status = {}, {}, {}
    # ⚠️ THE STREAK RESETS AT THE SEASON BOUNDARY. Counted across the summer, a star who rested
    # the last games of April reads as "absence game 3" in October's opener (Mitchell 2026-10-22:
    # last app 04-08, sat 04-10 and 04-12) — and every such first absence of the new season was
    # invisible as a trigger. The backtests carried that quirk (pooled franchise games); the
    # forward speed test (NBA_SPEED_PREREG.md) counts only THIS season's missed games.
    season = C.season_of(gdate)
    # For a FUTURE game, tonight's game is not in the box scores yet: if X is also ruled Out for
    # tonight and his team plays tonight, that is one more missed game before game_date.
    tonight_out, tonight_teams = set(), set()
    if horizon > 0:
        try:
            rt, _ = I.current(today_et)
        except sqlite3.OperationalError:
            rt = {}
        tonight_out = {pid for pid, v in rt.items() if v[2] in I.ABSENT}
        tonight_teams = {t for g in sched if g["date_et"] == today_et and g["status"] != 3
                         for t in (g["home"], g["away"])}
    for pid, (nm, tri, st, first) in rep.items():
        if st not in I.ABSENT:
            continue
        xa = _team_apps(apps, pid, tri)
        if xa and absence_index(xa[-1][0], team_dates[tri], season,
                                pid in tonight_out and tri in tonight_teams) > MAX_ABSENCE_GAME:
            why["x_absence_game_gt2"] += 1
            continue
        out_pid[pid] = (nm, tri)
        news_at[pid], x_status[pid] = first, st
    trig_src = {pid: "report" for pid in out_pid}
    # ── NEWS (amendment 2): add-only. An Out the report does not list yet is added; for one it
    # already lists, the EARLIER of the two times is the news time, credited to whoever was first.
    # news_outs() has already dropped any item a later official report contradicts.
    try:
        nws = NW.news_outs(gdate)
    except sqlite3.OperationalError:
        nws = {}
    _t = lambda iso: dt.datetime.fromisoformat(iso)
    for pid, (nm, tri, at, src, nst) in nws.items():
        if rep.get(pid, (None, None, None))[2] in I.ABSENT:
            if pid in news_at and _t(at) < _t(news_at[pid]):
                news_at[pid], trig_src[pid] = at, f"news:{src}"
            if pid in x_status and nst == "Out":
                x_status[pid] = "Out"                  # the strongest word at flag time
            continue
        out_all.add(pid)
        xa = _team_apps(apps, pid, tri)
        if xa and absence_index(xa[-1][0], team_dates[tri], season,
                                pid in tonight_out and tri in tonight_teams) > MAX_ABSENCE_GAME:
            why["x_absence_game_gt2"] += 1
            continue
        out_pid[pid], news_at[pid], trig_src[pid], x_status[pid] = (nm, tri), at, f"news:{src}", nst
        why["x_from_news"] += 1

    # AMENDMENT 16: every flag carries X's last-10 minutes for this franchise (the 24-28 cell).
    x_min = {}
    for _x, (_n, _t) in out_pid.items():
        _xa = _team_apps(apps, _x, _t)
        x_min[_x] = _mean_last10(_xa) if _xa else None
    # wowy: computed live (amendment 7). nba_wowy.sqlite is no longer read by the flag pass.
    cands = wowy_live(apps, out_pid, cur_team, games, out_all, why)

    # ── cold tier: exactly the pre-registered rule, through the shared function ──
    season = C.season_of(gdate)
    today = dt.date.fromisoformat(gdate)              # "active" is judged against the game date
    for x_id, (xname, tri) in out_pid.items():
        if tri not in games:
            why["no_game_today"] += 1
            continue
        xa = _team_apps(apps, x_id, tri)
        if len(xa) < 10 or _mean_last10(xa) < STAR_MIN:
            why["x_not_a_star_here"] += 1
            continue
        bm = {}
        for p, t in cur_team.items():
            if t != tri:
                continue
            pa = _team_apps(apps, p, tri)
            if (len(pa) >= MIN_PRIOR_APPS
                    and (today - dt.date.fromisoformat(pa[-1][0])).days <= ACTIVE_DAYS):
                bm[p] = _mean_last10(pa)
        for b_id, pmin in C.redistribute(bm, x_id, _mean_last10(xa)).items():
            # has a WOWY prior -> not cold-start: B played >= MIN_WOWY of X's missed games
            # (the cold-start registration's own rule, computed live; amendment 7)
            if b_id in out_all or len(split(apps, b_id, x_id, tri)[0]) >= C.MIN_WOWY:
                continue
            rate = C.per_min_rate(_team_apps(apps, b_id, tri), C.season_of, season)
            if not rate:
                continue
            for stat in STATS:
                cands.append(("cold", tri, xname, b_id, stat, rate[stat] * pmin, C.COLD_MARGIN,
                              x_id, None))

    # ── priced tier: the WNBA pricing machinery via nba_pricing (same code the test ran) ──
    ladders = board_ladders(now)
    pos = {pid: v[2] for pid, v in index.items()}
    priced_rows = []
    for x_id, (xname, tri) in out_pid.items():
        if tri not in games:
            continue
        xa = _team_apps(apps, x_id, tri)
        # SAME UNIVERSE AS THE TEST (NBA_PRICING_PREREG.md): X must be a >=28-min player with
        # >=10 apps for this franchise. Without it, live priced a 15-min Tomlin absence the
        # test never measured — forward shadow would grade a population the backtest did not.
        if len(xa) < 10 or _mean_last10(xa) < STAR_MIN:
            why["priced_x_not_a_star_here"] += 1
            continue
        x_first, x_dates = xa[0][0], {a[0]: a[1] for a in xa}
        for b_id, t in cur_team.items():
            if t != tri or b_id == x_id or b_id in out_all:
                continue
            ba = _team_apps(apps, b_id, tri)
            if len(ba) < MIN_PRIOR_APPS:
                continue
            since = [a for a in ba if a[0] >= x_first]
            mk = lambda a: P.row(a[1], a[2]["pts"], a[2]["reb"], a[2]["ast"], a[2]["fga"],
                                 a[2]["fta"], a[2]["fg3a"])
            b_out = [mk(a) for a in since if a[0] not in x_dates]
            b_in = [mk(a) for a in since if a[0] in x_dates]
            if len(b_out) < C.MIN_WOWY or len(b_in) < 3:
                continue
            lad = ladders.get(b_id)
            if not lad:
                why["priced_no_line"] += 1
                continue
            log = [dict(mk(a), date=a[0], game_id="", matchup="") for a in reversed(ba)]
            spots, _ = P.price(name.get(b_id, ""), log, P.wowy(b_in, b_out),
                               pos.get(b_id, ""), pos.get(x_id, ""), x_dates, lad)
            for sp in P.base_rung_overs(spots):
                priced_rows.append({"pred_date": gdate, "team": tri, "player": name.get(b_id),
                                    "stat": sp["stat"], "line": sp["line"], "side": "over",
                                    "ev": sp["ev"], "odds": sp["dec"], "d_min": sp.get("d_min"),
                                    "n_elev": sp["n"], "_x": xname, "_elev": sp["elev_avg"],
                                    "_pid": b_id, "_news": news_at.get(x_id), "_x_id": x_id,
                                    "_stale": int(bool(sp.get("stale")))})
    priced, _ = P.select(priced_rows) if priced_rows else ([], [])

    out_flags = []
    for r in priced:
        gid, gtime, mu = games[r["team"]]
        out_flags.append({"tier": "priced", "team": r["team"], "x": r["_x"], "b": r["player"],
                          "stat": r["stat"], "line": r["line"], "odds": r["odds"],
                          "proj": round(r["_elev"], 1), "margin": round(r["_elev"] - r["line"], 1),
                          "ev": round(r["ev"], 4), "gid": gid, "gtime": gtime, "matchup": mu,
                          "pid": r["_pid"], "news_at": r["_news"], "stale": r["_stale"],
                          "game_date": gdate, "horizon": horizon, "x_pid": r["_x_id"],
                          "trigger_src": trig_src.get(r["_x_id"]), "d_min": r.get("d_min"),
                          "x_status": x_status.get(r["_x_id"]), "x_min": x_min.get(r["_x_id"])})
    for tier, tri, xname, b_id, stat, proj, margin, x_id, d_min in cands:
        lk = lines.get((b_id, LEDGER_STAT[stat]))
        if not lk:
            why["no_line"] += 1
            continue
        line, odds, ts = lk
        if proj - line < margin:
            continue
        gid, gtime, mu = games[tri]
        out_flags.append({"tier": tier, "team": tri, "x": xname, "b": name.get(b_id),
                          "stat": stat, "line": line, "odds": odds, "proj": round(proj, 1),
                          "margin": round(proj - line, 1), "gid": gid, "gtime": gtime,
                          "matchup": mu, "pid": b_id, "news_at": news_at.get(x_id),
                          "game_date": gdate, "horizon": horizon, "x_pid": x_id,
                          "trigger_src": trig_src.get(x_id), "d_min": d_min,
                          "x_status": x_status.get(x_id), "x_min": x_min.get(x_id)})

    # AMENDMENT 9: OPPORTUNITY-CONFIRMED, at flag time, from the same prior split wowy uses
    trk = load_tracking({f["pid"] for f in out_flags if f.get("pid")})
    for f in out_flags:
        if f["tier"] in ("wowy", "priced") and f.get("pid") and f.get("x_pid"):
            b_out, b_in = split(apps, f["pid"], f["x_pid"], f["team"])
            f["opp_cell"], f["opp_ratio"] = opp_cell(trk, f["pid"], b_out, b_in, f["stat"])
        else:
            f["opp_cell"], f["opp_ratio"] = "n/a", None

    new_shadow = new_paper = 0
    inserted = []
    if not dry and out_flags:
        sh = _shadow(SHADOW)
        stamp = now.replace(microsecond=0, tzinfo=None).isoformat()
        new_shadow, inserted = _log_flags(sh, out_flags, stamp, why)
        # PINGS (user 2026-10-24: "0 latency"): one push per NEW play, in-process, right after the
        # commit; then a VOID for any pinged play whose premise died. Never breaks the pass.
        try:
            import nba_ping as PING
            for body, ok in PING.ping_plays(sh, inserted, now=now):
                print(f"  PING {'sent' if ok else 'NOT SENT'}: {body}")
        except Exception as e:                                       # noqa: BLE001
            print(f"  !! ping error: {type(e).__name__}: {e}")
        sh.close()
        paper = [f for f in out_flags if f["tier"] in LIVE_TIERS]
        if paper:
            import bet_ledger as BL
            led = sqlite3.connect(LEDGER)
            led.execute(BL.DDL)
            for f in paper:
                bid = f"nba|{fold(f['b'])}|{f['stat']}|{f['line']}|over|{f['game_date']}"
                if led.execute("SELECT 1 FROM bets WHERE bet_id=?", (bid,)).fetchone():
                    continue
                led.execute("INSERT INTO bets VALUES "
                            "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (bid, stamp, "nba", f["matchup"], f["b"], LEDGER_STAT[f["stat"]],
                             f["line"], "over", f["odds"], 1.0, None, None, f["line"],
                             f["tier"], f["gtime"], "open", None, None, None, None, None,
                             None))
                new_paper += 1
            led.commit()
            led.close()

    if not dry:
        void_pass(now)                         # every real pass, new flags or not
    for b in blind:
        print(f"  !! BLIND: {b}")
    for f in out_flags:
        print(f"  [NBA {f['tier']}] {f['b']} ({f['team']}) {f['stat'].upper()} O{f['line']:g} "
              f"@{f['odds']:.2f} · proj {f['proj']} (+{f['margin']})"
              + (f" · EV {f['ev']:+.2f}" if f.get("ev") is not None else "")
              + (f" · via {f['trigger_src']}" if (f.get("trigger_src") or "report") != "report" else "")
              + f" · {f['x']} OUT · {f['matchup']}")
    tiers = Counter(f["tier"] for f in out_flags)
    print(f"nba flags {gdate} (h{horizon}): report {rep_mark or 'NONE'} · {len(out_all)} Out, "
          f"{len(out_pid)} in absence game 1-2 · {len(games) // 2} "
          f"game(s) not yet started · lines: {lstat} · "
          f"candidates {Counter(c[0] for c in cands)} -> flags {dict(tiers)} · "
          f"shadow +{new_shadow} · paper +{new_paper} (live tiers: "
          f"{', '.join(sorted(LIVE_TIERS)) or 'none'})" + (" · DRY-RUN" if dry else ""))
    if why:
        print(f"  skipped: {dict(why)}")
    return out_flags


def _excess(f):
    """How far a wowy/cold flag clears its own threshold: (proj - line) / margin (amendment 18)."""
    thr = MARGIN.get(f["stat"]) if f["tier"] == "wowy" else C.COLD_MARGIN
    return (f.get("margin") or 0.0) / thr if thr else 0.0


CARD_ON = "COALESCE(card, 1) = 1 AND void_reason IS NULL"   # NULL = before amendment 18 = shown


def _card_rule(sh, gd, pid, team, tier, stat):
    """AMENDMENT 18, for a NEW wowy/cold play: 1 = on the card (pinged + shown), 0 = logged only.
    Off if the player already has a carded play that date (any tier), if the tier already has 2 carded
    plays in the team-game, or if it shares a P/R/A component with one of them."""
    if sh.execute(f"SELECT 1 FROM flags WHERE game_date=? AND pid=? AND {CARD_ON} LIMIT 1", (gd, pid)).fetchone():
        return 0
    mates = sh.execute(f"SELECT DISTINCT pid, stat FROM flags WHERE game_date=? AND team=? AND tier=? AND "
                       f"{CARD_ON}", (gd, team, tier)).fetchall()
    if len(mates) >= 2:
        return 0
    comp = CARD_COMPONENTS.get(stat, frozenset(stat))
    return 0 if any(comp & CARD_COMPONENTS.get(s, frozenset(s)) for _, s in mates) else 1


def _card(sh, f):
    """priced keeps its own selection (card 1). A re-flag of a known play (same date, player, stat,
    tier; any line) inherits that play's card value — sticky, never un-carded or re-pinged."""
    if f["tier"] == "priced":
        return 1
    prev = sh.execute("SELECT card FROM flags WHERE game_date=? AND pid=? AND stat=? AND tier=? AND "
                      "card IS NOT NULL ORDER BY logged_at LIMIT 1",
                      (f["game_date"], f.get("pid"), f["stat"], f["tier"])).fetchone()
    if prev:
        return prev[0]
    return _card_rule(sh, f["game_date"], f.get("pid"), f["team"], f["tier"], f["stat"])


def _log_flags(sh, out_flags, stamp, why):
    """Write one pass's flags to the shadow table; returns (new rows, the NEW CARDED flags to ping).
    AMENDMENT 18: priced first, then wowy/cold by excess, so the card takes the best play first."""
    new_shadow, inserted = 0, []
    order = sorted(out_flags, key=lambda f: (f["tier"] != "priced",
                                             0.0 if f["tier"] == "priced" else -_excess(f)))
    for f in order:
        fid = f"{f['tier']}|{fold(f['b'])}|{f['stat']}|{f['line']}|{f['game_date']}"
        if f["tier"] == "priced" and not _priced_slot_open(sh, f["game_date"], f, fid):
            why["priced_slot_taken"] += 1
            continue
        card = _card(sh, f)
        cur = sh.execute("INSERT OR IGNORE INTO flags (flag_id, logged_at, game_date, tier, "
                         "team, x, b, stat, line, odds, proj, margin, gid, gtime, matchup, ev, "
                         "pid, news_at, stale, horizon, x_pid, trigger_src, d_min, opp_cell, opp_ratio, x_status, x_min, "
                         "card) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (fid, stamp, f["game_date"], f["tier"], f["team"], f["x"], f["b"],
                          f["stat"], f["line"], f["odds"], f["proj"], f["margin"],
                          f["gid"], f["gtime"], f["matchup"], f.get("ev"), f.get("pid"),
                          f.get("news_at"), f.get("stale"), f["horizon"], f.get("x_pid"),
                          f.get("trigger_src"), f.get("d_min"), f.get("opp_cell"),
                          f.get("opp_ratio"), f.get("x_status"), f.get("x_min"), card))
        new_shadow += cur.rowcount
        if cur.rowcount and not card:
            why["card_off_logged_only"] += 1
        if cur.rowcount and card:
            inserted.append(dict(f, flag_id=fid))
    sh.commit()
    return new_shadow, inserted


def card_backfill(game_dates, path=None):
    """One-off (amendment 18): card values for flags logged before the card existed, by the same rule,
    play by play in logged order then excess. priced rows -> 1. Pings already sent are not recalled."""
    sh = _shadow(path or SHADOW)
    marks = ",".join("?" * len(game_dates))
    sh.execute(f"UPDATE flags SET card=1 WHERE card IS NULL AND tier='priced' AND game_date IN ({marks})",
               tuple(game_dates))
    rows = sh.execute(f"SELECT game_date, pid, team, tier, stat, MIN(logged_at), MAX(margin) FROM flags "
                      f"WHERE card IS NULL AND void_reason IS NULL AND tier IN ('wowy','cold') AND "
                      f"game_date IN ({marks}) GROUP BY game_date, pid, team, tier, stat", tuple(game_dates)).fetchall()
    sh.execute(f"UPDATE flags SET card=0 WHERE card IS NULL AND tier IN ('wowy','cold') AND game_date IN ({marks})",
               tuple(game_dates))
    plays = sorted(rows, key=lambda r: (r[5], -_excess({"tier": r[3], "stat": r[4], "margin": r[6]})))
    out = []
    for gd, pid, team, tier, stat, _at, _m in plays:
        v = _card_rule(sh, gd, pid, team, tier, stat)
        sh.execute("UPDATE flags SET card=? WHERE game_date=? AND pid=? AND tier=? AND stat=? AND card=0",
                   (v, gd, pid, tier, stat))
        out.append((gd, pid, team, tier, stat, v))
    sh.commit()
    sh.close()
    return out


def _priced_slot_open(sh, game_date, f, fid):
    """The WNBA card's sticky rule, applied across 10-minute cycles: a priced play that has
    entered the shadow for this team-game STAYS; a newcomer gets a slot only while fewer than 2
    are taken AND its P/R/A components are disjoint from the incumbent's. Without this, every
    play that was ever top-2 in some cycle would be counted — more than a card can hold."""
    import wnba_tonight as T
    inc = sh.execute("SELECT flag_id, stat FROM flags WHERE tier='priced' AND game_date=? AND "
                     "team=?", (game_date, f["team"])).fetchall()
    if any(i == fid for i, _ in inc):
        return True                                  # already in: INSERT OR IGNORE no-ops
    if len(inc) >= 2:
        return False
    comps = T._STAT_COMPONENTS
    return all(not (comps[f["stat"]] & comps[s]) for _, s in inc)


def _settle(b, stat, gtime):
    """Realized value; combos are summed from their components."""
    import bet_ledger as BL
    key = LEDGER_STAT.get(stat, stat)
    if key in COMBO:
        parts = [BL.settle_nba(b, k, gtime) for k in COMBO[key]]
        return None if any(v is None for v in parts) else sum(parts)
    return BL.settle_nba(b, key, gtime)


def grade():
    """Settle shadow rows for past dates from ESPN box scores (bet_ledger.settle_nba).
    A row whose player is not found stays ungraded and is retried — never a void."""
    if not SHADOW.exists():
        print("nba shadow: no table yet")
        return
    today_et = dt.datetime.now(dt.timezone.utc).astimezone(ET).date().isoformat()
    sh = _shadow(SHADOW)
    todo = sh.execute("SELECT flag_id, b, stat, line, gtime FROM flags "
                      "WHERE result IS NULL AND game_date < ?", (today_et,)).fetchall()
    done = 0
    for fid, b, stat, line, gtime in todo:
        actual = _settle(b, stat, gtime)
        if actual is None:
            continue
        sh.execute("UPDATE flags SET actual=?, result=?, graded_at=? WHERE flag_id=?",
                   (actual, "win" if actual > line else "loss",
                    dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(), fid))
        done += 1
    sh.commit()
    for tier, (w, n, u) in sorted(shadow_record(sh).items()):
        print(f"  shadow {tier}: {w}-{n - w}  {u:+.2f}u  ROI {100 * u / n:+.1f}%  (n={n})")
    print(f"nba shadow: graded {done} of {len(todo)} pending")
    sh.close()


def shadow_record(sh):
    """{tier: (wins, n, units)} counted the way the speed test counts (nba_clv): voided flags
    excluded, ONE opportunity per (tier, player, stat, game), its EARLIEST flag. Counting every
    graded row, re-flags at moved lines and voids included, printed wowy as 13-12 -5.6% on
    2026-10-24 while the registered count was 9-2 +49.3%."""
    first = {}
    for tier, key, stat, gid, at, result, odds in sh.execute(
            "SELECT tier, COALESCE(pid, b), stat, gid, logged_at, result, odds FROM flags "
            "WHERE result IS NOT NULL AND void_reason IS NULL ORDER BY logged_at"):
        first.setdefault((tier, key, stat, gid), (result, odds))
    rec = defaultdict(lambda: [0, 0, 0.0])
    for (tier, *_), (result, odds) in first.items():
        r = rec[tier]
        r[0] += result == "win"
        r[1] += 1
        r[2] += (odds - 1) if result == "win" else -1.0
    return {t: tuple(v) for t, v in rec.items()}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--grade", action="store_true")
    ap.add_argument("--amend6", action="store_true", help="apply amendment 6 to logged flags (idempotent)")
    a = ap.parse_args()
    if a.amend6:
        amend6(dry=a.dry_run)
    elif a.grade:
        grade()
    else:
        today = dt.datetime.now(dt.timezone.utc).astimezone(ET).date()
        for d in range(HORIZONS):                 # today, then tomorrow (amendment 1)
            flags(dry=a.dry_run, game_date=(today + dt.timedelta(days=d)).isoformat())
