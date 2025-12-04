'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { ArrowLeft, Trophy, History, TrendingUp } from 'lucide-react';
import Link from 'next/link';
import { motion } from 'framer-motion';

const API_BASE_URL = "http://localhost:8000/api/v1";

interface H2HStats {
    team1: {
        id: number;
        name: string;
        logo_url: string;
        wins: number;
        goals: number;
    };
    team2: {
        id: number;
        name: string;
        logo_url: string;
        wins: number;
        goals: number;
    };
    draws: number;
    total_matches: number;
    match_history: Array<{
        id: number;
        date: string;
        home_team: string;
        away_team: string;
        home_score: number;
        away_score: number;
        winner_id: number | null;
        result: string;
    }>;
}

async function getH2HStats(id1: number, id2: number): Promise<H2HStats> {
    const res = await fetch(`${API_BASE_URL}/teams/${id1}/vs/${id2}`);
    if (!res.ok) throw new Error("Failed to fetch H2H stats");
    return res.json();
}

export default function TeamH2HPage() {
    const params = useParams();
    const id1 = parseInt(params.id1 as string);
    const id2 = parseInt(params.id2 as string);
    const [stats, setStats] = useState<H2HStats | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (id1 && id2) {
            getH2HStats(id1, id2)
                .then(setStats)
                .catch(console.error)
                .finally(() => setLoading(false));
        }
    }, [id1, id2]);

    if (loading) {
        return (
            <main className="min-h-screen bg-gradient-to-br from-gray-50 via-blue-50 to-purple-50 dark:from-gray-900 dark:via-gray-900 dark:to-gray-900 p-4 md:p-8">
                <div className="max-w-6xl mx-auto">
                    <LoadingSpinner />
                </div>
            </main>
        );
    }

    if (!stats) {
        return (
            <main className="min-h-screen bg-gradient-to-br from-gray-50 via-blue-50 to-purple-50 dark:from-gray-900 dark:via-gray-900 dark:to-gray-900 p-4 md:p-8">
                <div className="max-w-6xl mx-auto text-center py-20">
                    <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Comparison not found</h1>
                </div>
            </main>
        );
    }

    const total = stats.total_matches || 1;
    const t1WinPct = Math.round((stats.team1.wins / total) * 100);
    const t2WinPct = Math.round((stats.team2.wins / total) * 100);
    const drawPct = 100 - t1WinPct - t2WinPct;

    return (
        <main className="min-h-screen bg-neutral-950 text-neutral-200 p-4 md:p-8 relative overflow-hidden">
            {/* Background Beams/Gradient */}
            <div className="absolute inset-0 z-0 pointer-events-none">
                <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-blue-900/20 via-neutral-950 to-neutral-950" />
            </div>

            <div className="max-w-6xl mx-auto relative z-10">
                <Link href="/compare">
                    <button className="mb-8 flex items-center gap-2 px-4 py-2 rounded-full bg-neutral-900 border border-neutral-800 text-neutral-400 hover:text-white hover:border-neutral-700 transition-all">
                        <ArrowLeft className="w-4 h-4" />
                        Back to Compare
                    </button>
                </Link>

                {/* Header / VS Section */}
                <div className="bg-neutral-900/50 border border-neutral-800 rounded-3xl p-8 shadow-2xl mb-8 backdrop-blur-sm">
                    <div className="flex flex-col md:flex-row items-center justify-between gap-8">
                        {/* Team 1 */}
                        <div className="flex flex-col items-center text-center flex-1">
                            <div className="w-32 h-32 mb-6 relative">
                                {stats.team1.logo_url && (
                                    <img src={stats.team1.logo_url} alt={stats.team1.name} className="w-full h-full object-contain drop-shadow-2xl" />
                                )}
                                {stats.team1.wins > stats.team2.wins && (
                                    <div className="absolute -top-2 -right-2 bg-yellow-500/20 text-yellow-500 border border-yellow-500/50 p-2 rounded-full shadow-[0_0_15px_rgba(234,179,8,0.3)]">
                                        <Trophy className="w-6 h-6" />
                                    </div>
                                )}
                            </div>
                            <h2 className="text-2xl font-black text-white mb-2">{stats.team1.name}</h2>
                            <div className="text-4xl font-black text-blue-500">{stats.team1.wins} Wins</div>
                        </div>

                        {/* VS */}
                        <div className="flex flex-col items-center">
                            <div className="text-6xl font-black text-neutral-800">VS</div>
                            <div className="mt-2 px-4 py-1 bg-neutral-800 rounded-full text-sm font-bold text-neutral-400 border border-neutral-700">
                                {stats.total_matches} Matches
                            </div>
                        </div>

                        {/* Team 2 */}
                        <div className="flex flex-col items-center text-center flex-1">
                            <div className="w-32 h-32 mb-6 relative">
                                {stats.team2.logo_url && (
                                    <img src={stats.team2.logo_url} alt={stats.team2.name} className="w-full h-full object-contain drop-shadow-2xl" />
                                )}
                                {stats.team2.wins > stats.team1.wins && (
                                    <div className="absolute -top-2 -right-2 bg-yellow-500/20 text-yellow-500 border border-yellow-500/50 p-2 rounded-full shadow-[0_0_15px_rgba(234,179,8,0.3)]">
                                        <Trophy className="w-6 h-6" />
                                    </div>
                                )}
                            </div>
                            <h2 className="text-2xl font-black text-white mb-2">{stats.team2.name}</h2>
                            <div className="text-4xl font-black text-purple-500">{stats.team2.wins} Wins</div>
                        </div>
                    </div>

                    {/* Win Probability Bar */}
                    <div className="mt-12">
                        <div className="flex justify-between text-sm font-bold mb-2 text-neutral-500">
                            <span className="text-blue-400">{t1WinPct}%</span>
                            <span>{drawPct}% Draw</span>
                            <span className="text-purple-400">{t2WinPct}%</span>
                        </div>
                        <div className="h-4 bg-neutral-800 rounded-full overflow-hidden flex">
                            <div style={{ width: `${t1WinPct}%` }} className="bg-blue-600 shadow-[0_0_10px_rgba(37,99,235,0.5)]" />
                            <div style={{ width: `${drawPct}%` }} className="bg-neutral-700" />
                            <div style={{ width: `${t2WinPct}%` }} className="bg-purple-600 shadow-[0_0_10px_rgba(147,51,234,0.5)]" />
                        </div>
                    </div>
                </div>

                {/* Stats Grid */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-8">
                    <div className="bg-neutral-900/50 border border-neutral-800 rounded-3xl p-6 shadow-xl backdrop-blur-sm">
                        <h3 className="text-xl font-bold mb-6 flex items-center gap-2 text-white">
                            <TrendingUp className="w-5 h-5 text-blue-500" />
                            Goals Scored
                        </h3>
                        <div className="flex items-end justify-between gap-4">
                            <div className="flex-1 text-center">
                                <div className="text-4xl font-black text-white mb-2">{stats.team1.goals}</div>
                                <div className="text-sm text-neutral-500">{stats.team1.name}</div>
                                <div className="h-2 bg-neutral-800 rounded-full mt-2 overflow-hidden">
                                    <div style={{ width: `${(stats.team1.goals / (stats.team1.goals + stats.team2.goals)) * 100}%` }} className="h-full bg-blue-500" />
                                </div>
                            </div>
                            <div className="flex-1 text-center">
                                <div className="text-4xl font-black text-white mb-2">{stats.team2.goals}</div>
                                <div className="text-sm text-neutral-500">{stats.team2.name}</div>
                                <div className="h-2 bg-neutral-800 rounded-full mt-2 overflow-hidden">
                                    <div style={{ width: `${(stats.team2.goals / (stats.team1.goals + stats.team2.goals)) * 100}%` }} className="h-full bg-purple-500" />
                                </div>
                            </div>
                        </div>
                    </div>

                    <div className="bg-neutral-900/50 border border-neutral-800 rounded-3xl p-6 shadow-xl backdrop-blur-sm">
                        <h3 className="text-xl font-bold mb-6 flex items-center gap-2 text-white">
                            <History className="w-5 h-5 text-green-500" />
                            Recent History
                        </h3>
                        <div className="space-y-3">
                            {(stats.match_history || []).slice(0, 5).map((match) => (
                                <div key={match.id} className="flex items-center justify-between p-3 bg-neutral-800/50 rounded-xl border border-neutral-800">
                                    <div className="text-sm font-bold text-neutral-500 w-20">{new Date(match.date).toLocaleDateString()}</div>
                                    <div className="flex-1 flex justify-center items-center gap-4 font-bold">
                                        <span className={match.winner_id === stats.team1.id ? 'text-blue-400' : 'text-neutral-400'}>{match.home_score}</span>
                                        <span className="text-neutral-600">-</span>
                                        <span className={match.winner_id === stats.team2.id ? 'text-purple-400' : 'text-neutral-400'}>{match.away_score}</span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>
        </main>
    );
}
