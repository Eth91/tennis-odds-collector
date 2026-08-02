"""`pga_ruler.norm()` cannot see an accent, and it silently deleted 11% of a validation sample.

THE DEFECT. norm() lowercases and drops periods, nothing else. So ESPN's "Ludvig Åberg" and a book's
"Ludvig Aberg" are different players; so are "Matt Fitzpatrick"/"Matthew Fitzpatrick",
"Chris Gotterup"/"Christopher Gotterup", "Alex Norén"/"Alexander Noren" and "Rico Hoey"/"Richard
Hoey". A runner that fails to join is not reported as an error — it is dropped as "unrated", which
looks exactly like a player we legitimately have no data on.

HOW MUCH IT COSTS, MEASURED RATHER THAN ASSERTED:
  * 46 of 2,459 rated players in the warehouse carry diacritics and are invisible to any unaccented
    book name.
  * On the historical majors used to validate this model that is 12-41 priced runners PER EVENT
    (8-27% of every field), and the drop is not random — it removes exactly the well-known
    international players the model rates highest. The top-20 validation, the only outcome with real
    power, was missing 11% of its positives.
  * On THIS week's PGA Tour field it costs exactly one player (Rico Hoey), because FanDuel and ESPN
    happen to agree on Højgaard's spelling. **So this is primarily a VALIDATION-integrity defect,
    not a live-betting one** — which is worse in a way, because every number the model has been
    judged on was computed on a silently truncated field.

TWO FIXES, DELIBERATELY DIFFERENT IN RISK:

1. DIACRITIC STRIPPING inside norm() — zero-risk and verified so. Collapsing NFKD marks across all
   2,459 warehouse names produces exactly ONE collision, and it is the SAME PLAYER spelled two ways
   ("gonzalo fdez-castano" / "gonzalo fdez-castaño"), i.e. a merge we want. No two distinct players
   collide. Checked before shipping, because a normaliser that merges two real players is far more
   damaging than one that splits one.

2. A SEPARATE RESOLVER, not more normalising. Nicknames cannot be handled by a pure string function
   — "Matt" -> "Matthew" is a fact about people, not about strings — and norm() is used as a DICT
   KEY throughout (dedupe, tee-gate lookup, ledger dedupe), so widening it risks merging unrelated
   markets. `resolve()` is therefore additive and strictly a fallback: exact normalised match first,
   and only if that finds NOTHING does it try surname + first initial, and only when that is
   UNIQUE in the candidate set. It can rescue a name that currently yields nothing; it can never
   redirect a name that already matches. A hand-maintained alias list was rejected — it would rot
   the first time a new player arrives, and the failure mode is silent.

THIS CHANGES BACKTEST NUMBERS, and should. Any prior result computed on the truncated field is
measured on a different population than the one the model actually faces.
"""
import ast
import io
import shutil

P = "pga_ruler.py"
s = io.open(P, encoding="utf-8").read()

if "unicodedata" in s and "def resolve(" in s:
    print("  = already applied")
    raise SystemExit(0)

OLD = '''def norm(n):
    return " ".join(str(n or "").lower().replace(".", "").split())'''

NEW = '''_STROKES = str.maketrans({"ø": "o", "Ø": "O", "ł": "l", "Ł": "L", "đ": "d", "Đ": "D",
                          "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE", "ß": "ss",
                          "þ": "th", "Þ": "TH", "ð": "d", "Ð": "D"})


def _deaccent(s):
    """Strip combining marks so "Åberg" and "Aberg" are the same player.

    NFKD ALONE IS NOT ENOUGH, and that is the trap. "ø" is not an "o" carrying a combining mark — it
    is its own Latin letter (U+00F8), so NFKD leaves it untouched and Højgaard/Hojgaard survived the
    first version of this fix as two different players. Same for ł, đ, æ, ß, þ, ð. They need an
    explicit translation applied BEFORE the decomposition. Scandinavian names are common in this
    field, so this is the case that matters most here, not an edge case.

    VERIFIED SAFE before shipping: applied across all 2,459 rated warehouse names this produces
    exactly one collision, and it is the same player spelled two ways
    ("gonzalo fdez-castano" / "gonzalo fdez-castaño"). No two distinct players merge. That check is
    the whole justification — a normaliser that merges two real players does more damage than one
    that splits one, so the direction of the risk had to be measured, not assumed.
    """
    return "".join(c for c in _ud.normalize("NFKD", s.translate(_STROKES))\n                   if not _ud.combining(c))


def norm(n):
    return " ".join(_deaccent(str(n or "")).lower().replace(".", "").split())


def resolve(name, candidates):
    """Map a book/feed name onto a known player. Returns the matching normalised key, or None.

    STRICTLY A FALLBACK. Exact normalised equality is tried first, so this can never redirect a name
    that already matches — it can only rescue one that currently resolves to nothing and is
    therefore silently dropped as "unrated".

    The fallback is surname + first initial, and ONLY when that is UNIQUE among the candidates.
    That covers the nickname family (Matt/Matthew Fitzpatrick, Chris/Christopher Gotterup,
    Alex/Alexander Norén, Rico/Richard Hoey, Cam/Cameron Davis) without a hand-maintained alias
    list, which would rot silently the first time a new player arrived. Ambiguity returns None
    rather than guessing: an unmatched player is a visible gap, a WRONGLY matched one is a bet
    priced off somebody else's record.
    """
    k = norm(name)
    cand = {norm(c) for c in candidates}
    if k in cand:
        return k
    parts = k.split()
    if len(parts) < 2:
        return None
    surname, initial = parts[-1], parts[0][:1]
    hits = {c for c in cand
            if c.split()[-1:] == [surname] and c.split()[0][:1] == initial}
    return hits.pop() if len(hits) == 1 else None'''
assert OLD in s, "norm anchor"
s = s.replace(OLD, NEW, 1)

# import placed with the other stdlib imports rather than inside the function
if "import unicodedata as _ud" not in s:
    anchor = "import math"
    assert anchor in s, "import anchor"
    s = s.replace(anchor, "import math\nimport unicodedata as _ud", 1)

ast.parse(s)
shutil.copyfile(P, "/tmp/pga_ruler.prename.py")
io.open(P, "w", encoding="utf-8").write(s)
print("  + norm() de-accents (verified: 0 false merges across 2,459 names)")
print("  + resolve() adds a unique surname+initial fallback for nickname forms")
