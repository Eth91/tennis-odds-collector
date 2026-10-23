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


def _migrate(con):
    con.execute(DDL)
    con.execute("CREATE TABLE IF NOT EXISTS news_sources (source TEXT PRIMARY KEY, "
                "first_polled_at TEXT)")
    if "seeded" not in {r[1] for r in con.execute("PRAGMA table_info(news_items)")}:
        con.execute("ALTER TABLE news_items ADD COLUMN seeded INTEGER DEFAULT 0")

# OUT-class phrasing only. "Doubtful"/"questionable" are not absences and never trigger.
OUT_RE = re.compile(r"\b(ruled out|listed out|won'?t (?:play|suit up|be available|dress)|will not "
                    r"(?:play|suit up|be available|dress)|will miss|out for|inactive for|"
                    r"sidelined for|not (?:playing|available)|remains out|listed as out)\b", re.I)
# A HEDGE means the item is not an absence. Kept narrow on purpose: generic words like
# "return" appear in real Out items ("...will look to return Saturday") and must not cancel them.
NOT_OUT_RE = re.compile(r"\b(questionable|doubtful|probable|game-time decision|"
                        r"(?:will|expected to|set to) play|cleared to play|"
                        r"upgraded to (?:available|probable|questionable))\b", re.I)
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
        if OUT_RE.search(t or ""):
            return "other" if NOT_OUT_RE.search(t or "") else "out"
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
                    "provenance": "x:underdog", "seen_at": j.get("t")})
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
            if st == "out" and pid and not seed:
                new_outs.append((name, pid, pname, tri, gdate, seen_at))
    con.commit()
    if own:
        con.close()
    return new_outs, errors


def news_outs(game_date, con=None):
    """{pid: (name, team, earliest_detected_at, source)} — news Outs for game_date that NO later
    official report contradicts (a non-Out status for that player-game published after the item)."""
    own = con is None
    con = con or sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT pid, player, team, MIN(detected_at), source FROM news_items "
                           "WHERE game_date=? AND status='out' AND pid IS NOT NULL "
                           "AND COALESCE(seeded,0)=0 GROUP BY pid", (game_date,)).fetchall()
    except sqlite3.OperationalError:
        rows = []
    out = {}
    for pid, name, team, first, src in rows:
        contra = con.execute(
            "SELECT 1 FROM snapshots WHERE game_date=? AND pid=? AND status!='Out' AND "
            "published_at > ? LIMIT 1", (game_date, pid, first)).fetchone()
        if not contra:
            out[pid] = (name, team, first, src)
    if own:
        con.close()
    return out


def journal():
    """Lead of each news Out over the league's first published Out for the same player-game."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = con.execute("""
        SELECT n.source, n.provenance, n.player, n.game_date, MIN(n.detected_at),
               (SELECT MIN(s.published_at) FROM snapshots s
                 WHERE s.pid = n.pid AND s.game_date = n.game_date AND s.status = 'Out')
        FROM news_items n WHERE n.status='out' AND n.pid IS NOT NULL AND COALESCE(n.seeded,0)=0
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
