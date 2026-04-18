Project Blueprint: Intelligent Football Analytics Platform

Bachelor Degree Capstone Project

1. Executive Summary

This project is a modern web application designed to provide real-time football statistics, comprehensive match data, and AI-driven predictive analytics for the top 5 European leagues (Premier League, La Liga, Bundesliga, Serie A, Ligue 1) and major UEFA competitions. Unlike standard scoreboards, this platform integrates a Deep Learning engine to forecast match outcomes based on historical performance metrics.

2. Technology Stack & Justification

Frontend: Next.js (React)

Why: Best-in-class Server Side Rendering (SSR) for SEO-friendly match pages and fast initial loads.

Backend: FastAPI (Python)

Why: Native support for asynchronous operations (essential for handling live WebSocket connections) and seamless integration with Python's AI ecosystem.

Database: PostgreSQL

Why: robust relational data modeling for complex relationships (Players -> Teams -> Matches -> Leagues).

AI/ML Engine: PyTorch (or TensorFlow)

Why: Industry-standard framework for building Deep Neural Networks, allowing for complex pattern recognition in non-linear sports data.

External API: API-Football (RapidAPI)

Why: Comprehensive coverage of required leagues with a student-friendly free tier.

3. System Architecture

3.1 Data Flow

Ingestion: A background scheduler (APScheduler) in FastAPI periodically fetches "Fixtures" and "Standings" from API-Football to keep the database fresh.

Live Updates: When a match is "Live", the backend opens a WebSocket connection to the specific match data stream and broadcasts events (goals, cards) to connected Next.js clients.

Prediction: 24 hours before a match, the PyTorch model runs, fetching historical stats for both teams, generating a probability score, and storing it in the match_predictions table.

4. Database Schema (Simplified ERD)

Leagues: id, name, country, logo_url

Teams: id, name, logo_url, stadium, league_id

Players: id, name, position, team_id, height, nationality

Matches: id, home_team_id, away_team_id, start_time, status (LIVE/FT), home_score, away_score

Predictions: id, match_id, home_win_prob, draw_prob, away_win_prob, confidence_score

5. The AI "Wow" Feature (PyTorch Implementation)

5.1 Data Acquisition (Building the Dataset from Scratch)

Since the AI needs historical context to learn, we cannot rely solely on "live" data.

The "Seeder" Script: A standalone Python script will be created to query the External API for match results from the past 5 seasons (2019-2024).

Normalization: Raw data (e.g., "Goals Scored") will be normalized to a 0-1 scale (using MinMax scaling) to ensure the Neural Network converges efficiently.

Tensor Conversion: The cleaned CSV data will be converted into PyTorch Tensors (torch.float32) for training.

5.2 Feature Engineering

The model inputs (Features) will be a vector of ~20 data points per match:

Home/Away Form (Last 5 games): Rolling average of points.

Goal Expectancy: Rolling average of Goals Scored vs. Conceded.

Head-to-Head Weight: A calculated score based on the last 3 meetings.

League Position Diff: Difference in league table rank (e.g., 1st vs 18th).

5.3 The Model Architecture (Deep Learning)

We will implement a Multi-Layer Perceptron (MLP) suitable for tabular data:

Input Layer: 20 Nodes (Features).

Hidden Layer 1: 64 Neurons + ReLU Activation + Dropout (to prevent overfitting).

Hidden Layer 2: 32 Neurons + ReLU Activation.

Output Layer: 3 Neurons (Home Win, Draw, Away Win) + Softmax Activation.

Loss Function: CrossEntropyLoss.

Optimizer: Adam.

6. API Endpoint Structure (FastAPI)

GET /api/v1/live - Returns currently active matches.

GET /api/v1/fixtures?league=39 - Returns schedule for Premier League.

GET /api/v1/match/{id}/details - Returns lineups, stats, and H2H.

GET /api/v1/match/{id}/prediction - Returns the AI forecast (probabilities).

WS /ws/match/{id} - WebSocket endpoint for real-time score pushes.

7. Development Roadmap

Phase 1 (Setup): Initialize Next.js repo and FastAPI backend. Set up PostgreSQL via Docker.

Phase 2 (Data Seeding): Write the "Time Machine" script to fetch historical data from API-Football and populate the DB.

Phase 3 (The AI): Build the PyTorch MLP class. Train it on the seeded data. Save the model weights (model.pth).

Phase 4 (Frontend Core): Build the Match List, Standings Table, and detailed Match View components.

Phase 5 (Integration): Create an API endpoint that loads model.pth, accepts current match stats, and returns a prediction.

Phase 6 (Real-Time): Implement WebSockets for live score updates.

8. Professor-Pleaser Details

Model Evaluation: clearly display the model's "Accuracy" and "F1-Score" in your final report.

Comparison: Briefly compare your Deep Learning model against a baseline (e.g., "Always predict Home Win") to prove it actually learned something.

Architecture Diagram: Include a visual representation of your Neural Network layers in the thesis.




03-match-page-complete-experience.md
01-player-f2f-cards.md
07-visualization-form-graphs-squad-depth.md
02-next-goal-next-assist-model.md
05-deep-fantasy-player-salary-cap.md
06-social-live-match-chat.md
04-advanced-ai-xg-model.md

Shadcn UI + Radix UI
TanStack Query
React Hook Form + Zod
Nivo
Sonner
React Virtuoso











Use these prompts in order, one per chat session, so the LLM stays focused and quality stays high.

Prompt for 03-match-page-complete-experience.md
Prompt text:
You are a senior full-stack engineer working in my existing Football-Hub repository (Next.js frontend, FastAPI backend, PostgreSQL). Implement a complete match experience page for route /match/[id].
Requirements:

Build or extend backend endpoints so one call can return match header, score/status, lineups/substitutions, events (goals, assists, cards), last 5 matches for both teams, AI predictions, and both squads with player basics (id, name, position, photo if available).

Keep current architecture and coding style. Do not rewrite unrelated modules.

Use TanStack Query for data fetching and caching, Shadcn UI plus Radix UI for components, and Sonner for error/success feedback.

Frontend must support loading states, partial-failure states, and empty states without crashing.

Make UX responsive and polished on desktop and mobile.

Restrict competition scope to Top 5 leagues plus UCL.

Add/update minimal tests for API contracts and page rendering.

At the end, summarize exactly what changed, which files were touched, and what remains for later.

Prompt for 01-player-f2f-cards.md

Prompt text:
Implement player head-to-head comparison cards on the existing compare players flow, with photo and meaningful real stats (not EA proprietary attributes).
Requirements:

Upgrade compare players UI to show two premium card-style panels side-by-side with player photo, team, position, nationality, age, season stats, and recent form.

Include at least one visual comparison chart using Nivo (radar or bar).

Define a transparent overall score formula from available stats and show score explanation.

Use TanStack Query for fetching and caching comparison data.

Add graceful fallback when one stat source is missing.

Keep scope to Top 5 plus UCL players only.

Maintain existing routes and do not break current compare page behavior.

Provide final summary with touched files and a short list of next improvements.

Prompt for 07-visualization-form-graphs-squad-depth.md

Prompt text:
Implement form graphs and squad depth visualizations for team analysis pages in this repository.
Requirements:

Add backend support for team form metrics (last 5 and last 10 matches, points trend, goals for/against, home/away split).

Add squad depth metrics by position (starter quality, bench quality, availability if data exists).

Build frontend visual components using Nivo with strong readability on desktop and mobile.

Add controls to switch time windows and graph types where useful.

Use TanStack Query for caching and refresh behavior.

Keep charts fast and provide fallback UI when data is incomplete.

Keep scope to Top 5 plus UCL teams.

Output a concise implementation report with endpoint contracts and UI behavior.

Prompt for 02-next-goal-next-assist-model.md


AM AJUNs AICI

Prompt text:
Build the first production-ready baseline for predicting next goal scorer and next assist provider in live matches.
Requirements:

Create a training pipeline in backend AI modules with clear feature engineering from available data (match state, minute, lineups, cards, player historical form, team attacking/defensive priors).

Implement baseline ranking model that returns Top 3 candidates for next goal and Top 3 for next assist with probabilities.

Expose inference endpoint usable by match page.

Add model evaluation scripts with Top-1, Top-3, log loss, and calibration metrics.

Add clear labels about model confidence and data limitations.

Keep scope to Top 5 plus UCL.

Add docs for retraining workflow and required data refresh cadence.

Provide final summary listing files changed, model assumptions, and known limitations.

Prompt for 05-deep-fantasy-player-salary-cap.md

Prompt text:
Implement player-based fantasy mode with salary cap in this app, extending current fantasy features without breaking existing flows.
Requirements:

Design and migrate schema for player squads, budgets, matchday picks, captain choice, transfers, and points history.

Build backend rules engine for squad validation, budget validation, deadline lock, and scoring rules.

Build frontend squad builder UX with React Hook Form and Zod validation.

Add drag-and-drop support only if it stays stable and does not delay core flow.

Add leaderboard and matchday points screens.

Use Sonner for user feedback and TanStack Query for data sync.

Keep scope to Top 5 plus UCL.

End with migration notes, rollback safety notes, and test coverage summary.

Prompt for 06-social-live-match-chat.md

Prompt text:
Implement live match chat rooms tied to match id, integrated with existing backend and frontend architecture.
Requirements:

Create WebSocket chat channels per match with authentication-aware usernames.

Store recent messages for replay when a user joins late.

Add anti-spam controls (rate limit per user), basic moderation hooks, and message sanitization.

Build polished chat UI and use React Virtuoso for high-performance message list rendering.

Show live connection state and error recovery states in UI.

Ensure stable behavior under multiple concurrent users.

Keep scope to Top 5 plus UCL matches.

Provide final implementation summary and operational notes for production safety.

Prompt for 04-advanced-ai-xg-model.md

Prompt text:
Implement an advanced xG module for this project, with honest labeling based on available data granularity.
Requirements:

If shot-level data is available, build true xG model; otherwise build xG proxy and label it explicitly as proxy.
Add backend training and inference pipeline, with reproducible configuration and feature docs.
Expose API endpoints for pre-match xG forecast and live xG updates.
Add frontend xG visualizations on match page using Nivo (trend over time and team comparison).
Include model evaluation metrics and calibration checks in training outputs.
Keep scope to Top 5 plus UCL.
Add clear disclaimers in UI about confidence and data quality limits.
End with report: architecture decisions, files changed, and next steps for accuracy improvements.