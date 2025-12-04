'use client';

import { useEffect, useState } from 'react';
import { getTeams, TeamDetailed, getLeagues, League } from '@/lib/api';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { Search, MapPin, Users, Trophy } from 'lucide-react';
import Link from 'next/link';
import { motion } from 'framer-motion';
import { CardSpotlight } from '@/components/ui/SpotlightCard';

export default function TeamsPage() {
    const [teams, setTeams] = useState<TeamDetailed[]>([]);
    const [leagues, setLeagues] = useState<League[]>([]);
    const [selectedLeague, setSelectedLeague] = useState<number | null>(null);
    const [searchTerm, setSearchTerm] = useState('');
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        getLeagues().then(setLeagues);
    }, []);

    useEffect(() => {
        setLoading(true);
        getTeams(selectedLeague || undefined, searchTerm || undefined)
            .then(setTeams)
            .catch(console.error)
            .finally(() => setLoading(false));
    }, [selectedLeague, searchTerm]);

    return (
        <main className="min-h-screen bg-neutral-950 text-neutral-200 p-4 md:p-8 relative overflow-hidden">
            {/* Background Beams/Gradient */}
            <div className="absolute inset-0 z-0 pointer-events-none">
                <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-blue-900/20 via-neutral-950 to-neutral-950" />
            </div>

            <div className="max-w-7xl mx-auto relative z-10">
                {/* Header */}
                <div className="mb-12">
                    <h1 className="text-5xl font-black mb-6 bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-purple-600 flex items-center gap-4">
                        <Trophy className="w-12 h-12 text-yellow-500" />
                        All Teams
                    </h1>
                    <p className="text-neutral-400 text-lg">
                        Browse teams from top European leagues
                    </p>
                </div>

                {/* Filters */}
                <div className="mb-12 space-y-6">
                    {/* Search */}
                    <div className="relative max-w-2xl">
                        <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-neutral-500" />
                        <input
                            type="text"
                            placeholder="Search teams..."
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                            className="w-full pl-12 pr-4 py-4 rounded-2xl border border-neutral-800 bg-neutral-900/50 text-neutral-200 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 transition-all text-lg placeholder:text-neutral-600"
                        />
                    </div>

                    {/* League Filter */}
                    <div className="flex flex-wrap gap-3">
                        <button
                            onClick={() => setSelectedLeague(null)}
                            className={`px-6 py-2 rounded-full font-medium transition-all duration-300 border ${selectedLeague === null
                                ? 'bg-white text-black border-white shadow-[0_0_20px_rgba(255,255,255,0.3)]'
                                : 'bg-neutral-900 text-neutral-400 border-neutral-800 hover:border-neutral-600 hover:text-neutral-200'
                                }`}
                        >
                            All Leagues
                        </button>
                        {leagues.map(league => (
                            <button
                                key={league.id}
                                onClick={() => setSelectedLeague(league.id)}
                                className={`px-6 py-2 rounded-full font-medium transition-all duration-300 border ${selectedLeague === league.id
                                    ? 'bg-white text-black border-white shadow-[0_0_20px_rgba(255,255,255,0.3)]'
                                    : 'bg-neutral-900 text-neutral-400 border-neutral-800 hover:border-neutral-600 hover:text-neutral-200'
                                    }`}
                            >
                                {league.name}
                            </button>
                        ))}
                    </div>
                </div>

                {/* Teams Grid */}
                {loading ? (
                    <LoadingSpinner />
                ) : teams.length === 0 ? (
                    <div className="text-center py-32 bg-neutral-900/30 border border-neutral-800 rounded-3xl">
                        <h3 className="text-2xl font-bold text-neutral-300 mb-2">
                            No teams found
                        </h3>
                        <p className="text-neutral-500">
                            Try adjusting your search or filter
                        </p>
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                        {teams.map((team, idx) => (
                            <motion.div
                                key={team.id}
                                initial={{ opacity: 0, y: 20 }}
                                animate={{ opacity: 1, y: 0 }}
                                transition={{ delay: idx * 0.05 }}
                            >
                                <Link href={`/team/${team.id}`}>
                                    <div className="h-full">
                                        <CardSpotlight className="h-full p-6 group cursor-pointer hover:border-neutral-700 transition-colors">
                                            <div className="flex flex-col items-center h-full">
                                                {/* Team Logo */}
                                                <div className="relative w-24 h-24 mb-6 transition-transform duration-300 group-hover:scale-110">
                                                    {team.logo_url ? (
                                                        <img
                                                            src={team.logo_url}
                                                            alt={team.name}
                                                            className="w-full h-full object-contain drop-shadow-2xl"
                                                        />
                                                    ) : (
                                                        <div className="w-full h-full bg-neutral-800 rounded-full flex items-center justify-center">
                                                            <Trophy className="w-10 h-10 text-neutral-600" />
                                                        </div>
                                                    )}
                                                </div>

                                                {/* Team Name */}
                                                <h3 className="text-xl font-bold text-center text-neutral-200 mb-3 line-clamp-2 group-hover:text-white transition-colors">
                                                    {team.name}
                                                </h3>

                                                {/* League Badge */}
                                                {team.league && (
                                                    <div className="flex items-center justify-center gap-2 mb-4 px-3 py-1 rounded-full bg-neutral-800/50 border border-neutral-800">
                                                        {team.league.logo_url && (
                                                            <img src={team.league.logo_url} alt={team.league.name} className="w-4 h-4 object-contain opacity-70" />
                                                        )}
                                                        <span className="text-xs font-medium text-neutral-400">
                                                            {team.league.name}
                                                        </span>
                                                    </div>
                                                )}

                                                {/* Info */}
                                                <div className="mt-auto w-full pt-4 border-t border-neutral-800 flex justify-between text-sm text-neutral-500">
                                                    <div className="flex items-center gap-1.5">
                                                        <MapPin className="w-3.5 h-3.5" />
                                                        <span className="line-clamp-1 max-w-[100px]">{team.stadium}</span>
                                                    </div>
                                                    <div className="flex items-center gap-1.5">
                                                        <Users className="w-3.5 h-3.5" />
                                                        <span>{team.player_count || 0}</span>
                                                    </div>
                                                </div>
                                            </div>
                                        </CardSpotlight>
                                    </div>
                                </Link>
                            </motion.div>
                        ))}
                    </div>
                )}
            </div>
        </main>
    );
}
