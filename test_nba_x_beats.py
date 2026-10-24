"""nba_x_beats (amendment 10): status vocabulary on beat-writer prose, query packing under X's cap,
author extraction from a SearchTimeline payload, the log format nba_news_watch reads, and its
provenance tag. MUTANTS in test_mutants()."""
import importlib
import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nba_news_watch as N
import nba_x_beats as X

PAYLOAD = {"search_by_raw_query": {"search_timeline": {"timeline": {"instructions": [{"entries": [
    {"content": {"itemContent": {"tweet_results": {"result": {
        "rest_id": "11", "core": {"user_results": {"result": {"core": {"screen_name": "IanBegley"}}}},
        "legacy": {"full_text": "Jalen Brunson (ankle) will not play tonight vs. Boston, Tom Thibodeau says."}}}}}},
    {"content": {"itemContent": {"tweet_results": {"result": {
        "rest_id": "12", "core": {"user_results": {"result": {"legacy": {"screen_name": "ShamsCharania"}}}},
        "legacy": {"full_text": "Sources: Micah Peavy has agreed on a two-way deal."}}}}}}]}]}}}}


def check(mod):
    ok = True

    def want(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"   {'ok ' if cond else 'BAD'} {label}")
    want(mod.status("Jalen Brunson (ankle) will not play tonight vs. Boston") == "out", "beat prose 'will not play' = out")
    want(mod.status("Embiid is doubtful for Saturday") == "out", "doubtful counts as out (as the Underdog watcher)")
    want(mod.status("Murray is questionable (hamstring)") == "q", "questionable = q")
    want(mod.status("Edwards is available tonight") == "in", "available = in")
    want(mod.status("Brunson has been removed from the injury report and will play") is None,
         "removed from the injury report = no news (as the Underdog watcher), even with 'will play'")
    want(mod.status("Sources: Peavy has agreed on a two-way deal") is None, "a signing is not an injury status")
    hs = [h for h, _ in mod.HANDLES]
    qs = mod.chunks(hs)
    want(all(len(q) <= mod.MAX_QUERY for q in qs) and sorted(sum((q.replace("from:", "").split(" OR ") for q in qs), []))
         == sorted(hs), "every handle in exactly one query, each under the length cap")
    posts = {i: (t, a) for i, t, a in mod.posts_of(PAYLOAD)}
    want(posts.get("11", ("", ""))[1] == "IanBegley" and posts.get("12", ("", ""))[1] == "ShamsCharania",
         "author read from both payload shapes (core.screen_name and legacy.screen_name)")
    d = pathlib.Path(tempfile.mkdtemp())
    mod.LOG = d / "x.jsonl"
    fresh, n = mod.log_new(mod.posts_of(PAYLOAD), set(), first=False)
    lines = [json.loads(x) for x in mod.LOG.read_text().splitlines()]
    want(n == 1 and len(fresh) == 2 and lines[0]["author"] == "IanBegley" and lines[0]["st"] == "out",
         "only the injury status is logged, with its author; both posts marked seen")
    mod.LOG.write_text("")
    fresh, n = mod.log_new(mod.posts_of(PAYLOAD), set(), first=True)
    want(n == 0 and len(fresh) == 2 and mod.LOG.read_text() == "", "first run = backlog marked seen, nothing logged")
    return ok


def test_x_beats():
    assert check(X)


def test_news_watch_provenance():
    import os
    d = pathlib.Path(tempfile.mkdtemp()) / "x.jsonl"
    d.write_text(json.dumps({"t": "2026-10-24T20:00:00+00:00", "id": "11", "text": "x", "st": "out",
                             "author": "IanBegley"}) + "\n" +
                 json.dumps({"t": "2026-10-24T20:00:00+00:00", "id": "12", "text": "y", "st": "out"}) + "\n")
    saved, cmd = os.environ.get("NBA_X_LOG"), N.X_LOCAL_HB_CMD
    os.environ.pop("NBA_X_SSH", None)
    os.environ["NBA_X_LOG"] = str(d)
    import datetime as dt
    N.X_LOCAL_HB_CMD = f"echo active; echo {dt.datetime.now(dt.timezone.utc).timestamp():.0f}"
    try:
        items = N.src_x()
    finally:
        N.X_LOCAL_HB_CMD = cmd
        os.environ.pop("NBA_X_LOG", None)
        if saved is not None:
            os.environ["NBA_X_LOG"] = saved
    assert [i["provenance"] for i in items] == ["x:IanBegley", "x:underdog"]


def test_mutants():
    src = pathlib.Path(X.__file__).read_text()
    for name, a, b in (("skip rule off", "    if SKIP_RX.search(txt):\n        return None\n", ""),
                       ("no length cap", "if cur and len(trial) > limit:", "if False:"),
                       ("first run logs backlog", "st = None if first else status(txt)", "st = status(txt)")):
        assert src.count(a) == 1, name
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "nba_x_beats_mut.py").write_text(src.replace(a, b))
        sys.path.insert(0, str(d))
        try:
            print(f"MUTANT ({name}) — must fail:")
            assert not check(importlib.import_module("nba_x_beats_mut")), name
        finally:
            sys.path.remove(str(d))
            sys.modules.pop("nba_x_beats_mut", None)


if __name__ == "__main__":
    test_x_beats()
    test_news_watch_provenance()
    test_mutants()
    print("test_nba_x_beats: OK")
