'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { getTeamDetails, TeamDetailed } from '@/lib/api';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { MapPin, ArrowLeft, Shield, Users2 } from 'lucide-react';
import Link from 'next/link';
import { motion } from 'framer-motion';

const getPositionColor = (position: string) => {
    if (position.includes('Goalkeeper') || position.includes('GK')) return 'from-yellow-500 to-orange-500';
    if (position.includes('Defender') || position.includes('Defence') || position.includes('Back')) return 'from-blue-500 to-cyan-500';
    if (position.includes('Midfielder') || position.includes('Midfield')) return 'from-green-500 to-emerald-500';
    if (position.includes('Attacker') || position.includes('Forward') || position.includes('Striker') || position.includes('Winger')) return 'from-red-500 to-pink-500';
    return 'from-gray-500 to-slate-500';
};

export default function TeamDetailPage() {
    const params = useParams();
    const teamId = parseInt(params.id as string);
    const [team, setTeam] = useState<TeamDetailed | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (teamId) {
            getTeamDetails(teamId)
                .then(setTeam)
                .catch(console.error)
                .finally(() => setLoading(false));
        }
    }, [teamId]);

    if (loading) {
        return (
            <main className="min-h-screen bg-gradient-to-br from-gray-50 via-blue-50 to-purple-50 dark:from-gray-900 dark:via-gray-900 dark:to-gray-900 p-4 md:p-8">
                <div className="max-w-7xl mx-auto">
                    <LoadingSpinner />
                </div>
            </main>
        );
    }

    if (!team) {
        return (
            <main className="min-h-screen bg-gradient-to-br from-gray-50 via-blue-50 to-purple-50 dark:from-gray-900 dark:via-gray-900 dark:to-gray-900 p-4 md:p-8">
                <div className="max-w-7xl mx-auto text-center py-20">
                    <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Team not found</h1>
                </div>
            </main>
        );
    }

    const positionGroups = [
        { key: 'Goalkeeper', label: 'Goalkeepers', icon: Shield, color: 'yellow' },
        { key: 'Defender', label: 'Defenders', icon: Shield, color: 'blue' },
        { key: 'Midfielder', label: 'Midfielders', icon: Users2, color: 'green' },
        { key: 'Attacker', label: 'Attackers', icon: Users2, color: 'red' }
    ];

    return (
        <main className="min-h-screen bg-gradient-to-br from-gray-50 via-blue-50 to-purple-50 dark:from-gray-900 dark:via-gray-900 dark:to-gray-900 p-4 md:p-8">
            <div className="max-w-7xl mx-auto">
                {/* Back Button */}
                <Link href="/teams">
                    <button className="mb-6 flex items-center gap-2 px-4 py-2 rounded-lg bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:shadow-md transition-all">
                        <ArrowLeft className="w-4 h-4" />
                        Back to Teams
                    </button>
                </Link>

                {/* Team Header */}
                <div className="bg-white dark:bg-gray-800 rounded-2xl p-8 mb-8 shadow-xl">
                    <div className="flex flex-col md:flex-row items-center gap-8">
                        {/* Team Logo */}
                        <div className="w-32 h-32 flex items-center justify-center">
                            {team.logo_url ? (
                                <img src={team.logo_url} alt={team.name} className="w-full h-full object-contain" />
                            ) : (
                                <div className="w-full h-full bg-gradient-to-br from-gray-200 to-gray-300 dark:from-gray-700 dark:to-gray-600 rounded-full" />
                            )}
                        </div>

                        {/* Team Info */}
                        <div className="flex-1 text-center md:text-left">
                            <h1 className="text-5xl font-black text-gray-900 dark:text-white mb-4">
                                {team.name}
                            </h1>

                            {team.league && (
                                <div className="flex items-center justify-center md:justify-start gap-3 mb-4">
                                    {team.league.logo_url && (
                                        <img src={team.league.logo_url} alt={team.league.name} className="w-6 h-6 object-contain" />
                                    )}
                                    <span className="text-lg text-gray-600 dark:text-gray-400">
                                        {team.league.name} • {team.league.country}
                                    </span>
                                </div>
                            )}

                            <div className="flex flex-col sm:flex-row gap-4 justify-center md:justify-start">
                                <div className="flex items-center gap-2 text-gray-600 dark:text-gray-400">
                                    <MapPin className="w-5 h-5" />
                                    <span>{team.stadium}</span>
                                </div>
                                <div className="flex items-center gap-2 text-gray-600 dark:text-gray-400">
                                    <Users2 className="w-5 h-5" />
                                    <span>{team.total_players || 0} Players</span>
                                </div>
                            </div>

                            {/* Statistics Button */}
                            <Link href={`/team/${teamId}/statistics`}>
                                <button className="mt-4 px-6 py-3 bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-xl font-bold hover:shadow-lg transition-all hover:scale-105">
                                    📊 View Team Statistics
                                </button>
                            </Link>
                        </div>
                    </div>
                </div>

                {/* Squad */}
                <div className="space-y-8">
                    {positionGroups.map(({ key, label, icon: Icon }) => {
                        const players = team.squad?.[key as keyof typeof team.squad] || [];

                        if (players.length === 0) return null;

                        return (
                            <div key={key}>
                                <div className="flex items-center gap-3 mb-4">
                                    <Icon className="w-6 h-6 text-gray-600 dark:text-gray-400" />
                                    <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
                                        {label}
                                    </h2>
                                    <span className="text-gray-500 dark:text-gray-400">({players.length})</span>
                                </div>

                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                                    {players.map((player, idx) => (
                                        <motion.div
                                            key={player.id}
                                            initial={{ opacity: 0, x: -20 }}
                                            animate={{ opacity: 1, x: 0 }}
                                            transition={{ delay: idx * 0.05 }}
                                        >
                                            <Link href={`/player/${player.id}`}>
                                                <div className={`group relative overflow-hidden bg-gradient-to-br ${getPositionColor(player.position || '')} p-0.5 rounded-xl hover:shadow-2xl hover:-translate-y-1 transition-all duration-300 cursor-pointer`}>
                                                    <div className="bg-white dark:bg-gray-800 rounded-xl p-4">
                                                        <div className="flex items-center gap-4">
                                                            <div className="w-16 h-16 bg-gradient-to-br from-gray-200 to-gray-300 dark:from-gray-700 dark:to-gray-600 rounded-full flex items-center justify-center text-2xl font-bold text-gray-500 dark:text-gray-400">
                                                                {player.name[0]}
                                                            </div>

                                                            <div className="flex-1 min-w-0">
                                                                <h3 className="font-bold text-gray-900 dark:text-white line-clamp-1 group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">
                                                                    {player.name}
                                                                </h3>
                                                                <p className="text-sm text-gray-500 dark:text-gray-400">
                                                                    {player.position}
                                                                </p>
                                                                <div className="flex items-center gap-2 mt-1 text-xs text-gray-400">
                                                                    <span>{player.nationality}</span>
                                                                    {player.height && (
                                                                        <>
                                                                            <span>•</span>
                                                                            <span>{player.height}</span>
                                                                        </>
                                                                    )}
                                                                </div>
                                                            </div>
                                                        </div>
                                                    </div>
                                                </div>
                                            </Link>
                                        </motion.div>
                                    ))}
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>
        </main >
    );
}
