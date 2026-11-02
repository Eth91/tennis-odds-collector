"""nba_cup: NBA.com's Cup labels, cached (a finished season once, the current one daily, a failure retried in an hour)."""
import datetime as dt
import json

import nba_cup as NC

T0 = dt.datetime(2026, 11, 2, 9, 0, tzinfo=dt.timezone.utc)


def sched(*games):
    return {"leagueSchedule": {"gameDates": [{"games": [
        {"gameId": gid, "gameLabel": lab, "gameSubLabel": sub, "gameSubtype": typ} for gid, lab, sub, typ in games]}]}}


S25 = sched(("0022500001", "", "", ""), ("0022500050", "Emirates NBA Cup", "West Group B", "in-season"),
            ("0022501201", "Emirates NBA Cup", "East Quarterfinal", "in-season-knockout"),
            ("0062500001", "Emirates NBA Cup", "Championship", "in-season-knockout"),
            ("0022500077", "AWS NBA Rivals Week", "", ""), ("0012500001", "Preseason", "", ""),
            ("0022500061", "Cup Night", "East Group C", "in-season"), ("0022500062", "NBA Cup", "", ""))   # either mark
S26 = sched(("0022600003", "Emirates NBA Cup", "East Group A", "in-season"), ("0022600009", "", "", ""))


def getter(calls, fail=()):
    def get(url):
        s = url.rsplit("=", 1)[1]
        calls.append(s)
        if s in fail:
            raise TimeoutError("slow")
        return {"2025-26": S25, "2026-27": S26}[s]
    return get


def test_parse_keeps_cup_games_only():
    assert NC.parse(S25) == {"0022500050": "West Group B", "0022501201": "East Quarterfinal", "0062500001": "Championship",
                             "0022500061": "East Group C", "0022500062": "NBA Cup"}


def test_cached_fetched_when_due(tmp_path):
    c, calls = tmp_path / "cup.json", []
    g = NC.games(("2025-26", "2026-27"), T0, getter(calls), c)
    assert calls == ["2025-26", "2026-27"] and len(g) == 6 and g["0022600003"] == "East Group A"
    assert NC.games(("2025-26", "2026-27"), T0 + dt.timedelta(hours=23), getter(calls), c) == g and len(calls) == 2
    NC.games(("2025-26", "2026-27"), T0 + dt.timedelta(hours=24), getter(calls), c)
    assert calls[2:] == ["2026-27"]                 # last season ended before it was fetched: never again


def test_a_failure_keeps_the_cache_and_waits_an_hour(tmp_path):
    c, calls = tmp_path / "cup.json", []
    g = NC.games(("2025-26", "2026-27"), T0, getter(calls), c)
    later = T0 + dt.timedelta(days=1)
    assert NC.games(("2025-26", "2026-27"), later, getter(calls, fail={"2026-27"}), c) == g      # never raises
    assert json.loads(c.read_text())["failed"] == later.isoformat()
    NC.games(("2025-26", "2026-27"), later + dt.timedelta(minutes=59), getter(calls), c)
    assert calls == ["2025-26", "2026-27", "2026-27"]
    NC.games(("2025-26", "2026-27"), later + dt.timedelta(hours=1), getter(calls), c)
    assert calls[3:] == ["2026-27"] and "failed" not in json.loads(c.read_text())


def test_nothing_cached_and_unreachable_is_no_cup_games(tmp_path):
    c, calls = tmp_path / "cup.json", []
    assert NC.games(("2025-26", "2026-27"), T0, getter(calls, fail={"2025-26", "2026-27"}), c) == {}
    assert calls == ["2025-26"]                     # the first failure stops the run: one slow request, not two


def test_a_schedule_without_cup_labels_is_not_taken(tmp_path):
    c = tmp_path / "cup.json"
    g = NC.games(("2026-27",), T0, getter([]), c)
    blank = lambda url: sched(("0022600003", "", "", ""))
    assert NC.games(("2026-27",), T0 + dt.timedelta(days=1), blank, c) == g
