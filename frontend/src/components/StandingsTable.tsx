'use client';

import { useEffect, useState } from 'react';
import { TrendingUp, TrendingDown, Trophy, Medal } from 'lucide-react';
import { motion } from 'framer-motion';
import { LoadingSpinner } from './LoadingSpinner';

const API_BASE_URL = "http://localhost:8000/api/v1";

export interface TeamStanding {
    rank: number; // Changed from position to match API
    team_id: number;
    team_name: string;
    team_logo?: string;
    played: number;
    won: number;
    drawn: number;
    lost: number;
    goals_for: number;
    goals_against: number;
    goal_difference: number;
    points: number;
    form: string;
}

async function getStandings(leagueId: number): Promise<TeamStanding[]> {
    const res = await fetch(`${API_BASE_URL}/league/${leagueId}/standings`);
    if (!res.ok) throw new Error("Failed to fetch standings");
    return res.json();
}

const FormIndicator = ({ form }: { form: string }) => {
    if (!form) return null;
    return (
        <div className="flex gap-1">
            {form.split(',').slice(-5).map((result, idx) => (
                <div
                    key={idx}
                    className={`w-7 h-7 rounded-lg flex items-center justify-center text-xs font-bold shadow-sm ${result === 'W' ? 'bg-gradient-to-br from-green-500 to-green-600 text-white' :
                            result === 'D' ? 'bg-gradient-to-br from-yellow-500 to-yellow-600 text-white' :
                                'bg-gradient-to-br from-red-500 to-red-600 text-white'
                        }`}
                >
                    {result}
                </div>
            ))}
        </div>
    );
};

export function StandingsTable({ leagueId = 2021, leagueName = "Premier League" }: { leagueId?: number, leagueName?: string }) {
    const [standings, setStandings] = useState<TeamStanding[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        setLoading(true);
        getStandings(leagueId)
            .then(setStandings)
            .catch(console.error)
            .finally(() => setLoading(false));
    }, [leagueId]);

    if (loading) return <LoadingSpinner />;

    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="w-full"
        >
            <div className="mb-6 flex items-center gap-3">
                <Trophy className="w-8 h-8 text-yellow-500" />
                <h2 className="text-3xl font-black text-gray-900 dark:text-white">
                    {leagueName} Standings
                </h2>
            </div>

            <div className="overflow-x-auto rounded-xl shadow-xl">
                <table className="w-full text-sm bg-white dark:bg-gray-800">
                    <thead>
                        <tr className="bg-gradient-to-r from-blue-600 to-purple-600 text-white">
                            <th className="text-left p-4 font-bold">#</th>
                            <th className="text-left p-4 font-bold">Team</th>
                            <th className="text-center p-4 font-bold hidden sm:table-cell">P</th>
                            <th className="text-center p-4 font-bold hidden md:table-cell">W</th>
                            <th className="text-center p-4 font-bold hidden md:table-cell">D</th>
                            <th className="text-center p-4 font-bold hidden md:table-cell">L</th>
                            <th className="text-center p-4 font-bold hidden lg:table-cell">GF</th>
                            <th className="text-center p-4 font-bold hidden lg:table-cell">GA</th>
                            <th className="text-center p-4 font-bold">GD</th>
                            <th className="text-center p-4 font-bold">Pts</th>
                            <th className="text-center p-4 font-bold hidden xl:table-cell">Form</th>
                        </tr>
                    </thead>
                    <tbody>
                        {standings.map((team, idx) => {
                            const isChampionsLeague = team.rank <= 4;
                            const isRelegation = team.rank >= standings.length - 2;

                            return (
                                <motion.tr
                                    key={team.team_id}
                                    initial={{ opacity: 0, x: -20 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    transition={{ delay: idx * 0.02 }}
                                    className={`border-b border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors ${isChampionsLeague ? 'bg-blue-50/50 dark:bg-blue-900/10' :
                                            isRelegation ? 'bg-red-50/50 dark:bg-red-900/10' :
                                                ''
                                        }`}
                                >
                                    <td className="p-4">
                                        <div className="flex items-center gap-2">
                                            {team.rank === 1 && <Medal className="w-5 h-5 text-yellow-500" />}
                                            {team.rank === 2 && <Medal className="w-5 h-5 text-gray-400" />}
                                            {team.rank === 3 && <Medal className="w-5 h-5 text-orange-600" />}
                                            <span className="font-bold text-gray-900 dark:text-white">{team.rank}</span>
                                        </div>
                                    </td>
                                    <td className="p-4">
                                        <div className="flex items-center gap-3">
                                            {team.rank === 1 && <TrendingUp className="w-4 h-4 text-green-500 hidden sm:block" />}
                                            {team.rank === standings.length && <TrendingDown className="w-4 h-4 text-red-500 hidden sm:block" />}
                                            {team.team_logo ? (
                                                <img src={team.team_logo} alt={team.team_name} className="w-8 h-8 object-contain" />
                                            ) : (
                                                <div className="w-8 h-8 bg-gray-200 dark:bg-gray-700 rounded-full" />
                                            )}
                                            <span className="font-semibold text-gray-900 dark:text-white">
                                                {team.team_name}
                                            </span>
                                        </div>
                                    </td>
                                    <td className="text-center p-4 text-gray-600 dark:text-gray-300 hidden sm:table-cell">{team.played}</td>
                                    <td className="text-center p-4 text-gray-600 dark:text-gray-300 hidden md:table-cell">{team.won}</td>
                                    <td className="text-center p-4 text-gray-600 dark:text-gray-300 hidden md:table-cell">{team.drawn}</td>
                                    <td className="text-center p-4 text-gray-600 dark:text-gray-300 hidden md:table-cell">{team.lost}</td>
                                    <td className="text-center p-4 text-gray-600 dark:text-gray-300 hidden lg:table-cell">{team.goals_for}</td>
                                    <td className="text-center p-4 text-gray-600 dark:text-gray-300 hidden lg:table-cell">{team.goals_against}</td>
                                    <td className="text-center p-4">
                                        <span className={`font-semibold ${team.goal_difference > 0 ? 'text-green-600 dark:text-green-400' :
                                                team.goal_difference < 0 ? 'text-red-600 dark:text-red-400' :
                                                    'text-gray-600 dark:text-gray-300'
                                            }`}>
                                            {team.goal_difference > 0 ? '+' : ''}{team.goal_difference}
                                        </span>
                                    </td>
                                    <td className="text-center p-4">
                                        <span className="font-black text-lg text-gray-900 dark:text-white">
                                            {team.points}
                                        </span>
                                    </td>
                                    <td className="p-4 hidden xl:table-cell">
                                        <FormIndicator form={team.form} />
                                    </td>
                                </motion.tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>

            {/* Legend */}
            <div className="mt-6 flex flex-wrap gap-6 text-sm justify-center">
                <div className="flex items-center gap-2">
                    <div className="w-6 h-6 bg-blue-100 dark:bg-blue-900/20 rounded"></div>
                    <span className="text-gray-600 dark:text-gray-400">Champions League</span>
                </div>
                <div className="flex items-center gap-2">
                    <div className="w-6 h-6 bg-red-100 dark:bg-red-900/20 rounded"></div>
                    <span className="text-gray-600 dark:text-gray-400">Relegation Zone</span>
                </div>
            </div>
        </motion.div>
    );
}
