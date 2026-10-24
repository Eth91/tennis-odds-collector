#!/usr/bin/env python3
"""NBA news layer — injury rulings from sources that can beat the official report. MAC-ONLY.

The league's report publishes every 15 minutes, and teams often tell reporters first. Every news
item is stored with the moment WE first saw it, so the lead over the official report is MEASURED
per source, not assumed — the WNBA built the same journal to prove or kill its news layer.

SOURCES (no credentials):
  rotowire  rotowire.com/basketball/news.php — structured: player, team, headline, text, and the
            item's own source link. ⚠️ Measured 2026-10-22: RotoWire's items for that afternoon's
            rulings link to the official report's PDF as their source, i.e. they are DOWNSTREAM of
            it. Its beat-sourced items may still lead; `provenance` records which is which.
  bsky      Bluesky post search (unauthenticated). Noisy — fantasy accounts repost; kept for the
            journal, and only an exact, unique name on a team playing that day can match.
  x         @UnderdogNBA via the VM's underdog-watch.service (repointed 2026-10-22; the burner
            cookie stays on the VM), pulled over ssh ($NBA_X_SSH). Measured on day one: its
            "listed out" posts RELAY the official report ~10 s after it publishes (no lead), but its
            coach/beat posts lead it by HOURS — "Keefe: AJ Dybantsa (ankle) ruled out for Friday"
            at 16:16 UTC; the league listed him at 20:45 (+4 h 28 min).

ADD-ONLY. A news Out can add an absence before the official report lists it; it never clears an
official one. If an official report published AFTER the news item lists the player for that game
with any non-Out status, the news Out is dropped from then on (the league is the authority).

    python nba_news_watch.py            # poll every enabled source once, store, print new Outs
    python nba_news_watch.py --journal  # lead time vs the official report, per source
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sqlite3
import unicodedata
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

import nba_injury_report as I
import nba_rosters as R

HERE = Path(__file__).resolve().parent
DB = I.DB                                    # nba_news.sqlite — same store as the official reports
ET = ZoneInfo("America/New_York")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/129.0 Safari/537.36"}
DDL = """CREATE TABLE IF NOT EXISTS news_items (
    source TEXT, item_id TEXT, detected_at TEXT, player TEXT, pid INTEGER, team TEXT,
    game_date TEXT, status TEXT, headline TEXT, body TEXT, provenance TEXT,
    seeded INTEGER DEFAULT 0, PRIMARY KEY (source, item_id))"""


CHOICES_DDL = """CREATE TABLE IF NOT EXISTS choices (pid INTEGER, player TEXT, team TEXT,
    date_a TEXT, date_b TEXT, item TEXT, provenance TEXT, created_at TEXT, state TEXT,
    resolved_at TEXT, note TEXT, PRIMARY KEY (pid, date_a, date_b))"""
B2B_RE = re.compile(r"back-to-back|both (?:legs|games|nights|ends)", re.I)


def choice_dates(text, now_et, team_dates):
    """The two games a choice is between (amendment 14): the NAMED days on which the team plays, or,
    for 'both legs / both games of the back-to-back' without named days, the team's next two games
    on consecutive dates. Exactly two dates, or None."""
    t = (text or "").lower()
    named = set()
    if re.search(r"\b(tonight|today)\b", t):
        named.add(now_et.date().isoformat())
    if re.search(r"\btomorrow\b", t):
        named.add((now_et.date() + dt.timedelta(days=1)).isoformat())
    for i in range(7):
        d = now_et.date() + dt.timedelta(days=i)
        if re.search(rf"\b{DAYS[d.weekday()]}\b", t):
            named.add(d.isoformat())
    dates = sorted(d for d in named if d in team_dates)
    if len(dates) == 2:
        return dates
    if len(dates) < 2 and B2B_RE.search(t):
        ahead = sorted(d for d in team_dates if d >= now_et.date().isoformat())
        for a, b in zip(ahead, ahead[1:]):
            if (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days == 1:
                return [a, b]
    return None


def register_choice(con, it, index, team_games, now_et, now):
    """A `choice` item -> a pending choice, when its player and its two games are unambiguous."""
    text = f"{it.get('headline') or ''} {it.get('body') or ''}"
    ft = f" {fold(text)} "
    cands = [(p, n, t) for p, (t, n, _) in index.items()
             if t in team_games and len(fold(n).split()) >= 2 and f" {fold(n)} " in ft]
    if len(cands) != 1:
        return None
    pid, name, tri = cands[0]
    dates = choice_dates(text, now_et, team_games[tri])
    if not dates:
        return None
    con.execute(CHOICES_DDL)
    con.execute("INSERT OR IGNORE INTO choices VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (pid, name, tri, dates[0], dates[1], str(it.get("item_id")), it.get("provenance"),
                 now.isoformat(), "pending", None, None))
    return pid, name, tri, dates


def _migrate(con):
    con.execute(DDL)
    con.execute(CHOICES_DDL)
    con.execute("CREATE TABLE IF NOT EXISTS news_sources (source TEXT PRIMARY KEY, "
                "first_polled_at TEXT)")
    if "seeded" not in {r[1] for r in con.execute("PRAGMA table_info(news_items)")}:
        con.execute("ALTER TABLE news_items ADD COLUMN seeded INTEGER DEFAULT 0")

# OUT-class phrasing. "Questionable" is not an absence and never triggers. "Doubtful" is (amendment
# 15): it is stored `doubtful` and triggers like `out`.
OUT_RE = re.compile(r"\b(ruled out|listed out|won'?t (?:play|suit up|be available|dress)|will not "
                    r"(?:play|suit up|be available|dress)|will miss|out for|inactive for|"
                    r"sidelined for|not (?:playing|available)|remains out|listed as out)\b", re.I)
# A HEDGE means the item is not an absence. Kept narrow on purpose: generic words like
# "return" appear in real Out items ("...will look to return Saturday") and must not cancel them.
NOT_OUT_RE = re.compile(r"\b(questionable|probable|game-time decision|"
                        r"(?:will|expected to|set to) play|cleared to play|"
                        r"upgraded to (?:available|probable|questionable))\b", re.I)
# A CHOICE is not a ruling (2026-10-24): "Embiid said he won't play in both legs of the back-to-back
# ... I'm playing in one of them" read as "Embiid out Saturday" and flagged Edgecombe. He will sit ONE
# of two games and has not said which. Narrow on purpose, like the hedge list: only wording that picks
# one game out of several. "Will miss one game" (no "of") stays an Out, and so does a specific night
# ("won't play Sunday, the second night of the back-to-back").
CHOICE_RE = re.compile(r"\b(?:won'?t|will not|not) (?:play|suit up|be available|dress) (?:in )?both\b|"
                       r"\b(?:play|playing|suit up|sit|sitting|rest|resting|miss|missing) (?:out )?"
                       r"(?:in )?(?:only )?(?:one|either) of\b|"
                       r"\bone of (?:them|the two|those|these|the (?:two |back-to-back )?(?:games|nights|legs))\b|"
                       r"\beither (?:game|night|leg|end)\b|\bonly one of\b", re.I)
# AMENDMENT 15: "doubtful" with no other hedge is an absence. Not "upgraded from doubtful", "no longer
# doubtful", or a doubtful that also says questionable / probable / game-time decision.
DOUBTFUL_RE = re.compile(r"\bdoubtful\b", re.I)
NOT_DOUBTFUL_RE = re.compile(r"\b(?:no longer|not|upgraded? from|removed? from|off)\b[\w\s]{0,12}?\bdoubtful\b", re.I)
SIT_CHOICE_RE = re.compile(r"\b(?:sit|sitting|rest|resting|miss|missing)(?: out)? (?:one|either)\b", re.I)
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def fold(s):
    n = unicodedata.normalize("NFKD", s or "")
    n = "".join(c for c in n if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", n.lower()).split())


def status_of(headline, body=""):
    """'out' only for unambiguous absence phrasing with no hedge. The HEADLINE decides when it
    says anything (RotoWire's: "Ruled out for Friday" / "Doubtful for Friday"); the body is used
    only when the headline is silent, because bodies narrate other games too."""
    for t in (headline, body):
        t = t or ""
        if OUT_RE.search(t):
            if NOT_OUT_RE.search(t):
                return "other"
            # a CHOICE between games is not a ruling (amendment 13) but is news (amendment 14)
            return "choice" if CHOICE_RE.search(t) else "out"
        if CHOICE_RE.search(t) and SIT_CHOICE_RE.search(t) and not NOT_OUT_RE.search(t):
            return "choice"                    # "will sit one of the two games" carries no Out verb
        if DOUBTFUL_RE.search(t):
            hedged = NOT_OUT_RE.search(t) or NOT_DOUBTFUL_RE.search(t) or CHOICE_RE.search(t)
            return "other" if hedged else "doubtful"
        if NOT_OUT_RE.search(t or ""):
            return "other"
    return "other"


def game_date_of(headline, body, now_et):
    """Which game the item is about. The HEADLINE first, then the body: tonight/today -> today;
    a weekday -> the next date with that weekday within 6 days (today counts). Bodies narrate
    past games ("after missing Wednesday's"), so a body only decides when the headline is silent.
    None when no day is named."""
    for t in ((headline or "").lower(), (body or "").lower()):
        if re.search(r"\b(tonight|today|this evening)\b", t):
            return now_et.date().isoformat()
        for i in range(7):
            d = now_et.date() + dt.timedelta(days=i)
            if re.search(rf"\b{DAYS[d.weekday()]}\b", t):
                return d.isoformat()
    return None


# ── sources: each returns [{item_id, player, team_name|None, headline, body, provenance}] ──

RW_SPLIT = r'<div class="(news-update(?: [^"]*)?)">'    # captures the class: injury items add one
RW_MAX = 40


def src_rotowire():
    h = requests.get("https://www.rotowire.com/basketball/news.php", headers=UA, timeout=20).text
    # ⚠️ INJURY ITEMS CARRY A SECOND CLASS: <div class="news-update is-injured">. The first version
    # split on the exact plain class and silently skipped EVERY injury item (2026-10-22: 13 stat
    # lines parsed, 0 of the page's injury items) — a news layer blind to injuries reads as a quiet
    # day. Split on the class prefix, and refuse a page whose injury items we failed to parse.
    parts = re.split(RW_SPLIT, h)
    pairs = list(zip(parts[1::2], parts[2::2]))[:RW_MAX]       # (class attribute, block html)
    # counted INDEPENDENTLY of the split, so a broken splitter cannot hide from it
    n_inj_page = sum(1 for c in re.findall(r'<div class="(news-update(?: [^"]*)?)">', h)[:RW_MAX]
                     if "is-injured" in c)
    out = []
    for cls, blk in pairs:
        m = re.search(r'news-update__player-link" href="[^"]*?-(\d+)">([^<]+)</a>.*?'
                      r'news-update__headline" href="[^"]*?-(\d+)">([^<]+)<', blk, re.S)
        if not m:
            continue
        team = re.search(r'news-update__pos">[^<]*</b>([^<]+)</div>', blk)
        body = re.search(r'news-update__news">(.*?)</div>', blk, re.S)
        btxt = re.sub(r"<[^>]+>", "", body.group(1)) if body else ""
        links = re.findall(r'href="(https?://[^"]+)"', body.group(1)) if body else []
        prov = ("official_report" if any("cms.nba.com/referee/injury" in u for u in links) else
                "x" if any(("twitter.com" in u or "x.com" in u) for u in links) else
                (links[0].split("/")[2] if links else "unsourced"))
        out.append({"item_id": m.group(3), "player": m.group(2).strip(),
                    "team_name": team.group(1).strip() if team else None,
                    "headline": m.group(4).strip(), "body": btxt.strip()[:400], "provenance": prov,
                    "_injured": "is-injured" in cls})
    n_inj_parsed = sum(1 for o in out if o["_injured"])
    if n_inj_parsed < n_inj_page:
        raise RuntimeError(f"RotoWire page has {n_inj_page} injury items, parsed {n_inj_parsed} — "
                           f"layout change; refusing a partial read")
    return out


def src_bsky():
    out = []
    for q in ("ruled out", "won't play tonight", "will not play"):
        r = requests.get("https://api.bsky.app/xrpc/app.bsky.feed.searchPosts",
                         params={"q": q, "limit": 25, "sort": "latest"}, headers=UA, timeout=15)
        for p in (r.json().get("posts") or []) if r.status_code == 200 else []:
            rec = p.get("record") or {}
            try:
                age = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(
                    rec.get("createdAt", "").replace("Z", "+00:00"))).total_seconds() / 60
            except ValueError:
                continue
            if age > 45:                              # search returns history; only fresh posts
                continue
            out.append({"item_id": p.get("uri"), "player": None, "team_name": None,
                        "headline": "", "body": (rec.get("text") or "").replace("\n", " ")[:400],
                        "provenance": "bsky:" + (p.get("author") or {}).get("handle", "?")})
    return out


X_STALE_MIN = 10                               # VM watcher silent this long = a dead source


X_LOCAL_HB_CMD = ("systemctl is-active underdog-watch; "
                  "journalctl -u underdog-watch -n 1 -o short-unix --no-pager | tail -1")


def _x_heartbeat(hb):
    """hb = ['active', '<unix ts of the watcher's last journal line>', ...] or it raises."""
    if not hb or hb[0] != "active":
        raise RuntimeError(f"VM underdog-watch is {hb[0] if hb else 'unknown'}")
    try:
        age = (dt.datetime.now(dt.timezone.utc).timestamp() - float(hb[1])) / 60
    except (IndexError, ValueError):
        age = 1e9
    if age > X_STALE_MIN:
        raise RuntimeError(f"VM underdog-watch silent for {age:.0f} min")


def src_x():
    """@UnderdogNBA, read by the VM's underdog-watch.service (it holds the burner cookie; the
    cookie never leaves the VM) into underdog_nba_log.jsonl. Configured by
    NBA_X_SSH="user@host:/path/to/underdog_nba_log.jsonl" (+ NBA_X_KEY, the ssh key); or a local
    copy via NBA_X_LOG. BENCHED when neither is set.

    The VM logs only status tweets (out/q/in/lineup), each with ITS first-seen time `t` (<= ~20 s
    after posting) — that, not our pull time, is the item's news time. A heartbeat rides along:
    the watcher prints a line every poll, so a silent journal means the source is dead, and that
    RAISES (a dead X source must not read as a quiet news day)."""
    import subprocess
    remote, local = os.environ.get("NBA_X_SSH"), os.environ.get("NBA_X_LOG")
    if remote:
        host, path = remote.split(":", 1)
        key = os.path.expanduser(os.environ.get("NBA_X_KEY", "~/.ssh/oracle_vm"))
        cmd = (f"tail -n 300 {path} 2>/dev/null; echo '@@HB'; systemctl is-active underdog-watch; "
               "journalctl -u underdog-watch -n 1 -o short-unix --no-pager | tail -1")
        r = subprocess.run(["ssh", "-i", key, "-o", "ConnectTimeout=10", "-o", "BatchMode=yes",
                            host, cmd], capture_output=True, text=True, timeout=40)
        if r.returncode != 0 or "@@HB" not in r.stdout:
            raise RuntimeError(f"ssh to the X watcher failed (rc {r.returncode})")
        body, hb = r.stdout.split("@@HB", 1)
        _x_heartbeat(hb.split())
        lines = body.splitlines()
    elif local and Path(local).exists():
        # ON THE VM (amendment 4): the same heartbeat, read locally — a dead watcher must raise
        # here too, not read as a quiet news day
        hb = subprocess.run(["sh", "-c", X_LOCAL_HB_CMD], capture_output=True, text=True,
                            timeout=20).stdout
        _x_heartbeat(hb.split())
        lines = Path(local).read_text().splitlines()[-300:]
    else:
        return None                                   # BENCHED
    out = []
    for line in lines:
        try:
            j = json.loads(line)
        except ValueError:
            continue
        if j.get("st") == "lineup":
            continue
        out.append({"item_id": str(j.get("id")), "player": None, "team_name": None,
                    "headline": "", "body": (j.get("text") or "")[:400],
                    # beat writers (nba_x_beats, amendment 10) write to the same log with an author
                    "provenance": f"x:{j['author']}" if j.get("author") else "x:underdog",
                    "seen_at": j.get("t")})
    return out


SOURCES = {"rotowire": src_rotowire, "bsky": src_bsky, "x": src_x}


def resolve(item, index, playing_by_date, now_et):
    """-> (pid, name, team, game_date) or None. RotoWire carries the team, so match within it;
    free text (bsky/x) must contain the EXACT full name of exactly one player whose team plays
    on the named date — never a surname guess (reference_name_key_collapse)."""
    text = f"{item['headline']} {item['body']}"
    gdate = game_date_of(item["headline"], item["body"], now_et)
    if not gdate or gdate not in playing_by_date:
        return None
    teams = playing_by_date[gdate]
    if item.get("team_name"):
        tri = I.TEAMS.get(item["team_name"])
        if tri not in teams:
            return None
        cands = [(p, n) for p, (t, n, _) in index.items()
                 if t == tri and fold(n) == fold(item["player"])]
    else:
        ft = f" {fold(text)} "
        cands = [(p, n) for p, (t, n, _) in index.items()
                 if t in teams and len(fold(n).split()) >= 2 and f" {fold(n)} " in ft]
    if len(cands) != 1:
        return None
    pid, name = cands[0]
    return pid, name, index[pid][0], gdate


# AMENDMENT 17: a post naming several players ("Jalen Green doubtful, Oso Ighodaro out for Warriors vs.
# Suns on Saturday") is read clause by clause, and each clause naming exactly one player gets its own
# status. "Doubtful: A, B" lines give every named player the label. Bare "out" counts only as a short
# clause's last word or before a time/game phrase ("Al Horford also out"), never "worked out at ...".
LABEL_LINE_RE = re.compile(r"^\W*(out|doubtful|questionable|probable|available|game-time decision|gtd)"
                           r"\s*:\s*(.+)$", re.I)
CLAUSE_SPLIT_RE = re.compile(r"[,;&\n]|\band\b|(?<=[a-z0-9)])\.\s+(?=[A-Z])")
BARE_OUT_RE = re.compile(r"\bout(?:\s+(?:tonight|today|for\b.*|vs\b.*|against\b.*|on\b.*|" + "|".join(
    ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]) + r"))?\W*$", re.I)


def _named(text, index, teams):
    ft = f" {fold(text)} "
    return [(p, n) for p, (t, n, _) in index.items()
            if t in teams and len(fold(n).split()) >= 2 and f" {fold(n)} " in ft]


def clause_status(clause):
    st = status_of("", clause)
    if (st == "other" and len(clause.split()) <= 8 and BARE_OUT_RE.search(clause)
            and not NOT_OUT_RE.search(clause) and not CHOICE_RE.search(clause)):
        st = "out"
    return st


def split_list(item, index, playing_by_date, now_et):
    """AMENDMENT 17: [(pid, name, team, game_date, status)] for each player of a MULTI-player post whose
    own clause (or labelled line) reads out / doubtful. [] for a one-player post or no playing date."""
    text = f"{item['headline']}\n{item['body']}"
    gdate = game_date_of(item["headline"], item["body"], now_et)
    if not gdate or gdate not in playing_by_date or item.get("team_name"):
        return []
    teams = playing_by_date[gdate]
    if len(_named(text, index, teams)) < 2:
        return []
    found = {}
    for line in text.splitlines():
        m = LABEL_LINE_RE.match(line)
        if m:
            st = {"out": "out", "doubtful": "doubtful"}.get(m.group(1).lower())
            for p, n in (_named(m.group(2), index, teams) if st else []):
                found.setdefault(p, (n, st))
            continue
        for clause in CLAUSE_SPLIT_RE.split(line):
            named = _named(clause, index, teams)
            if len(named) == 1 and clause_status(clause) in ("out", "doubtful"):
                found.setdefault(named[0][0], (named[0][1], clause_status(clause)))
    return [(p, n, index[p][0], gdate, st) for p, (n, st) in found.items()]


def store_list(con, name, it, subs, seen_at):
    """Store each split absence as its own item `{item}#{pid}`; returns the NEW ones as poll outs."""
    new = []
    for pid, pname, tri, gdate, st in subs:
        cur = con.execute("INSERT OR IGNORE INTO news_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                          (name, f"{it['item_id']}#{pid}", seen_at, pname, pid, tri, gdate, st,
                           it["headline"], it["body"], it["provenance"], 0))
        if cur.rowcount:
            new.append((name, pid, pname, tri, gdate, seen_at))
    return new


def poll(now=None, sources=None, con=None):
    """Poll enabled sources; store every NEW item (Out-class or not, for the journal).
    Returns [(source, pid, name, team, game_date, detected_at)] for new OUT items."""
    now = now or dt.datetime.now(dt.timezone.utc)
    now_et = now.astimezone(ET)
    own = con is None
    con = con or sqlite3.connect(DB, timeout=60)
    _migrate(con)
    index, _ = R.player_index(now_et.date().isoformat())
    sched = R.schedule()
    playing = {}
    for g in sched:
        if g["status"] == 1:
            playing.setdefault(g["date_et"], set()).update((g["home"], g["away"]))
    horizon = (now_et.date() + dt.timedelta(days=3)).isoformat()
    team_games = {}                                   # team -> its game dates in the next 3 days
    for g in sched:
        if now_et.date().isoformat() <= g["date_et"] <= horizon:
            for t in (g["home"], g["away"]):
                team_games.setdefault(t, set()).add(g["date_et"])
    new_outs, errors = [], []
    for name in (sources or SOURCES):
        try:
            items = SOURCES[name]()
        except Exception as e:                        # one dead source must not stop the rest
            errors.append(f"{name}: {type(e).__name__}: {str(e)[:100]}")
            continue
        if items is None:
            continue                                  # benched
        # FIRST POLL OF A SOURCE = SEED. Everything already on the page predates us: its "first
        # seen" is just "first polled", and an old Out the report never listed would fire as fresh
        # news. Seeded rows are stored for the record but never trigger and never enter the journal.
        # keyed on "first time POLLED", not "no rows yet": a source whose first poll is empty (the
        # X log right after the switch to @UnderdogNBA) would otherwise swallow its first REAL item
        seed = not con.execute("SELECT 1 FROM news_sources WHERE source=?", (name,)).fetchone()
        if seed:
            con.execute("INSERT INTO news_sources VALUES (?,?)", (name, now.isoformat()))
        for it in items:
            if con.execute("SELECT 1 FROM news_items WHERE source=? AND item_id=?",
                           (name, it["item_id"])).fetchone():
                continue
            st = status_of(it["headline"], it["body"])
            hit = resolve(it, index, playing, now_et)
            pid, pname, tri, gdate = hit if hit else (None, it.get("player"), None, None)
            seen_at = it.get("seen_at") or now.isoformat()
            con.execute("INSERT INTO news_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (name, it["item_id"], seen_at, pname, pid, tri, gdate, st,
                         it["headline"], it["body"], it["provenance"], int(seed)))
            if st in ("out", "doubtful") and pid and not seed:
                new_outs.append((name, pid, pname, tri, gdate, seen_at))
            if not hit and not seed:                  # amendment 17: a list post, player by player
                new_outs += store_list(con, name, it, split_list(it, index, playing, now_et), seen_at)
            if st == "choice" and not seed:
                register_choice(con, it, index, team_games, now_et, now)
    con.commit()
    if own:
        con.close()
    return new_outs, errors


def reread_lists(now=None, con=None):
    """One-off (amendment 17): today's stored, unresolved, unseeded items re-read player by player.
    Each item's day words are read from the time it was first seen. Returns the new absences as poll
    outs [(source, pid, name, team, game_date, detected_at)]."""
    now = now or dt.datetime.now(dt.timezone.utc)
    own = con is None
    con = con or sqlite3.connect(DB, timeout=60)
    _migrate(con)
    index, _ = R.player_index(now.astimezone(ET).date().isoformat())
    playing = {}
    for g in R.schedule():
        if g["status"] == 1:
            playing.setdefault(g["date_et"], set()).update((g["home"], g["away"]))
    day0 = (now - dt.timedelta(hours=24)).isoformat()
    new = []
    for src, iid, at, hl, body, prov in con.execute(
            "SELECT source, item_id, detected_at, headline, body, provenance FROM news_items WHERE pid IS NULL "
            "AND COALESCE(seeded,0)=0 AND detected_at >= ? AND item_id NOT LIKE '%#%'", (day0,)).fetchall():
        it = {"item_id": iid, "headline": hl or "", "body": body or "", "provenance": prov}
        seen_et = dt.datetime.fromisoformat(at).astimezone(ET)
        new += store_list(con, src, it, split_list(it, index, playing, seen_et), at)
    con.commit()
    if own:
        con.close()
    return new


def reclassify_choices(now=None, con=None):
    """One-off (amendment 14): stored items the corrected classifier reads as a choice are relabelled
    `choice` and registered as pending choices. Returns [(item_id, registered)]."""
    now = now or dt.datetime.now(dt.timezone.utc)
    now_et = now.astimezone(ET)
    own = con is None
    con = con or sqlite3.connect(DB, timeout=60)
    _migrate(con)
    index, _ = R.player_index(now_et.date().isoformat())
    horizon = (now_et.date() + dt.timedelta(days=3)).isoformat()
    team_games = {}
    for g in R.schedule():
        if now_et.date().isoformat() <= g["date_et"] <= horizon:
            for t in (g["home"], g["away"]):
                team_games.setdefault(t, set()).add(g["date_et"])
    out = []
    for src, iid, h, b, prov, st in con.execute(
            "SELECT source, item_id, headline, body, provenance, status FROM news_items").fetchall():
        if st != "choice" and status_of(h or "", b or "") == "choice":
            con.execute("UPDATE news_items SET status='choice' WHERE source=? AND item_id=?", (src, iid))
            reg = register_choice(con, {"item_id": iid, "headline": h, "body": b, "provenance": prov},
                                  index, team_games, now_et, now)
            out.append((iid, reg))
    con.commit()
    if own:
        con.close()
    return out


def news_outs(game_date, con=None):
    """{pid: (name, team, earliest_detected_at, source, status)} — news Outs and Doubtfuls (amendment
    15) for game_date that NO later official report contradicts (a status outside I.ABSENT for that
    player-game published after the item). status is "Out" if any item says out, else "Doubtful"."""
    own = con is None
    con = con or sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT pid, player, team, MIN(detected_at), source FROM news_items "
                           "WHERE game_date=? AND status IN ('out', 'doubtful') AND pid IS NOT NULL "
                           "AND COALESCE(seeded,0)=0 GROUP BY pid", (game_date,)).fetchall()
        said_out = {p for (p,) in con.execute("SELECT DISTINCT pid FROM news_items WHERE game_date=? "
                                              "AND status='out' AND COALESCE(seeded,0)=0", (game_date,))}
    except sqlite3.OperationalError:
        rows, said_out = [], set()
    out = {}
    for pid, name, team, first, src in rows:
        contra = con.execute(
            f"SELECT 1 FROM snapshots WHERE game_date=? AND pid=? AND NOT {I.ABSENT_SQL} AND "
            "published_at > ? LIMIT 1", (game_date, pid, first)).fetchone()
        if not contra:
            out[pid] = (name, team, first, src, "Out" if pid in said_out else "Doubtful")
    if own:
        con.close()
    return out


def journal():
    """Lead of each news Out over the league's first published Out for the same player-game."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = con.execute("""
        SELECT n.source, n.provenance, n.player, n.game_date, MIN(n.detected_at),
               (SELECT MIN(s.published_at) FROM snapshots s
                 WHERE s.pid = n.pid AND s.game_date = n.game_date AND s.status IN ('Out', 'Doubtful'))
        FROM news_items n WHERE n.status IN ('out', 'doubtful') AND n.pid IS NOT NULL AND COALESCE(n.seeded,0)=0
        GROUP BY n.source, n.pid, n.game_date ORDER BY 5""").fetchall()
    if not rows:
        print("news journal: no resolved news Outs yet")
        return
    print(f"{'source':<9}{'provenance':<17}{'player':<24}{'game':<12}{'news seen':>10}"
          f"{'official':>10}{'lead (min)':>12}")
    for src, prov, pl, gd, seen, off in rows:
        lead = ((dt.datetime.fromisoformat(off) - dt.datetime.fromisoformat(seen))
                .total_seconds() / 60) if off else None
        print(f"{src:<9}{(prov or '')[:16]:<17}{(pl or '')[:23]:<24}{gd:<12}{seen[11:16]:>10}"
              f"{(off[11:16] if off else 'never'):>10}"
              f"{(f'{lead:+.1f}' if lead is not None else 'unconfirmed'):>12}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--journal", action="store_true")
    a = ap.parse_args()
    if a.journal:
        journal()
    else:
        outs, errs = poll()
        for e in errs:
            print(f"  !! source error: {e}")
        for src, pid, name, tri, gd, at in outs:
            print(f"  NEWS OUT [{src}] {name} ({tri}) for {gd} — seen {at[11:19]} UTC")
        print(f"nba news: {len(outs)} new Out item(s)")
