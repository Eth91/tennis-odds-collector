"""The footer still credited FanDuel alone for a 'confirmed' line — BetMGM counts too since 7/29."""
import ast, io, shutil
P="dashboard.py"; s=io.open(P,encoding="utf-8").read()
n=0
old_py = "f'at this line · only pairs ≥70% shown · confirmed = FanDuel has posted the line (tracked) · '"
new_py = "f'at this line · only pairs ≥70% shown · confirmed = a REAL posted line (FanDuel or BetMGM) · '"
if old_py in s: s=s.replace(old_py,new_py,1); n+=1
old_js = "' ' + mid + ' confirmed = FanDuel has posted the line (tracked) '"
new_js = "' ' + mid + ' confirmed = a REAL posted line (FanDuel or BetMGM) '"
if old_js in s: s=s.replace(old_js,new_js,1); n+=1
# the js footer is one long concatenation; catch it however it is written
for a,b in (("confirmed = FanDuel has posted the line (tracked)","confirmed = a REAL posted line (FanDuel or BetMGM)"),):
    if a in s: s=s.replace(a,b); n+=1
assert n, "no footer text matched"
ast.parse(s); shutil.copyfile(P,"/tmp/dashboard.prefoot.py")
io.open(P,"w",encoding="utf-8").write(s)
print("  + footer now says a real posted line can be FanDuel OR BetMGM (%d site(s))"%n)
