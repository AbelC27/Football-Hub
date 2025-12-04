'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { getPlayerEnhanced, PlayerDetailed } from '@/lib/api';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { EnhancedPlayerCard } from '@/components/EnhancedPlayerCard';
import { ArrowLeft, Info } from 'lucide-react';
import Link from 'next/link';

export default function PlayerDetailPage() {
    const params = useParams();
    const playerId = parseInt(params.id as string);
    const [player, setPlayer] = useState<PlayerDetailed | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (playerId) {
            getPlayerEnhanced(playerId)
                .then(setPlayer)
                .catch(console.error)
                .finally(() => setLoading(false));
        }
    }, [playerId]);

    if (loading) {
        return (
            <main className="min-h-screen bg-gradient-to-br from-gray-50 via-blue-50 to-purple-50 dark:from-gray-900 dark:via-gray-900 dark:to-gray-900 p-4 md:p-8">
                <div className="max-w-7xl mx-auto">
                    <LoadingSpinner />
                </div>
            </main>
        );
    }

    if (!player) {
        return (
            <main className="min-h-screen bg-gradient-to-br from-gray-50 via-blue-50 to-purple-50 dark:from-gray-900 dark:via-gray-900 dark:to-gray-900 p-4 md:p-8">
                <div className="max-w-7xl mx-auto text-center py-20">
                    <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Player not found</h1>
                </div>
            </main>
        );
    }

    return (
        <main className="min-h-screen bg-gradient-to-br from-gray-50 via-blue-50 to-purple-50 dark:from-gray-900 dark:via-gray-900 dark:to-gray-900 p-4 md:p-8">
            <div className="max-w-7xl mx-auto">
                {/* Back Button */}
                <Link href={player.team ? `/team/${player.team.id}` : '/teams'}>
                    <button className="mb-6 flex items-center gap-2 px-4 py-2 rounded-lg bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:shadow-md transition-all">
                        <ArrowLeft className="w-4 h-4" />
                        Back to {player.team ? player.team.name : 'Teams'}
                    </button>
                </Link>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                    {/* EA FC Card */}
                    <div className="flex items-center justify-center">
                        <EnhancedPlayerCard player={player} />
                    </div>

                    {/* Player Info */}
                    <div className="space-y-6">
                        <div className="bg-white dark:bg-gray-800 rounded-2xl p-8 shadow-xl">
                            <div className="flex items-center gap-3 mb-6">
                                <Info className="w-6 h-6 text-blue-500" />
                                <h2 className="text-3xl font-black text-gray-900 dark:text-white">
                                    Player Information
                                </h2>
                            </div>

                            <div className="space-y-4">
                                <div>
                                    <div className="text-sm text-gray-500 dark:text-gray-400 mb-1">Full Name</div>
                                    <div className="text-xl font-bold text-gray-900 dark:text-white">{player.name}</div>
                                </div>

                                <div>
                                    <div className="text-sm text-gray-500 dark:text-gray-400 mb-1">Position</div>
                                    <div className="text-xl font-bold text-gray-900 dark:text-white">{player.position || 'Unknown'}</div>
                                </div>

                                {player.nationality && (
                                    <div>
                                        <div className="text-sm text-gray-500 dark:text-gray-400 mb-1">Nationality</div>
                                        <div className="text-xl font-bold text-gray-900 dark:text-white">{player.nationality}</div>
                                    </div>
                                )}

                                {player.height && (
                                    <div>
                                        <div className="text-sm text-gray-500 dark:text-gray-400 mb-1">Height</div>
                                        <div className="text-xl font-bold text-gray-900 dark:text-white">{player.height}</div>
                                    </div>
                                )}

                                {player.team && (
                                    <div>
                                        <div className="text-sm text-gray-500 dark:text-gray-400 mb-1">Current Club</div>
                                        <Link href={`/team/${player.team.id}`}>
                                            <div className="flex items-center gap-3 p-3 rounded-lg bg-gray-50 dark:bg-gray-700 hover:bg-gray-100 dark:hover:bg-gray-600 transition-colors cursor-pointer">
                                                {player.team.logo_url && (
                                                    <img src={player.team.logo_url} alt={player.team.name} className="w-12 h-12 object-contain" />
                                                )}
                                                <div>
                                                    <div className="font-bold text-gray-900 dark:text-white">{player.team.name}</div>
                                                    {player.team.stadium && (
                                                        <div className="text-sm text-gray-500 dark:text-gray-400">{player.team.stadium}</div>
                                                    )}
                                                </div>
                                            </div>
                                        </Link>
                                    </div>
                                )}

                                {player.league && (
                                    <div>
                                        <div className="text-sm text-gray-500 dark:text-gray-400 mb-1">League</div>
                                        <div className="text-xl font-bold text-gray-900 dark:text-white">
                                            {player.league.name} ({player.league.country})
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* Note about Stats */}
                        <div className="bg-blue-50 dark:bg-blue-900/20 border-2 border-blue-200 dark:border-blue-800 rounded-2xl p-6">
                            <h3 className="font-bold text-blue-900 dark:text-blue-300 mb-2">📊 Player Stats Coming Soon</h3>
                            <p className="text-sm text-blue-800 dark:text-blue-400">
                                Detailed player statistics including pace, shooting, passing, dribbling, defending, and physical attributes will be available once we integrate additional player data sources.
                            </p>
                        </div>
                    </div>
                </div>
            </div>
        </main>
    );
}
