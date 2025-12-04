'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { TeamDetailed } from '@/lib/api';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { ArrowLeft } from 'lucide-react';
import Link from 'next/link';
import { motion } from 'framer-motion';

const API_BASE_URL = "http://localhost:8000/api/v1";

interface TeamStats {
    team_id: number;
    team_name: string;
    matches_played: number;
    wins: number;
    draws: number;
    losses: number;
    goals_scored: number;
    goals_conceded: number;
    goal_difference: number;
    clean_sheets: number;
    win_rate: number;
    form: string[];
    average_goals_scored: number;
    average_goals_conceded: number;
}

async function getTeamStatistics(teamId: number): Promise<TeamStats> {
    const res = await fetch(`${API_BASE_URL}/teams/${teamId}/statistics`);
    if (!res.ok) throw new Error("Failed to fetch team statistics");
    return res.json();
}

export default function TeamStatisticsPage() {
    const params = useParams();
    const teamId = parseInt(params.id as string);
    const [stats, setStats] = useState<TeamStats | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (teamId) {
            getTeamStatistics(teamId)
                .then(setStats)
                .catch(console.error)
                .finally(() => setLoading(false));
        }
    }, [teamId]);

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
                    <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Statistics not available</h1>
                </div>
            </main>
        );
    }

    const StatCard = ({ label, value, subtext }: { label: string, value: string | number, subtext?: string }) => (
        <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-lg hover:shadow-xl transition-shadow"
        >
            <div className="text-sm text-gray-500 dark:text-gray-400 mb-2 font-semibold">{label}</div>
            <div className="text-4xl font-black text-gray-900 dark:text-white mb-1">{value}</div>
            {subtext && <div className="text-xs text-gray-400">{subtext}</div>}
        </motion.div>
    );

    return (
        <main className="min-h-screen bg-gradient-to-br from-gray-50 via-blue-50 to-purple-50 dark:from-gray-900 dark:via-gray-900 dark:to-gray-900 p-4 md:p-8">
            <div className="max-w-6xl mx-auto">
                {/* Back Button */}
                <Link href={`/team/${teamId}`}>
                    <button className="mb-6 flex items-center gap-2 px-4 py-2 rounded-lg bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:shadow-md transition-all">
                        <ArrowLeft className="w-4 h-4" />
                        Back to Team
                    </button>
                </Link>

                {/* Header */}
                <div className="mb-8">
                    <h1 className="text-5xl font-black text-gray-900 dark:text-white mb-2">
                        {stats.team_name} Statistics
                    </h1>
                    <p className="text-gray-600 dark:text-gray-400">Season performance overview</p>
                </div>

                {/* Main Stats Grid */}
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
                    <StatCard label="Matches Played" value={stats.matches_played} />
                    <StatCard label="Wins" value={stats.wins} subtext={`${stats.win_rate}% win rate`} />
                    <StatCard label="Draws" value={stats.draws} />
                    <StatCard label="Losses" value={stats.losses} />
                </div>

                {/* Goals Stats */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
                    <StatCard label="Goals Scored" value={stats.goals_scored} subtext={`${stats.average_goals_scored} per match`} />
                    <StatCard label="Goals Conceded" value={stats.goals_conceded} subtext={`${stats.average_goals_conceded} per match`} />
                    <StatCard label="Goal Difference" value={stats.goal_difference > 0 ? `+${stats.goal_difference}` : stats.goal_difference} />
                </div>

                {/* Additional Stats */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
                    <StatCard label="Clean Sheets" value={stats.clean_sheets} />
                    <StatCard label="Win Rate" value={`${stats.win_rate}%`} />
                </div>

                {/* Form */}
                <div className="bg-white dark:bg-gray-800 rounded-xl p-8 shadow-lg">
                    <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-6">Recent Form</h2>
                    <div className="flex gap-3 flex-wrap">
                        {stats.form.map((result, idx) => (
                            <div
                                key={idx}
                                className={`w-16 h-16 rounded-xl flex items-center justify-center text-2xl font-black shadow-md ${result === 'W' ? 'bg-gradient-to-br from-green-500 to-green-600 text-white' :
                                        result === 'D' ? 'bg-gradient-to-br from-yellow-500 to-yellow-600 text-white' :
                                            'bg-gradient-to-br from-red-500 to-red-600 text-white'
                                    }`}
                            >
                                {result}
                            </div>
                        ))}
                    </div>
                    <p className="text-sm text-gray-500 dark:text-gray-400 mt-4">
                        Last {stats.form.length} matches (oldest to most recent)
                    </p>
                </div>
            </div>
        </main>
    );
}
