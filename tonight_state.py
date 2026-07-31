"""What could still produce a play tonight, and when would it have to happen?"""
import datetime as dt, json
import dashboard as DB

now = dt.datetime.now(dt.timezone.utc)
et = now.astimezone(dt.timezone(dt.timedelta(hours=-4)))
slate = et.date().isoformat()
tt = DB._tip_times() or {}
games = sorted({(v, t) for (d, t), v in tt.items() if d == slate})
print("  now %s UTC   slate %s" % (now.strftime("%H:%MZ"), slate))
print("\n  tonight's teams and tips:")
seen = {}
for tip, team in games:
    seen.setdefault(tip, []).append(team)
for tip in sorted(seen):
    mins = (tip - now).total_seconds() / 60
    print("    %s UTC  %-14s  %s" % (tip.strftime("%H:%M"), " v ".join(sorted(seen[tip])),
                                     ("in %.0f min" % mins) if mins > 0 else "STARTED"))

d = json.load(open("wnba_injuries_board.json"))
print("\n  statuses on tonight's teams:")
for r in d.get("rows") or []:
    st = r.get("status") or ""
    drives = "drives a play" if st.lower().startswith(("out", "doubt")) else "no play unless downgraded"
    print("    %-22s %-4s %-9s mpg %-5s ppg %-5s  -> %s"
          % (r["player"][:22], r["team"], st, r.get("mpg"), r.get("ppg"), drives))

print("\n  teams playing tonight with NO listed status (nothing to react to):")
teams = {t for (_d, t) in tt if _d == slate}
have = {(r.get("team") or "").upper() for r in (d.get("rows") or [])}
print("    %s" % (sorted(teams - have) or "none"))
