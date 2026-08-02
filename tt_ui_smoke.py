"""Exercise the BetMGM render path with a synthetic bet — do not wait for one to appear."""
import datetime as dt, json
import dashboard as DB

now = dt.datetime.now(dt.timezone.utc)
fake = {
  "elite_h2h": [], "elite_upcoming": [],
  "bets": [{"p1": "Krzysztof Juszczyk", "p2": "Sebastian Szostok", "side": "U≥74.5",
            "play_to": 74.5, "raw": 88, "n": 31,
            "ts": int((now + dt.timedelta(hours=2)).timestamp()),
            "book": {"line": 74.5, "od": 1.87, "nb": 3}}],
}
html = DB._tt_totals_card(fake, now=now)
import re
print("  rendered:", " ".join(re.sub(r"<[^>]+>", " ", html).split()))
print()
for k, lab in (("podds bmgm", "gold price class"), ("data:image/svg", "gold badge img"),
               ("BetMGM · confirmed", "book label"), ("-115", "decimal 1.87 -> American")):
    print("  %-24s %s" % (lab, k in html))
print()
print("  full name present:", "Krzysztof Juszczyk" in html and "Sebastian Szostok" in html)
