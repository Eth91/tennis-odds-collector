#!/usr/bin/env python3
"""NBA beat writers + news accounts on X -> the NBA news layer (NBA_SPEED_PREREG.md amendment 10).

Beat writers break injury news before the league's official report: a coach's pregame word, a
shootaround downgrade. This reads them through X SEARCH. One request covers ~25 accounts
(`from:a OR from:b ...`, Latest tab), and the daemon rotates through the account chunks. X's per-account
timeline budget is 50 requests / 15 min, and @UnderdogNBA alone uses ~45 of it, so polling each writer's
timeline would get the burner account limited. Search has its own budget (187 / 15 min, measured
2026-10-24); one search every 10 s across 3 chunks uses 90 of it and refreshes each account every 30 s.

Every post in a recognisable injury status (out / doubtful / questionable / available) is appended to
the SAME log the @UnderdogNBA watcher writes (NBA_X_LOG), tagged with its author. nba_news_watch then
treats it exactly like any other X item: the full name of exactly one player whose team plays on the
stated date, its own Out classifier, and amendment 2's rule that a news trigger counts only if the
official report confirms it before tip.

The X session cookie stays on the VM (X_AUTH_TOKEN / X_CT0 from wnba-loop.env, via the systemd unit).
The request plumbing (public web bearer, headers) is borrowed AT RUNTIME from the existing
underdog_watch.py, so nothing about the session is copied here.

    python3 nba_x_beats.py --validate     # resolve every handle; print who it really is
    python3 nba_x_beats.py --test         # one search per chunk; print the latest posts
    python3 nba_x_beats.py --loop 10      # daemon: one search every 10 s, rotating chunks
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
UW_PATH = Path(os.environ.get("NBA_UW_PATH", "/home/ubuntu/tennis-odds-collector/underdog_watch.py"))
LOG = Path(os.environ.get("NBA_X_LOG") or (HERE / "x_beats_log.jsonl"))
SEEN = HERE / "x_beats_seen.txt"
QCACHE = HERE / ".x_beats_qids.json"
MAX_QUERY = 480                     # X search caps a query near 512 characters

# (handle, team) — national insiders and injury aggregators first, then team beat writers.
# Every handle is checked with --validate before it is trusted. Dropped 2026-10-24 after validation:
# unresolvable (tomer_azarly, StefanBondy, DougSmithStar, Tony_Jones_) and resolving to an account that
# does not look like the reporter (Rotoworld_BK -> "NAA", ChrisHine -> "christine", highkin -> "pre",
# Jason_Anderson -> a handle-style name). A wrong account would feed noise, not news.
HANDLES = [
    ("ShamsCharania", "NBA"), ("ChrisBHaynes", "NBA"), ("TheSteinLine", "NBA"), ("JakeLFischer", "NBA"),
    ("RotoBallerNBA", "NBA"), ("FantasyLabsNBA", "NBA"), ("InStreetClothes", "NBA"),
    ("KLChouinard", "ATL"), ("ByJayKing", "BOS"), ("AdamHimmelsbach", "BOS"), ("NYPost_Lewis", "BKN"),
    ("ErikSlater_", "BKN"), ("rodboone", "CHA"), ("KCJHoop", "CHI"), ("ChrisFedor", "CLE"),
    ("townbrad", "DAL"), ("tim_cato", "DAL"), ("msinger", "DEN"), ("HarrisonWind", "DEN"),
    ("BennettDurando", "DEN"), ("omarisankofa", "DET"), ("anthonyVslater", "GSW"), ("Jonathan_Feigen", "HOU"),
    ("KellyIko", "HOU"), ("ScottAgness", "IND"), ("DustinDopirak", "IND"), ("JoeyLinn_", "LAC"), ("LawMurrayTheNU", "LAC"), ("mcten", "LAL"), ("jovanbuha", "LAL"),
    ("DanWoikeSports", "LAL"), ("DamichaelC", "MEM"), ("IraHeatBeat", "MIA"), ("Anthony_Chiang", "MIA"),
    ("JimOwczarski", "MIL"), ("eric_nehm", "MIL"), ("JonKrawczynski", "MIN"),
    ("DaneMooreNBA", "MIN"), ("Christian_Clark", "NOP"), ("WillGuillory", "NOP"), ("IanBegley", "NYK"),
    ("FredKatz", "NYK"), ("joe_mussatto", "OKC"), ("RylanStiles", "OKC"),
    ("BrandonRahbar", "OKC"), ("Khobi_Price", "ORL"), ("PompeyOnSixers", "PHI"), ("rich_hofmann", "PHI"),
    ("DerekBodnerNBA", "PHI"), ("KyleNeubeck", "PHI"), ("DuaneRankin", "PHX"), ("GeraldBourguet", "PHX"),
    ("CHold", "POR"), ("jwquick", "POR"), ("James_HamNBA", "SAC"),
    ("JMcDonald_SAEN", "SAS"), ("tom_orsborn", "SAS"), ("JLew1050", "TOR"),
    ("MichaelGrange", "TOR"), ("tribjazz", "UTA"), ("andyblarsen", "UTA"), ("JoshuaBRobbins", "WAS"),
    # AMENDMENT 29 (2026-10-25): a second writer for thin teams, each resolved first (display name = the reporter).
    # Not added: unresolved (gwashNBA, ScottFowlerObs, MarkGiannotto, ChrisHineStrib, JasonBeedeOS, chase_hughes,
    # QuinnOnDC, SBondyNYPost, SamAmicoNBA, JamesHamNBA, Brian_Windhorst, IanLevyNBA); a wrong name (SeanHighkin ->
    # "1.0"); not an injury source or not a current beat (wojespn, ZachLowe_NBA, ChrisMannixYS, BobbyMarks42,
    # ChrisKirschner, ANTHONYPUCCIO, Ky_Carlin, JoshRobbins); UnderdogNBA has its own watcher.
    ("williamslaurenl", "ATL"), ("Jared_Weiss", "BOS"), ("byjuliapoe", "CHI"), ("DarnellMayberry", "CHI"),
    ("joevardon", "CLE"), ("AmNotEvan", "CLE"), ("DwainPrice", "DAL"), ("keithlanglois", "DET"),
    ("HunterPatterson", "DET"), ("kendra__andrews", "GSW"), ("NickFriedell", "GSW"), ("ThompsonScribe", "GSW"),
    ("TomerAzarly", "LAC"), ("DrewHill_DM", "MEM"), ("Rod_Walker", "NOP"), ("SeanCunningham", "SAC"),
    ("WolstatSun", "TOR"), ("Tjonesonthenba", "UTA"),
]
VALIDATED = HERE / "x_beats_handles.json"      # written by --validate: the handles that resolved

# the same status vocabulary the @UnderdogNBA watcher uses (underdog_watch._ud_status)
SKIP_RX = re.compile(r"not (?:listed |currently )?on (?:the )?injury report|"
                     r"removed from (?:the )?injury report", re.I)
OUT_RX = re.compile(r"ruled out|listed out|\bis out\b|\bout for\b|will not play|won'?t play|"
                    r"sidelined|out indefinitely|\binactive\b|doubtful", re.I)
Q_RX = re.compile(r"questionable|game[- ]time decision|\bGTD\b", re.I)
IN_RX = re.compile(r"probable|available|will play|cleared to play|upgraded|good to go|active(?! roster)", re.I)


def status(txt):
    """'out' / 'q' / 'in', or None when the post is not an injury status."""
    if SKIP_RX.search(txt):
        return None
    if OUT_RX.search(txt):
        return "out"
    if Q_RX.search(txt):
        return "q"
    if IN_RX.search(txt):
        return "in"
    return None


def chunks(handles, limit=MAX_QUERY):
    """Pack `from:h` terms into OR-queries no longer than `limit` characters."""
    out, cur = [], []
    for h in handles:
        trial = " OR ".join(f"from:{x}" for x in cur + [h])
        if cur and len(trial) > limit:
            out.append(" OR ".join(f"from:{x}" for x in cur))
            cur = [h]
        else:
            cur.append(h)
    if cur:
        out.append(" OR ".join(f"from:{x}" for x in cur))
    return out


def _uw():
    """The existing watcher's request plumbing, loaded by path (public bearer + headers)."""
    spec = importlib.util.spec_from_file_location("_uw_for_beats", UW_PATH)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def query_ids(uw, ct0):
    """{op: queryId} for SearchTimeline + UserByScreenName, discovered from X's JS bundle, daily."""
    today = dt.date.today().isoformat()
    try:
        c = json.loads(QCACHE.read_text())
        if c.get("date") == today and "SearchTimeline" in c.get("ids", {}):
            return c["ids"]
    except (ValueError, OSError):
        c = {}
    ids, hh = {}, {**uw.UA, "cookie": f"auth_token={os.environ['X_AUTH_TOKEN']}; ct0={ct0}"}
    try:
        home = requests.get("https://x.com/", headers=hh, timeout=15).text
        urls = re.findall(r"https://abs\.twimg\.com/responsive-web/client-web[^\"']*?\.js", home)
        for url in urls[:12]:
            try:
                body = requests.get(url, headers=uw.UA, timeout=15).text
            except requests.RequestException:
                continue
            for op in ("SearchTimeline", "UserByScreenName"):
                m = (re.search(r'queryId:"([^"]+)",operationName:"%s"' % op, body)
                     or re.search(r'operationName:"%s",queryId:"([^"]+)"' % op, body))
                if m:
                    ids[op] = m.group(1)
            if len(ids) == 2:
                break
    except requests.RequestException:
        pass
    if "SearchTimeline" in ids:
        QCACHE.write_text(json.dumps({"date": today, "ids": ids}))
        return ids
    return c.get("ids") or {}


FEATURES = {"rweb_tipjar_consumption_enabled": True, "responsive_web_graphql_exclude_directive_enabled": True,
            "verified_phone_label_enabled": False, "creator_subscriptions_tweet_preview_api_enabled": True,
            "responsive_web_graphql_timeline_navigation_enabled": True,
            "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
            "communities_web_enable_tweet_community_results_fetch": True,
            "c9s_tweet_anatomy_moderator_badge_enabled": True, "articles_preview_enabled": True,
            "tweetypie_unmention_optimization_enabled": True, "responsive_web_edit_tweet_api_enabled": True,
            "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
            "view_counts_everywhere_api_enabled": True, "longform_notetweets_consumption_enabled": True,
            "responsive_web_twitter_article_tweet_consumption_enabled": True,
            "tweet_awards_web_tipping_enabled": False, "creator_subscriptions_quote_tweet_preview_enabled": False,
            "freedom_of_speech_not_reach_fetch_enabled": True, "standardized_nudges_misinfo": True,
            "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
            "rweb_video_timestamps_enabled": True, "longform_notetweets_rich_text_read_enabled": True,
            "longform_notetweets_inline_media_enabled": True, "responsive_web_enhance_cards_enabled": False}
RATE = {"remaining": None, "reset": None, "limit": None}


def _note(r):
    for k, h in (("remaining", "x-rate-limit-remaining"), ("reset", "x-rate-limit-reset"),
                 ("limit", "x-rate-limit-limit")):
        try:
            if r.headers.get(h) is not None:
                RATE[k] = int(r.headers[h])
        except (TypeError, ValueError):
            pass


def posts_of(payload):
    """[(id, text, author)] from a SearchTimeline payload: a deep walk, as underdog_watch does."""
    out = {}

    def walk(o):
        if isinstance(o, dict):
            lg = o.get("legacy")
            if isinstance(lg, dict) and lg.get("full_text") and o.get("rest_id"):
                core = (o.get("core") or {}).get("user_results", {}).get("result", {})
                author = ((core.get("legacy") or {}).get("screen_name")
                          or (core.get("core") or {}).get("screen_name") or "?")
                out[str(o["rest_id"])] = (lg["full_text"], author)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(payload)
    return [(i, t, a) for i, (t, a) in out.items()]


def search(uw, ids, ct0, q):
    """SearchTimeline must be a POST (a GET answers 404 as of 2026-10-24); its budget is 187 / 15 min."""
    var = {"rawQuery": q, "count": 20, "querySource": "typed_query", "product": "Latest"}
    url = f"https://x.com/i/api/graphql/{ids['SearchTimeline']}/SearchTimeline"
    r = requests.post(url, headers=uw._headers(ct0), timeout=20,
                      json={"variables": var, "features": FEATURES, "queryId": ids["SearchTimeline"]})
    _note(r)
    if r.status_code in (401, 403):
        return "AUTH"
    if r.status_code == 429:
        return "RATE"
    if r.status_code != 200:
        return f"HTTP{r.status_code}"
    try:
        return posts_of(r.json().get("data") or {})
    except ValueError:
        return "PARSE"


def validate():
    uw = _uw()
    at, ct0 = uw._cookie()
    if not at:
        sys.exit("no X_AUTH_TOKEN in the environment (run under the service's EnvironmentFile)")
    ids = {**uw._query_ids(ct0), **query_ids(uw, ct0)}
    ok = []
    for h, team in HANDLES:
        var = {"screen_name": h}
        feat = {"hidden_profile_subscriptions_enabled": True, "responsive_web_graphql_exclude_directive_enabled": True,
                "verified_phone_label_enabled": False, "highlights_tweets_tab_ui_enabled": True,
                "creator_subscriptions_tweet_preview_api_enabled": True,
                "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
                "responsive_web_graphql_timeline_navigation_enabled": True}
        url = (f"https://x.com/i/api/graphql/{ids['UserByScreenName']}/UserByScreenName"
               f"?variables={requests.utils.quote(json.dumps(var))}&features={requests.utils.quote(json.dumps(feat))}")
        r = requests.get(url, headers=uw._headers(ct0), timeout=15)
        try:
            res = r.json()["data"]["user"]["result"]
            lg = res.get("legacy") or {}
            name = (res.get("core") or {}).get("name") or lg.get("name") or "?"
            desc = (lg.get("description") or "").replace("\n", " ")[:70]
            fol = lg.get("followers_count")
            print(f"  OK   @{h:<17} {team:<4} {name:<26} {fol!s:>8}  {desc}")
            ok.append([h, team, name, fol, desc])
        except (ValueError, KeyError, TypeError):
            print(f"  --   @{h:<17} {team:<4} not resolved (HTTP {r.status_code})")
        time.sleep(1.5)
    VALIDATED.write_text(json.dumps(ok, indent=1))
    print(f"{len(ok)} of {len(HANDLES)} handles resolved -> {VALIDATED.name}")


def handles():
    """The validated handle list, else every handle (a dead one simply returns nothing)."""
    try:
        return [h for h, *_ in json.loads(VALIDATED.read_text())]
    except (ValueError, OSError):
        return [h for h, _ in HANDLES]


def log_new(posts, seen, first):
    fresh, n = [], 0
    for pid, txt, author in posts:
        if pid in seen:
            continue
        fresh.append(pid)
        st = None if first else status(txt)
        if not st:
            continue
        n += 1
        with LOG.open("a") as f:
            f.write(json.dumps({"t": dt.datetime.now(dt.timezone.utc).isoformat(), "id": pid,
                                "text": txt[:280], "st": st, "author": author}) + "\n")
        print(f"NEWS ({st}) @{author}: {txt[:120]}", flush=True)
    return fresh, n


def run(loop_s=None, test=False):
    uw = _uw()
    at, ct0 = uw._cookie()
    if not at:
        print("nba_x_beats: no X_AUTH_TOKEN -> benched", flush=True)
        return
    ids = query_ids(uw, ct0)
    if "SearchTimeline" not in ids:
        print("nba_x_beats: could not discover SearchTimeline queryId", flush=True)
        return
    qs = chunks(handles())
    print(f"nba_x_beats: {len(handles())} accounts in {len(qs)} search chunks -> {LOG}", flush=True)
    try:
        seen = set(SEEN.read_text().split())
    except OSError:
        seen = set()
    first = not SEEN.exists()
    i = 0
    while True:
        q = qs[i % len(qs)]
        res = search(uw, ids, ct0, q)
        if isinstance(res, str):
            print(f"nba_x_beats: chunk {i % len(qs)} -> {res} (remaining {RATE['remaining']})", flush=True)
            if res == "AUTH":
                time.sleep(600)
        elif test:
            print(f"chunk {i % len(qs)}: {len(res)} posts · rate limit {RATE}")
            for pid, txt, author in res[:5]:
                print(f"   @{author}: {txt[:110].replace(chr(10), ' ')}")
        else:
            fresh, n = log_new(res, seen, first)
            seen.update(fresh)
            SEEN.write_text(" ".join(list(seen)[-6000:]))
            print(f"nba_x_beats: chunk {i % len(qs)} · {len(res)} posts, {len(fresh)} new, {n} status "
                  f"· remaining {RATE['remaining']}", flush=True)
        i += 1
        if test and i >= len(qs):
            return
        if first and i >= len(qs):
            first = False                        # backlog of every chunk marked seen, now live
        if loop_s is None and not test:
            return
        wait = loop_s or 30
        if RATE["remaining"] is not None and RATE["reset"] and RATE["remaining"] <= 5:
            wait = max(wait, min(900, RATE["reset"] - time.time() + 5))
        time.sleep(wait)


if __name__ == "__main__":
    if "--validate" in sys.argv:
        validate()
    elif "--test" in sys.argv:
        run(test=True)
    elif "--loop" in sys.argv:
        i = sys.argv.index("--loop")
        run(loop_s=max(10, int(sys.argv[i + 1])) if len(sys.argv) > i + 1 else 30)
    else:
        run()
