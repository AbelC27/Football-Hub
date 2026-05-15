# Implementation Plan: News Ecosystem

## Overview

Convert the feature design into a series of prompts for a code-generation LLM that will implement each step with incremental progress. Make sure that each prompt builds on the previous prompts, and ends with wiring things together. There should be no hanging or orphaned code that isn't integrated into a previous step. Focus ONLY on tasks that involve writing, modifying, or testing code.

The build proceeds in this order:

1. Data layer (SQLAlchemy models, Pydantic schemas, migration script)
2. Configuration loader (env-driven with safe defaults and key redaction)
3. Pure backend services (RSS aggregator, content safety filter, OpenRouter client, recap trigger)
4. AI journalist agent (payload builder → budget/counter/backoff helpers → orchestration)
5. Unified `/api/news` router (pagination → ETag/If-None-Match)
6. Backend wiring (register router in `main.py`, extend `scheduler.py`, patch `_sync_competition_matches` for status-transition triggers)
7. Frontend client + hook (`lib/news.ts`, `useMediaQuery`)
8. `NewsSidebar` component (core fetch + infinite scroll → UI states + per-item rendering)
9. Home-page integration (`app/page.tsx` flex layout)

All test sub-tasks (property tests against the 19 design properties, example/smoke tests, and accessibility checks) are marked optional with `*` per the user instruction so the orchestrator skips them when batch-queuing.

## Tasks

- [x] 1. Set up data layer (models, schemas, migration)

  - [x] 1.1 Add `NewsArticle` and `AIRecapAttempt` SQLAlchemy models in `backend/models.py`
    - Define `NewsArticle` columns: `id`, `source_type` (CHECK in `'rss','ai_recap'`), `source_name`, `title`, `summary`, `url`, `image_url`, `published_at` (indexed), `external_id`, `match_id` (FK → `matches.id`), `created_at` (default `utcnow`)
    - Define `UniqueConstraint('source_type', 'external_id', name='uq_news_articles_source_external')`
    - Define `AIRecapAttempt` columns: `id`, `match_id` (UNIQUE, FK), `attempt_count` (default 0), `last_attempt_at`, `next_attempt_after`, `last_error`, `abandoned` (default False)
    - _Requirements: 1.1, 1.2, 1.4, 1.5, 1.7, 7.4, 7.6_

  - [x] 1.2 Add Pydantic schemas `NewsArticleOut` and `NewsListResponse` in `backend/schemas.py`
    - `NewsArticleOut`: `id`, `source_type` (Literal), `source_name`, `title`, `summary`, `url: str | None`, `image_url: str | None`, `published_at: datetime`, `match_id: int | None`
    - `NewsListResponse`: `items: list[NewsArticleOut]`, `next_cursor: str | None`
    - _Requirements: 10.1, 10.8, 10.9_

  - [x] 1.3 Create migration script `backend/migrate_news_ecosystem.py`
    - Use `engine.begin()` raw-SQL pattern from existing migration scripts
    - Create `news_articles` and `ai_recap_attempts` tables with `IF NOT EXISTS`
    - Create partial unique index `uq_news_articles_ai_recap_match ON news_articles (match_id) WHERE source_type = 'ai_recap'`
    - Create composite index `ix_news_articles_published_at_id ON news_articles (published_at DESC, id DESC)`
    - _Requirements: 1.1, 1.4, 1.5_

- [x] 2. Implement configuration loader

  - [x] 2.1 Add news-config module `backend/services/news_config.py`
    - Load `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` (default `openai/gpt-4o-mini`), `NEWS_RSS_FEEDS`, `NEWS_AI_DAILY_BUDGET`, `NEWS_AI_DENY_PATTERNS` via `python-dotenv`
    - Parse `NEWS_RSS_FEEDS` as comma-separated list with default `[Sky Sports, BBC Football]`
    - Parse `NEWS_AI_DAILY_BUDGET` as positive int with fallback 200; log a single startup `ERROR` on parse failure
    - Provide a `redact_api_key(value)` helper that returns the literal string `"***"`
    - _Requirements: 2.1, 2.2, 8.1, 9.3, 13.1, 13.3, 13.4_

  - [ ]* 2.2 Write property test `backend/tests/test_news_config_property.py`
    - **Property 3: Comma-separated env list parsing is a round-trip**
    - **Property 19: NEWS_AI_DAILY_BUDGET parses with safe fallback**
    - **Validates: Requirements 2.1, 2.2, 13.4**

- [ ] 3. Implement RSS aggregator service

  - [ ] 3.1 Implement `backend/services/news_service.py`
    - `parse_feed(feed_url, raw_bytes) -> list[ParsedRssEntry]` extracts `title`, `summary`, `link`, `published`, image URL; converts `published` to UTC; falls back to `now()` when missing; uses `guid` for `external_id` else `link`
    - `upsert_rss_article(db, entry) -> NewsArticle | None` catches `IntegrityError` on the `(source_type, external_id)` constraint, rolls back the savepoint, and logs `WARNING`
    - `fetch_and_store_rss_articles(db) -> RssIngestionReport` iterates configured feeds via `requests.get(url, timeout=10)` then `feedparser.parse(bytes)`; per-feed exceptions are caught and logged at `ERROR`; per-entry skip when missing `title` or `link` logs `WARNING` with the feed URL
    - _Requirements: 1.1, 1.3, 1.6, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9_

  - [ ]* 3.2 Write property test for RSS ingestion idempotency in `backend/tests/test_news_service_property.py`
    - **Property 1: RSS ingestion is idempotent and never raises**
    - **Validates: Requirements 1.4, 1.6, 2.8**

  - [ ]* 3.3 Write property test for RSS entry mapping (same file `backend/tests/test_news_service_property.py`)
    - **Property 2: RSS entry to NewsArticle mapping preserves all extracted fields and skip rules**
    - **Validates: Requirements 1.1, 1.3, 2.4, 2.5, 2.6, 2.7, 2.9**

  - [ ]* 3.4 Write example test for real RSS XML in `backend/tests/test_news_service_examples.py`
    - Add `backend/tests/fixtures/skysports.xml` and `backend/tests/fixtures/bbc_football.xml` samples
    - Assert `parse_feed` extracts title, link, pubDate, guid, and an image URL from each fixture
    - _Requirements: 2.4, 2.7_

- [ ] 4. Implement content safety filter

  - [ ] 4.1 Implement `backend/services/content_safety.py`
    - `class SafetyRejection(Exception)` with `reason` attribute
    - `validate_recap_text(text, *, deny_patterns) -> str` enforces word count ∈ [50, 300], rejects matches of `https?://`, `<[^>]+>`, `!\[[^\]]*\]\([^)]+\)`, and any case-insensitive deny-list substring
    - On accept: return `text.strip()` with internal runs of 3+ whitespace characters collapsed to a single space
    - _Requirements: 9.1, 9.2, 9.3, 9.5_

  - [ ]* 4.2 Write property test `backend/tests/test_content_safety_property.py`
    - **Property 11: Content safety filter is sound and idempotent on accepted text**
    - **Validates: Requirements 9.1, 9.2, 9.3, 9.5**

- [ ] 5. Implement OpenRouter client

  - [ ] 5.1 Implement `backend/services/openrouter_client.py`
    - `class ConfigurationError(RuntimeError)` and `class OpenRouterError(RuntimeError)` with `status_code` and `body_excerpt` attributes
    - `call_openrouter_chat(messages, *, model, api_key, temperature=0.6, max_tokens=400, timeout_seconds=30.0) -> OpenRouterResponse`
    - POST to `https://openrouter.ai/api/v1/chat/completions` with `Authorization: Bearer <api_key>` and the documented JSON body
    - Raise `ConfigurationError` when `api_key` is empty before any network call
    - Raise `OpenRouterError` on non-2xx status (capturing first 500 chars of body) and on missing `choices[0].message.content`
    - Return `OpenRouterResponse(content, usage)`
    - Ensure log messages emit `"***"` instead of the raw key
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 8.4, 13.3_

  - [ ]* 5.2 Write property test for OpenRouter request shape in `backend/tests/test_openrouter_client_property.py`
    - **Property 6: OpenRouter request body shape and payload bounds**
    - **Validates: Requirements 6.3, 6.5, 8.4, 8.5**

  - [ ]* 5.3 Write property test for OpenRouter error mapping (same file)
    - **Property 7: OpenRouter error mapping for non-2xx and malformed responses**
    - **Validates: Requirements 6.7, 6.8**

- [ ] 6. Implement match-finished trigger

  - [ ] 6.1 Implement `backend/services/recap_trigger.py`
    - `FINISHED_STATUSES = {"FT", "AET", "PEN"}`
    - `is_transition_to_finished(prev_status, new_status) -> bool`
    - `handle_status_change(match_id, prev_status, new_status) -> None` — logs `INFO` with `match_id` and triggering status, then submits `enqueue_recap` to a thread pool when the predicate holds and no `ai_recap` `News_Article` exists
    - `enqueue_recap(match_id, *, reason) -> None` — stub that the AI journalist module will implement (resolved by import in task 7.6)
    - _Requirements: 4.1, 4.3, 4.4_

  - [ ]* 6.2 Write property test `backend/tests/test_recap_trigger_property.py`
    - **Property 4: Recap trigger fires exactly when status crosses into a finished state and no recap exists**
    - **Validates: Requirements 4.1, 4.2, 4.3**

- [ ] 7. Implement AI journalist agent

  - [ ] 7.1 Implement `_build_recap_payload` and `RecapPayload` dataclass in `backend/services/ai_journalist.py`
    - `RecapPayload` dataclass with all fields from the design (match metadata, score, goalscorers, match_statistics, xg_home/away, xg_disclaimers)
    - `_build_recap_payload(db, match)` populates `goalscorers` from goal-typed `MatchEvent` rows ordered by ascending minute (truncated to 20), `match_statistics` from `MatchStatistics` (`{}` when absent, truncated to ≤25 keys)
    - Invoke `xg_inference_service.predict_live(db, match)`; on exception set `xg_home=xg_away=None` and append `"xG unavailable"` to `xg_disclaimers`
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 8.5_

  - [ ]* 7.2 Write property test for `_build_recap_payload` in `backend/tests/test_ai_journalist_property.py`
    - **Property 5: RecapPayload reflects database state and xG service outcome**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.6**

  - [ ] 7.3 Implement budget gate, attempt counter, and exponential backoff helpers in `backend/services/ai_journalist.py`
    - `_is_within_daily_budget(db) -> bool` counts `News_Article` rows with `source_type='ai_recap'` and `created_at` in the current UTC calendar day; emits at most one `WARNING` per scheduler tick when exhausted (use a tick-scoped set passed by callers)
    - `_get_or_create_attempt(db, match_id) -> AIRecapAttempt`
    - `_next_attempt_due(db, match_id) -> datetime | None` returns `last_attempt_at + min(2^attempt_count, 60) minutes`
    - `_record_failure(db, match_id, reason)` increments `attempt_count`, sets `last_attempt_at=now`, sets `next_attempt_after=now + min(2^new_count, 60) minutes`, sets `abandoned=True` and logs one `ERROR` when `attempt_count >= 5`
    - _Requirements: 7.4, 7.6, 7.7, 8.1, 8.2, 8.3, 13.2_

  - [ ]* 7.4 Write property test for daily budget gate (same file `backend/tests/test_ai_journalist_property.py`)
    - **Property 10: Daily budget gate**
    - **Validates: Requirements 8.2, 8.3, 13.2**

  - [ ]* 7.5 Write property test for attempt counter, abandonment, and exponential backoff (same file)
    - **Property 9: Attempt counter, abandonment, and exponential backoff**
    - **Validates: Requirements 7.6, 7.7**

  - [ ] 7.6 Implement `generate_recap_for_match` orchestration and `enqueue_recap` in `backend/services/ai_journalist.py`
    - Short-circuit on existing `ai_recap` `News_Article`, missing `OPENROUTER_API_KEY`, exhausted daily budget, abandoned attempt, and not-yet-due retry
    - Build payload, call `OpenRouter_Client.call_openrouter_chat`; on `OpenRouterError` call `_record_failure` and return
    - Run `validate_recap_text` over the response content; on `SafetyRejection` call `_record_failure` and return
    - Persist `News_Article` with `source_type='ai_recap'`, `source_name='TerraBall AI'`, `match_id`, `title="AI Match Recap: {home} vs {away}"`, `summary=cleaned_text`, `external_id="ai_recap:{match_id}"`, `published_at=now`
    - Log token `usage` as a single `INFO` line per success
    - When response word count is outside [80, 200] log a `WARNING` with `match_id` and observed count but persist unchanged
    - Re-export `enqueue_recap` for `recap_trigger` to import
    - _Requirements: 1.2, 7.1, 7.2, 7.3, 7.4, 7.5, 8.6, 9.4_

  - [ ]* 7.7 Write property test for AI recap persistence idempotency (same file)
    - **Property 8: AI recap persistence is idempotent and respects failure side-effects**
    - **Validates: Requirements 1.2, 1.5, 7.1, 7.2, 7.4, 7.5, 9.4**

  - [ ]* 7.8 Write property test for API key redaction in logs (same file)
    - **Property 18: API key redaction in logs**
    - **Validates: Requirements 13.3**

- [ ] 8. Checkpoint - Backend services compile and tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. Implement unified news API router

  - [ ] 9.1 Implement `backend/routers/news_router.py` with cursor pagination
    - `GET /api/news` with `limit: int = Query(50, ge=1, le=100)` and `cursor: str | None = Query(None)`
    - Parse `cursor` as ISO-8601; on failure raise `HTTPException(422)` identifying `cursor`
    - Query `NewsArticle` ordered by `(published_at DESC, id DESC)` with `published_at < cursor` when provided, limited to `limit`
    - Set `next_cursor` to the last item's `published_at` ISO string when result count equals `limit`, else `null`
    - For `ai_recap` rows set `url=null` and surface `match_id`; for `rss` rows surface `match_id=null`
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9_

  - [ ] 9.2 Add ETag and Cache-Control handling to `backend/routers/news_router.py`
    - Compute `ETag = W/"<max_published_at_iso>:<first_id>"`, or `W/"empty"` for empty results
    - Compare to incoming `If-None-Match`; on match return `Response(status_code=304, headers={ETag, Cache-Control})` with empty body
    - Otherwise set `Cache-Control: public, max-age=30, stale-while-revalidate=60` and `ETag`
    - _Requirements: 10.10, 10.11, 10.12_

  - [ ]* 9.3 Write property test for pagination invariants in `backend/tests/test_news_router_property.py`
    - **Property 12: `/api/news` pagination invariants**
    - **Validates: Requirements 10.2, 10.3, 10.4, 10.5**

  - [ ]* 9.4 Write property test for response schema and AI-recap field mapping (same file)
    - **Property 13: `/api/news` response schema and AI recap field mapping**
    - **Validates: Requirements 10.8, 10.9**

  - [ ]* 9.5 Write property test for query parameter validation (same file)
    - **Property 14: `/api/news` query parameter validation**
    - **Validates: Requirements 10.6, 10.7**

  - [ ]* 9.6 Write property test for ETag and conditional GET (same file)
    - **Property 15: `/api/news` ETag and conditional GET**
    - **Validates: Requirements 10.11, 10.12**

  - [ ]* 9.7 Write example tests in `backend/tests/test_news_router_examples.py`
    - Default `limit` (50) and Cache-Control header values
    - 422 error body shape for invalid `limit` and `cursor`
    - _Requirements: 10.6, 10.7, 10.10_

- [ ] 10. Wire backend integration

  - [ ] 10.1 Register `news_router` in `backend/main.py`
    - Import and `app.include_router(news_router.router)` next to existing routers
    - _Requirements: 10.1_

  - [ ] 10.2 Extend `backend/scheduler.py` with two new APScheduler jobs
    - `news_rss_refresh` on `IntervalTrigger(minutes=15)`, `replace_existing=True`, `next_run_time=now` — wraps `fetch_and_store_rss_articles` in its own `SessionLocal()` with `try/except` logging at `ERROR` and `finally` closing
    - `ai_recap_backfill` on `IntervalTrigger(minutes=10)`, `replace_existing=True` — selects matches in `{FT, AET, PEN}` without an existing `ai_recap` `News_Article` and enqueues each via `enqueue_recap`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 4.2_

  - [ ] 10.3 Patch `_sync_competition_matches` in `backend/scheduler.py` for status-transition triggers
    - Capture each match's previous `status` before mutation
    - After `db.commit()` call `recap_trigger.handle_status_change(match_id, prev_status, new_status)` for matches whose status changed
    - _Requirements: 4.1, 4.4_

  - [ ]* 10.4 Write smoke test `backend/tests/test_news_smoke.py` for scheduler job registration
    - Build a `BackgroundScheduler` (without `start()`), invoke the registration function, and assert presence of both job IDs and their interval triggers
    - _Requirements: 3.1, 3.4, 4.2_

- [ ] 11. Checkpoint - Backend integration verified
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 12. Implement frontend news client and hook

  - [ ] 12.1 Implement `frontend/src/lib/news.ts`
    - Export types `NewsSourceType`, `NewsArticle`, `NewsListResponse` matching the API schema
    - Export `fetchNews({ limit, cursor, signal })` using `fetch` against `${process.env.NEXT_PUBLIC_API_BASE_URL}/api/news` with `cache: 'no-store'`
    - Throw on non-2xx status so TanStack Query surfaces an error state
    - _Requirements: 11.3_

  - [ ] 12.2 Implement `frontend/src/hooks/useMediaQuery.ts`
    - SSR-safe hook returning a boolean for a `window.matchMedia` query string
    - _Requirements: 11.1, 11.2_

- [ ] 13. Implement NewsSidebar component

  - [ ] 13.1 Implement `frontend/src/components/news/NewsSidebar.tsx` core fetch and infinite scroll
    - `'use client'` component; render `<aside role="complementary" aria-label="Football news" class="hidden xl:block w-[360px] sticky top-0 h-screen overflow-y-auto">`
    - Use `useInfiniteQuery` keyed on `'news'`, `getNextPageParam: (last) => last.next_cursor`, `refetchInterval: 60_000`, `enabled: useMediaQuery('(min-width: 1280px)')`
    - Attach a `scroll` listener that calls `fetchNextPage()` when `scrollHeight - scrollTop - clientHeight < 200` and `hasNextPage`
    - Deduplicate paginated items by `id` via a `Map<number, NewsArticle>` before rendering
    - _Requirements: 11.1, 11.3, 11.4, 11.11, 11.12, 12.1_

  - [ ] 13.2 Implement NewsSidebar UI states and per-item rendering in `frontend/src/components/news/NewsSidebar.tsx`
    - Loading skeleton during initial load using `components/ui/skeleton.tsx`
    - Error state showing `"News unavailable"` with a `<button>` that calls `refetch()`
    - For `source_type='ai_recap'`: render the badge `<span aria-label="AI generated match recap"><span aria-hidden="true">🤖</span> AI Match Recap</span>` inside `<Link href={'/match/' + item.match_id}>`
    - For `source_type='rss'`: render `<a href={item.url} target="_blank" rel="noopener noreferrer">` wrapping the title
    - When `image_url` is present render `<img alt={item.title}>`
    - Live-update region uses `aria-live="polite"` and `aria-atomic="false"`; items are focusable via document order
    - _Requirements: 11.5, 11.6, 11.7, 11.8, 11.9, 11.10, 11.12, 12.1, 12.2, 12.3, 12.4, 12.7, 12.8_

  - [ ]* 13.3 Write property test for per-item rendering in `frontend/src/components/news/NewsSidebar.test.tsx`
    - **Property 16: NewsSidebar per-item rendering contract**
    - **Validates: Requirements 11.5, 11.6, 11.7, 12.8**

  - [ ]* 13.4 Write property test for pagination and deduplication (same file)
    - **Property 17: NewsSidebar pagination and deduplication**
    - **Validates: Requirements 11.11, 11.12**

  - [ ]* 13.5 Write example tests in `frontend/src/components/news/NewsSidebar.examples.test.tsx`
    - Loading skeleton appears during the initial fetch
    - Error state renders `"News unavailable"` and a retry button operable with Enter and Space
    - ARIA attributes (`role="complementary"`, `aria-label="Football news"`, `aria-live="polite"`, `aria-atomic="false"`) are present
    - Image `alt` falls back to article `title`
    - _Requirements: 11.8, 11.9, 11.10, 12.1, 12.2, 12.3, 12.7, 12.8_

  - [ ]* 13.6 Add axe-core accessibility smoke test (same file `NewsSidebar.examples.test.tsx`)
    - Run `axe.run` on the rendered sidebar and assert no `color-contrast` or `focus-visible` violations
    - _Requirements: 12.5, 12.6_

- [ ] 14. Integrate sidebar into home page

  - [ ] 14.1 Mount `NewsSidebar` in `frontend/src/app/page.tsx`
    - Wrap existing main content in `<div class="xl:flex xl:gap-6 xl:items-start">` with `<div class="flex-1 min-w-0">{existing}</div>` and `<NewsSidebar />`
    - Below `xl` breakpoint the sidebar collapses to `display: none` and main content takes full width
    - _Requirements: 11.1, 11.2_

- [ ] 15. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and will be skipped by the orchestrator when batch-queuing. They cover property-based tests against the 19 design properties (Hypothesis on the backend, fast-check on the frontend), example/smoke tests for headers, fixtures, and scheduler registration, and accessibility checks via axe-core.
- Each property test sub-task references its design property number and the requirement clauses it validates so traceability survives even when tests are added later.
- Implementation tasks (non-optional) form a complete, runnable feature on their own; the user can opt to layer in tests at any point.
- Multiple property tests share a single test file (e.g. `test_ai_journalist_property.py`, `test_news_router_property.py`); the dependency graph below sequences these into different waves to avoid file-write conflicts.
- Checkpoints (tasks 8, 11, 15) and top-level parent tasks without sub-tasks are excluded from the dependency graph per workflow conventions.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "2.1", "4.1", "12.1", "12.2"] },
    { "id": 1, "tasks": ["1.3", "2.2", "3.1", "4.2", "5.1", "6.1"] },
    { "id": 2, "tasks": ["3.2", "5.2", "6.2", "7.1", "9.1"] },
    { "id": 3, "tasks": ["3.3", "5.3", "7.2", "7.3", "9.2"] },
    { "id": 4, "tasks": ["3.4", "7.4", "7.6", "9.3", "9.7"] },
    { "id": 5, "tasks": ["7.5", "9.4", "10.1", "10.2"] },
    { "id": 6, "tasks": ["7.7", "9.5", "10.3", "13.1"] },
    { "id": 7, "tasks": ["7.8", "9.6", "10.4", "13.2"] },
    { "id": 8, "tasks": ["13.3", "13.5", "14.1"] },
    { "id": 9, "tasks": ["13.4", "13.6"] }
  ]
}
```
