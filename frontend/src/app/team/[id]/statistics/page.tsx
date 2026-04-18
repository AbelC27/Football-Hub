'use client';

import { useMemo, useState } from 'react';
import { useParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { getTeamStatistics } from '@/lib/api';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { TeamFormChart, TeamFormChartType } from '@/components/team/TeamFormChart';
import { SquadDepthChartType, TeamSquadDepthChart } from '@/components/team/TeamSquadDepthChart';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ArrowLeft, RefreshCw, ShieldAlert } from 'lucide-react';
import Link from 'next/link';
import { toast } from 'sonner';

type FormWindowKey = 'last_5' | 'last_10';

function StatsTile({
    label,
    value,
    helper,
}: {
    label: string;
    value: string | number;
    helper?: string;
}) {
    return (
        <div className="rounded-xl border border-neutral-200 bg-white p-4 shadow-sm dark:border-neutral-800 dark:bg-neutral-900">
            <div className="text-xs font-semibold uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
                {label}
            </div>
            <div className="mt-2 text-2xl font-bold text-neutral-900 dark:text-neutral-50">{value}</div>
            {helper ? <div className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">{helper}</div> : null}
        </div>
    );
}

function toSignedValue(value: number) {
    if (value > 0) return `+${value}`;
    return `${value}`;
}

export default function TeamStatisticsPage() {
    const params = useParams();
    const [windowKey, setWindowKey] = useState<FormWindowKey>('last_5');
    const [formChartType, setFormChartType] = useState<TeamFormChartType>('trend');
    const [squadChartType, setSquadChartType] = useState<SquadDepthChartType>('quality');

    const teamId = useMemo(() => {
        const rawId = Array.isArray(params.id) ? params.id[0] : params.id;
        const parsed = Number(rawId);
        return Number.isFinite(parsed) ? parsed : null;
    }, [params.id]);

    const statsQuery = useQuery({
        queryKey: ['team-statistics', teamId],
        queryFn: ({ signal }) => getTeamStatistics(teamId as number, signal),
        enabled: typeof teamId === 'number' && teamId > 0,
        staleTime: 60_000,
        gcTime: 300_000,
        refetchInterval: 120_000,
        placeholderData: (previousData) => previousData,
    });

    const stats = statsQuery.data;
    const selectedWindow = stats?.form_metrics?.[windowKey];

    const handleRefresh = async () => {
        const result = await statsQuery.refetch();
        if (result.error) {
            toast.error(result.error.message || 'Could not refresh team analytics');
            return;
        }

        toast.success('Team analytics refreshed');
    };

    if (!teamId || teamId <= 0) {
        return (
            <main className="min-h-screen bg-[radial-gradient(circle_at_top,_#f4f9ff_0%,_#f6f8fc_40%,_#f1f2f5_100%)] p-4 md:p-8 dark:bg-[radial-gradient(circle_at_top,_#1b2432_0%,_#0f1117_40%,_#0b0c10_100%)]">
                <div className="mx-auto max-w-6xl">
                    <Alert variant="destructive">
                        <AlertTitle>Invalid team id</AlertTitle>
                        <AlertDescription>Open the statistics page from a valid team link.</AlertDescription>
                    </Alert>
                </div>
            </main>
        );
    }

    if (statsQuery.isPending) {
        return (
            <main className="min-h-screen bg-[radial-gradient(circle_at_top,_#f4f9ff_0%,_#f6f8fc_40%,_#f1f2f5_100%)] p-4 md:p-8 dark:bg-[radial-gradient(circle_at_top,_#1b2432_0%,_#0f1117_40%,_#0b0c10_100%)]">
                <div className="max-w-6xl mx-auto">
                    <LoadingSpinner />
                </div>
            </main>
        );
    }

    if (statsQuery.isError) {
        return (
            <main className="min-h-screen bg-[radial-gradient(circle_at_top,_#f4f9ff_0%,_#f6f8fc_40%,_#f1f2f5_100%)] p-4 md:p-8 dark:bg-[radial-gradient(circle_at_top,_#1b2432_0%,_#0f1117_40%,_#0b0c10_100%)]">
                <div className="mx-auto max-w-6xl space-y-4">
                    <Alert variant="destructive">
                        <AlertTitle>Could not load team analysis</AlertTitle>
                        <AlertDescription>
                            {statsQuery.error instanceof Error
                                ? statsQuery.error.message
                                : 'The server returned an unexpected response.'}
                        </AlertDescription>
                    </Alert>
                    <button
                        onClick={handleRefresh}
                        className="inline-flex items-center gap-2 rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-neutral-700 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-300"
                    >
                        <RefreshCw className="h-4 w-4" />
                        Retry
                    </button>
                </div>
            </main>
        );
    }

    if (!stats || !selectedWindow) {
        return (
            <main className="min-h-screen bg-[radial-gradient(circle_at_top,_#f4f9ff_0%,_#f6f8fc_40%,_#f1f2f5_100%)] p-4 md:p-8 dark:bg-[radial-gradient(circle_at_top,_#1b2432_0%,_#0f1117_40%,_#0b0c10_100%)]">
                <div className="mx-auto max-w-6xl">
                    <Alert>
                        <AlertTitle>Team analytics unavailable</AlertTitle>
                        <AlertDescription>The API returned an incomplete payload for this team.</AlertDescription>
                    </Alert>
                </div>
            </main>
        );
    }

    return (
        <main className="min-h-screen bg-[radial-gradient(circle_at_top,_#f4f9ff_0%,_#f6f8fc_40%,_#f1f2f5_100%)] p-4 md:p-8 dark:bg-[radial-gradient(circle_at_top,_#1b2432_0%,_#0f1117_40%,_#0b0c10_100%)]">
            <div className="max-w-6xl mx-auto">
                <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
                    <Link href={`/team/${teamId}`}>
                        <button className="flex items-center gap-2 rounded-lg bg-white px-4 py-2 text-sm font-medium text-neutral-700 shadow-sm transition hover:shadow-md dark:bg-neutral-900 dark:text-neutral-200">
                            <ArrowLeft className="w-4 h-4" />
                            Back to Team
                        </button>
                    </Link>

                    <button
                        onClick={handleRefresh}
                        disabled={statsQuery.isFetching}
                        className="inline-flex items-center gap-2 rounded-lg bg-neutral-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-neutral-700 disabled:cursor-not-allowed disabled:opacity-70 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-300"
                    >
                        <RefreshCw className={`h-4 w-4 ${statsQuery.isFetching ? 'animate-spin' : ''}`} />
                        Refresh
                    </button>
                </div>

                <Card className="mb-6 border-cyan-100/70 bg-white/95 dark:border-cyan-900/40 dark:bg-neutral-900/85">
                    <CardHeader className="pb-3">
                        <CardTitle className="text-3xl font-black tracking-tight text-neutral-900 dark:text-neutral-50 md:text-4xl">
                            {stats.team_name} Team Analysis
                        </CardTitle>
                        <p className="text-sm text-neutral-600 dark:text-neutral-300">{stats.scope}</p>
                    </CardHeader>
                    <CardContent className="pt-0">
                        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
                            <StatsTile label="Matches" value={stats.matches_played} />
                            <StatsTile label="Win Rate" value={`${stats.win_rate}%`} helper={`${stats.wins}W/${stats.draws}D/${stats.losses}L`} />
                            <StatsTile label="Goals For" value={stats.goals_scored} helper={`${stats.average_goals_scored} per match`} />
                            <StatsTile label="Goals Against" value={stats.goals_conceded} helper={`${stats.average_goals_conceded} per match`} />
                            <StatsTile label="Goal Diff" value={toSignedValue(stats.goal_difference)} />
                            <StatsTile label="Clean Sheets" value={stats.clean_sheets} />
                        </div>
                    </CardContent>
                </Card>

                {(stats.fallback_notes.length > 0 || !stats.data_completeness.has_last_10) && (
                    <Alert className="mb-6 border-amber-200 bg-amber-50/70 text-amber-900 dark:border-amber-800 dark:bg-amber-950/35 dark:text-amber-100">
                        <ShieldAlert className="h-4 w-4" />
                        <AlertTitle>Partial analytics</AlertTitle>
                        <AlertDescription>
                            {stats.fallback_notes.length > 0
                                ? stats.fallback_notes.join(' ')
                                : 'Some windows are currently partial and may expand as more matches are recorded.'}
                        </AlertDescription>
                    </Alert>
                )}

                <Card className="mb-6">
                    <CardHeader className="pb-3">
                        <CardTitle className="text-xl">Form Graphs</CardTitle>
                        <p className="text-sm text-neutral-500 dark:text-neutral-400">
                            Switch between last 5 and last 10 to inspect points trend, result mix, and home vs away split.
                        </p>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <div className="flex flex-wrap gap-3">
                            <Tabs value={windowKey} onValueChange={(value) => setWindowKey(value as FormWindowKey)}>
                                <TabsList>
                                    <TabsTrigger value="last_5">Last 5</TabsTrigger>
                                    <TabsTrigger value="last_10">Last 10</TabsTrigger>
                                </TabsList>
                            </Tabs>

                            <Tabs value={formChartType} onValueChange={(value) => setFormChartType(value as TeamFormChartType)}>
                                <TabsList>
                                    <TabsTrigger value="trend">Points Trend</TabsTrigger>
                                    <TabsTrigger value="results">W/D/L Mix</TabsTrigger>
                                    <TabsTrigger value="split">Home vs Away</TabsTrigger>
                                </TabsList>
                            </Tabs>
                        </div>

                        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                            <StatsTile label="Window Matches" value={selectedWindow.matches_count} helper={`Target: ${selectedWindow.window}`} />
                            <StatsTile label="Window Points" value={selectedWindow.points} helper={`${selectedWindow.points_per_match} ppm`} />
                            <StatsTile label="Window Goal Diff" value={toSignedValue(selectedWindow.goal_difference)} />
                            <StatsTile
                                label="Home vs Away PPM"
                                value={`${selectedWindow.home_away_split.home.points_per_match} / ${selectedWindow.home_away_split.away.points_per_match}`}
                                helper="Home first"
                            />
                        </div>

                        <TeamFormChart metrics={selectedWindow} chartType={formChartType} />
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader className="pb-3">
                        <CardTitle className="text-xl">Squad Depth by Position</CardTitle>
                        <p className="text-sm text-neutral-500 dark:text-neutral-400">
                            Starter and bench quality are position-weighted estimates from rating, output, and minutes. Availability uses minutes when present.
                        </p>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <div className="flex flex-wrap gap-3">
                            <Tabs value={squadChartType} onValueChange={(value) => setSquadChartType(value as SquadDepthChartType)}>
                                <TabsList>
                                    <TabsTrigger value="quality">Starter vs Bench Quality</TabsTrigger>
                                    <TabsTrigger value="availability">Availability</TabsTrigger>
                                </TabsList>
                            </Tabs>
                        </div>

                        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                            <StatsTile label="Squad Size" value={stats.squad_depth.overall.squad_size} />
                            <StatsTile
                                label="Starter Quality"
                                value={stats.squad_depth.overall.starter_quality ?? 'N/A'}
                                helper="0-100 scale"
                            />
                            <StatsTile
                                label="Bench Quality"
                                value={stats.squad_depth.overall.bench_quality ?? 'N/A'}
                                helper="0-100 scale"
                            />
                            <StatsTile
                                label="Availability"
                                value={stats.squad_depth.overall.availability_pct != null ? `${stats.squad_depth.overall.availability_pct}%` : 'N/A'}
                                helper={`${stats.squad_depth.overall.availability_coverage_pct}% coverage`}
                            />
                        </div>

                        <TeamSquadDepthChart positions={stats.squad_depth.position_groups} chartType={squadChartType} />
                    </CardContent>
                </Card>

                <p className="mt-6 text-xs text-neutral-500 dark:text-neutral-400">
                    Scope is restricted to Top 5 domestic leagues and UEFA Champions League teams. Data refreshes automatically and on focus.
                </p>
            </div>
        </main>
    );
}
