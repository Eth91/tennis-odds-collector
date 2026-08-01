"""Strip emoji from the UI, remove the boxes behind logos, and wire a real BetMGM asset.

EMOJI. Apple does not put emoji in chrome — section headers are words. Every decorative emoji in a
heading or tag is removed. The MLB tag emoji (2673-2682) are LOOKUP KEYS as well as labels, so
those are left alone: renaming a key silently breaks the _TAGLBL/_CONF dictionaries that read it.

LOGO BOXES. Every mark sat on a --cu-fill rounded square or circle. Real league and team marks are
already designed shapes with their own silhouette; boxing them adds a second container the brand
never had. The box goes; only the MONOGRAM fallback keeps one, because a bare two-letter string
with no container reads as stray text.

BETMGM. There is no BetMGM SVG on Wikimedia and betmgm.com returns 403 to a direct fetch, so I
cannot obtain the real mark. The code now points at docs/book-mgm.png and falls back to the
monogram if it is absent — drop the real file in and it appears with no further change.
"""
import ast, io, re, shutil
P="dashboard.py"; s=io.open(P,encoding="utf-8").read()
if "CUPERTINO-CLEAN" in s: print("= already"); raise SystemExit(0)
n=0
def sub(old,new,label,count=1):
    global s,n
    assert old in s, "MISSING: "+label
    s=s.replace(old,new,count); n+=1; print("   -",label)

sub('card("🏓", "TT Elite"', 'card("", "TT Elite"', "tracker TT Elite")
sub('card("🏓", "Table tennis"', 'card("", "Table tennis"', "tracker Table tennis")
sub('<div class="thead">🏓 Other TT leagues ', '<div class="thead">Other TT leagues ', "other TT leagues")
sub('<div class="thead">🏓 Table tennis</div>', '<div class="thead">Table tennis</div>', "TT head")
sub('<div class="thead">🎰 WNBA Parlays</div>', '<div class="thead">WNBA Parlays</div>', "parlays head")
sub('<div class="sw-title">🏥 Injury report ', '<div class="sw-title">Injury report ', "injury title")
sub("""        text = f"⚠️ {board} feed issue:""", """        text = f"{board} feed issue:""", "feed warning")
# inline prose glyphs — the colour already carries these
sub('''        b.append(f"⚠ she\'s gone OVER in''', '''        b.append(f"She\'s gone OVER in''', "prose warn 1")
sub('''        b.append("⚠ not in the projected starting five''', '''        b.append("Not in the projected starting five''', "prose warn 2")
sub('''    verdict = ("✓ " + side + " friendly") if supports else ("⚠ against the " + side)''',
    '''    verdict = (side + " friendly") if supports else ("against the " + side)''', "regime verdict")

# TT flags header emoji lives in the JS renderer
sub("""    el.innerHTML = '<div class="card"><h3 class="ttlg">\\\\uD83C\\\\uDFD3 TT Elite ' + mid + ' Flags'""",
    """    el.innerHTML = '<div class="card"><h3 class="ttlg">TT Elite ' + mid + ' Flags'""",
    "TT flags header (JS)")

# BetMGM: point at a real asset, monogram only as fallback
old_mgm = s[s.index('  var _TTMGM = "data:image/svg+xml'):s.index('%3C/svg%3E";')+len('%3C/svg%3E";')]
new_mgm = ('  // Real BetMGM mark when docs/book-mgm.png exists; the monogram below is only the\n'
           '  // fallback for when it does not (no BetMGM SVG is publicly obtainable).\n'
           '  var _TTMGM = "book-mgm.png";\n'
           '  var _TTMGM_FALLBACK = "data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\'"\n'
           '    + " viewBox=\'0 0 24 24\'%3E%3Crect width=\'24\' height=\'24\' rx=\'6\' fill=\'%23c9a227\'/%3E"\n'
           '    + "%3Ctext x=\'12\' y=\'16\' font-size=\'8.5\' font-weight=\'700\' text-anchor=\'middle\'"\n'
           '    + " fill=\'%23151b24\' font-family=\'Arial,sans-serif\'%3EMGM%3C/text%3E%3C/svg%3E";')
s = s.replace(old_mgm, new_mgm, 1); n+=1; print("   - BetMGM -> real asset with monogram fallback")
sub("""'<img class="bklogo" src="' + (_mgm ? _TTMGM : 'book-fd.png') + '" alt="'""",
    """'<img class="bklogo" src="' + (_mgm ? _TTMGM : 'book-fd.png')
            + '" onerror="if(this.src.indexOf(\\'book-mgm\\')>-1)this.src=_TTMGM_FALLBACK" alt="'""",
    "BetMGM onerror fallback")

CSS = r"""
  /* ══════════════════ CUPERTINO-CLEAN ══════════════════
     No boxes behind marks. A league or team logo is already a designed shape with its own
     silhouette; wrapping it in a tinted rounded square adds a container the brand never had.
     Only the MONOGRAM fallback keeps a box — a bare two-letter string needs one to read as a mark
     rather than as stray text. */
  .mk, .glogo, .plogo, .bklogo, .llogo, .tlogo,
  #wnba .cu-tm, #wnba .cu-gl, #wnba .glogo, #wnba .plogo, #wnba .bklogo,
  #wnba .llogo, #wnba .swrow .glogo, #tt .bklogo, #pga .bklogo, #tracker .bklogo {{
      background:none !important; border:0 !important; padding:0 !important;
      border-radius:0 !important; }}
  #wnba .llogo, #wnba .cu-gl {{ overflow:visible; }}
  #wnba .llogo img {{ padding:0 !important; }}
  /* monogram fallback keeps its container */
  .llogo.mono, #wnba .llogo.mono {{ background:var(--cu-fill) !important; border-radius:6px !important;
      display:inline-flex; align-items:center; justify-content:center; }}
  /* marks are round-ish artwork; give them consistent optical sizes now the boxes are gone */
  #wnba .cu-tm {{ width:20px; height:20px; }}
  #wnba .cu-gl, #wnba .glogo {{ width:20px; height:20px; }}
  #wnba .swrow .glogo {{ width:24px; height:24px; }}
  .bklogo {{ width:22px !important; height:22px !important; }}
  #wnba .cu-hd .bklogo {{ width:24px !important; height:24px !important; }}
"""
a="</style></head><body>"; assert a in s; s=s.replace(a, CSS+a, 1)
ast.parse(s); shutil.copyfile(P,"/tmp/dashboard.preclean.py"); io.open(P,"w",encoding="utf-8").write(s)
print(f"  {n} edits; emoji stripped from chrome, logo boxes removed, BetMGM wired")
