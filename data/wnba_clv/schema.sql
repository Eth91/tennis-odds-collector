CREATE TABLE clv(
  date TEXT, player TEXT, stat TEXT, out_player TEXT, flagged_at TEXT, proj REAL,
  flag_line REAL, flag_over REAL, close_line REAL, close_over REAL, closed INTEGER DEFAULT 0,
  actual REAL, graded INTEGER DEFAULT 0, v INTEGER, tip TEXT, tier TEXT DEFAULT 'firm', UNIQUE(date, player, stat));
