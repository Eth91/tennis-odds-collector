"""Amendment 17: multi-player posts read player by player (the three real 2026-10-24 posts), and a stray
FILE at the cycle-lock path is removed. MUTANTS in test_mutants()."""
import datetime as dt
import importlib
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_injury_report as I
import nba_news_watch as NW
import nba_watch as W

SAT = dt.datetime(2026, 10, 24, 17, 37, tzinfo=NW.ET)
INDEX = {1630224: ("PHX", "Jalen Green", "G"), 1631367: ("PHX", "Oso Ighodaro", "F"),
         203110: ("GSW", "Draymond Green", "F"), 201143: ("GSW", "Al Horford", "C"),
         1630228: ("GSW", "Brandin Podziemski", "G"), 201939: ("GSW", "Stephen Curry", "G"),
         202681: ("DAL", "Kyrie Irving", "G"), 1642843: ("DAL", "Cooper Flagg", "F"),
         2544: ("LAL", "LeBron James", "F"), 1629029: ("LAL", "Luka Dončić", "G")}
PLAYING = {"2026-10-24": {"PHX", "GSW", "DAL", "SAS", "LAL", "BOS"}}
POSTS = {
    "rotoballer": ("Jalen Green doubtful, Oso Ighodaro out for Warriors vs. Suns on Saturday (@DuaneRankin)",
                   {1630224: "doubtful", 1631367: "out"}),
    "slater": ("Steph Curry officially ruled out tonight in Phoenix for the Warriors first back-to-back. Right knee "
               "management. Brandin Podziemski and Al Horford also out. Draymond Green is doubtful.",
               {201143: "out", 203110: "doubtful"}),
    "label": ("Injury news for tonight\nDoubtful: Draymond Green, Kyrie Irving\nQuestionable: Cooper Flagg",
              {203110: "doubtful", 202681: "doubtful"}),
    "hedged": ("Kyrie Irving will play tonight, Cooper Flagg ruled out", {1642843: "out"}),
    "worked out": ("LeBron James worked out at shootaround tonight and Luka Dončić is questionable", {}),
    "one player": ("Jalen Green doubtful for Saturday", {}),          # one-player posts: the old path
    "surname only": ("Curry, Ighodaro out, Green doubtful tonight", {}),   # Rankin: never resolves
}


def check(nw):
    ok = True
    for tag, (body, want) in POSTS.items():
        got = {p: st for p, _, _, _, st in nw.split_list({"headline": "", "body": body}, INDEX, PLAYING, SAT)}
        good = got == want
        ok &= good
        print(f"   {'ok ' if good else 'BAD'} {tag}: {got}")
    return ok


def test_split_list():
    assert check(NW)


def test_store_list_once():
    con = sqlite3.connect(":memory:")
    con.executescript(I.DDL)
    NW._migrate(con)
    it = {"item_id": "2114108943777562818", "headline": "", "body": POSTS["rotoballer"][0], "provenance": "x:RotoBallerNBA"}
    subs = NW.split_list(it, INDEX, PLAYING, SAT)
    new = NW.store_list(con, "x", it, subs, "2026-10-24T21:37:38+00:00")
    again = NW.store_list(con, "x", it, subs, "2026-10-24T21:37:38+00:00")
    assert sorted(n[1] for n in new) == [1630224, 1631367] and again == []
    # amendment 22: RotoBaller is an aggregator, so its word alone does not trigger...
    assert 1630224 not in NW.news_outs("2026-10-24", con=con)
    # ...until a trusted source has him; the news time stays RotoBaller's (the earliest).
    con.execute("INSERT INTO news_items (source, item_id, detected_at, player, pid, team, game_date, status, "
                "headline, body, provenance) VALUES ('x','ud1','2026-10-24T21:50:00+00:00','Jalen Green',1630224,"
                "'PHX','2026-10-24','doubtful','','','x:underdog')")
    got = NW.news_outs("2026-10-24", con=con)[1630224]
    assert got[2] == "2026-10-24T21:37:38+00:00" and got[4] == "Doubtful", got


def test_aggregator_classes():
    agg = ["bsky:rotowirenba.bsky.social", "x:RotoBallerNBA", "x:FantasyLabsNBA", "unsourced", "x", ""]
    trusted = ["x:underdog", "x:anthonyVslater", "x:ShamsCharania", "official_report", "inferred:x:underdog"]
    assert all(NW.aggregator(p) for p in agg) and not any(NW.aggregator(p) for p in trusted)


def test_stray_lock_file_is_cleared():
    d = pathlib.Path(tempfile.mkdtemp())
    W.LOCK = d / "nba-cycle.lock"
    W.LOCK.write_text("")                            # what the 2026-10-24 21:46Z script left behind
    with W.cycle_lock() as got:
        assert got and W.LOCK.is_dir()
    assert not W.LOCK.exists()


def test_mutants():
    src = pathlib.Path(NW.__file__).read_text()
    for tag, a, b in (
            ("no clause split", 'CLAUSE_SPLIT_RE = re.compile(r"[,;&\\n]|\\band\\b|(?<=[a-z0-9)])\\.\\s+(?=[A-Z])")',
             'CLAUSE_SPLIT_RE = re.compile(r"\\n")'),
            ("label lines ignored", "        if m:\n            st = {", "        if False:\n            st = {"),
            ("bare out anywhere", '    if (st == "other" and len(clause.split()) <= 8 and BARE_OUT_RE.search(clause)',
             '    if (st == "other" and " out" in clause')):
        assert src.count(a) == 1, tag
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_news_watch_mut17.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            print(f"MUTANT ({tag}) — must fail:")
            assert not check(importlib.import_module("nba_news_watch_mut17")), tag
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_news_watch_mut17", None)


if __name__ == "__main__":
    test_split_list(); test_store_list_once(); test_stray_lock_file_is_cleared(); test_mutants()
    print("test_nba_lists: OK")
