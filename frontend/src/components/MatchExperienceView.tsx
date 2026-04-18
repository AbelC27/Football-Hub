import Link from "next/link";
import {
  CalendarClock,
  Clock3,
  Info,
  MapPin,
  ShieldAlert,
  Swords,
  Users,
  Trophy,
  ArrowRightLeft,
} from "lucide-react";
import {
  MatchExperience,
  NextEventPredictionResponse,
  NextEventTaskPrediction,
} from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

interface MatchExperienceViewProps {
  data: MatchExperience;
  nextEventPrediction?: NextEventPredictionResponse | null;
  nextEventPredictionLoading?: boolean;
  nextEventPredictionError?: string | null;
}

function formatKickoff(value: string) {
  return new Date(value).toLocaleString(undefined, {
    weekday: "short",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function getStatusTone(status: string): "default" | "success" | "warning" | "danger" {
  const normalized = status.toUpperCase();

  if (["LIVE", "HT", "ET", "P"].includes(normalized)) return "danger";
  if (["FT", "AET", "PEN"].includes(normalized)) return "success";
  if (["NS", "TBD"].includes(normalized)) return "default";

  return "warning";
}

function TeamCrest({ logo, name }: { logo?: string | null; name: string }) {
  if (logo) {
    return <img src={logo} alt={name} className="h-16 w-16 rounded-full object-contain bg-white p-2 shadow-sm md:h-20 md:w-20" />;
  }

  return (
    <div className="flex h-16 w-16 items-center justify-center rounded-full bg-neutral-200 text-lg font-black text-neutral-500 dark:bg-neutral-800 dark:text-neutral-300 md:h-20 md:w-20">
      {name.slice(0, 2).toUpperCase()}
    </div>
  );
}

function ResultBadge({ result }: { result?: "W" | "D" | "L" | null }) {
  if (!result) return <Badge tone="default">-</Badge>;

  if (result === "W") return <Badge tone="success">W</Badge>;
  if (result === "D") return <Badge tone="warning">D</Badge>;
  return <Badge tone="danger">L</Badge>;
}

function EventBadge({ type }: { type: string }) {
  if (type === "goal") return <Badge tone="success">Goal</Badge>;
  if (type === "assist") return <Badge tone="default">Assist</Badge>;
  if (type === "card") return <Badge tone="danger">Card</Badge>;
  return <Badge tone="default">Event</Badge>;
}

function confidenceTone(label: string): "success" | "warning" | "danger" {
  const normalized = label.toLowerCase();
  if (normalized === "high") return "success";
  if (normalized === "medium") return "warning";
  return "danger";
}

function sourceLabel(source: string) {
  if (source === "trained_model") return "trained model";
  if (source === "heuristic_fallback") return "heuristic fallback";
  return source;
}

function NextEventTaskCard({
  title,
  payload,
}: {
  title: string;
  payload: NextEventTaskPrediction;
}) {
  return (
    <div className="space-y-3 rounded-xl border border-neutral-200 bg-neutral-50 p-4 dark:border-neutral-800 dark:bg-neutral-900/70">
      <div className="flex flex-wrap items-center gap-2">
        <h4 className="text-sm font-semibold uppercase tracking-wide text-neutral-700 dark:text-neutral-200">{title}</h4>
        <Badge tone={confidenceTone(payload.confidence_label)}>{payload.confidence_label.toUpperCase()}</Badge>
        <Badge>{(payload.confidence_score * 100).toFixed(1)}%</Badge>
        <Badge>{sourceLabel(payload.source)}</Badge>
      </div>

      <p className="text-xs text-neutral-500 dark:text-neutral-400">
        Minute {payload.minute_context} · Top-3 mass from full distribution: {(payload.top3_probability_mass_from_full_distribution * 100).toFixed(1)}%
      </p>

      {payload.top_candidates.length === 0 ? (
        <div className="rounded-lg border border-dashed border-neutral-300 p-3 text-sm text-neutral-500 dark:border-neutral-700 dark:text-neutral-400">
          No candidate ranking available.
        </div>
      ) : (
        <div className="space-y-2">
          {payload.top_candidates.map((candidate) => (
            <Link
              key={`${payload.task}-${candidate.player_id}-${candidate.rank}`}
              href={`/player/${candidate.player_id}`}
              className="flex items-center justify-between rounded-lg border border-neutral-200 bg-white px-3 py-2 transition hover:border-neutral-300 hover:bg-neutral-100 dark:border-neutral-800 dark:bg-neutral-950 dark:hover:border-neutral-700 dark:hover:bg-neutral-900"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-neutral-900 dark:text-neutral-100">
                  #{candidate.rank} {candidate.player_name}
                </p>
                <p className="truncate text-xs text-neutral-500 dark:text-neutral-400">{candidate.team_name}</p>
              </div>
              <p className="text-sm font-bold text-sky-600 dark:text-sky-400">{(candidate.probability * 100).toFixed(1)}%</p>
            </Link>
          ))}
        </div>
      )}

      {payload.data_limitations.length > 0 ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-900/50 dark:bg-amber-900/20 dark:text-amber-200">
          <p className="mb-1 font-semibold">Data limitations</p>
          <ul className="list-disc space-y-1 pl-4">
            {payload.data_limitations.map((note, index) => (
              <li key={`${payload.task}-limit-${index}`}>{note}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function PlayerRow({ id, name, position, photo_url }: { id: number; name: string; position?: string | null; photo_url?: string | null }) {
  return (
    <Link
      href={`/player/${id}`}
      className="flex items-center gap-3 rounded-lg border border-neutral-200 bg-white px-3 py-2 transition hover:border-neutral-300 hover:bg-neutral-50 dark:border-neutral-800 dark:bg-neutral-900 dark:hover:border-neutral-700 dark:hover:bg-neutral-800"
    >
      {photo_url ? (
        <img src={photo_url} alt={name} className="h-8 w-8 rounded-full object-cover" />
      ) : (
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-neutral-200 text-[10px] font-bold text-neutral-600 dark:bg-neutral-700 dark:text-neutral-200">
          {name.slice(0, 2).toUpperCase()}
        </div>
      )}
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-neutral-900 dark:text-neutral-100">{name}</p>
        <p className="truncate text-xs text-neutral-500 dark:text-neutral-400">{position || "Unknown"}</p>
      </div>
    </Link>
  );
}

function TeamFormColumn({
  teamName,
  items,
}: {
  teamName: string;
  items: MatchExperienceViewProps["data"]["form"]["home_last_five"];
}) {
  return (
    <div className="space-y-3">
      <h4 className="text-sm font-semibold uppercase tracking-wide text-neutral-600 dark:text-neutral-300">{teamName}</h4>
      {items.length === 0 ? (
        <div className="rounded-lg border border-dashed border-neutral-300 p-4 text-sm text-neutral-500 dark:border-neutral-700 dark:text-neutral-400">
          No recent matches found.
        </div>
      ) : (
        <div className="space-y-2">
          {items.map((item) => (
            <div
              key={item.match_id}
              className="grid grid-cols-[auto_1fr_auto] items-center gap-3 rounded-lg border border-neutral-200 bg-white px-3 py-2 dark:border-neutral-800 dark:bg-neutral-900"
            >
              <ResultBadge result={item.result} />
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-neutral-900 dark:text-neutral-100">vs {item.opponent_name}</p>
                <p className="truncate text-xs text-neutral-500 dark:text-neutral-400">
                  {item.team_score ?? "-"}:{item.opponent_score ?? "-"} · {new Date(item.start_time).toLocaleDateString()}
                </p>
              </div>
              <Clock3 className="h-4 w-4 text-neutral-400" />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function MatchExperienceView({
  data,
  nextEventPrediction = null,
  nextEventPredictionLoading = false,
  nextEventPredictionError = null,
}: MatchExperienceViewProps) {
  const home = data.teams.home;
  const away = data.teams.away;
  const score = data.header.score;
  const statusTone = getStatusTone(data.header.status);

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top,_#eef8ff_0%,_#f6f7fb_42%,_#f1f1f5_100%)] px-4 py-6 dark:bg-[radial-gradient(circle_at_top,_#1a2433_0%,_#0f1115_42%,_#0b0c0f_100%)] md:px-8 md:py-10">
      <div className="mx-auto max-w-6xl space-y-6">
        <Link href="/" className="inline-flex items-center gap-2 text-sm font-medium text-neutral-700 transition hover:text-neutral-900 dark:text-neutral-300 dark:hover:text-neutral-100">
          <Swords className="h-4 w-4" />
          Back to Matches
        </Link>

        <Card className="overflow-hidden border-0 shadow-xl shadow-sky-500/10">
          <div className="bg-gradient-to-r from-sky-600 via-cyan-500 to-teal-500 p-[1px]">
            <div className="space-y-6 bg-white p-6 dark:bg-neutral-950 md:p-8">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={statusTone}>{data.header.status}</Badge>
                {data.header.competition?.name ? <Badge>{data.header.competition.name}</Badge> : null}
                {data.header.competition?.country ? <Badge>{data.header.competition.country}</Badge> : null}
              </div>

              <div className="grid gap-6 lg:grid-cols-[1fr_auto_1fr] lg:items-center">
                <div className="flex items-center gap-4">
                  <TeamCrest logo={home.logo_url} name={home.name} />
                  <div>
                    <h1 className="text-lg font-bold text-neutral-900 dark:text-neutral-50 md:text-2xl">{home.name}</h1>
                    <p className="text-xs text-neutral-500 dark:text-neutral-400">Home</p>
                  </div>
                </div>

                <div className="text-center">
                  <p className="text-4xl font-black tracking-tight text-neutral-900 dark:text-neutral-50 md:text-6xl">
                    {score.home ?? "-"} : {score.away ?? "-"}
                  </p>
                  <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">Live Scoreboard</p>
                </div>

                <div className="flex items-center justify-start gap-4 lg:justify-end">
                  <div className="text-right">
                    <h2 className="text-lg font-bold text-neutral-900 dark:text-neutral-50 md:text-2xl">{away.name}</h2>
                    <p className="text-xs text-neutral-500 dark:text-neutral-400">Away</p>
                  </div>
                  <TeamCrest logo={away.logo_url} name={away.name} />
                </div>
              </div>

              <div className="grid gap-3 rounded-xl border border-neutral-200 bg-neutral-50 p-4 text-sm text-neutral-600 dark:border-neutral-800 dark:bg-neutral-900/60 dark:text-neutral-300 md:grid-cols-2">
                <div className="flex items-center gap-2">
                  <CalendarClock className="h-4 w-4" />
                  <span>{formatKickoff(data.header.start_time)}</span>
                </div>
                <div className="flex items-center gap-2 md:justify-end">
                  <MapPin className="h-4 w-4" />
                  <span>{home.stadium || away.stadium || "Stadium information unavailable"}</span>
                </div>
              </div>
            </div>
          </div>
        </Card>

        {data.partial_failures.length > 0 ? (
          <Alert variant="destructive">
            <AlertTitle className="flex items-center gap-2">
              <ShieldAlert className="h-4 w-4" />
              Partial Data Available
            </AlertTitle>
            <AlertDescription>
              {data.partial_failures.map((failure) => failure.message).join(" ")}
            </AlertDescription>
          </Alert>
        ) : null}

        <Tabs defaultValue="overview" className="w-full">
          <TabsList className="grid h-auto w-full grid-cols-2 gap-2 p-2 md:grid-cols-4">
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="events">Events</TabsTrigger>
            <TabsTrigger value="lineups">Lineups</TabsTrigger>
            <TabsTrigger value="squads">Squads</TabsTrigger>
          </TabsList>

          <TabsContent value="overview">
            <div className="grid gap-4 lg:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-xl">
                    <Trophy className="h-5 w-5" />
                    AI Prediction
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {data.prediction ? (
                    <div className="space-y-3">
                      <div className="grid gap-2 text-sm sm:grid-cols-3">
                        <div className="rounded-lg border border-neutral-200 bg-neutral-50 p-3 text-center dark:border-neutral-800 dark:bg-neutral-900">
                          <p className="text-xs text-neutral-500">Home</p>
                          <p className="text-lg font-bold text-emerald-600">{data.prediction.home_win_prob.toFixed(1)}%</p>
                        </div>
                        <div className="rounded-lg border border-neutral-200 bg-neutral-50 p-3 text-center dark:border-neutral-800 dark:bg-neutral-900">
                          <p className="text-xs text-neutral-500">Draw</p>
                          <p className="text-lg font-bold text-amber-600">{data.prediction.draw_prob.toFixed(1)}%</p>
                        </div>
                        <div className="rounded-lg border border-neutral-200 bg-neutral-50 p-3 text-center dark:border-neutral-800 dark:bg-neutral-900">
                          <p className="text-xs text-neutral-500">Away</p>
                          <p className="text-lg font-bold text-sky-600">{data.prediction.away_win_prob.toFixed(1)}%</p>
                        </div>
                      </div>
                      <p className="text-sm text-neutral-500 dark:text-neutral-400">
                        Confidence score: <span className="font-semibold text-neutral-700 dark:text-neutral-200">{data.prediction.confidence_score.toFixed(2)}</span>
                      </p>
                    </div>
                  ) : (
                    <div className="rounded-lg border border-dashed border-neutral-300 p-5 text-sm text-neutral-500 dark:border-neutral-700 dark:text-neutral-400">
                      AI prediction is not available yet for this match.
                    </div>
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-xl">
                    <ArrowRightLeft className="h-5 w-5" />
                    Last 5 Matches
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid gap-4 md:grid-cols-2">
                    <TeamFormColumn teamName={home.name} items={data.form.home_last_five} />
                    <TeamFormColumn teamName={away.name} items={data.form.away_last_five} />
                  </div>
                </CardContent>
              </Card>
            </div>

            <Card className="mt-4">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-xl">
                  <Info className="h-5 w-5" />
                  Next Goal Scorer and Next Assist Provider
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {nextEventPredictionLoading && !nextEventPrediction ? (
                  <div className="rounded-lg border border-dashed border-neutral-300 p-5 text-sm text-neutral-500 dark:border-neutral-700 dark:text-neutral-400">
                    Loading next-event predictions...
                  </div>
                ) : null}

                {nextEventPredictionError && !nextEventPrediction ? (
                  <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/50 dark:bg-red-900/20 dark:text-red-200">
                    {nextEventPredictionError}
                  </div>
                ) : null}

                {nextEventPrediction ? (
                  <>
                    <div className="flex flex-wrap items-center gap-2 text-xs">
                      <Badge>{nextEventPrediction.scope}</Badge>
                      <Badge>{nextEventPrediction.model_version}</Badge>
                      <Badge>{new Date(nextEventPrediction.generated_at_utc).toLocaleTimeString()}</Badge>
                    </div>

                    <div className="grid gap-4 lg:grid-cols-2">
                      <NextEventTaskCard title="Next Goal" payload={nextEventPrediction.next_goal} />
                      <NextEventTaskCard title="Next Assist" payload={nextEventPrediction.next_assist} />
                    </div>

                    {nextEventPrediction.global_limitations.length > 0 ? (
                      <div className="rounded-lg border border-neutral-200 bg-neutral-50 px-4 py-3 text-xs text-neutral-600 dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-300">
                        <p className="mb-1 font-semibold">Model limitations</p>
                        <ul className="list-disc space-y-1 pl-4">
                          {nextEventPrediction.global_limitations.map((note, index) => (
                            <li key={`global-limit-${index}`}>{note}</li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                  </>
                ) : null}

                {!nextEventPredictionLoading && !nextEventPredictionError && !nextEventPrediction ? (
                  <div className="rounded-lg border border-dashed border-neutral-300 p-5 text-sm text-neutral-500 dark:border-neutral-700 dark:text-neutral-400">
                    Next-event predictions are not available for this match yet.
                  </div>
                ) : null}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="events">
            <Card>
              <CardHeader>
                <CardTitle className="text-xl">Goals, Assists and Cards</CardTitle>
              </CardHeader>
              <CardContent>
                {data.events.length === 0 ? (
                  <div className="rounded-lg border border-dashed border-neutral-300 p-6 text-center text-sm text-neutral-500 dark:border-neutral-700 dark:text-neutral-400">
                    No events recorded yet.
                  </div>
                ) : (
                  <div className="space-y-2">
                    {data.events.map((event) => (
                      <div
                        key={event.id}
                        className="grid grid-cols-[auto_1fr_auto] items-center gap-3 rounded-lg border border-neutral-200 bg-white px-3 py-2 dark:border-neutral-800 dark:bg-neutral-900"
                      >
                        <Badge>{event.minute}'</Badge>
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium text-neutral-900 dark:text-neutral-100">{event.player_name || "Unknown Player"}</p>
                          <p className="truncate text-xs text-neutral-500 dark:text-neutral-400">
                            {event.assist_player ? `Assist: ${event.assist_player} · ` : ""}
                            {event.card_type || event.detail || "No extra details"}
                          </p>
                        </div>
                        <EventBadge type={event.event_type} />
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="lineups">
            <div className="grid gap-4 lg:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle className="text-xl">Starting XI</CardTitle>
                </CardHeader>
                <CardContent className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <h4 className="text-sm font-semibold uppercase tracking-wide text-neutral-600 dark:text-neutral-300">{home.name}</h4>
                    {data.lineups.home_starting_xi.length === 0 ? (
                      <p className="text-sm text-neutral-500 dark:text-neutral-400">No lineup available.</p>
                    ) : (
                      data.lineups.home_starting_xi.map((player) => (
                        <PlayerRow key={player.id} id={player.id} name={player.name} position={player.position} photo_url={player.photo_url} />
                      ))
                    )}
                  </div>

                  <div className="space-y-2">
                    <h4 className="text-sm font-semibold uppercase tracking-wide text-neutral-600 dark:text-neutral-300">{away.name}</h4>
                    {data.lineups.away_starting_xi.length === 0 ? (
                      <p className="text-sm text-neutral-500 dark:text-neutral-400">No lineup available.</p>
                    ) : (
                      data.lineups.away_starting_xi.map((player) => (
                        <PlayerRow key={player.id} id={player.id} name={player.name} position={player.position} photo_url={player.photo_url} />
                      ))
                    )}
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-xl">Substitutions</CardTitle>
                </CardHeader>
                <CardContent>
                  {data.lineups.substitutions.length === 0 ? (
                    <div className="rounded-lg border border-dashed border-neutral-300 p-6 text-center text-sm text-neutral-500 dark:border-neutral-700 dark:text-neutral-400">
                      No substitutions recorded.
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {data.lineups.substitutions.map((sub) => (
                        <div
                          key={sub.id}
                          className="grid grid-cols-[auto_1fr] items-center gap-3 rounded-lg border border-neutral-200 bg-white px-3 py-2 dark:border-neutral-800 dark:bg-neutral-900"
                        >
                          <Badge tone="warning">{sub.minute}'</Badge>
                          <div>
                            <p className="text-sm font-medium text-neutral-900 dark:text-neutral-100">{sub.player_name || "Unknown Player"}</p>
                            <p className="text-xs text-neutral-500 dark:text-neutral-400">{sub.detail || "Substitution event"}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                  <p className="mt-4 text-xs text-neutral-500 dark:text-neutral-400">Lineup source: {data.lineups.source}</p>
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          <TabsContent value="squads">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-xl">
                  <Users className="h-5 w-5" />
                  Full Squads
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <h4 className="text-sm font-semibold uppercase tracking-wide text-neutral-600 dark:text-neutral-300">{home.name}</h4>
                    {data.squads.home.length === 0 ? (
                      <p className="text-sm text-neutral-500 dark:text-neutral-400">No players found for home team.</p>
                    ) : (
                      <div className="max-h-[420px] space-y-2 overflow-y-auto pr-1">
                        {data.squads.home.map((player) => (
                          <PlayerRow key={player.id} id={player.id} name={player.name} position={player.position} photo_url={player.photo_url} />
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="space-y-2">
                    <h4 className="text-sm font-semibold uppercase tracking-wide text-neutral-600 dark:text-neutral-300">{away.name}</h4>
                    {data.squads.away.length === 0 ? (
                      <p className="text-sm text-neutral-500 dark:text-neutral-400">No players found for away team.</p>
                    ) : (
                      <div className="max-h-[420px] space-y-2 overflow-y-auto pr-1">
                        {data.squads.away.map((player) => (
                          <PlayerRow key={player.id} id={player.id} name={player.name} position={player.position} photo_url={player.photo_url} />
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </main>
  );
}
