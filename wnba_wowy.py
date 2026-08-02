"""WNBA WOWY (with-or-without-you) + minutes-band engine — PropsCash, automated.

The manual grind this replaces: when a key player sits, figure out who inherits the
minutes/usage, then recall how the beneficiary produced in past games at that role.
This computes it from the free WNBA stats API (stats.nba.com, LeagueID=10):

  wowy(player, teammate)  -> that player's MIN/PTS/REB/AST split by teammate IN vs OUT
  minutes_bands(player)   -> production distribution bucketed by minutes played
  beneficiaries(team, out)-> for a given out-list, who historically gains minutes/usage

Game-by-game: a game_id in player Y's log but NOT in teammate X's log = a game X missed,
so Y's rows there are the "without X" split. No injury feed needed for the history — the
absence IS the signal.

    python wnba_wowy.py --player "Jackie Young" --without "A'ja Wilson"
    python wnba_wowy.py --team LVA --out "A'ja Wilson"     # who benefits if Wilson sits
"""
from __future__ import annotations

import argparse
import statistics as st
import time

import requests

# ESPN's public API — datacenter-reachable (stats.nba.com blocks cloud IPs, so we can't
# run that in CI). Rosters + per-game logs with the fields the usage model needs.
SITE = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba"
WEB = "https://site.web.api.espn.com/apis/common/v3/sports/basketball/wnba"

# GAME-LOG DISK CACHE (2026-07-16, "full accuracy + speed"): logs only change when a game
# FINISHES, so refetching ~60-100 of them serially every scan (the whole ~47-90s cost) buys
# nothing intra-day. Entries carry fetched_at; default max_age_h=6 serves scans; GRADING
# passes max_age_h=0 (always fresh — the Rae Burrell staleness class stays dead). Merged
# read-modify-write so concurrent processes (alert + watch) don't clobber each other.
import json as _json
import datetime as _dt
from pathlib import Path as _Path
_GLOG_FILE = _Path(__file__).resolve().parent / "wnba_glog_cache.json"
_GLOG = None


def _glog_load():
    global _GLOG
    if _GLOG is None:
        try:
            _GLOG = _json.loads(_GLOG_FILE.read_text())
        except (OSError, ValueError):
            _GLOG = {}
    return _GLOG


def flush_glog_cache():
    """Merge-write the in-memory log cache to disk (newest fetched_at wins per player)."""
    if _GLOG is None:
        return
    try:
        disk = _json.loads(_GLOG_FILE.read_text())
    except (OSError, ValueError):
        disk = {}
    for k, v in _GLOG.items():
        if k not in disk or v.get("fetched_at", "") > disk[k].get("fetched_at", ""):
            disk[k] = v
    try:
        _GLOG_FILE.write_text(_json.dumps(disk))
    except OSError:
        pass
H = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

# Pooled session (2026-07-29 latency work): a fresh requests.get() per call rebuilt the SSL
# context and re-read the CA bundle every time — profiled at 166ms of load_verify_locations
# PER CALL, ~4.3s across one scan. One Session keeps the connection alive to ESPN and builds
# that context once. Pool sized for the per-player fan-out.
_SESSION = requests.Session()
_SESSION.mount("https://", requests.adapters.HTTPAdapter(
    pool_connections=4, pool_maxsize=8, max_retries=0))

_PLAYERS_CACHE = {}


def _get(url):
    for attempt in range(3):
        try:
            r = _SESSION.get(url, headers=H, timeout=30)
            if r.status_code == 200:
                return r.json()
        except requests.RequestException:
            pass
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"ESPN API failed: {url[:60]}")


def _made_att(s):
    """'8-14' -> (8, 14); robust to '--' / empty."""
    try:
        m, a = str(s).split("-")
        return int(m), int(a)
    except (ValueError, AttributeError):
        return 0, 0




def game_log(pid, max_age_h=6.0):
    """[{game_id, date, min, pts, reb, ast, fga, fg3a, fta, tov, poss, dd, matchup}]
    for a player, from ESPN — disk-cached (max_age_h; 0 = always fresh, used by grading).
    fga/fta/tov feed the usage proxy; dd = double-double."""
    cache = _glog_load()
    ent = cache.get(str(pid))
    if ent and max_age_h > 0:
        try:
            age_h = (_dt.datetime.now(_dt.timezone.utc)
                     - _dt.datetime.fromisoformat(ent["fetched_at"])).total_seconds() / 3600
            if age_h < max_age_h:
                return ent["log"]
        except (KeyError, ValueError):
            pass
    j = _get(f"{WEB}/athletes/{pid}/gamelog")
    labels = j.get("names") or []
    li = {name: k for k, name in enumerate(labels)}
    meta = j.get("events", {}) or {}
    out = []
    for stype in j.get("seasonTypes") or []:
        # DROP preseason: scrub-lineup exhibition games leak into the WOWY 'without' split, players()
        # season averages, and the elevated-minutes sample — all of which drive LIVE bets. game_log is
        # the shared source for serving AND backtesting, so filtering here keeps train/serve consistent.
        if "preseason" in (stype.get("displayName") or "").lower():
            continue
        for cat in stype.get("categories") or []:
            for ev in cat.get("events") or []:
                s = ev.get("stats") or []
                eid = str(ev.get("eventId"))
                if len(s) < len(labels):
                    continue
                def num(key, d=0.0):
                    i = li.get(key)
                    try:
                        return float(s[i]) if i is not None else d
                    except (ValueError, TypeError):
                        return d
                p, rb, a = num("points"), num("totalRebounds"), num("assists")
                _fgm, fga = _made_att(s[li["fieldGoalsMade-fieldGoalsAttempted"]]) \
                    if "fieldGoalsMade-fieldGoalsAttempted" in li else (0, 0)
                _3m, fg3a = _made_att(s[li["threePointFieldGoalsMade-threePointFieldGoalsAttempted"]]) \
                    if "threePointFieldGoalsMade-threePointFieldGoalsAttempted" in li else (0, 0)
                _ftm, fta = _made_att(s[li["freeThrowsMade-freeThrowsAttempted"]]) \
                    if "freeThrowsMade-freeThrowsAttempted" in li else (0, 0)
                tov = num("turnovers")
                m = meta.get(eid, {})
                opp = (m.get("opponent") or {}).get("abbreviation", "")
                out.append({"game_id": eid, "date": m.get("gameDate", ""),
                            "min": num("minutes"), "pts": p, "reb": rb, "ast": a,
                            "fga": fga, "fg3a": fg3a, "fta": fta, "tov": tov,
                            "poss": fga + 0.44 * fta + tov,
                            "pra": p + rb + a, "pts_reb": p + rb, "pts_ast": p + a, "reb_ast": rb + a,
                            "dd": sum(1 for v in (p, rb, a) if v >= 10) >= 2,
                            "matchup": opp,
                            "result": m.get("gameResult", "")})   # 'W'/'L' once FINAL, '' if not
    _glog_load()[str(pid)] = {
        "fetched_at": _dt.datetime.now(_dt.timezone.utc).isoformat(), "log": out}
    # Throttle lives HERE, next to the request that earns it. It used to sit in players()
    # and fired once per player even when this function returned a cached log without
    # touching the network — ~10s of sleeping against nothing on a full roster sweep.
    time.sleep(0.05)
    return out


def players():
    """{name: {'id','team','min','pts','reb','ast','gp','position'}} — rosters (ESPN) with
    season averages computed from each player's game log. Cached per process."""
    if _PLAYERS_CACHE:
        return _PLAYERS_CACHE
    teams = _get(f"{SITE}/teams").get("sports", [{}])[0].get("leagues", [{}])[0].get("teams", [])
    out = {}
    for t in teams:
        tm = t["team"]
        abbr = tm["abbreviation"]
        roster = _get(f"{SITE}/teams/{tm['id']}/roster").get("athletes", [])
        for a in roster:
            pid, name = a.get("id"), a.get("displayName")
            pos = (a.get("position") or {}).get("abbreviation", "")
            if not pid or not name:
                continue
            try:
                log = game_log(pid)
            except RuntimeError:
                continue
            gp = len(log)
            if gp == 0:
                out[name] = {"id": pid, "team": abbr, "min": 0, "pts": 0, "reb": 0,
                             "ast": 0, "gp": 0, "position": pos}
                continue
            out[name] = {"id": pid, "team": abbr, "position": pos, "gp": gp,
                         "min": st.mean([g["min"] for g in log]),
                         "pts": st.mean([g["pts"] for g in log]),
                         "reb": st.mean([g["reb"] for g in log]),
                         "ast": st.mean([g["ast"] for g in log])}
    _PLAYERS_CACHE.update(out)
    return out


def roster_ids():
    """{name: espn_id} for every rostered player — teams + rosters ONLY, no per-player game_log.
    Grading just needs the id map, so this skips the ~180-call season-average rebuild players()
    does (that rebuild throttles and aborts the grade pass). Per-team guarded: one flaky roster
    fetch drops only that team, never the whole map."""
    out = {}
    try:
        teams = _get(f"{SITE}/teams").get("sports", [{}])[0].get("leagues", [{}])[0].get("teams", [])
    except RuntimeError:
        return out
    for t in teams:
        try:
            roster = _get(f"{SITE}/teams/{t['team']['id']}/roster").get("athletes", [])
        except RuntimeError:
            continue
        for a in roster:
            pid, name = a.get("id"), a.get("displayName")
            if pid and name:
                out[name] = pid
    return out


def _summ(games, stat):
    vals = [g[stat] for g in games]
    return {"n": len(vals), "mean": st.mean(vals) if vals else 0,
            "vals": sorted(vals, reverse=True)}


def wowy_multi(player_log, teammate_logs):
    """Split player's games by whether ALL the given teammates were ABSENT that game.
    'without' = games none of them played (the multi-out scenario the user cares about —
    a beneficiary often gets a BIGGER boost when 2+ impact players sit together); 'with' =
    at least one of them played. Returns per-stat means over MIN/PTS/REB/AST/FGA/FTA/3PA."""
    # SAME-SIDE ONLY. A game_id identifies a GAME, not a SIDE, so two players who faced each other
    # share one. For a player traded in mid-season that is the ONLY way she ever shares a game_id
    # with her new teammates, which made her "with" set a single game played AGAINST them and her
    # "without" set the beneficiary's entire season. Teammates record the same opponent in a shared
    # game; opponents record each other's team — verified a perfect discriminator (22/22 and 21/21
    # for real TOR pairs, 0/1 for Morrow, who has never played a game FOR Toronto).
    own = {g["game_id"]: g.get("matchup") for g in player_log}
    present = set()
    for tl in teammate_logs:
        for g in tl:
            gid = g["game_id"]
            if gid not in own:
                continue
            mine, theirs = own[gid], g.get("matchup")
            # Missing discriminator -> keep the old behaviour for that game. Treating an unknown
            # as "opponent" would reclassify real teammates and corrupt the splits that work.
            if mine is None or theirs is None or mine == theirs:
                present.add(gid)
    with_g = [g for g in player_log if g["game_id"] in present]
    without_g = [g for g in player_log if g["game_id"] not in present]
    def block(gs):
        return {s: _summ(gs, s) for s in ("min", "pts", "reb", "ast", "fga", "fta", "fg3a",
                                          "pra", "pts_reb", "pts_ast", "reb_ast")}
    return {"with": block(with_g), "without": block(without_g),
            "n_with": len(with_g), "n_without": len(without_g)}


def wowy(player_log, teammate_log):
    """Single-teammate with/without split (thin wrapper over wowy_multi)."""
    return wowy_multi(player_log, [teammate_log])


def peer_regime(player_log, peer_log, peer_plays_tonight, out_game_ids, min_gap=3.0):
    """⚠ REGIME WARNING — is the elevated sample borrowed from the WRONG lineup?

    `wowy_multi` conditions ONLY on the out player(s) and lets every other teammate float.
    That is the Edwards case (2026-07-28, user-caught): Griner out projected her +5.0 min /
    13.1 pts, but 5 of those 7 elevated games ALSO had Aneesah Morrow out. Morrow — not Griner
    — is the forward she actually competes with for minutes. Holding Morrow ON the floor,
    Griner's absence is worth only +1.8 min and her scoring DROPS 9.3 -> 7.2. Morrow played
    that night, so the projection was priced off a lineup that was not happening.

    Checks ONE peer — the highest-minutes same-position teammate — because that is who
    contests the minutes, and because a full out-set match is combinatorially rare: a
    match-ALL-peers version scored <0.25 on 84% of historical bets, too degenerate to test.

    DISPLAY ONLY — returns a warning, never a veto. The selected-bet ledger (~51 rows) cannot
    validate a hard gate, and this session produced three examples of a filter fit on a thin
    sample costing money. Let it accrue, then test it on the post-selection universe.

    Returns None when the sample is fine, else a dict; `gap_min` is roughly how many minutes
    the projection is borrowing from the wrong regime.
    """
    elev = [g for g in player_log
            if g["game_id"] not in out_game_ids and (g.get("min") or 0) > 0]
    if len(elev) < 3 or not peer_log:
        return None
    peer_games = {g["game_id"] for g in peer_log if (g.get("min") or 0) > 0}
    want = bool(peer_plays_tonight)
    match = [g for g in elev if (g["game_id"] in peer_games) == want]
    other = [g for g in elev if (g["game_id"] in peer_games) != want]
    frac = len(match) / len(elev)
    if not other:
        return None                                   # whole sample matches tonight -> fine
    mm = (sum(g["min"] for g in match) / len(match)) if match else None
    mo = sum(g["min"] for g in other) / len(other)
    gap = (mo - mm) if mm is not None else None
    # Trigger on the GAP, not the match fraction. First version returned early when >=50% of
    # the sample matched -- which silently passed the very case this exists for: Edwards was
    # 5/9 matching (55.6%) yet the projection still averaged all 9 games, 18.8 min in the
    # matching lineup vs 25.5 in the wrong one. What matters is that a material share of the
    # sample comes from a lineup that is not happening AND moves the minutes.
    if len(other) / len(elev) < 0.25:
        return None                                   # mismatched games too rare to distort
    if gap is None or gap < min_gap:
        return None                                   # peer state barely moves the minutes
    return {"peer_match": round(frac, 2), "n_elev": len(elev), "n_match": len(match),
            "peer_plays_tonight": want,
            "min_match": round(mm, 1) if mm is not None else None,
            "min_other": round(mo, 1), "gap_min": round(gap, 1) if gap is not None else None}


def peer_regime_scan(bene, team_players, out_names, logs, pos_of, plays_tonight, min_gap=3.0):
    """Run peer_regime against EVERY same-position peer and return the worst mismatch.

    Picking one "top peer" first was the wrong shape twice: by minutes it chose the teammate
    who never misses a game (no availability variance -> can never explain the role change),
    and by whole-season minutes-gap it still chose Nelson-Ododa over Morrow because the gap
    was measured across ALL games rather than inside the elevated sample the projection is
    actually built from. Scanning sidesteps the choice: every peer is checked against the
    elevated games, and the biggest borrowed-minutes gap is what gets surfaced.

    `plays_tonight(name) -> bool`. Returns the worst warning dict (with `peer` added) or None.
    """
    grp = {"G": "G", "F": "F", "C": "F"}

    def g_of(n):
        return grp.get((pos_of(n) or "?")[:1].upper(), "?")

    mine = g_of(bene)
    blog = logs.get(bene) or []
    out_ids = {g["game_id"] for o in out_names
               for g in (logs.get(o) or []) if (g.get("min") or 0) > 0}
    worst = None
    for n in team_players:
        if n == bene or n in out_names or g_of(n) != mine:
            continue
        w = peer_regime(blog, logs.get(n), plays_tonight(n), out_ids, min_gap=min_gap)
        if w and (worst is None or (w["gap_min"] or 0) > (worst["gap_min"] or 0)):
            w = dict(w, peer=n)
            worst = w
    return worst


def ramp_state(peer_log, as_of, missed_days=12, back_max=4, deficit_min=2.0):
    """Is this peer still CLIMBING BACK into their role as of `as_of`? None when not.

    peer_regime asks whether a peer played — a binary. That is the right question for a stable
    role and the wrong one for someone working back from an absence, because their minutes are a
    moving target and every game they take back is a game the beneficiary gives up.

    The case this was built from: Julie Allemand's elevated sample had 11 games, 9 of them with
    Kiki Rice out. peer_regime correctly flagged that. But the 2 games it said to trust were Rice's
    first two back — 17 and 23 minutes against a 26.7-minute pre-absence norm — so the "good"
    sub-sample was itself taken from a lineup that had not settled. Rice climbed 17 -> 23, and the
    game where she came closest to her norm is the game Allemand dropped 32 -> 22 minutes.

    Strictly-prior games only. UNPROVEN: measured at 3 of 52 graded bets (6%), all from one slate
    and one peer, which is too rare to validate. Logged, never gated.
    """
    import datetime as _dt
    gs = sorted([g for g in peer_log if str(g.get("date"))[:10] < as_of],
                key=lambda g: str(g.get("date"))[:10])
    played = [g for g in gs if (g.get("min") or 0) > 0]
    if len(played) < 4:
        return None

    def _d(x):
        return _dt.date.fromisoformat(str(x.get("date"))[:10])

    for nb in range(1, back_max + 1):
        if len(played) < nb + 1:
            return None
        gap = (_d(played[-nb]) - _d(played[-nb - 1])).days
        if gap >= missed_days:                       # found the absence behind this stretch
            cur = played[-nb:]
            pre = played[:-nb][-8:]
            if len(pre) < 3:
                return None
            norm = sum(g["min"] for g in pre) / len(pre)
            mins = [g["min"] for g in cur]
            deficit = norm - (sum(mins) / len(mins))
            if deficit < deficit_min:
                return None                          # role already restored
            return {"games_back": nb, "gap_days": gap, "norm": round(norm, 1),
                    "since": mins, "deficit": round(deficit, 1),
                    "trend": round(mins[-1] - mins[0], 1) if len(mins) > 1 else 0.0}
    return None

def top_peer(bene, team_players, out_names, logs, pos_of, min_each=2):
    """The same-position teammate whose ABSENCE actually moves `bene`'s minutes most.

    NOT "whoever plays the most minutes" — that was the first version and it picks the wrong
    player. For Edwards it returned Nelson-Ododa, who never misses a game: a teammate with no
    variance in availability cannot explain any variance in Edwards' role, so the check never
    fired. What matters is the peer whose availability VARIES and co-moves with bene's minutes
    — Morrow, worth ~+8.9 min when she sits.

    Requires >=`min_each` games on each side of the split so a one-game absence can't win.
    Returns None when no peer has a usable both-ways sample (then there is nothing to warn on).
    """
    grp = {"G": "G", "F": "F", "C": "F"}      # bigs share a minute pool; guards are separate

    def g_of(n):
        return grp.get((pos_of(n) or "?")[:1].upper(), "?")

    mine = g_of(bene)
    blog = logs.get(bene) or []
    best, best_gap = None, 0.0
    for n in team_players:
        if n == bene or n in out_names or g_of(n) != mine:
            continue
        pg = {g["game_id"] for g in (logs.get(n) or []) if (g.get("min") or 0) > 0}
        if not pg:
            continue
        with_p = [g["min"] for g in blog if (g.get("min") or 0) > 0 and g["game_id"] in pg]
        without_p = [g["min"] for g in blog if (g.get("min") or 0) > 0 and g["game_id"] not in pg]
        if len(with_p) < min_each or len(without_p) < min_each:
            continue                            # no usable both-ways sample
        gap = sum(without_p) / len(without_p) - sum(with_p) / len(with_p)
        if gap > best_gap:
            best, best_gap = n, gap
    return best


def minutes_bands(pl_log, width=4):
    """Production bucketed by minutes played — the 'similar-minutes games' lookup."""
    bands = {}
    for g in pl_log:
        b = int(g["min"] // width) * width
        bands.setdefault(b, []).append(g)
    return {f"{b}-{b+width}": {s: _summ(gs, s) for s in ("pts", "reb", "ast")}
            for b, gs in sorted(bands.items())}


def _delta_line(label, w, wo):
    d = wo["mean"] - w["mean"]
    return (f"  {label:4} with {w['mean']:5.1f} (n{w['n']}) → without {wo['mean']:5.1f} "
            f"(n{wo['n']})   {d:+.1f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--player")
    ap.add_argument("--without", help="teammate whose absence to split on")
    ap.add_argument("--team", help="show all players on a team")
    ap.add_argument("--out", help="with --team: teammate assumed out, rank beneficiaries")
    args = ap.parse_args()
    pl = players()

    if args.player and args.without:
        p, t = pl.get(args.player), pl.get(args.without)
        if not p or not t:
            raise SystemExit("player/teammate not found (exact name).")
        w = wowy(game_log(p["id"]), game_log(t["id"]))
        print(f"\n{args.player} — with vs WITHOUT {args.without}:")
        for s in ("min", "pts", "reb", "ast"):
            print(_delta_line(s.upper(), w["with"][s], w["without"][s]))
        print(f"\n{args.player} — production by minutes band:")
        for band, prod in minutes_bands(game_log(p["id"])).items():
            pts = prod["pts"]
            print(f"  {band:>7} min (n{pts['n']}): PTS {pts['vals']}")
        return

    if args.team and args.out:
        team_pl = {n: v for n, v in pl.items() if v["team"] == args.team.upper()}
        tout = pl.get(args.out)
        if not tout:
            raise SystemExit("out-player not found.")
        tlog = game_log(tout["id"])
        print(f"\nIf {args.out} sits — {args.team} beneficiaries (MIN & PTS gain WITHOUT him):")
        rows = []
        for n, v in team_pl.items():
            if n == args.out or v["gp"] < 5:
                continue
            try:
                w = wowy(game_log(v["id"]), tlog)
            except RuntimeError:
                continue
            if w["n_without"] >= 2:
                dmin = w["without"]["min"]["mean"] - w["with"]["min"]["mean"]
                dpts = w["without"]["pts"]["mean"] - w["with"]["pts"]["mean"]
                rows.append((dmin, dpts, n, w["n_without"]))
            time.sleep(0.2)
        for dmin, dpts, n, nw in sorted(rows, reverse=True)[:8]:
            print(f"  {n:22} {dmin:+.1f} min, {dpts:+.1f} pts   (n{nw} games without)")


if __name__ == "__main__":
    main()
