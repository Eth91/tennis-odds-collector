CREATE TABLE predictions(
  pred_date TEXT, out_player TEXT, player TEXT, team TEXT, opp TEXT,
  stat TEXT, line REAL, odds REAL, book TEXT,
  proj_hit REAL, season_avg REAL, elev_avg REAL, proj_min REAL, n_elev INTEGER,
  ev REAL, stale INTEGER,
  d_stat REAL, d_fga REAL, d_min REAL, driver REAL, vac REAL,
  total REAL, pace REAL, opp_def REAL, d_fta REAL, d_3pa REAL,
  result TEXT, actual REAL, graded INTEGER DEFAULT 0, basis TEXT, samples TEXT, confidence TEXT, played INTEGER DEFAULT 0, side TEXT DEFAULT 'over', regime TEXT, vol TEXT, spread REAL, pi_role REAL, actual_total REAL, actual_margin REAL, odds_other REAL,
  UNIQUE(pred_date, player, stat, line)
);
CREATE TABLE parlays(
  pred_date TEXT, key TEXT, legs TEXT, n INTEGER, dec REAL, ev REAL,
  result TEXT, pnl REAL, graded INTEGER DEFAULT 0, graded_at TEXT, played INTEGER DEFAULT 0,
  UNIQUE(pred_date, key));
CREATE TABLE selections (
    pred_date TEXT, team TEXT, player TEXT, stat TEXT, selected_at TEXT,
    PRIMARY KEY (pred_date, team, player, stat));
