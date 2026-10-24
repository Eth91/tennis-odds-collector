"""nba_news_watch: classifier, day parsing, add-only/contradiction. A MUTANT that ignores a later
official contradiction must fail."""
import datetime as dt
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_news_watch as N

THU = dt.datetime(2026, 10, 22, 16, 30, tzinfo=N.ET)


def test_classifier():
    cases = [("Ruled out for Friday", "", "out"), ("Won't suit up Friday", "", "out"),
             ("Doubtful for Friday", "", "other"), ("Remains out for Friday", "", "out"),
             ("Missing second straight game", "Martin (thumb) won't play Friday.", "out"),
             ("Won't play Friday", "He'll look to return Saturday.", "out"),
             ("Questionable for Friday", "", "other"), ("Iffy for Friday", "", "other"),
             ("Likely to play Friday", "", "other"), ("Quiet in season debut", "9 points.", "other")]
    for h, b, want in cases:
        assert N.status_of(h, b) == want, (h, b)


def test_day_parse_headline_first():
    assert N.game_date_of("Ruled out for Friday", "after missing Wednesday's game", THU) == "2026-10-23"
    assert N.game_date_of("Out tonight", "", THU) == "2026-10-22"
    assert N.game_date_of("Big night", "won't play Saturday", THU) == "2026-10-24"
    assert N.game_date_of("Big night", "no day here", THU) is None


def _db(official_status, official_after_news):
    d = pathlib.Path(tempfile.mkdtemp()) / "n.sqlite"
    con = sqlite3.connect(d)
    con.executescript(N.I.DDL)
    N._migrate(con)
    con.execute("INSERT INTO news_items (source, item_id, detected_at, player, pid, team, game_date, "
                "status, headline, body, provenance) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                ("rotowire", "1", "2026-10-22T19:00:00+00:00", "P", 7, "NYK", "2026-10-23", "out",
                 "Ruled out for Friday", "", "x"))
    pub = "2026-10-22T19:15:04+00:00" if official_after_news else "2026-10-22T18:45:04+00:00"
    con.execute("INSERT INTO snapshots VALUES (?,?,?,?,?,?,?,?,?)",
                ("m", pub, "2026-10-23", "NYK@BOS", "NYK", 7, "P", official_status, ""))
    con.commit()
    return con


def check(fn):
    later_q = 7 in fn("2026-10-23", con=_db("Questionable", official_after_news=True))
    earlier_q = 7 in fn("2026-10-23", con=_db("Questionable", official_after_news=False))
    later_out = 7 in fn("2026-10-23", con=_db("Out", official_after_news=True))
    return (not later_q) and earlier_q and later_out


def test_add_only_and_contradiction():
    assert check(N.news_outs)


def test_mutant_ignoring_contradiction_fails():
    def mutant(game_date, con):
        return {p: (n, t, f, s) for p, n, t, f, s in con.execute(
            "SELECT pid, player, team, MIN(detected_at), source FROM news_items WHERE game_date=? "
            "AND status='out' AND pid IS NOT NULL GROUP BY pid", (game_date,))}
    assert not check(mutant)


if __name__ == "__main__":
    test_classifier(); test_day_parse_headline_first(); test_add_only_and_contradiction()
    test_mutant_ignoring_contradiction_fails()
    print("test_nba_news: OK")


# The poll reads the LIVE schedule for which teams play tonight/tomorrow. These two tests are pinned
# to 2026-10-22/23, so they need that slate as it was, not as it is now: once NYK's 10-23 game
# finished (status 3) they failed for a reason that had nothing to do with the code (2026-10-24).
FIXED_SLATE = [{"date_et": "2026-10-23", "status": 1, "home": "NYK", "away": "MIA",
                "gid": "0022600099", "utc": "2026-10-23T23:30:00Z"}]


def _pinned_schedule():
    saved = N.R.schedule
    N.R.schedule = lambda: FIXED_SLATE
    return saved


def test_first_poll_of_a_source_seeds_and_never_triggers():
    d = pathlib.Path(tempfile.mkdtemp()) / "n.sqlite"
    con = sqlite3.connect(d)
    con.executescript(N.I.DDL)
    item = {"item_id": "1", "player": "Jalen Brunson", "team_name": "New York Knicks",
            "headline": "Ruled out for Friday", "body": "", "provenance": "x"}
    saved = N.SOURCES
    saved_sched = _pinned_schedule()
    N.SOURCES = {"fake": lambda: [item]}
    try:
        outs1, _ = N.poll(now=dt.datetime(2026, 10, 22, 20, 0, tzinfo=dt.timezone.utc), con=con)
        item2 = dict(item, item_id="2")
        N.SOURCES = {"fake": lambda: [item, item2]}
        outs2, _ = N.poll(now=dt.datetime(2026, 10, 22, 20, 1, tzinfo=dt.timezone.utc), con=con)
    finally:
        N.SOURCES = saved
        N.R.schedule = saved_sched
    assert outs1 == []                                    # the backlog never fires
    assert len(outs2) == 1                                # a genuinely new item does
    assert con.execute("select seeded from news_items where item_id='1'").fetchone()[0] == 1


def test_underdog_phrasings():
    cases = [("Anthony Black (ankle) listed out for Friday.", "out"),
             ("Keefe: AJ Dybantsa (ankle) ruled out for Friday; remains day-to-day.", "out"),
             ("Jewell Loyd (leg) listed out Wednesday.", "out"),
             ("Jewell Loyd (leg) downgraded to doubtful for Wednesday.", "other"),
             ("Josh Giddey (wrist) listed probable for Friday.", "other"),
             ("Aaron Nesmith (hamstring) listed questionable for Friday.", "other"),
             ("Jarrett Allen (knee) plans to play Thursday, per @realDCunningham.", "other"),
             ("Status alert: Allisha Gray (hand) a game-time decision Friday.", "other")]
    for txt, want in cases:
        assert N.status_of("", txt) == want, txt


def test_a_choice_is_not_a_ruling():
    """2026-10-24: Embiid's 'won't play in both ... playing in one of them' was read as Out Saturday."""
    cases = [("Joel Embiid said he won't play in both legs of Sixers' back-to-back set on Saturday and "
              "Sunday. \"I'm playing in one of them.\"", "other"),
             ("Sixers say Embiid will sit one of the two games this weekend.", "other"),
             ("Embiid won't play both games of the back-to-back, Nurse said.", "other"),
             ("LeBron will rest either game of the back-to-back; no decision yet.", "other"),
             ("Embiid won't play Sunday, the second night of the back-to-back.", "out"),
             ("Jalen Brunson will miss one game with an ankle sprain, the Knicks said.", "out"),
             ("Trae Young (knee) won't play Friday; unclear when he returns.", "out")]
    for txt, want in cases:
        assert N.status_of("", txt) == want, txt


def test_empty_first_poll_does_not_swallow_the_first_real_item():
    """The X log was empty right after the switch to @UnderdogNBA. Seeding keyed on 'no rows yet'
    would have treated the first REAL ruling as backlog; it is keyed on 'first poll'."""
    d = pathlib.Path(tempfile.mkdtemp()) / "n.sqlite"
    con = sqlite3.connect(d)
    con.executescript(N.I.DDL)
    item = {"item_id": "9", "player": "Jalen Brunson", "team_name": "New York Knicks",
            "headline": "Ruled out for Friday", "body": "", "provenance": "x"}
    saved = N.SOURCES
    saved_sched = _pinned_schedule()
    try:
        N.SOURCES = {"fake": lambda: []}
        o1, _ = N.poll(now=dt.datetime(2026, 10, 22, 20, 0, tzinfo=dt.timezone.utc), con=con)
        N.SOURCES = {"fake": lambda: [item]}
        o2, _ = N.poll(now=dt.datetime(2026, 10, 22, 20, 1, tzinfo=dt.timezone.utc), con=con)
    finally:
        N.SOURCES = saved
        N.R.schedule = saved_sched
    assert o1 == [] and len(o2) == 1


def _local_x(path, hb_cmd):
    """src_x in local mode (the VM, amendment 4) with a stand-in for the watcher heartbeat."""
    import os
    saved = {k: os.environ.get(k) for k in ("NBA_X_SSH", "NBA_X_LOG")}
    saved_cmd = N.X_LOCAL_HB_CMD
    os.environ.pop("NBA_X_SSH", None)
    os.environ["NBA_X_LOG"] = str(path)
    N.X_LOCAL_HB_CMD = hb_cmd
    try:
        return N.src_x()
    finally:
        N.X_LOCAL_HB_CMD = saved_cmd
        for k, v in saved.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v


def test_x_local_mode_raises_on_a_dead_or_silent_watcher():
    """On the VM the X log is read locally; a stopped watcher, or one whose journal went quiet,
    must RAISE — not read as a quiet news day."""
    d = pathlib.Path(tempfile.mkdtemp()) / "x.jsonl"
    d.write_text("")
    old = dt.datetime.now(dt.timezone.utc).timestamp() - 3600
    for cmd, why in (("echo inactive", "stopped"), (f"echo active; echo {old:.0f}", "silent an hour"),
                     ("true", "no heartbeat at all")):
        try:
            _local_x(d, cmd)
        except RuntimeError:
            continue
        raise AssertionError(f"local X mode did not raise for a watcher that is {why}")


def test_x_reader_uses_the_vms_first_seen_time_and_skips_lineups(monkeypatch=None):
    import json, os
    d = pathlib.Path(tempfile.mkdtemp()) / "x.jsonl"
    d.write_text("\n".join(json.dumps(r) for r in (
        {"t": "2026-10-22T16:17:05+00:00", "id": "1", "text": "Keefe: AJ Dybantsa (ankle) ruled out for Friday.", "st": "out"},
        {"t": "2026-10-22T18:00:00+00:00", "id": "2", "text": "Lineup alert: Knicks will start ...", "st": "lineup"})))
    items = _local_x(d, f"echo active; echo {dt.datetime.now(dt.timezone.utc).timestamp():.0f}")
    assert [i["item_id"] for i in items] == ["1"]
    assert items[0]["seen_at"] == "2026-10-22T16:17:05+00:00" and items[0]["provenance"] == "x:underdog"
