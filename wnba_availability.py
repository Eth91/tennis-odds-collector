"""AVAILABILITY FROM APPEARANCES — the injury report is one input, not the truth.

WHY THIS EXISTS (2026-08-12)
A season-ending injury drops off the daily report. RotoWire lists who is questionable for
TONIGHT; it does not keep re-announcing that a player has been gone since July. So the
model goes blind to them. Measured live, EIGHT players above 12 mpg had missed 2+ straight
games with no injury-report entry at all:

    Leonie Fiebich      NY   29.3 mpg   14 games missed
    Jovana Nogic        PHX  20.1       18
    Satou Sabally       NY   16.7       17
    Sarah Ashlee Barker POR  24.7        5
    Luisa Geiselsoder   POR  16.6        4
    Te-Hina Paopao      ATL  12.5        9
    Teja Oblak          POR  13.1        2
    Katie Lou Samuelson SEA  15.2        2

Portland alone was missing ~54 mpg of role the model could not see; New York ~46.

TWO SETS, BECAUSE THEY ANSWER DIFFERENT QUESTIONS
`baseline_out` — everyone actually unavailable, however long. Used to CLEAN comparison
samples. Whether a player is injured, traded or waived is irrelevant here: the effect on
a team-mate's minutes is identical, and a WOWY "with X" average that quietly averages over
games where a 25-mpg team-mate was also gone is measuring two different rotations at once.
This is the bug that inflated Puoch's d_min to +9.5 — her 16.5-minute "with Leite" baseline
was mostly pre-Barker games that no longer describe her role. Same shape as Carrington
under Sheldon and Morrow under Juskaite, but structural rather than one-off.

`flag_out` — only absences new enough that the price may not have absorbed them. A player
gone 14 games is not news; the market has had three weeks. Generating a "beneficiary of X's
injury" flag off that is the opposite of a speed edge — it is the stalest possible signal.
Fresh report entries always qualify; a derived ghost only qualifies while STALE_GAMES has
not elapsed.

⚠️ THE TWO SETS ARE NOT NESTED THE WAY YOU EXPECT. `flag_out` is not simply a subset filter
on `baseline_out`: a report-listed Out is fresh by construction and belongs to both, while a
long-gone ghost belongs to `baseline_out` ONLY. Using one where the other belongs is the
whole point of separating them — pass `baseline_out` to a flag generator and you will bet
three-week-old news; pass `flag_out` to a baseline cleaner and you will leave the
contamination in place.

⚠️ ABSENCE IS INFERRED, NOT OBSERVED. A player who does not appear in a box score might be
injured, rested, traded, waived, or simply a coach's decision. For the baseline question
that distinction does not matter. It DOES matter for flagging, which is the second reason
`flag_out` is conservative.
"""
from __future__ import annotations

MIN_MPG = 12.0        # below this an absence does not move a team-mate's role
MIN_MISSED = 2        # one miss is a rest day or a late scratch, not a regime change
STALE_GAMES = 4       # a ghost older than this is priced in -- baseline only, never a flag
MIN_GP = 5            # too few appearances to establish a role at all


def _team_dates(team, players, glog, top=3):
    """The team's game dates, unioned over its highest-minute players so one player's own
    absence cannot shorten the schedule we measure everyone else against."""
    squad = sorted(((n, v) for n, v in players.items() if v.get("team") == team),
                   key=lambda x: -x[1].get("min", 0))
    dates = set()
    for n, v in squad[:top]:
        for g in glog(v["id"]) or []:
            dates.add(g["date"][:10])
    return sorted(dates, reverse=True)


def absent_sets(team, players, glog, injuries=None, as_of=None):
    """-> {"baseline_out": {name: games_missed}, "flag_out": {name: games_missed},
           "ghosts": {name: games_missed}}

    `ghosts` are the derived absences ONLY -- the players the injury report never mentions.
    Kept separate so a caller can see what this module added versus what the feed supplied.
    """
    injuries = injuries or {}
    report_out = {n for n, s in injuries.items() if "out" in str(s).lower()}
    dates = _team_dates(team, players, glog)
    if as_of:
        dates = [d for d in dates if d < as_of]
    baseline, flags, ghosts = {}, {}, {}
    for n, v in players.items():
        if v.get("team") != team:
            continue
        if v.get("min", 0) < MIN_MPG or v.get("gp", 0) < MIN_GP:
            continue
        lg = glog(v["id"]) or []
        if not lg:
            continue
        last = lg[0]["date"][:10]
        missed = sum(1 for d in dates if d > last)
        if n in report_out:
            baseline[n] = missed
            flags[n] = missed                 # a report entry is fresh by construction
        elif missed >= MIN_MISSED:
            ghosts[n] = missed
            baseline[n] = missed              # always cleans the baseline
            if missed <= STALE_GAMES:         # ...but only flags while it is still news
                flags[n] = missed
    return {"baseline_out": baseline, "flag_out": flags, "ghosts": ghosts}


def regime_games(log, baseline_out, players, glog):
    """Filter a player's game log to the games that match TONIGHT's availability regime:
    every currently-absent team-mate was ALSO absent.

    This is the de-contamination step. Without it, "with X" averages a player's role from
    two different rotations and reports the difference as an X effect.

    ⚠️ It can cut the sample hard, which is a feature -- if only three games resemble
    tonight, the honest answer is that the estimate is thin, not that a 30-game average
    applies. Callers must check the returned length and fall back rather than pretending.
    """
    if not baseline_out:
        return list(log)
    played_dates = []
    for n in baseline_out:
        v = players.get(n)
        if not v:
            continue
        played_dates.append({g["date"][:10] for g in (glog(v["id"]) or [])})
    if not played_dates:
        return list(log)
    keep = []
    for g in log:
        d = g["date"][:10]
        if not any(d in s for s in played_dates):   # none of tonight's absentees played
            keep.append(g)
    return keep


def summary(team, players, glog, injuries=None, as_of=None):
    a = absent_sets(team, players, glog, injuries, as_of)
    mpg = {n: players[n].get("min", 0) for n in a["baseline_out"] if n in players}
    return {
        "team": team,
        "baseline_out": a["baseline_out"],
        "flag_out": a["flag_out"],
        "ghosts": a["ghosts"],
        "hidden_mpg": round(sum(v for n, v in mpg.items() if n in a["ghosts"]), 1),
        "total_out_mpg": round(sum(mpg.values()), 1),
    }


def regime_weights(log, baseline_out, players, glog):
    """-> [(game, weight)] — how much each past game resembles TONIGHT's availability.

    ⚠️ WHY THIS EXISTS RATHER THAN A HARD FILTER. `regime_games` is a binary match, and on
    a heavily-depleted team it returns NOTHING: Portland tonight is missing Leite, Barker,
    Geiselsoder and Oblak, a combination that has literally never occurred, so strict
    matching abstained on all 8 rotation players — precisely the team where the
    contamination is worst. Measured league-wide, strict matching left a usable (>=4 game)
    sample for only 47 of 87 rotation players.

    So weight instead of filter. The weight is the SHARE OF TONIGHT'S MISSING MINUTES that
    was also missing in that game, which makes a 25-mpg absence count for far more than a
    13-mpg one. A game from the current rotation approaches 1.0; a game from a healthy
    early-season rotation approaches 0 and stops polluting the average without being
    discarded outright.

    Returns weights only — the caller does the weighted mean. Deliberately not folded into
    a stat helper, because "with/without" splits, medians and hit-rates each need to consume
    it differently, and a single blessed aggregate would get reused where it does not fit.
    """
    tot = 0.0
    absent_dates = {}
    for n in baseline_out:
        v = players.get(n)
        if not v:
            continue
        m = v.get("min", 0) or 0.0
        tot += m
        absent_dates[n] = (m, {g["date"][:10] for g in (glog(v["id"]) or [])})
    if tot <= 0:
        return [(g, 1.0) for g in log]
    out = []
    for g in log:
        d = g["date"][:10]
        matched = sum(m for _n, (m, played) in absent_dates.items() if d not in played)
        out.append((g, matched / tot))
    return out


def weighted_mean(pairs, key):
    """Weighted mean of `key` over [(game, weight)], plus the EFFECTIVE sample size.

    n_eff = (sum w)^2 / sum(w^2) — the standard Kish formula. Reporting it matters: 30 games
    at weight 0.1 are not 30 games of evidence, and a caller that reads len() instead will
    treat a diluted average as if it were fully observed.
    """
    num = den = sq = 0.0
    for g, w in pairs:
        v = g.get(key)
        if v is None or w <= 0:
            continue
        num += w * v
        den += w
        sq += w * w
    if den <= 0:
        return None, 0.0
    return num / den, (den * den / sq if sq > 0 else 0.0)
