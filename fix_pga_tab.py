"""Give PGA its own tab and move the PGA plays off the Table Tennis tab.

The PGA panel was rendered inside the `tt` panel, so golf plays only appeared if you went looking
under Table Tennis — two unrelated sports sharing one surface. Now it gets a peer tab alongside
WNBA / TT / Tracker, with an icon in the same line-art style as the others (shared `_ic` attrs, so
stroke weight and sizing match rather than approximating the design system).
"""
import ast
import io

p = "dashboard.py"
s = io.open(p, encoding="utf-8").read()

# ---------------------------------------------------------------- 1. the icon
anchor = '''    ICON_TRK = f'<svg {_ic}><path d="M4 4v16h16"/><path d="M8 16v-4M12 16V8M16 16v-6"/></svg>\''''
icon = '''    # flagstick + pennant + ball, drawn on the same 24x24 grid and stroke as the others
    ICON_PGA = (f'<svg {_ic}><path d="M7.4 20.4V3.6l8.4 3-8.4 3"/>'
                '<circle cx="16.2" cy="17.8" r="2.1"/><path d="M3.6 20.4h16.8"/></svg>')
''' + anchor
if "ICON_PGA" in s:
    print("  = ICON_PGA already present")
else:
    assert anchor in s, "ICON_TRK anchor missing"
    s = s.replace(anchor, icon, 1)

# ------------------------------------------------------------ 2. the tab button
tab_anchor = '''    <div class="tab" data-tab="tt" onclick="showTab('tt')">{ICON_TT}<span>TT</span></div>'''
tab_new = tab_anchor + '''
    <div class="tab" data-tab="pga" onclick="showTab('pga')">{ICON_PGA}<span>PGA</span></div>'''
if 'data-tab="pga"' in s:
    print("  = PGA tab button already present")
else:
    assert tab_anchor in s, "tt tab button anchor missing"
    s = s.replace(tab_anchor, tab_new, 1)

# --------------------------------------- 3. move the panel out of the tt panel
old_panel = '''  <div class="panel hidden" id="tt">
    <h2>Table tennis · real FD lines</h2>
    {tt_html}
    {pga_html}
  </div>'''
new_panel = '''  <div class="panel hidden" id="tt">
    <h2>Table tennis · real FD lines</h2>
    {tt_html}
  </div>
  <div class="panel hidden" id="pga">
    <h2>PGA Tour · FanDuel</h2>
    {pga_html}
  </div>'''
if '<div class="panel hidden" id="pga">' in s:
    print("  = PGA panel already separate")
else:
    assert old_panel in s, "tt panel anchor missing"
    s = s.replace(old_panel, new_panel, 1)

ast.parse(s)
io.open(p, "w", encoding="utf-8").write(s)
print("  + PGA tab added; pga_html moved out of the TT panel into its own")
