'use client';

import React, { useState, useEffect } from 'react';
import { Match } from '../lib/api';
import { PredictionBadge } from './PredictionBadge';
import { Card, CardContent } from './ui/card';
import { Calendar } from 'lucide-react';
import Link from 'next/link';

interface MatchCardProps {
    match: Match;
}

export const MatchCard: React.FC<MatchCardProps> = ({ match }) => {
    const [formattedDate, setFormattedDate] = useState<string>('');

    useEffect(() => {
        // Only format date on client to avoid hydration mismatch
        setFormattedDate(new Date(match.start_time).toLocaleString());
    }, [match.start_time]);

    return (
        <Link href={`/match/${match.id}`} className="block">
            <Card className="hover:shadow-lg transition-shadow cursor-pointer dark:bg-gray-800 dark:border-gray-700">
                <CardContent className="p-4">
                    <div className="flex justify-between items-center mb-3">
                        <div className="text-xs text-gray-500 dark:text-gray-400 flex items-center gap-2">
                            <Calendar className="w-3 h-3" />
                            {formattedDate || 'Loading...'}
                        </div>
                        {match.status === 'LIVE' && (
                            <div className="flex items-center gap-2">
                                <div className="w-2 h-2 bg-red-600 rounded-full animate-pulse"></div>
                                <span className="text-xs font-bold text-red-600">LIVE</span>
                            </div>
                        )}
                    </div>

                    <div className="flex justify-between items-center">
                        {/* Home Team */}
                        <div className="flex flex-col items-center flex-1">
                            {match.home_team_logo ? (
                                <img
                                    src={match.home_team_logo}
                                    alt={match.home_team_name || 'Home'}
                                    className="w-12 h-12 object-contain mb-2"
                                    onError={(e) => {
                                        (e.target as HTMLImageElement).style.display = 'none';
                                    }}
                                />
                            ) : (
                                <div className="w-12 h-12 bg-gray-200 dark:bg-gray-700 rounded-full mb-2 flex items-center justify-center">
                                    <span className="text-gray-400 dark:text-gray-500 font-bold">H</span>
                                </div>
                            )}
                            <span className="text-sm font-semibold text-center line-clamp-2 dark:text-gray-100">
                                {match.home_team_name || `Team ${match.home_team_id}`}
                            </span>
                        </div>

                        {/* Score */}
                        <div className="flex flex-col items-center px-4">
                            <div className="text-3xl font-black dark:text-white">
                                {match.home_score ?? '-'} : {match.away_score ?? '-'}
                            </div>
                            <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                                {match.status}
                            </div>
                        </div>

                        {/* Away Team */}
                        <div className="flex flex-col items-center flex-1">
                            {match.away_team_logo ? (
                                <img
                                    src={match.away_team_logo}
                                    alt={match.away_team_name || 'Away'}
                                    className="w-12 h-12 object-contain mb-2"
                                    onError={(e) => {
                                        (e.target as HTMLImageElement).style.display = 'none';
                                    }}
                                />
                            ) : (
                                <div className="w-12 h-12 bg-gray-200 dark:bg-gray-700 rounded-full mb-2 flex items-center justify-center">
                                    <span className="text-gray-400 dark:text-gray-500 font-bold">A</span>
                                </div>
                            )}
                            <span className="text-sm font-semibold text-center line-clamp-2 dark:text-gray-100">
                                {match.away_team_name || `Team ${match.away_team_id}`}
                            </span>
                        </div>
                    </div>

                    {match.prediction && (
                        <div className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-700">
                            <PredictionBadge
                                homeProb={match.prediction.home_win_prob}
                                drawProb={match.prediction.draw_prob}
                                awayProb={match.prediction.away_win_prob}
                            />
                        </div>
                    )}
                </CardContent>
            </Card>
        </Link>
    );
};
