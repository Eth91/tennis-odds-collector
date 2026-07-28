CREATE TABLE projections(
  date TEXT, pid TEXT, player TEXT, team TEXT, opp TEXT, out_player TEXT, confidence TEXT,
  basis TEXT, n_games INTEGER, pos TEXT, d_min REAL, flagged INTEGER DEFAULT 0,
  proj_min REAL, proj_pts REAL, proj_reb REAL, proj_ast REAL, logged_at TEXT,
  actual_min REAL, actual_pts REAL, actual_reb REAL, actual_ast REAL, graded INTEGER DEFAULT 0,
  UNIQUE(date, pid));
