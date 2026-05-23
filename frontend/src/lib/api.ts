const API_BASE_URL = "http://localhost:8000/api/v1";

export interface Match {
  id: number;
  start_time: string;
  status: string;
  home_score?: number;
  away_score?: number;
  home_team_id: number;
  away_team_id: number;
  home_team_name?: string;
  away_team_name?: string;
  home_team_logo?: string;
  away_team_logo?: string;
  home_team_stadium?: string;
  home_players?: Array<{ name: string; position: string }>;
  away_players?: Array<{ name: string; position: string }>;
  league_id?: number;
  prediction?: {
    home_win_prob: number;
    draw_prob: number;
    away_win_prob: number;
    confidence_score: number;
  };
}

export interface MatchExperienceCompetition {
  id: number;
  name: string;
  country?: string | null;
  logo_url?: string | null;
}

export interface MatchExperiencePlayer {
  id: number;
  name: string;
  position?: string | null;
  photo_url?: string | null;
}

export interface MatchExperienceEvent {
  id: number;
  minute: number;
  event_type: "goal" | "assist" | "card" | string;
  team_id?: number | null;
  player_name?: string | null;
  assist_player?: string | null;
  card_type?: string | null;
  detail?: string | null;
}

export interface MatchExperienceSubstitution {
  id: number;
  minute: number;
  team_id?: number | null;
  player_name?: string | null;
  detail?: string | null;
}

export interface MatchExperienceRecentMatch {
  match_id: number;
  start_time: string;
  status: string;
  opponent_name: string;
  opponent_logo?: string | null;
  is_home: boolean;
  team_score?: number | null;
  opponent_score?: number | null;
  result?: "W" | "D" | "L" | null;
  competition_name?: string | null;
}

export interface MatchExperience {
  header: {
    match_id: number;
    start_time: string;
    status: string;
    score: {
      home?: number | null;
      away?: number | null;
    };
    competition?: MatchExperienceCompetition | null;
    current_minute?: number | null;
  };
  teams: {
    home: {
      id: number;
      name: string;
      logo_url?: string | null;
      stadium?: string | null;
    };
    away: {
      id: number;
      name: string;
      logo_url?: string | null;
      stadium?: string | null;
    };
  };
  prediction?: {
    id: number;
    match_id: number;
    home_win_prob: number;
    draw_prob: number;
    away_win_prob: number;
    confidence_score: number;
  } | null;
  events: MatchExperienceEvent[];
  lineups: {
    home_starting_xi: MatchExperiencePlayer[];
    away_starting_xi: MatchExperiencePlayer[];
    substitutions: MatchExperienceSubstitution[];
    source: string;
  };
  form: {
    home_last_five: MatchExperienceRecentMatch[];
    away_last_five: MatchExperienceRecentMatch[];
  };
  squads: {
    home: MatchExperiencePlayer[];
    away: MatchExperiencePlayer[];
  };
  partial_failures: Array<{
    section: string;
    message: string;
  }>;
}

export interface NextEventCandidate {
  rank: number;
  player_id: number;
  player_name: string;
  team_id: number;
  team_name: string;
  probability: number;
  full_distribution_probability: number;
}

export interface NextEventTaskPrediction {
  task: "goal" | "assist" | string;
  minute_context: number;
  source: "trained_model" | "heuristic_fallback" | "unavailable" | string;
  candidate_count: number;
  top_candidates: NextEventCandidate[];
  top3_probability_mass_from_full_distribution: number;
  confidence_score: number;
  confidence_label: "high" | "medium" | "low" | string;
  data_limitations: string[];
}

export interface NextEventPredictionResponse {
  match_id: number;
  scope: string;
  model_version: string;
  generated_at_utc: string;
  global_limitations: string[];
  next_goal: NextEventTaskPrediction;
  next_assist: NextEventTaskPrediction;
}

export interface XGModelMetadata {
  mode: "true_xg" | "xg_proxy" | string;
  is_proxy: boolean;
  model_version: string;
  trained_at_utc?: string | null;
  confidence_score: number;
  confidence_label: "high" | "medium" | "low" | string;
  granularity_reason?: string | null;
  training_sample_size: number;
  calibration_summary: Record<string, number>;
}

export interface MatchXGTeamValue {
  team_id: number;
  team_name: string;
  xg: number;
}

export interface MatchXGPreMatchResponse {
  match_id: number;
  scope: string;
  generated_at_utc: string;
  model: XGModelMetadata;
  home: MatchXGTeamValue;
  away: MatchXGTeamValue;
  expected_total_xg: number;
  feature_coverage: Record<string, number>;
  disclaimers: string[];
}

export interface MatchXGTimelinePoint {
  minute: number;
  home_xg: number;
  away_xg: number;
}

export interface MatchXGLiveResponse {
  match_id: number;
  scope: string;
  generated_at_utc: string;
  model: XGModelMetadata;
  minute_context: number;
  home_current_xg: number;
  away_current_xg: number;
  timeline: MatchXGTimelinePoint[];
  pre_match_baseline: {
    home_xg: number;
    away_xg: number;
  };
  live_signals: Record<string, number | boolean>;
  disclaimers: string[];
}

export interface Team {
  id: number;
  name: string;
  logo_url: string;
  stadium: string;
  league?: {
    id: number;
    name: string;
    country: string;
    logo_url: string;
  };
}

export interface Player {
  id: number;
  name: string;
  position: string;
  nationality: string;
  height: string;
  team?: {
    id: number;
    name: string;
    logo_url: string;
  };
}

export interface SearchResults {
  teams: Team[];
  players: Player[];
}

export interface League {
  id: number;
  name: string;
  country: string;
  logo_url: string;
}

export async function getLeagues(): Promise<League[]> {
  const res = await fetch(`${API_BASE_URL}/leagues`);
  if (!res.ok) throw new Error("Failed to fetch leagues");
  return res.json();
}

// ---------------------------------------------------------------------------
// Match events (goals / assists / cards / subs).
//
// Powered by /api/v1/match/{id}/events which chains api-sports.io and FPL.
// Every event row carries enough info to render either the api-sports rich
// shape (with minute timing) or the FPL aggregate shape (minute === null,
// scorer / assister live as separate rows).
// ---------------------------------------------------------------------------

export type MatchEventType = "Goal" | "Assist" | "Card" | "Subst" | string;

export interface MatchEventEntry {
  id: number;
  minute: number | null;
  event_type: MatchEventType;
  team_id: number | null;
  player_id: number | null;
  player_name: string | null;
  assist_player_id: number | null;
  assist_player_name: string | null;
  detail: string | null;
}

export async function getMatchEventEntries(
  matchId: number,
  signal?: AbortSignal
): Promise<MatchEventEntry[]> {
  const res = await fetch(`${API_BASE_URL}/match/${matchId}/events`, { signal });
  if (res.status === 503) {
    // Provider quota exceeded — caller decides how to surface.
    const payload = await res.json().catch(() => null);
    throw new Error(payload?.detail || "Provider quota exceeded; try later.");
  }
  if (!res.ok) {
    const payload = await res.json().catch(() => null);
    throw new Error(payload?.detail || "Failed to fetch match events");
  }
  return res.json();
}

export async function getMatchEventsBulk(
  matchIds: number[],
  signal?: AbortSignal
): Promise<Record<string, MatchEventEntry[]>> {
  if (matchIds.length === 0) return {};
  // Cap at 200 to match the backend; chunk if a caller ever overshoots.
  const ids = matchIds.slice(0, 200).join(",");
  const res = await fetch(`${API_BASE_URL}/match-events/bulk?match_ids=${ids}`, { signal });
  if (!res.ok) {
    const payload = await res.json().catch(() => null);
    throw new Error(payload?.detail || "Failed to fetch match events");
  }
  return res.json();
}

export type MatchStatusGroup = "live" | "upcoming" | "finished";

export interface PaginatedMatches {
  items: Match[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface GetLiveMatchesParams {
  status?: MatchStatusGroup | string;
  leagueId?: number;
  limit?: number;
  offset?: number;
  order?: "asc" | "desc";
  daysBack?: number;
  daysForward?: number;
  signal?: AbortSignal;
}

export async function getLiveMatches(
  params: GetLiveMatchesParams = {}
): Promise<PaginatedMatches> {
  const search = new URLSearchParams();
  if (params.status) search.set("status", params.status);
  if (typeof params.leagueId === "number") search.set("league_id", String(params.leagueId));
  if (typeof params.limit === "number") search.set("limit", String(params.limit));
  if (typeof params.offset === "number") search.set("offset", String(params.offset));
  if (params.order) search.set("order", params.order);
  if (typeof params.daysBack === "number") search.set("days_back", String(params.daysBack));
  if (typeof params.daysForward === "number") search.set("days_forward", String(params.daysForward));

  const suffix = search.toString() ? `?${search.toString()}` : "";
  const res = await fetch(`${API_BASE_URL}/live-matches${suffix}`, { signal: params.signal });
  if (!res.ok) throw new Error("Failed to fetch live matches");

  const payload = await res.json();
  // Backwards compatibility: older builds returned a bare array.
  if (Array.isArray(payload)) {
    return {
      items: payload as Match[],
      total: payload.length,
      limit: payload.length,
      offset: 0,
      has_more: false,
    };
  }
  return payload as PaginatedMatches;
}

export async function getMatchExperience(matchId: number): Promise<MatchExperience> {
  const res = await fetch(`${API_BASE_URL}/match/${matchId}/experience`);

  if (!res.ok) {
    const errorPayload = await res.json().catch(() => null);
    throw new Error(errorPayload?.detail || "Failed to fetch match experience");
  }

  return res.json();
}

export async function getMatchNextEventsPrediction(
  matchId: number,
  minute?: number
): Promise<NextEventPredictionResponse> {
  const params = new URLSearchParams();
  if (typeof minute === "number") params.set("minute", String(minute));

  const suffix = params.toString() ? `?${params.toString()}` : "";
  const res = await fetch(`${API_BASE_URL}/match/${matchId}/next-events/prediction${suffix}`);

  if (!res.ok) {
    const errorPayload = await res.json().catch(() => null);
    throw new Error(errorPayload?.detail || "Failed to fetch next-event predictions");
  }

  return res.json();
}

export async function getMatchXGPreMatch(matchId: number): Promise<MatchXGPreMatchResponse> {
  const res = await fetch(`${API_BASE_URL}/match/${matchId}/xg/pre-match`);

  if (!res.ok) {
    const errorPayload = await res.json().catch(() => null);
    throw new Error(errorPayload?.detail || "Failed to fetch pre-match xG forecast");
  }

  return res.json();
}

export async function getMatchXGLive(
  matchId: number,
  minute?: number
): Promise<MatchXGLiveResponse> {
  const params = new URLSearchParams();
  if (typeof minute === "number") params.set("minute", String(minute));

  const suffix = params.toString() ? `?${params.toString()}` : "";
  const res = await fetch(`${API_BASE_URL}/match/${matchId}/xg/live${suffix}`);

  if (!res.ok) {
    const errorPayload = await res.json().catch(() => null);
    throw new Error(errorPayload?.detail || "Failed to fetch live xG update");
  }

  return res.json();
}

export async function getFixtures(leagueId: number): Promise<Match[]> {
  const res = await fetch(`${API_BASE_URL}/fixtures?league=${leagueId}`);
  if (!res.ok) throw new Error("Failed to fetch fixtures");
  return res.json();
}

export async function searchTeams(query: string, leagueId?: number): Promise<Team[]> {
  const params = new URLSearchParams({ q: query });
  if (leagueId) params.append('league_id', leagueId.toString());

  const res = await fetch(`${API_BASE_URL}/search/teams?${params}`);
  if (!res.ok) throw new Error("Failed to search teams");
  return res.json();
}

export async function searchPlayers(
  query: string,
  teamId?: number,
  position?: string
): Promise<Player[]> {
  const params = new URLSearchParams({ q: query });
  if (teamId) params.append('team_id', teamId.toString());
  if (position) params.append('position', position);

  const res = await fetch(`${API_BASE_URL}/search/players?${params}`);
  if (!res.ok) throw new Error("Failed to search players");
  return res.json();
}

export async function searchAll(query: string): Promise<SearchResults> {
  const res = await fetch(`${API_BASE_URL}/search/all?q=${encodeURIComponent(query)}`);
  if (!res.ok) throw new Error("Failed to search");
  return res.json();
}

// Teams API
export interface TeamDetailed {
  id: number;
  name: string;
  logo_url: string;
  stadium: string;
  league: {
    id: number;
    name: string;
    country: string;
    logo_url: string;
  } | null;
  player_count?: number;
  squad?: {
    Goalkeeper: Player[];
    Defender: Player[];
    Midfielder: Player[];
    Attacker: Player[];
    Unknown: Player[];
  };
  total_players?: number;
}

export interface TeamFormSequenceMatch {
  match_id: number;
  start_time: string;
  opponent_name: string;
  opponent_logo?: string | null;
  is_home: boolean;
  result: "W" | "D" | "L";
  points: number;
  goals_for: number;
  goals_against: number;
  competition_name?: string | null;
  cumulative_points: number;
}

export interface TeamPointsTrendPoint {
  label: string;
  match_id: number;
  result: "W" | "D" | "L";
  points: number;
  cumulative_points: number;
}

export interface TeamHomeAwaySplit {
  played: number;
  wins: number;
  draws: number;
  losses: number;
  points: number;
  goals_for: number;
  goals_against: number;
  goal_difference: number;
  points_per_match: number;
}

export interface TeamFormWindowMetrics {
  window: number;
  matches_count: number;
  wins: number;
  draws: number;
  losses: number;
  points: number;
  points_per_match: number;
  goals_for: number;
  goals_against: number;
  goal_difference: number;
  form: Array<"W" | "D" | "L">;
  form_sequence: TeamFormSequenceMatch[];
  points_trend: TeamPointsTrendPoint[];
  result_distribution: {
    W: number;
    D: number;
    L: number;
  };
  home_away_split: {
    home: TeamHomeAwaySplit;
    away: TeamHomeAwaySplit;
  };
}

export interface TeamSquadDepthPositionMetrics {
  position_key: string;
  position_label: string;
  squad_count: number;
  starter_count: number;
  bench_count: number;
  starter_quality: number | null;
  bench_quality: number | null;
  depth_delta: number | null;
  availability_pct: number | null;
  quality_data_points: number;
  availability_data_points: number;
}

export interface TeamSquadDepthMetrics {
  position_groups: TeamSquadDepthPositionMetrics[];
  overall: {
    squad_size: number;
    starter_quality: number | null;
    bench_quality: number | null;
    availability_pct: number | null;
    quality_coverage_pct: number;
    availability_coverage_pct: number;
  };
  fallback_notes: string[];
}

export interface TeamStatisticsResponse {
  team_id: number;
  team_name: string;
  scope: string;
  league: {
    id: number | null;
    name: string | null;
    country: string | null;
  };
  matches_played: number;
  wins: number;
  draws: number;
  losses: number;
  goals_scored: number;
  goals_conceded: number;
  goal_difference: number;
  clean_sheets: number;
  win_rate: number;
  form: Array<"W" | "D" | "L">;
  average_goals_scored: number;
  average_goals_conceded: number;
  form_metrics: {
    last_5: TeamFormWindowMetrics;
    last_10: TeamFormWindowMetrics;
  };
  squad_depth: TeamSquadDepthMetrics;
  data_completeness: {
    has_last_5: boolean;
    has_last_10: boolean;
    squad_quality_coverage_pct: number;
    squad_availability_coverage_pct: number;
  };
  fallback_notes: string[];
}

export async function getTeams(leagueId?: number, search?: string): Promise<TeamDetailed[]> {
  const params = new URLSearchParams();
  if (leagueId) params.append('league_id', leagueId.toString());
  if (search) params.append('search', search);

  const res = await fetch(`${API_BASE_URL}/teams?${params}`);
  if (!res.ok) throw new Error("Failed to fetch teams");
  return res.json();
}

export async function getTeamDetails(teamId: number): Promise<TeamDetailed> {
  const res = await fetch(`${API_BASE_URL}/teams/${teamId}`);
  if (!res.ok) throw new Error("Failed to fetch team details");
  return res.json();
}

export async function getTeamStatistics(
  teamId: number,
  signal?: AbortSignal
): Promise<TeamStatisticsResponse> {
  const res = await fetch(`${API_BASE_URL}/teams/${teamId}/statistics`, { signal });

  if (!res.ok) {
    const errorPayload = await res.json().catch(() => null);
    throw new Error(errorPayload?.detail || "Failed to fetch team statistics");
  }

  return res.json();
}

// Players API
export interface PlayerDetailed {
  id: number;
  name: string;
  position: string;
  nationality: string;
  height: string;
  team: {
    id: number;
    name: string;
    logo_url: string;
    stadium?: string;
    league_id?: number;
  } | null;
  league?: {
    id: number;
    name: string;
    country: string;
    logo_url?: string;
  } | null;
  photo_url?: string;
  date_of_birth?: string;
  stats?: {
    goals?: number;
    assists?: number;
    rating?: number;
    minutes?: number;
    yellow_cards?: number;
    red_cards?: number;
    overall_rating?: number;
  };
}

export interface PlayerComparisonFormMatch {
  match_id: number;
  start_time: string;
  result: "W" | "D" | "L" | null;
  opponent_name: string;
  opponent_logo?: string | null;
  goals?: number;
  assists?: number;
  yellow_cards?: number;
  red_cards?: number;
}

export interface PlayerComparisonScoreComponent {
  key: string;
  label: string;
  weight: number;
  raw_value: number | { yellow_cards?: number | null; red_cards?: number | null } | null;
  normalized_value: number | null;
  expression: string;
  available: boolean;
  contribution: number;
}

export interface PlayerComparisonOverallScore {
  value: number;
  available_weight: number;
  formula: string;
  components: PlayerComparisonScoreComponent[];
}

export type ComparedPlayer = Omit<PlayerDetailed, 'stats'> & {
  age?: number | null;
  recent_form?: PlayerComparisonFormMatch[];
  overall_score?: PlayerComparisonOverallScore;
  data_sources?: {
    photo?: string;
    stats?: string;
    form?: string;
    discipline?: string;
  };
  fallback_notes?: string[];
  stats?: {
    goals?: number | null;
    assists?: number | null;
    rating?: number | null;
    minutes?: number | null;
    yellow_cards?: number | null;
    red_cards?: number | null;
    goal_involvements?: number | null;
    overall_rating?: number | null;
  };
};

export interface PlayerComparisonResponse {
  player1: ComparedPlayer;
  player2: ComparedPlayer;
  comparison?: {
    metric_deltas?: {
      goals?: number | null;
      assists?: number | null;
      rating?: number | null;
      minutes?: number | null;
      goal_involvements?: number | null;
      overall_rating?: number | null;
      overall_score?: number | null;
    };
    score_winner_id?: number | null;
    scope?: string;
    fallback_active?: boolean;
  };
  score_formula?: string;
  note?: string;
}

export async function getPlayerEnhanced(playerId: number): Promise<PlayerDetailed> {
  const res = await fetch(`${API_BASE_URL}/players/${playerId}/enhanced`);
  if (!res.ok) throw new Error("Failed to fetch enhanced player details");
  return res.json();
}

export async function getPlayers(
  teamId?: number,
  position?: string,
  search?: string,
  supportedOnly = false
): Promise<PlayerDetailed[]> {
  const params = new URLSearchParams();
  if (teamId) params.append('team_id', teamId.toString());
  if (position) params.append('position', position);
  if (search) params.append('search', search);
  if (supportedOnly) params.append('supported_only', 'true');

  const res = await fetch(`${API_BASE_URL}/players?${params}`);
  if (!res.ok) throw new Error("Failed to fetch players");
  return res.json();
}

export async function getPlayerDetails(playerId: number): Promise<PlayerDetailed> {
  const res = await fetch(`${API_BASE_URL}/players/${playerId}`);
  if (!res.ok) throw new Error("Failed to fetch player details");
  return res.json();
}

export async function getPlayerComparison(player1Id: number, player2Id: number): Promise<PlayerComparisonResponse> {
  const res = await fetch(`${API_BASE_URL}/players/${player1Id}/vs/${player2Id}`);

  if (!res.ok) {
    const errorPayload = await res.json().catch(() => null);
    throw new Error(errorPayload?.detail || "Failed to fetch player comparison");
  }

  return res.json();
}

// Player-based Fantasy API
export interface FantasyRulesResponse {
  squad_size: number;
  budget_cap: number;
  position_limits: Record<string, number>;
  starting_limits: Record<string, { min: number; max: number }>;
  free_transfers_per_matchday: number;
  extra_transfer_penalty: number;
  scoring_rules: Record<string, number>;
}

export interface FantasyPlayerPoolItem {
  player_id: number;
  player_name: string;
  position_key: string;
  team_id: number;
  team_name: string;
  team_logo?: string | null;
  league_id?: number | null;
  league_name?: string | null;
  price: number;
  goals_season: number;
  assists_season: number;
  rating_season?: number | null;
  minutes_played: number;
}

export interface FantasySquadPlayer {
  player_id: number;
  player_name: string;
  position_key: string;
  team_id: number;
  team_name: string;
  team_logo?: string | null;
  purchase_price: number;
  is_active: boolean;
}

export interface FantasySquadResponse {
  squad_id: number;
  user_id: number;
  budget_cap: number;
  budget_spent: number;
  budget_remaining: number;
  created_at: string;
  updated_at: string;
  players: FantasySquadPlayer[];
}

export type FantasyPickRole = "starter" | "bench";

export interface FantasyMatchdayPick {
  player_id: number;
  player_name?: string;
  position_key?: string;
  role: FantasyPickRole;
  bench_order?: number | null;
  is_captain: boolean;
  is_vice_captain: boolean;
}

export interface FantasyMatchdayPicksResponse {
  matchday_key: string;
  is_locked: boolean;
  picks: Array<{
    player_id: number;
    player_name: string;
    position_key: string;
    role: FantasyPickRole;
    bench_order?: number | null;
    is_captain: boolean;
    is_vice_captain: boolean;
  }>;
}

export interface FantasyTransferItem {
  out_player_id: number;
  in_player_id: number;
}

export interface FantasyTransferResponse {
  matchday_key: string;
  transfers_used: number;
  penalty_points: number;
  budget_spent: number;
  budget_remaining: number;
}

export interface FantasyPointsHistoryEntry {
  player_id?: number | null;
  player_name?: string | null;
  match_id?: number | null;
  points: number;
  reason: string;
}

export interface FantasyMatchdayPointsResponse {
  matchday_key: string;
  total_points: number;
  transfer_penalty: number;
  captain_player_id?: number | null;
  entries: FantasyPointsHistoryEntry[];
}

export interface FantasyLeaderboardEntry {
  rank: number;
  username: string;
  total_points: number;
  matchday_points: number;
  squad_size: number;
}

export interface FantasyLeaderboardResponse {
  matchday_key: string;
  entries: FantasyLeaderboardEntry[];
}

function authHeaders(token: string, includeJson = false): HeadersInit {
  return includeJson
    ? {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    }
    : {
      Authorization: `Bearer ${token}`,
    };
}

export async function getFantasyPlayerModeRules(): Promise<FantasyRulesResponse> {
  const res = await fetch(`${API_BASE_URL}/fantasy/player-mode/rules`);

  if (!res.ok) {
    const errorPayload = await res.json().catch(() => null);
    throw new Error(errorPayload?.detail || "Failed to fetch fantasy rules");
  }

  return res.json();
}

export async function getFantasyPlayerPool(
  params: {
    search?: string;
    position?: string;
    skip?: number;
    limit?: number;
  } = {}
): Promise<FantasyPlayerPoolItem[]> {
  const query = new URLSearchParams();
  if (params.search) query.append("search", params.search);
  if (params.position) query.append("position", params.position);
  if (typeof params.skip === "number") query.append("skip", String(params.skip));
  if (typeof params.limit === "number") query.append("limit", String(params.limit));

  const suffix = query.toString() ? `?${query.toString()}` : "";
  const res = await fetch(`${API_BASE_URL}/fantasy/player-mode/players${suffix}`);

  if (!res.ok) {
    const errorPayload = await res.json().catch(() => null);
    throw new Error(errorPayload?.detail || "Failed to fetch fantasy player pool");
  }

  return res.json();
}

export async function getFantasyPlayerSquad(token: string): Promise<FantasySquadResponse> {
  const res = await fetch(`${API_BASE_URL}/fantasy/player-mode/squad`, {
    headers: authHeaders(token),
  });

  if (!res.ok) {
    const errorPayload = await res.json().catch(() => null);
    throw new Error(errorPayload?.detail || "Failed to fetch fantasy squad");
  }

  return res.json();
}

export async function saveFantasyPlayerSquad(token: string, playerIds: number[]): Promise<FantasySquadResponse> {
  const res = await fetch(`${API_BASE_URL}/fantasy/player-mode/squad`, {
    method: "POST",
    headers: authHeaders(token, true),
    body: JSON.stringify({ player_ids: playerIds }),
  });

  if (!res.ok) {
    const errorPayload = await res.json().catch(() => null);
    throw new Error(errorPayload?.detail || "Failed to save fantasy squad");
  }

  return res.json();
}

export async function getFantasyMatchdayPicks(
  token: string,
  matchdayKey: string
): Promise<FantasyMatchdayPicksResponse> {
  const res = await fetch(`${API_BASE_URL}/fantasy/player-mode/matchday/${matchdayKey}/picks`, {
    headers: authHeaders(token),
  });

  if (!res.ok) {
    const errorPayload = await res.json().catch(() => null);
    throw new Error(errorPayload?.detail || "Failed to fetch matchday picks");
  }

  return res.json();
}

export async function saveFantasyMatchdayPicks(
  token: string,
  matchdayKey: string,
  picks: FantasyMatchdayPick[]
): Promise<FantasyMatchdayPicksResponse> {
  const res = await fetch(`${API_BASE_URL}/fantasy/player-mode/matchday/${matchdayKey}/picks`, {
    method: "PUT",
    headers: authHeaders(token, true),
    body: JSON.stringify({ picks }),
  });

  if (!res.ok) {
    const errorPayload = await res.json().catch(() => null);
    throw new Error(errorPayload?.detail || "Failed to save matchday picks");
  }

  return res.json();
}

export async function applyFantasyTransfers(
  token: string,
  matchdayKey: string,
  transfers: FantasyTransferItem[]
): Promise<FantasyTransferResponse> {
  const res = await fetch(`${API_BASE_URL}/fantasy/player-mode/matchday/${matchdayKey}/transfers`, {
    method: "POST",
    headers: authHeaders(token, true),
    body: JSON.stringify({ transfers }),
  });

  if (!res.ok) {
    const errorPayload = await res.json().catch(() => null);
    throw new Error(errorPayload?.detail || "Failed to apply fantasy transfers");
  }

  return res.json();
}

export async function getFantasyMatchdayPoints(
  token: string,
  matchdayKey: string,
  recompute = true
): Promise<FantasyMatchdayPointsResponse> {
  const query = new URLSearchParams({ recompute: recompute ? "true" : "false" });
  const res = await fetch(`${API_BASE_URL}/fantasy/player-mode/matchday/${matchdayKey}/points?${query.toString()}`, {
    headers: authHeaders(token),
  });

  if (!res.ok) {
    const errorPayload = await res.json().catch(() => null);
    throw new Error(errorPayload?.detail || "Failed to fetch matchday fantasy points");
  }

  return res.json();
}

export async function getFantasyPlayerModeLeaderboard(
  matchdayKey?: string,
  refreshMatchday = true
): Promise<FantasyLeaderboardResponse> {
  const query = new URLSearchParams();
  if (matchdayKey) query.append("matchday_key", matchdayKey);
  query.append("refresh_matchday", refreshMatchday ? "true" : "false");

  const suffix = query.toString() ? `?${query.toString()}` : "";
  const res = await fetch(`${API_BASE_URL}/fantasy/player-mode/leaderboard${suffix}`);

  if (!res.ok) {
    const errorPayload = await res.json().catch(() => null);
    throw new Error(errorPayload?.detail || "Failed to fetch fantasy leaderboard");
  }

  return res.json();
}

// ----------------------------------------------------------------------------
// AI News Agent
// ----------------------------------------------------------------------------

export type NewsType = "post_match" | "pre_derby";

export interface NewsArticleSummary {
  id: number;
  title: string;
  summary: string;
  news_type: NewsType;
  related_fixture_id: number | null;
  created_at: string;
}

export interface NewsTeamRef {
  id: number;
  name: string;
  logo_url?: string | null;
}

export interface NewsLeagueRef {
  id: number;
  name: string;
  country?: string | null;
}

export interface NewsArticle extends NewsArticleSummary {
  content: string;
  league?: NewsLeagueRef | null;
  home_team?: NewsTeamRef | null;
  away_team?: NewsTeamRef | null;
}

export async function getNewsTicker(limit = 15): Promise<NewsArticleSummary[]> {
  const res = await fetch(`${API_BASE_URL}/editorial/feed?limit=${limit}&_t=${Date.now()}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Failed to fetch news feed");
  return res.json();
}

export async function getNews(opts?: {
  limit?: number;
  newsType?: NewsType;
  leagueId?: number;
}): Promise<NewsArticle[]> {
  const params = new URLSearchParams();
  if (opts?.limit) params.set("limit", String(opts.limit));
  if (opts?.newsType) params.set("news_type", opts.newsType);
  if (opts?.leagueId) params.set("league_id", String(opts.leagueId));
  const suffix = params.toString() ? `?${params.toString()}&_t=${Date.now()}` : `?_t=${Date.now()}`;

  const res = await fetch(`${API_BASE_URL}/editorial${suffix}`, { cache: "no-store", headers: {
    "Cache-Control": "no-cache",
    "Pragma": "no-cache"
  } });
  if (!res.ok) throw new Error("Failed to fetch news");
  return res.json();
}
