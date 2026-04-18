# Data Provider Decision (Top 5 + UCL)

## Short Answer
Yes, buying the football-data.org 29 USD plan is a good move for your app core.

## What You Get That Helps Immediately
- Stable data for your exact scope: Premier League, La Liga, Bundesliga, Serie A, Ligue 1, UCL.
- Live scores for match page and homepage tabs.
- Fixtures and schedules for upcoming and finished lists.
- League tables for standings pages.
- Lineups and substitutions for richer match detail pages.
- Goal scorers and cards for event timelines.
- Squads for team pages and player lists.
- 30 calls per minute, enough if backend caching is done correctly.

## What This Plan Does Not Fully Solve
- FIFA-like player card ratings (pace, shooting, dribbling, etc.) are not native in football-data.org.
- True advanced player analytics for next-goal and next-assist models are limited.
- True xG usually needs shot-level data (shot location, body part, context), which this plan typically does not provide.

## Recommendation
- Buy it for reliable official match backbone data.
- Keep or add one complementary source for richer player-level metrics and photos.
- Build your UX features on top of football-data, but do not expect it alone to power advanced player models at high quality.

## Scope Guardrail
Build everything only for:
- PL, PD, BL1, SA, FL1, and UCL.
This keeps costs and complexity under control.
