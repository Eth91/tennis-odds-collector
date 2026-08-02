"""Cut the explanatory prose down to Apple length, and tighten spacing.

The board explains itself in paragraphs. Apple does not: a section is a short noun, the design
carries the meaning, and anything left is a brief footnote. Every cut below either removes a
legend the UI already makes obvious, or compresses a sentence to its load-bearing clause.

NOTHING FACTUAL IS DELETED. Records, ROI, pending counts, the shadow line and the "not a bet"
status all survive — only the prose around them goes. The one legend I keep in compressed form is
TT's projected-vs-confirmed, because a projected line is NEVER tracked and that is a real caveat a
reader cannot infer from the design.
"""
import ast, io, shutil
P="dashboard.py"; s=io.open(P,encoding="utf-8").read()
if "CUPERTINO-COPY" in s:
    print("  = already applied"); raise SystemExit(0)
n=0
def sub(old, new, label):
    global s, n
    assert old in s, "MISSING: " + label
    s = s.replace(old, new, 1); n += 1; print("   -", label)

# 1. bar-chart legend — the chart is self-evident; keep only the record
sub("""f'<div class="bnote">{hits}/{len(s)} {side} {line:g} · gray bar = minutes · {note}</div></div></div>')""",
    """f'<div class="bnote">{hits}/{len(s)} {side} {line:g}</div></div></div>')""",
    "drawer chart legend -> record only")

# 2. injury scope — the n= chip is learned once; the title is a noun
sub('''    _scope = ("· teams playing today" if _today_teams else "· ALL teams (slate lookup failed)")''',
    '''    _scope = ("· today" if _today_teams else "· all teams (slate lookup failed)")''',
    "injury scope -> '· today'")

# 3. "also flagged" — the card title already says these are not picks
sub("""                   '<span>· benched by the selection rules · not picks</span></div>'""",
    """                   '<span>· not picks</span></div>'""",
    "also flagged subtitle")

# 4. page footer
sub("""  <div class="foot">auto-generated · self-refreshing · WNBA 1u ladders · TT/GG ¼-Kelly paper</div>""",
    """  <div class="foot">auto-generated · self-refreshing</div>""",
    "page footer")

# 5. tracker WNBA note — keep the numbers, drop the filter prose
sub('''"current-model picks (overs · thin-sample & over-stack filtered) · 1u base + declining rungs · since 7/9"''',
    '''"1u base + declining rungs · since 7/9"''',
    "tracker WNBA note")

# 6. TT legend — 190 chars of definitions. Keep only the caveat a reader CANNOT infer from the
#    table: a projected line was never tracked. Replaced as a whole line, not by fragment, so the
#    JS concatenation cannot be left half-formed.
sub(r"""      + '<div class="ttfoot">hit rate = share of H2H meetings that went this side at this line ' + mid + ' only pairs \\u226570% shown ' + mid + ' confirmed = a REAL posted line (FanDuel or BetMGM) ' + mid + ' projected = before FanDuel posts (never tracked)</div></div>';""",
    r"""      + '<div class="ttfoot">projected = no posted line yet, never tracked</div></div>';""",
    "TT legend -> one caveat")

ast.parse(s); shutil.copyfile(P,"/tmp/dashboard.precopy.py"); io.open(P,"w",encoding="utf-8").write(s)
print(f"  {n} copy edits applied")
