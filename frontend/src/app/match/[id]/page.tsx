'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { Match } from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { PredictionBadge } from '@/components/PredictionBadge';
import { MatchTimeline } from '@/components/MatchTimeline';
import { MatchStats } from '@/components/MatchStats';
import { ArrowLeft, Calendar, MapPin, Trophy } from 'lucide-react';
import Link from 'next/link';
import { motion } from 'framer-motion';
import { useWebSocket } from '@/hooks/useWebSocket';

const API_BASE_URL = "http://localhost:8000/api/v1";
const WS_URL = "ws://localhost:8000/ws/live";

async function getMatchDetails(id: string): Promise<Match> {
    const res = await fetch(`${API_BASE_URL}/match/${id}/details`);
    if (!res.ok) throw new Error("Failed to fetch match details");
    return res.json();
}

export default function MatchDetails() {
    const params = useParams();
    const [match, setMatch] = useState<Match | null>(null);
    const [loading, setLoading] = useState(true);
    const lastMessage = useWebSocket(WS_URL);

    useEffect(() => {
        if (params.id) {
            getMatchDetails(params.id as string)
                .then(setMatch)
                .catch(console.error)
                .finally(() => setLoading(false));
        }
    }, [params.id]);

    useEffect(() => {
        if (lastMessage && lastMessage.type === 'match_update' && match && lastMessage.data.match_id === match.id) {
            setMatch(prev => prev ? { ...prev, home_score: lastMessage.data.home_score, away_score: lastMessage.data.away_score } : null);
        }
    }, [lastMessage, match]);

    if (loading) return <div className="p-8 text-center">Loading match details...</div>;
    if (!match) return <div className="p-8 text-center">Match not found</div>;

    return (
        <main className="min-h-screen p-4 md:p-8 bg-gray-50 dark:bg-gray-900">
            <div className="max-w-4xl mx-auto">
                <Link href="/" className="inline-flex items-center text-blue-600 hover:underline mb-6">
                    <ArrowLeft className="w-4 h-4 mr-2" /> Back to Matches
                </Link>

                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.5 }}
                >
                    <Card className="mb-8 overflow-hidden border-t-4 border-t-blue-600">
                        <CardHeader className="bg-white dark:bg-gray-800 pb-8">
                            <div className="flex flex-col md:flex-row justify-between items-center text-sm text-gray-500 mb-6">
                                <div className="flex items-center mb-2 md:mb-0">
                                    <Calendar className="w-4 h-4 mr-2" />
                                    {new Date(match.start_time).toLocaleString()}
                                </div>
                                <div className="flex items-center">
                                    <MapPin className="w-4 h-4 mr-2" />
                                    {match.home_team_stadium || 'Stadium Info'}
                                </div>
                            </div>

                            <div className="flex justify-between items-center w-full">
                                <div className="flex flex-col items-center flex-1">
                                    {match.home_team_logo ? (
                                        <img
                                            src={match.home_team_logo}
                                            alt={match.home_team_name || 'Home'}
                                            className="w-24 h-24 object-contain mb-4"
                                            onError={(e) => {
                                                (e.target as HTMLImageElement).style.display = 'none';
                                            }}
                                        />
                                    ) : (
                                        <div className="w-24 h-24 bg-gray-200 rounded-full mb-4 flex items-center justify-center text-2xl font-bold text-gray-400">
                                            H
                                        </div>
                                    )}
                                    <h2 className="text-xl md:text-2xl font-bold text-center">
                                        {match.home_team_name || `Team ${match.home_team_id}`}
                                    </h2>
                                </div>

                                <div className="flex flex-col items-center px-4 md:px-12">
                                    <div className="text-4xl md:text-6xl font-black text-gray-900 dark:text-white mb-2">
                                        {match.home_score ?? '-'} : {match.away_score ?? '-'}
                                    </div>
                                    <div className={`px-3 py-1 rounded-full text-sm font-bold ${match.status === 'LIVE' ? 'bg-red-100 text-red-600 animate-pulse' : 'bg-gray-100 text-gray-600'}`}>
                                        {match.status}
                                    </div>
                                </div>

                                <div className="flex flex-col items-center flex-1">
                                    {match.away_team_logo ? (
                                        <img
                                            src={match.away_team_logo}
                                            alt={match.away_team_name || 'Away'}
                                            className="w-24 h-24 object-contain mb-4"
                                            onError={(e) => {
                                                (e.target as HTMLImageElement).style.display = 'none';
                                            }}
                                        />
                                    ) : (
                                        <div className="w-24 h-24 bg-gray-200 rounded-full mb-4 flex items-center justify-center text-2xl font-bold text-gray-400">
                                            A
                                        </div>
                                    )}
                                    <h2 className="text-xl md:text-2xl font-bold text-center">
                                        {match.away_team_name || `Team ${match.away_team_id}`}
                                    </h2>
                                </div>
                            </div>
                        </CardHeader>
                    </Card>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
                        <Card>
                            <CardHeader>
                                <CardTitle className="flex items-center">
                                    <Trophy className="w-5 h-5 mr-2 text-yellow-500" />
                                    AI Prediction
                                </CardTitle>
                            </CardHeader>
                            <CardContent>
                                {match.prediction ? (
                                    <PredictionBadge
                                        homeProb={match.prediction.home_win_prob}
                                        drawProb={match.prediction.draw_prob}
                                        awayProb={match.prediction.away_win_prob}
                                    />
                                ) : (
                                    <div className="text-center text-gray-500 py-4">
                                        No prediction available for this match.
                                    </div>
                                )}
                            </CardContent>
                        </Card>

                        {/* Stats Section - Only show if we have stats logic (currently placeholder or hidden) */}
                        {/* Since free API doesn't have stats, we'll show a message or hide it. 
                            For now, keeping the component but it handles its own empty state. 
                            Let's wrap it to be cleaner. */}
                        <MatchStats matchId={match.id} />
                    </div>

                    <Card className="mb-6">
                        <CardContent className="p-6">
                            <MatchTimeline matchId={match.id} />
                        </CardContent>
                    </Card>

                    {(match.home_players && match.home_players.length > 0) && (
                        <Card>
                            <CardHeader>
                                <CardTitle>Team Squads</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                    <div>
                                        <h3 className="font-bold text-lg mb-3">{match.home_team_name}</h3>
                                        <div className="space-y-2 max-h-96 overflow-y-auto pr-2">
                                            {match.home_players.map((player, idx) => (
                                                <div key={idx} className="flex justify-between items-center p-2 bg-gray-50 dark:bg-gray-800 rounded">
                                                    <span className="font-medium">{player.name}</span>
                                                    <span className="text-sm text-gray-500">{player.position}</span>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                    <div>
                                        <h3 className="font-bold text-lg mb-3">{match.away_team_name}</h3>
                                        <div className="space-y-2 max-h-96 overflow-y-auto pr-2">
                                            {match.away_players?.map((player, idx) => (
                                                <div key={idx} className="flex justify-between items-center p-2 bg-gray-50 dark:bg-gray-800 rounded">
                                                    <span className="font-medium">{player.name}</span>
                                                    <span className="text-sm text-gray-500">{player.position}</span>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                    )}
                </motion.div>
            </div>
        </main>
    );
}
