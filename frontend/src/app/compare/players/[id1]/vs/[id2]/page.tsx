'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { EnhancedPlayerCard } from '@/components/EnhancedPlayerCard';
import { ArrowLeft } from 'lucide-react';
import Link from 'next/link';

const API_BASE_URL = "http://localhost:8000/api/v1";

interface PlayerH2H {
    player1: any;
    player2: any;
    comparison: {
        goals_diff: number;
        assists_diff: number;
        rating_diff: number;
    };
}

async function getPlayerH2H(id1: number, id2: number): Promise<PlayerH2H> {
    const res = await fetch(`${API_BASE_URL}/players/${id1}/vs/${id2}`);
    if (!res.ok) throw new Error("Failed to fetch player comparison");
    return res.json();
}

export default function PlayerComparePage() {
    const params = useParams();
    const id1 = parseInt(params.id1 as string);
    const id2 = parseInt(params.id2 as string);
    const [data, setData] = useState<PlayerH2H | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (id1 && id2) {
            getPlayerH2H(id1, id2)
                .then(setData)
                .catch(console.error)
                .finally(() => setLoading(false));
        }
    }, [id1, id2]);

    if (loading) {
        return (
            <main className="min-h-screen bg-gradient-to-br from-gray-50 via-blue-50 to-purple-50 dark:from-gray-900 dark:via-gray-900 dark:to-gray-900 p-4 md:p-8">
                <div className="max-w-7xl mx-auto">
                    <LoadingSpinner />
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
            {/* Background Beams/Gradient */}
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
                    <h1 className="text-4xl font-black text-white mb-6">Player Comparison</h1>
                    <div className="inline-flex items-center gap-6 px-8 py-3 bg-neutral-900/50 border border-neutral-800 rounded-full shadow-2xl backdrop-blur-sm">
                        <span className="font-bold text-blue-500 text-xl">{data.player1.name}</span>
                        <span className="text-neutral-600 font-black text-sm">VS</span>
                        <span className="font-bold text-purple-500 text-xl">{data.player2.name}</span>
                    </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-8 md:gap-16 items-start">
                    {/* Player 1 */}
                    <div className="flex flex-col items-center">
                        <EnhancedPlayerCard player={data.player1} />
                    </div>

                    {/* Player 2 */}
                    <div className="flex flex-col items-center">
                        <EnhancedPlayerCard player={data.player2} />
                    </div>
                </div>

                {/* Stat Comparison Bars */}
                <div className="mt-16 bg-neutral-900/50 border border-neutral-800 rounded-3xl p-8 shadow-2xl max-w-4xl mx-auto backdrop-blur-sm">
                    <h2 className="text-2xl font-bold text-center mb-12 text-white">Head-to-Head Stats</h2>

                    <div className="space-y-10">
                        {/* Goals */}
                        <div>
                            <div className="flex justify-between mb-3 font-bold text-lg">
                                <span className="text-blue-500">{data.player1.stats?.goals || 0}</span>
                                <span className="text-neutral-500 uppercase text-sm tracking-widest">Goals</span>
                                <span className="text-purple-500">{data.player2.stats?.goals || 0}</span>
                            </div>
                            <div className="h-4 bg-neutral-800 rounded-full overflow-hidden flex shadow-inner">
                                <div className="flex-1 flex justify-end">
                                    <div
                                        style={{ width: `${Math.min(100, ((data.player1.stats?.goals || 0) / ((data.player1.stats?.goals || 0) + (data.player2.stats?.goals || 0) || 1)) * 100)}%` }}
                                        className="h-full bg-blue-600 rounded-l-full shadow-[0_0_10px_rgba(37,99,235,0.5)]"
                                    />
                                </div>
                                <div className="w-1 bg-neutral-900 z-10" />
                                <div className="flex-1 flex justify-start">
                                    <div
                                        style={{ width: `${Math.min(100, ((data.player2.stats?.goals || 0) / ((data.player1.stats?.goals || 0) + (data.player2.stats?.goals || 0) || 1)) * 100)}%` }}
                                        className="h-full bg-purple-600 rounded-r-full shadow-[0_0_10px_rgba(147,51,234,0.5)]"
                                    />
                                </div>
                            </div>
                        </div>

                        {/* Assists */}
                        <div>
                            <div className="flex justify-between mb-3 font-bold text-lg">
                                <span className="text-blue-500">{data.player1.stats?.assists || 0}</span>
                                <span className="text-neutral-500 uppercase text-sm tracking-widest">Assists</span>
                                <span className="text-purple-500">{data.player2.stats?.assists || 0}</span>
                            </div>
                            <div className="h-4 bg-neutral-800 rounded-full overflow-hidden flex shadow-inner">
                                <div className="flex-1 flex justify-end">
                                    <div
                                        style={{ width: `${Math.min(100, ((data.player1.stats?.assists || 0) / ((data.player1.stats?.assists || 0) + (data.player2.stats?.assists || 0) || 1)) * 100)}%` }}
                                        className="h-full bg-blue-600 rounded-l-full shadow-[0_0_10px_rgba(37,99,235,0.5)]"
                                    />
                                </div>
                                <div className="w-1 bg-neutral-900 z-10" />
                                <div className="flex-1 flex justify-start">
                                    <div
                                        style={{ width: `${Math.min(100, ((data.player2.stats?.assists || 0) / ((data.player1.stats?.assists || 0) + (data.player2.stats?.assists || 0) || 1)) * 100)}%` }}
                                        className="h-full bg-purple-600 rounded-r-full shadow-[0_0_10px_rgba(147,51,234,0.5)]"
                                    />
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </main>
    );
}
