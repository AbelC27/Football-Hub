'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ArrowLeft, TrendingUp, TrendingDown } from 'lucide-react';
import Link from 'next/link';
import { motion } from 'framer-motion';

const API_BASE_URL = "http://localhost:8000/api/v1";

interface TeamStanding {
    position: number;
    team_id: number;
    team_name: string;
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
    return (
        <div className="flex gap-1">
            {form.split('').map((result, idx) => (
                <div
                    key={idx}
                    className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${result === 'W' ? 'bg-green-500 text-white' :
                            result === 'D' ? 'bg-yellow-500 text-white' :
                                'bg-red-500 text-white'
                        }`}
                >
                    {result}
                </div>
            ))}
        </div>
    );
};

export default function LeagueStandings() {
    const params = useParams();
    const [standings, setStandings] = useState<TeamStanding[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (params.id) {
            getStandings(Number(params.id))
                .then(setStandings)
                .catch(console.error)
                .finally(() => setLoading(false));
        }
    }, [params.id]);

    if (loading) return <div className="p-8 text-center">Loading standings...</div>;

    return (
        <main className="min-h-screen p-4 md:p-8 bg-gray-50 dark:bg-gray-900">
            <div className="max-w-6xl mx-auto">
                <Link href="/" className="inline-flex items-center text-blue-600 hover:underline mb-6">
                    <ArrowLeft className="w-4 h-4 mr-2" /> Back to Matches
                </Link>

                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.5 }}
                >
                    <Card>
                        <CardHeader>
                            <CardTitle className="text-2xl">League Standings</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="overflow-x-auto">
                                <table className="w-full text-sm">
                                    <thead>
                                        <tr className="border-b-2 border-gray-200 dark:border-gray-700">
                                            <th className="text-left p-3">#</th>
                                            <th className="text-left p-3">Team</th>
                                            <th className="text-center p-3">P</th>
                                            <th className="text-center p-3">W</th>
                                            <th className="text-center p-3">D</th>
                                            <th className="text-center p-3">L</th>
                                            <th className="text-center p-3">GF</th>
                                            <th className="text-center p-3">GA</th>
                                            <th className="text-center p-3">GD</th>
                                            <th className="text-center p-3 font-bold">Pts</th>
                                            <th className="text-center p-3">Form</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {standings.map((team, idx) => (
                                            <motion.tr
                                                key={team.team_id}
                                                initial={{ opacity: 0, x: -20 }}
                                                animate={{ opacity: 1, x: 0 }}
                                                transition={{ delay: idx * 0.05 }}
                                                className={`border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800 ${team.position <= 4 ? 'bg-blue-50 dark:bg-blue-900/20' :
                                                        team.position >= standings.length - 2 ? 'bg-red-50 dark:bg-red-900/20' :
                                                            ''
                                                    }`}
                                            >
                                                <td className="p-3 font-bold">{team.position}</td>
                                                <td className="p-3">
                                                    <div className="flex items-center gap-2">
                                                        {team.position === 1 && <TrendingUp className="w-4 h-4 text-green-500" />}
                                                        {team.position === standings.length && <TrendingDown className="w-4 h-4 text-red-500" />}
                                                        <span className="font-medium">{team.team_name}</span>
                                                    </div>
                                                </td>
                                                <td className="text-center p-3">{team.played}</td>
                                                <td className="text-center p-3">{team.won}</td>
                                                <td className="text-center p-3">{team.drawn}</td>
                                                <td className="text-center p-3">{team.lost}</td>
                                                <td className="text-center p-3">{team.goals_for}</td>
                                                <td className="text-center p-3">{team.goals_against}</td>
                                                <td className="text-center p-3 font-semibold">{team.goal_difference > 0 ? '+' : ''}{team.goal_difference}</td>
                                                <td className="text-center p-3 font-bold text-lg">{team.points}</td>
                                                <td className="p-3">
                                                    <FormIndicator form={team.form} />
                                                </td>
                                            </motion.tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>

                            <div className="mt-6 flex gap-4 text-sm">
                                <div className="flex items-center gap-2">
                                    <div className="w-4 h-4 bg-blue-100 dark:bg-blue-900/20 rounded"></div>
                                    <span>Champions League</span>
                                </div>
                                <div className="flex items-center gap-2">
                                    <div className="w-4 h-4 bg-red-100 dark:bg-red-900/20 rounded"></div>
                                    <span>Relegation Zone</span>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                </motion.div>
            </div>
        </main>
    );
}
