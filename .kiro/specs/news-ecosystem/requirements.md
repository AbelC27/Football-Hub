# Requirements Document

## Introduction

The News Ecosystem adds an HLTV-style news experience to the TerraBall Football Hub. It combines a traditional RSS feed aggregator (pulling public sports feeds such as Sky Sports and BBC Football) with an AI Match Journalist Agent that generates post-match recaps when matches finish. Articles from both sources are persisted in PostgreSQL via SQLAlchemy, exposed through a unified `/api/news` endpoint, and rendered in a fixed-width `NewsSidebar` on the home page. AI-generated recaps carry a visual badge so readers can distinguish editorial RSS items from AI-authored content.

The feature has four pillars:
1. RSS feed aggregator (FastAPI service + APScheduler job)
2. AI Match Journalist Agent (xG-aware OpenRouter integration)
3. Persistent storage layer (SQLAlchemy models for news articles)
4. Unified delivery (`/api/news` endpoint + Next.js sidebar)

## Glossary

- **News_Service**: Backend service in `backend/services/news_service.py` responsible for fetching, parsing, and persisting RSS feed entries.
- **AI_Journalist_Agent**: Backend service that generates a post-match recap by sending match data to OpenRouter and persisting the response.
- **Match_Recap_Trigger**: Backend component that detects matches whose status transitions to `FT`, `AET`, or `PEN` and enqueues them for the AI_Journalist_Agent.
- **OpenRouter_Client**: Backend client wrapping HTTP calls to the OpenRouter API at `https://openrouter.ai/api/v1/chat/completions`.
- **News_API**: FastAPI router exposing `GET /api/news` which returns a unified, chronologically sorted list of `NewsArticle` records.
- **News_Article**: SQLAlchemy model `NewsArticle` representing one item in the unified feed (either RSS-sourced or AI-generated).
- **News_Sidebar**: Next.js client component `NewsSidebar.tsx` rendered on the right of the home page that displays `News_Article` items.
- **AI_Badge**: Visual indicator (label "🤖 AI Match Recap") shown on `News_Sidebar` items whose source is the AI_Journalist_Agent.
- **RSS_Feed_Source**: A URL pointing to a public sports RSS feed configured via the `NEWS_RSS_FEEDS` environment variable.
- **xG_Model**: The existing expected-goals model exposed by `backend/ai/xg_model.py`.
- **Finished_Match**: A `Match` row whose `status` is one of `FT`, `AET`, `PEN`.
- **Recap_Payload**: The structured dictionary sent to OpenRouter containing match metadata, score, statistics, goalscorers, and xG values for one Finished_Match.
- **Article_Source_Type**: An enumerated string field on `News_Article` with values `rss` or `ai_recap`.
- **Recap_Attempt_Counter**: A persistent integer column on `News_Article` (or a sibling table) tracking the number of OpenRouter generation attempts for a given `match_id`.
- **Daily_Recap_Budget**: An operator-configured upper bound on how many AI recaps the system will generate per UTC calendar day, read from the `NEWS_AI_DAILY_BUDGET` environment variable.
- **Content_Safety_Filter**: A backend component that inspects LLM output before persistence and rejects content matching disallowed patterns.

## Requirements

### Requirement 1: News Article Persistence

**User Story:** As a backend developer, I want news articles from all sources persisted in PostgreSQL, so that the API can serve a consistent, queryable feed even when external feeds are unreachable.

#### Acceptance Criteria

1. THE News_Service SHALL persist each ingested RSS entry as a `News_Article` row with fields `id`, `source_type`, `source_name`, `title`, `summary`, `url`, `image_url`, `published_at`, `external_id`, `created_at`.
2. THE AI_Journalist_Agent SHALL persist each generated recap as a `News_Article` row with `source_type` equal to `ai_recap` and an associated `match_id` foreign key referencing `matches.id`.
3. WHEN a `News_Article` row is inserted, THE News_Service SHALL set `created_at` to the current UTC timestamp.
4. THE News_Article schema SHALL enforce a unique constraint on the pair (`source_type`, `external_id`) so that the same RSS entry cannot be persisted twice.
5. THE News_Article schema SHALL enforce a unique constraint on `match_id` when `source_type` is `ai_recap`, so that exactly one AI recap exists per Finished_Match.
6. IF a database insert fails because of a unique-constraint violation, THEN THE News_Service SHALL log a warning at level `WARNING` and continue processing remaining entries without raising.
7. THE News_Article `source_type` field SHALL only accept the values `rss` or `ai_recap`.

### Requirement 2: RSS Feed Aggregation

**User Story:** As a user, I want the news feed populated with fresh sports headlines, so that the sidebar shows current football news.

#### Acceptance Criteria

1. THE News_Service SHALL read the list of RSS_Feed_Source URLs from the `NEWS_RSS_FEEDS` environment variable as a comma-separated list.
2. WHERE `NEWS_RSS_FEEDS` is unset, THE News_Service SHALL default to the URLs `https://www.skysports.com/rss/12040` (Sky Sports Football) and `https://feeds.bbci.co.uk/sport/football/rss.xml` (BBC Football).
3. WHEN the News_Service is invoked, THE News_Service SHALL fetch each RSS_Feed_Source using `feedparser` with an HTTP timeout of 10 seconds.
4. WHEN parsing an RSS entry, THE News_Service SHALL extract `title`, `summary`, `link`, `published`, and the first enclosure or media-thumbnail URL when present.
5. IF an RSS entry is missing a `title` or `link`, THEN THE News_Service SHALL skip the entry and log a warning identifying the feed URL.
6. IF an RSS entry has no `published` date, THEN THE News_Service SHALL set `published_at` to the current UTC timestamp.
7. THE News_Service SHALL set `external_id` for an RSS entry to the entry's `guid` value when present, otherwise to its `link` value.
8. IF fetching an RSS_Feed_Source raises a network or parse exception, THEN THE News_Service SHALL log the error and continue processing remaining feeds without raising.
9. THE News_Service SHALL convert all parsed `published_at` timestamps to UTC before persisting.

### Requirement 3: Scheduled RSS Refresh

**User Story:** As a user, I want the news feed to refresh automatically, so that I see new headlines without reloading manually.

#### Acceptance Criteria

1. WHEN the FastAPI application starts, THE scheduler SHALL register a background job that invokes the News_Service RSS ingestion every 15 minutes.
2. WHEN the FastAPI application starts, THE scheduler SHALL invoke the News_Service RSS ingestion once immediately at startup.
3. IF an RSS ingestion job raises an exception, THEN THE scheduler SHALL log the error at level `ERROR` and keep the job registered for the next interval.
4. THE scheduler SHALL register the RSS ingestion job with the unique id `news_rss_refresh` and `replace_existing=True`.

### Requirement 4: Match-Finished Trigger for AI Journalist

**User Story:** As a user, I want an AI-written recap to appear shortly after a match ends, so that I can read post-match analysis in the sidebar.

#### Acceptance Criteria

1. WHEN the existing match-sync scheduler updates a `Match` row whose `status` transitions from a non-finished value to one of `FT`, `AET`, `PEN`, THE Match_Recap_Trigger SHALL enqueue the match for the AI_Journalist_Agent.
2. WHEN the FastAPI application starts, THE scheduler SHALL register a background job named `ai_recap_backfill` that runs every 10 minutes and enqueues any Finished_Match without an existing `ai_recap` News_Article.
3. IF a Finished_Match already has a `News_Article` with `source_type='ai_recap'` and the same `match_id`, THEN THE Match_Recap_Trigger SHALL NOT enqueue the match.
4. WHEN the Match_Recap_Trigger enqueues a match, THE Match_Recap_Trigger SHALL log an INFO entry containing the `match_id` and the triggering status.

### Requirement 5: AI Recap Data Gathering

**User Story:** As an AI agent, I want a complete data payload for a finished match, so that the generated recap is grounded in real statistics.

#### Acceptance Criteria

1. WHEN the AI_Journalist_Agent processes a Finished_Match, THE AI_Journalist_Agent SHALL build a Recap_Payload containing: `match_id`, `home_team_name`, `away_team_name`, `home_score`, `away_score`, `competition_name`, `kickoff_utc`, `goalscorers`, `match_statistics`, `xg_home`, `xg_away`, and `xg_disclaimers`.
2. THE AI_Journalist_Agent SHALL populate `goalscorers` from `MatchEvent` rows whose `event_type` indicates a goal, ordered by `minute` ascending, with each entry containing `minute`, `team_id`, and `player_name`.
3. THE AI_Journalist_Agent SHALL populate `match_statistics` from the `MatchStatistics` row matching `match_id` when present.
4. THE AI_Journalist_Agent SHALL populate `xg_home`, `xg_away`, and `xg_disclaimers` by invoking the existing xG_Model live inference for the match.
5. IF the xG_Model raises an exception or returns no value for a match, THEN THE AI_Journalist_Agent SHALL set `xg_home` and `xg_away` to `null` and append a string `"xG unavailable"` to `xg_disclaimers`.
6. IF a `MatchStatistics` row does not exist for the match, THEN THE AI_Journalist_Agent SHALL set `match_statistics` to an empty object `{}`.

### Requirement 6: OpenRouter LLM Integration

**User Story:** As a user, I want the AI recap to read like a professional sports journalist, so that the sidebar feels editorial rather than templated.

#### Acceptance Criteria

1. THE OpenRouter_Client SHALL read the API key from the `OPENROUTER_API_KEY` environment variable.
2. THE OpenRouter_Client SHALL read the model identifier from the `OPENROUTER_MODEL` environment variable, defaulting to `openai/gpt-4o-mini`.
3. WHEN the AI_Journalist_Agent calls the OpenRouter_Client, THE OpenRouter_Client SHALL POST to `https://openrouter.ai/api/v1/chat/completions` with header `Authorization: Bearer ${OPENROUTER_API_KEY}` and JSON body containing `model`, `messages`, `temperature=0.6`, and `max_tokens=400`.
4. THE OpenRouter_Client SHALL include a system message instructing the model to act as a professional football journalist who writes a concise, engaging post-match recap of 100 to 150 words emphasizing match statistics and the xG narrative, using only the provided data and inventing no facts.
5. THE OpenRouter_Client SHALL include a user message containing the Recap_Payload serialized as JSON.
6. THE OpenRouter_Client SHALL apply an HTTP timeout of 30 seconds.
7. IF the OpenRouter response status code is not in the 200-299 range, THEN THE OpenRouter_Client SHALL raise an `OpenRouterError` containing the status code and response body excerpt.
8. IF the OpenRouter response is missing the `choices[0].message.content` field, THEN THE OpenRouter_Client SHALL raise an `OpenRouterError` indicating a malformed response.
9. WHERE `OPENROUTER_API_KEY` is unset, THE OpenRouter_Client SHALL raise a `ConfigurationError` before performing any network call.

### Requirement 7: Recap Persistence and Idempotency

**User Story:** As a backend developer, I want recap generation to be idempotent and resilient, so that retries do not produce duplicate articles or break on transient failures.

#### Acceptance Criteria

1. WHEN the AI_Journalist_Agent receives a successful LLM response, THE AI_Journalist_Agent SHALL persist a `News_Article` with `source_type='ai_recap'`, `source_name='TerraBall AI'`, `match_id` set to the Finished_Match id, `title` set to `"AI Match Recap: {home_team_name} vs {away_team_name}"`, `summary` set to the LLM content, and `published_at` set to the current UTC timestamp.
2. THE AI_Journalist_Agent SHALL set `external_id` of the persisted recap to `"ai_recap:{match_id}"`.
3. IF the LLM response content has a word count outside the inclusive range 80 to 200, THEN THE AI_Journalist_Agent SHALL log a warning containing `match_id` and observed word count, and persist the recap unchanged.
4. IF the OpenRouter_Client raises an `OpenRouterError`, THEN THE AI_Journalist_Agent SHALL log the error with `match_id`, leave no `News_Article` row persisted for that match, increment the Recap_Attempt_Counter for that `match_id`, and allow the next scheduler run to retry.
5. WHEN the AI_Journalist_Agent is invoked for a `match_id` that already has a `News_Article` with `source_type='ai_recap'`, THE AI_Journalist_Agent SHALL return without contacting OpenRouter.
6. IF the Recap_Attempt_Counter for a `match_id` is greater than or equal to 5, THEN THE AI_Journalist_Agent SHALL skip recap generation for that match and log a single ERROR-level message identifying the `match_id` and the abandonment reason.
7. WHEN the AI_Journalist_Agent retries a failed match, THE AI_Journalist_Agent SHALL apply exponential backoff such that retry N is attempted only after `min(2^N, 60)` minutes have elapsed since the previous attempt.

### Requirement 8: AI Cost Controls

**User Story:** As an operator, I want bounded LLM spend, so that a flood of finished matches or a runaway loop does not exhaust the OpenRouter budget.

#### Acceptance Criteria

1. THE backend SHALL read `NEWS_AI_DAILY_BUDGET` from environment variables as a positive integer, defaulting to 200 recaps per UTC calendar day.
2. WHEN the AI_Journalist_Agent is about to call the OpenRouter_Client, THE AI_Journalist_Agent SHALL count `News_Article` rows with `source_type='ai_recap'` and `created_at` within the current UTC calendar day.
3. IF the count from criterion 2 is greater than or equal to `NEWS_AI_DAILY_BUDGET`, THEN THE AI_Journalist_Agent SHALL skip the OpenRouter call, log a single WARNING per scheduler tick stating that the daily budget is exhausted, and defer remaining matches until the next UTC day.
4. THE OpenRouter_Client SHALL set the OpenRouter request body field `max_tokens` to 400 to bound per-call output cost.
5. THE Recap_Payload SHALL truncate `goalscorers` to the first 20 entries and `match_statistics` to at most 25 key-value pairs to bound per-call input cost.
6. WHEN the OpenRouter response includes a `usage` object, THE AI_Journalist_Agent SHALL log a single INFO entry containing `match_id`, `prompt_tokens`, `completion_tokens`, and `total_tokens`.

### Requirement 9: Content Safety and Length Guarantees

**User Story:** As a user, I want AI recaps to be safe, on-topic, and consistently sized, so that the sidebar never exposes harmful or malformed content.

#### Acceptance Criteria

1. THE Content_Safety_Filter SHALL reject LLM output whose word count is below 50 or above 300.
2. THE Content_Safety_Filter SHALL reject LLM output that contains URLs, HTML tags, or Markdown image syntax.
3. THE Content_Safety_Filter SHALL reject LLM output that matches a configured deny-list of patterns provided via the `NEWS_AI_DENY_PATTERNS` environment variable as a comma-separated list of case-insensitive substrings.
4. IF the Content_Safety_Filter rejects an LLM output, THEN THE AI_Journalist_Agent SHALL discard the response, log a WARNING with `match_id` and rejection reason, increment the Recap_Attempt_Counter for that `match_id`, and persist no `News_Article` row.
5. WHEN the Content_Safety_Filter accepts an LLM output, THE AI_Journalist_Agent SHALL strip leading and trailing whitespace and collapse internal runs of whitespace longer than two characters to a single space before persistence.
6. THE OpenRouter_Client system prompt SHALL instruct the model to write between 100 and 150 words, to use only data from the user message, to avoid speculation, and to avoid quoting non-public information.

### Requirement 10: Unified News API

**User Story:** As a frontend developer, I want a single endpoint for all news, so that the sidebar component does not need to merge sources client-side.

#### Acceptance Criteria

1. THE News_API SHALL expose `GET /api/news` returning a JSON object `{"items": NewsArticle[], "next_cursor": string|null}`.
2. THE News_API SHALL accept a query parameter `limit` (integer, default 50, maximum 100) and a query parameter `cursor` (ISO-8601 UTC timestamp string, optional).
3. THE News_API SHALL return `News_Article` rows ordered by `published_at` descending and break ties by `id` descending.
4. WHERE the `cursor` query parameter is provided, THE News_API SHALL return only `News_Article` rows whose `published_at` is strictly less than the cursor value.
5. THE News_API SHALL set `next_cursor` to the `published_at` of the last item in the response when the response contains exactly `limit` items, otherwise to `null`.
6. IF `limit` is outside the inclusive range 1 to 100, THEN THE News_API SHALL respond with HTTP status 422 and an error body identifying the invalid parameter.
7. IF `cursor` cannot be parsed as an ISO-8601 timestamp, THEN THE News_API SHALL respond with HTTP status 422 and an error body identifying the invalid parameter.
8. THE News_API response item schema SHALL include the fields `id`, `source_type`, `source_name`, `title`, `summary`, `url`, `image_url`, `published_at`, `match_id`.
9. WHERE a `News_Article` has `source_type='ai_recap'`, THE News_API SHALL set `url` to `null` and `match_id` to the associated match id.
10. THE News_API SHALL set the response header `Cache-Control` to `public, max-age=30, stale-while-revalidate=60`.
11. THE News_API SHALL set an `ETag` response header derived from the maximum `published_at` and the `id` of the first item in the response.
12. WHEN the request includes an `If-None-Match` header equal to the current `ETag`, THE News_API SHALL respond with HTTP status 304 and an empty body.

### Requirement 11: News Sidebar Component

**User Story:** As a user, I want a fixed-width news sidebar on the right side of the home page, so that I can browse news without leaving the dashboard.

#### Acceptance Criteria

1. THE News_Sidebar SHALL render on the home page (`frontend/src/app/page.tsx`) at a fixed width of 360 pixels on viewports at least 1280 pixels wide.
2. WHILE the viewport width is below 1280 pixels, THE News_Sidebar SHALL be hidden.
3. WHEN the News_Sidebar mounts, THE News_Sidebar SHALL fetch `GET /api/news?limit=50` and render the returned items.
4. WHILE the News_Sidebar is mounted, THE News_Sidebar SHALL refetch `GET /api/news?limit=50` every 60 seconds.
5. WHEN rendering an item with `source_type='ai_recap'`, THE News_Sidebar SHALL display the AI_Badge with text `🤖 AI Match Recap`.
6. WHEN rendering an item with `source_type='rss'`, THE News_Sidebar SHALL render the title as a hyperlink whose `href` is the item `url` and which opens in a new tab with `rel="noopener noreferrer"`.
7. WHEN rendering an item with `source_type='ai_recap'`, THE News_Sidebar SHALL render the item as a hyperlink whose `href` is `/match/{match_id}`.
8. WHILE the initial fetch is in progress, THE News_Sidebar SHALL display a loading skeleton.
9. IF the fetch returns an error or non-2xx status, THEN THE News_Sidebar SHALL display the message `"News unavailable"` and a retry button.
10. WHEN the retry button is clicked, THE News_Sidebar SHALL refetch `GET /api/news?limit=50`.
11. WHEN the user scrolls within the News_Sidebar to a position less than 200 pixels from the bottom and `next_cursor` is non-null, THE News_Sidebar SHALL fetch the next page using the current `next_cursor` and append items to the rendered list.
12. WHEN the News_Sidebar appends paginated items, THE News_Sidebar SHALL deduplicate by `id` so that the rendered list contains each `News_Article` at most once.

### Requirement 12: Accessibility

**User Story:** As a user relying on assistive technology, I want the news sidebar to be perceivable and operable, so that I can read and navigate news with a screen reader and keyboard.

#### Acceptance Criteria

1. THE News_Sidebar SHALL render its container with `role="complementary"` and an `aria-label` attribute set to `"Football news"`.
2. THE AI_Badge SHALL include an `aria-label` attribute set to `"AI generated match recap"` and SHALL render the emoji `🤖` with `aria-hidden="true"`.
3. THE News_Sidebar SHALL render the live-update region with `aria-live="polite"` and `aria-atomic="false"`.
4. THE News_Sidebar SHALL render each item as a focusable element reachable in document order via the Tab key.
5. WHEN an item receives keyboard focus, THE News_Sidebar SHALL render a visible focus ring with a contrast ratio of at least 3 to 1 against the adjacent background.
6. THE News_Sidebar text content SHALL meet WCAG 2.1 AA contrast (4.5 to 1 for body text, 3 to 1 for text 18pt or larger).
7. THE retry button defined in Requirement 11 SHALL be operable with both Enter and Space keys when focused.
8. WHEN a `News_Article` has an `image_url`, THE News_Sidebar SHALL render the image with an `alt` attribute set to the article `title`.

### Requirement 13: Configuration and Secrets

**User Story:** As an operator, I want all third-party credentials and feed URLs to be configurable via environment variables, so that the application can be deployed without code changes.

#### Acceptance Criteria

1. THE backend SHALL read `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `NEWS_RSS_FEEDS`, `NEWS_AI_DAILY_BUDGET`, and `NEWS_AI_DENY_PATTERNS` from environment variables loaded via `python-dotenv`.
2. WHERE `OPENROUTER_API_KEY` is unset, THE AI_Journalist_Agent SHALL skip recap generation and log a single WARNING per scheduler tick stating that recap generation is disabled.
3. WHEN the backend logs an event referencing the OpenRouter configuration, THE backend SHALL redact the `OPENROUTER_API_KEY` value and emit only the string `"***"` in its place.
4. WHERE the configured `NEWS_AI_DAILY_BUDGET` value cannot be parsed as a positive integer, THE backend SHALL log an ERROR at startup and use the default value 200.
