'use client';

import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'next/navigation';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import {
    ComparedPlayer,
    PlayerComparisonResponse,
    PlayerComparisonScoreComponent,
    getPlayerComparison,
} from '@/lib/api';
import { PlayerComparisonRadar } from '@/components/compare/PlayerComparisonRadar';
import { AlertTriangle, ArrowLeft, Info } from 'lucide-react';
import Link from 'next/link';

const FORM_BADGE_CLASSES: Record<string, string> = {
    W: 'bg-emerald-500/20 border-emerald-400/40 text-emerald-200',
    D: 'bg-amber-500/20 border-amber-400/40 text-amber-200',
    L: 'bg-rose-500/20 border-rose-400/40 text-rose-200',
};

const SOURCE_LABELS: Record<string, string> = {
    photo: 'Photo',
    stats: 'Stats',
    form: 'Form',
    discipline: 'Cards',
};

function parseParamToNumber(param: string | string[] | undefined): number {
    if (Array.isArray(param)) {
        return Number(param[0]);
    }

    return Number(param);
}

function formatNumber(value: number | null | undefined, digits = 0): string {
    if (value == null || Number.isNaN(value)) return 'N/A';
    return value.toFixed(digits);
}

function formatSource(value: string | undefined): string {
    if (!value) return 'missing';
    return value.replace(/_/g, ' ');
}

function formatDelta(value: number | null | undefined, digits = 1): string {
    if (value == null || Number.isNaN(value)) return 'N/A';
    const sign = value > 0 ? '+' : '';
    return `${sign}${value.toFixed(digits)}`;
}

function PlayerComparisonCard({
    player,
    tone,
    isWinner,
}: {
    player: ComparedPlayer;
    tone: 'teal' | 'amber';
    isWinner: boolean;
}) {
    const score = player.overall_score?.value ?? 0;
    const stats = player.stats ?? {};
    const recentForm = player.recent_form ?? [];

    const initials = player.name
        .split(' ')
        .map((part) => part[0])
        .join('')
        .slice(0, 2)
        .toUpperCase();

    const cardsValue =
        stats.yellow_cards == null || stats.red_cards == null
            ? 'N/A'
            : `${stats.yellow_cards}/${stats.red_cards}`;

    const seasonStats = [
        { label: 'Goals', value: formatNumber(stats.goals) },
        { label: 'Assists', value: formatNumber(stats.assists) },
        { label: 'Minutes', value: formatNumber(stats.minutes) },
        { label: 'Rating', value: formatNumber(stats.rating, 2) },
        { label: 'G+A', value: formatNumber(stats.goal_involvements) },
        { label: 'Y/R Cards', value: cardsValue },
    ];

    const cardTone =
        tone === 'teal'
            ? 'border-teal-500/35 shadow-[0_18px_45px_-24px_rgba(20,184,166,0.9)]'
            : 'border-amber-500/35 shadow-[0_18px_45px_-24px_rgba(245,158,11,0.9)]';

    const badgeTone = tone === 'teal' ? 'bg-teal-500/20 text-teal-200' : 'bg-amber-500/20 text-amber-200';

    return (
        <section
            className={`relative overflow-hidden rounded-3xl border bg-slate-900/70 backdrop-blur-sm ${cardTone} ${
                isWinner ? 'ring-2 ring-emerald-400/50' : ''
            }`}
        >
            <div className="absolute inset-0 bg-[radial-gradient(130%_80%_at_80%_0%,rgba(15,23,42,0.2),rgba(15,23,42,0.92))]" />
            <div className="relative p-6">
                <div className="flex items-start justify-between gap-4">
                    <div className="flex items-center gap-4 min-w-0">
                        {player.photo_url ? (
                            <img
                                src={player.photo_url}
                                alt={player.name}
                                className="h-20 w-20 rounded-2xl object-cover border border-slate-700"
                            />
                        ) : (
                            <div className="h-20 w-20 rounded-2xl bg-slate-800 border border-slate-700 flex items-center justify-center text-2xl font-black text-slate-300">
                                {initials || 'NA'}
                            </div>
                        )}

                        <div className="min-w-0">
                            <p className="text-2xl font-black text-white truncate">{player.name}</p>
                            <div className="mt-2 flex items-center gap-2 min-w-0">
                                {player.team?.logo_url ? (
                                    <img
                                        src={player.team.logo_url}
                                        alt={player.team.name}
                                        className="h-5 w-5 object-contain"
                                    />
                                ) : null}
                                <p className="text-sm text-slate-300 truncate">
                                    {[player.team?.name, player.league?.name].filter(Boolean).join(' • ') || 'Unknown team'}
                                </p>
                            </div>
                        </div>
                    </div>

                    <div className="text-right">
                        <p className="text-[11px] uppercase tracking-[0.2em] text-slate-400">Overall Score</p>
                        <p className={`text-4xl font-black ${isWinner ? 'text-emerald-300' : 'text-white'}`}>
                            {formatNumber(score, 1)}
                        </p>
                    </div>
                </div>

                <div className="mt-5 flex flex-wrap gap-2">
                    <span className="px-3 py-1 rounded-full bg-slate-800 text-slate-100 text-xs border border-slate-700">
                        Position: {player.position || 'N/A'}
                    </span>
                    <span className="px-3 py-1 rounded-full bg-slate-800 text-slate-100 text-xs border border-slate-700">
                        Nationality: {player.nationality || 'N/A'}
                    </span>
                    <span className="px-3 py-1 rounded-full bg-slate-800 text-slate-100 text-xs border border-slate-700">
                        Age: {player.age ?? 'N/A'}
                    </span>
                </div>

                <div className="mt-6">
                    <p className="text-[11px] uppercase tracking-[0.2em] text-slate-400">Season Stats</p>
                    <div className="mt-3 grid grid-cols-2 sm:grid-cols-3 gap-3">
                        {seasonStats.map((item) => (
                            <div key={item.label} className="rounded-xl border border-slate-800 bg-slate-900/80 p-3">
                                <p className="text-[11px] uppercase tracking-[0.16em] text-slate-500">{item.label}</p>
                                <p className="mt-1 text-xl font-bold text-slate-100">{item.value}</p>
                            </div>
                        ))}
                    </div>
                </div>

                <div className="mt-6">
                    <p className="text-[11px] uppercase tracking-[0.2em] text-slate-400">Recent Form (Last 5)</p>
                    {recentForm.length > 0 ? (
                        <div className="mt-3 flex flex-wrap gap-2">
                            {recentForm.map((match, index) => {
                                const result = match.result || '-';
                                const badgeClass =
                                    FORM_BADGE_CLASSES[result] || 'bg-slate-700/40 border-slate-600/50 text-slate-200';

                                return (
                                    <div
                                        key={`${match.match_id}-${index}`}
                                        className={`rounded-xl border px-3 py-2 min-w-[108px] ${badgeClass}`}
                                    >
                                        <p className="text-sm font-black">{result}</p>
                                        <p className="text-xs truncate">vs {match.opponent_name}</p>
                                    </div>
                                );
                            })}
                        </div>
                    ) : (
                        <p className="mt-2 text-sm text-slate-400">No supported recent-form data available.</p>
                    )}
                </div>

                <div className="mt-6 flex flex-wrap gap-2">
                    {Object.entries(player.data_sources ?? {}).map(([key, value]) => (
                        <span key={key} className={`px-3 py-1 rounded-full border border-transparent text-xs ${badgeTone}`}>
                            {SOURCE_LABELS[key] || key}: {formatSource(value)}
                        </span>
                    ))}
                </div>

                {player.fallback_notes && player.fallback_notes.length > 0 ? (
                    <div className="mt-4 rounded-xl border border-amber-400/30 bg-amber-500/10 p-3 text-sm text-amber-100">
                        <div className="flex items-center gap-2 mb-1">
                            <AlertTriangle className="w-4 h-4" />
                            <span className="font-semibold">Fallback Active</span>
                        </div>
                        <ul className="space-y-1 text-xs text-amber-100/90">
                            {player.fallback_notes.map((note) => (
                                <li key={note}>{note}</li>
                            ))}
                        </ul>
                    </div>
                ) : null}
            </div>
        </section>
    );
}

export default function PlayerComparePage() {
    const params = useParams();
    const id1 = parseParamToNumber(params.id1);
    const id2 = parseParamToNumber(params.id2);

    const { data, isLoading, isError, error } = useQuery<PlayerComparisonResponse, Error>({
        queryKey: ['player-comparison', id1, id2],
        queryFn: () => getPlayerComparison(id1, id2),
        enabled: Number.isFinite(id1) && Number.isFinite(id2) && id1 > 0 && id2 > 0,
        staleTime: 5 * 60 * 1000,
    });

    const scoreRows = useMemo(() => {
        if (!data) return [];

        const leftComponents = new Map<string, PlayerComparisonScoreComponent>(
            (data.player1.overall_score?.components ?? []).map((component) => [component.key, component])
        );
        const rightComponents = new Map<string, PlayerComparisonScoreComponent>(
            (data.player2.overall_score?.components ?? []).map((component) => [component.key, component])
        );

        const orderedKeys = ['rating', 'goals', 'assists', 'minutes', 'discipline', 'form'];
        return orderedKeys.map((key) => {
            const left = leftComponents.get(key);
            const right = rightComponents.get(key);

            return {
                key,
                label: left?.label || right?.label || key,
                weight: left?.weight ?? right?.weight ?? 0,
                left,
                right,
            };
        });
    }, [data]);

    if (isLoading) {
        return (
            <main className="min-h-screen bg-gradient-to-br from-gray-50 via-blue-50 to-purple-50 dark:from-gray-900 dark:via-gray-900 dark:to-gray-900 p-4 md:p-8">
                <div className="max-w-7xl mx-auto">
                    <LoadingSpinner />
                </div>
            </main>
        );
    }

    if (isError) {
        return (
            <main className="min-h-screen bg-neutral-950 text-neutral-200 p-4 md:p-8">
                <div className="max-w-4xl mx-auto py-16 text-center">
                    <h1 className="text-3xl font-bold text-white">Comparison unavailable</h1>
                    <p className="mt-4 text-neutral-400">
                        {error?.message || 'Could not load player comparison data.'}
                    </p>
                    <Link href="/compare" className="inline-flex mt-8 items-center gap-2 px-4 py-2 rounded-full bg-neutral-900 border border-neutral-800 hover:border-neutral-600 transition-colors">
                        <ArrowLeft className="w-4 h-4" />
                        Back to Compare
                    </Link>
                </div>
            </main>
        );
    }

    if (!data) {
        return (
            <main className="min-h-screen bg-gradient-to-br from-gray-50 via-blue-50 to-purple-50 dark:from-gray-900 dark:via-gray-900 dark:to-gray-900 p-4 md:p-8">
                <div className="max-w-7xl mx-auto text-center py-20">
                    <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Comparison not found</h1>
                </div>
            </main>
        );
    }

    return (
        <main className="min-h-screen bg-neutral-950 text-neutral-200 p-4 md:p-8 relative overflow-hidden">
            <div className="absolute inset-0 z-0 pointer-events-none">
                <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-purple-900/20 via-neutral-950 to-neutral-950" />
            </div>

            <div className="max-w-7xl mx-auto relative z-10">
                <Link href="/compare">
                    <button className="mb-8 flex items-center gap-2 px-4 py-2 rounded-full bg-neutral-900 border border-neutral-800 text-neutral-400 hover:text-white hover:border-neutral-700 transition-all">
                        <ArrowLeft className="w-4 h-4" />
                        Back to Compare
                    </button>
                </Link>

                <div className="text-center mb-12">
                    <h1 className="text-4xl md:text-5xl font-black text-white mb-6">Player Head-to-Head</h1>
                    <div className="inline-flex items-center gap-6 px-8 py-3 bg-neutral-900/50 border border-neutral-800 rounded-full shadow-2xl backdrop-blur-sm">
                        <span className="font-bold text-teal-400 text-xl">{data.player1.name}</span>
                        <span className="text-neutral-600 font-black text-sm">VS</span>
                        <span className="font-bold text-amber-400 text-xl">{data.player2.name}</span>
                    </div>
                    <p className="mt-4 text-sm text-neutral-400">
                        Scope: {data.comparison?.scope || 'Top 5 leagues + UEFA Champions League'}
                    </p>
                </div>

                <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 items-stretch">
                    <PlayerComparisonCard
                        player={data.player1}
                        tone="teal"
                        isWinner={data.comparison?.score_winner_id === data.player1.id}
                    />
                    <PlayerComparisonCard
                        player={data.player2}
                        tone="amber"
                        isWinner={data.comparison?.score_winner_id === data.player2.id}
                    />
                </div>

                <div className="mt-10 grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-4">
                        <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Overall Delta</p>
                        <p className="mt-2 text-2xl font-black text-white">
                            {formatDelta(data.comparison?.metric_deltas?.overall_score, 1)}
                        </p>
                        <p className="text-xs text-slate-400 mt-1">Positive means {data.player1.name} leads.</p>
                    </div>
                    <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-4">
                        <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Goals Delta</p>
                        <p className="mt-2 text-2xl font-black text-white">
                            {formatDelta(data.comparison?.metric_deltas?.goals, 0)}
                        </p>
                    </div>
                    <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-4">
                        <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Assists Delta</p>
                        <p className="mt-2 text-2xl font-black text-white">
                            {formatDelta(data.comparison?.metric_deltas?.assists, 0)}
                        </p>
                    </div>
                </div>

                <div className="mt-8 grid grid-cols-1 xl:grid-cols-5 gap-6">
                    <section className="xl:col-span-2 rounded-3xl border border-slate-800 bg-slate-900/70 p-6">
                        <h2 className="text-xl font-bold text-white">Performance Radar</h2>
                        <p className="mt-2 text-sm text-slate-400">
                            Nivo radar visualization of normalized season and form metrics.
                        </p>
                        <div className="mt-4">
                            <PlayerComparisonRadar player1={data.player1} player2={data.player2} />
                        </div>
                    </section>

                    <section className="xl:col-span-3 rounded-3xl border border-slate-800 bg-slate-900/70 p-6">
                        <h2 className="text-xl font-bold text-white">Overall Score Formula</h2>
                        <p className="mt-2 text-sm text-slate-300">
                            {data.score_formula ||
                                'Weighted score from rating, goals, assists, minutes, discipline, and recent form.'}
                        </p>
                        <div className="mt-2 flex items-start gap-2 text-xs text-slate-400">
                            <Info className="w-4 h-4 mt-0.5" />
                            <p>
                                Missing metrics are excluded from score calculation and remaining weights are re-scaled to
                                keep the formula transparent.
                            </p>
                        </div>

                        {data.comparison?.fallback_active ? (
                            <div className="mt-4 rounded-xl border border-amber-400/30 bg-amber-500/10 p-3 text-sm text-amber-100 flex items-start gap-2">
                                <AlertTriangle className="w-4 h-4 mt-0.5" />
                                <p>
                                    One or more providers are missing data. Fallback values from local DB or match history are
                                    being used where available.
                                </p>
                            </div>
                        ) : null}

                        <div className="mt-5 overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="text-left text-slate-400 border-b border-slate-800">
                                        <th className="py-2 pr-3">Metric</th>
                                        <th className="py-2 pr-3">Weight</th>
                                        <th className="py-2 pr-3">{data.player1.name}</th>
                                        <th className="py-2">{data.player2.name}</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {scoreRows.map((row) => (
                                        <tr key={row.key} className="border-b border-slate-900/80">
                                            <td className="py-2 pr-3 text-slate-200">{row.label}</td>
                                            <td className="py-2 pr-3 text-slate-400">{row.weight}%</td>
                                            <td className="py-2 pr-3 text-slate-200">
                                                {row.left?.available
                                                    ? `${formatNumber(row.left.contribution, 1)} pts`
                                                    : 'N/A'}
                                            </td>
                                            <td className="py-2 text-slate-200">
                                                {row.right?.available
                                                    ? `${formatNumber(row.right.contribution, 1)} pts`
                                                    : 'N/A'}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </section>
                </div>

                {data.note ? <p className="mt-6 text-xs text-neutral-500 text-center">{data.note}</p> : null}
            </div>
        </main>
    );
}
