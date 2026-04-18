# xG Feature Documentation

- Scope: Top 5 leagues + UEFA Champions League
- Model mode: xg_proxy
- Trained at (UTC): 2026-04-18T19:03:57Z
- Granularity note: No shot-level table with coordinates was found; using aggregate match statistics (shots, possession, corners, events) for an explicitly labeled xG proxy.

## Feature Catalog

| Feature | Description |
|---|---|
| is_home | 1 if perspective team is home, else 0. |
| team_points_per_match | Team average league points per match from recent supported history. |
| team_goals_for_avg | Team average goals scored per match over recent supported history. |
| team_goals_against_avg | Team average goals conceded per match over recent supported history. |
| team_shots_on_avg | Team average shots on target from available aggregate match statistics. |
| team_shots_off_avg | Team average shots off target from available aggregate match statistics. |
| team_possession_avg | Team average possession percentage from available aggregate match statistics. |
| team_corners_avg | Team average corners from available aggregate match statistics. |
| team_form_points_last5 | Team points collected in the last five supported finished matches. |
| team_rest_days | Days since team last supported finished match before kickoff. |
| opp_points_per_match | Opponent average points per match from recent supported history. |
| opp_goals_for_avg | Opponent average goals scored per match over recent supported history. |
| opp_goals_against_avg | Opponent average goals conceded per match over recent supported history. |
| opp_shots_on_avg | Opponent average shots on target from available aggregate match statistics. |
| opp_shots_off_avg | Opponent average shots off target from available aggregate match statistics. |
| opp_possession_avg | Opponent average possession percentage from available aggregate match statistics. |
| opp_corners_avg | Opponent average corners from available aggregate match statistics. |
| opp_form_points_last5 | Opponent points in last five supported finished matches. |
| opp_rest_days | Days since opponent last supported finished match before kickoff. |
| is_ucl_match | 1 when competition name indicates Champions League context, else 0. |
| team_stats_coverage | Share of history matches where aggregate stats were available for the perspective team. |
| opp_stats_coverage | Share of history matches where aggregate stats were available for the opponent. |

## Notes

- xG proxy mode is explicitly labeled and should not be interpreted as event-level true xG.
- Confidence and calibration outputs are included in training metrics JSON.