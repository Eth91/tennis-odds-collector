import sqlite3
import pga_sg as S
import pga_ruler as RU
# drop the mislabeled GIR (02420 = Distance from Edge of Fairway, NOT greens in regulation)
c = sqlite3.connect(str(RU.DB))
n = c.execute("DELETE FROM sg_stats WHERE stat='GIR'").rowcount
c.commit(); c.close()
print("  removed %d mislabeled GIR rows" % n)
S.SG_STATS = {"102": "DRIVE_ACC", "103": "GIR", "130": "SCRAMBLE"}
S.harvest(years=(2023, 2024, 2025, 2026))
