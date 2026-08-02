"""Collect DraftKings MILESTONE rungs ("15+", "18+"). 459 WNBA points selections were being dropped.

THE BUG. DK exposes three different "Points" subcategories and the parser only understood one:

    cat 1206  "Points"      240 sels  label='Marina Mabrey'  points=-6.5   <- player HANDICAP
    cat 1215  "Points"      459 sels  label='12+'            points=None   <- MILESTONE ladder
              "Points O/U"  120 sels  label='Over'           points=6.5    <- the main line

Side was derived purely from `label.startswith("over"/"under")`, so every milestone selection got
side=None and hit `continue`. All 459 were discarded, every cycle. That is why the board showed DK
holding only Bridget Carleton's 13.5 while the app plainly offers her 15+, 18+ and 20+.

It also explains a wrong conclusion I reported earlier — that FanDuel carried ~5x DK's alt depth
(median 7 rungs vs 1). That gap was this bug, not DK's actual coverage.

WHY THIS IS DELICATE, AND WHY THE DISCRIMINATOR IS NARROW. Category 1206 is a player-vs-player
HANDICAP market whose `points` field holds a spread (-6.5, +5.5), not a total. A loose "accept
anything with a number" fix would ingest those as points lines and quietly poison the model with
negative and half-team-sized totals — considerably worse than missing the milestones. So a
selection is only read as a milestone when BOTH hold:

    label matches ^<number>+$   (e.g. "15+", never a player name)
    points is None              (handicaps always carry a points value)

Either alone would be unsafe; together they cannot match 1206 or the O/U shape.

"15+" MEANS 15 OR MORE, i.e. over 14.5 — so the stored line is threshold - 0.5, which puts DK's
rungs on exactly the same scale as FanDuel's and the ledger's. Getting this off by one would
silently shift every DK alt rung a full point.

Milestones are ONE-SIDED (no under is offered), which is already how FanDuel's alt ladder behaves
downstream: the pricer treats a one-sided rung as an alt with a fatter, un-devigable hold and holds
it to LADDER_EV_MIN rather than the two-way bar.
"""
import ast
import io
import shutil

P = "dk_collect.py"
s = io.open(P, encoding="utf-8").read()

if "MILESTONE" in s:
    print("  = already applied")
    raise SystemExit(0)

OLD = """        for sel in j.get("selections", []):
            label = (sel.get("label") or "").strip().lower()
            side = "over" if label.startswith("over") else \\
                   "under" if label.startswith("under") else None
            pts, dec, player = sel.get("points"), _dec(sel), _player(sel)
            if side is None or pts is None or dec is None or not player:
                continue"""

NEW = """        for sel in j.get("selections", []):
            raw = (sel.get("label") or "").strip()
            label = raw.lower()
            pts, dec, player = sel.get("points"), _dec(sel), _player(sel)
            side = "over" if label.startswith("over") else \\
                   "under" if label.startswith("under") else None
            # MILESTONE RUNGS. DK posts its alt ladder as one-sided "15+" selections with NO
            # `points` value, so the over/under label test dropped all of them — 459 WNBA points
            # selections per cycle, which is why the board only ever had DK's main line.
            #
            # The discriminator is deliberately narrow. Category 1206 is a player-vs-player
            # HANDICAP market whose `points` holds a spread (-6.5), not a total; accepting it as a
            # points line would poison the model far worse than missing the milestones. Requiring
            # BOTH a bare "<number>+" label AND points=None excludes it structurally.
            if side is None and pts is None and _MILESTONE.fullmatch(raw):
                side = "over"
                pts = float(raw[:-1]) - 0.5     # "15+" == 15 or more == over 14.5
            if side is None or pts is None or dec is None or not player:
                continue"""
assert OLD in s, "selection-parse anchor"
s = s.replace(OLD, NEW, 1)

OLD2 = "def _stat_key(subcat_name):"
NEW2 = ('# DK milestone rung label: "15+", "8+". Anchored so a player name or an "Over 14.5" can\n'
        '# never match, which is what keeps the 1206 handicap market out of the points ladder.\n'
        '_MILESTONE = re.compile(r"\\d+(?:\\.\\d+)?\\+")\n\n\n'
        'def _stat_key(subcat_name):')
assert OLD2 in s, "stat_key anchor"
s = s.replace(OLD2, NEW2, 1)

ast.parse(s)
shutil.copyfile(P, "/tmp/dk_collect.premilestone.py")
io.open(P, "w", encoding="utf-8").write(s)
print("  + dk_collect reads milestone rungs ('15+' -> over 14.5), handicap market still excluded")
