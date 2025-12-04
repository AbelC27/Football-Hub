'use client';

import React from 'react';
import { Match } from '../lib/api';
import { Card } from './ui/card';
import { Calendar, MapPin, Activity, TrendingUp, Zap } from 'lucide-react';
import Link from 'next/link';
import { motion } from 'framer-motion';

interface EnhancedMatchCardProps {
    match: Match;
}

const getStatusColor = (status: string) => {
    if (['LIVE', 'HT', 'ET', 'P'].includes(status)) return 'from-red-500 to-pink-500';
    if (status === 'FT') return 'from-green-500 to-emerald-500';
    if (status === 'NS') return 'from-blue-500 to-cyan-500';
    return 'from-gray-500 to-slate-500';
};

const getStatusText = (status: string) => {
    const statusMap: Record<string, string> = {
        'NS': 'Scheduled',
        'LIVE': 'LIVE NOW',
        'HT': 'Half Time',
        'FT': 'Full Time',
        'ET': 'Extra Time',
        'P': 'Penalties',
        'PST': 'Postponed',
        'CANC': 'Cancelled',
        'TBD': 'To Be Determined'
    };
    return statusMap[status] || status;
};

export const EnhancedMatchCard: React.FC<EnhancedMatchCardProps> = ({ match }) => {
    const isLive = ['LIVE', 'HT', 'ET', 'P'].includes(match.status);
    const isFinished = match.status === 'FT';
    const formattedDate = new Date(match.start_time).toLocaleString('en-US', {
        weekday: 'short',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });

    // Determine winner for finished matches
    const homeWin = isFinished && match.home_score !== null && match.away_score !== null && match.home_score > match.away_score;
    const awayWin = isFinished && match.home_score !== null && match.away_score !== null && match.away_score > match.home_score;

    return (
        <Link href={`/match/${match.id}`} className="block group">
            <motion.div
                whileHover={{ scale: 1.02, y: -4 }}
                transition={{ duration: 0.2 }}
            >
                <Card className="relative overflow-hidden transition-all duration-300 hover:shadow-2xl bg-gradient-to-br from-white to-gray-50 dark:from-gray-800 dark:to-gray-900 border-2 border-gray-200 dark:border-gray-700">
                    {/* Animated Background Pattern */}
                    <div className="absolute inset-0 opacity-5">
                        <div className="absolute top-0 right-0 w-64 h-64 bg-blue-500 rounded-full blur-3xl"></div>
                        <div className="absolute bottom-0 left-0 w-64 h-64 bg-purple-500 rounded-full blur-3xl"></div>
                    </div>

                    {/* Status Badge */}
                    <div className="relative">
                        <div className={`absolute -top-1 -right-1 ${isLive ? 'animate-pulse' : ''}`}>
                            <div className={`px-4 py-2 bg-gradient-to-r ${getStatusColor(match.status)} text-white text-xs font-black rounded-bl-2xl rounded-tr-xl shadow-lg flex items-center gap-2`}>
                                {isLive && <Zap className="w-4 h-4 animate-bounce" />}
                                {getStatusText(match.status)}
                            </div>
                        </div>
                    </div>

                    {/* Content */}
                    <div className="p-6 pt-12 relative z-10">
                        {/* Date & Time */}
                        <div className="flex items-center justify-center gap-2 text-sm text-gray-500 dark:text-gray-400 mb-6">
                            <Calendar className="w-4 h-4" />
                            <span className="font-medium">{formattedDate}</span>
                        </div>

                        {/* Teams & Score */}
                        <div className="space-y-4">
                            {/* Home Team */}
                            <div className={`flex items-center justify-between p-4 rounded-xl transition-all ${homeWin ? 'bg-green-50 dark:bg-green-900/20 ring-2 ring-green-500/50' :
                                    'bg-gray-50 dark:bg-gray-800/50'
                                }`}>
                                <div className="flex items-center gap-4 flex-1 min-w-0">
                                    <div className="relative w-14 h-14 flex-shrink-0">
                                        {match.home_team_logo ? (
                                            <img
                                                src={match.home_team_logo}
                                                alt={match.home_team_name || 'Home'}
                                                className="w-full h-full object-contain transition-transform group-hover:scale-110"
                                            />
                                        ) : (
                                            <div className="w-full h-full bg-gradient-to-br from-gray-200 to-gray-300 dark:from-gray-700 dark:to-gray-600 rounded-full flex items-center justify-center">
                                                <span className="text-2xl font-bold text-gray-400 dark:text-gray-500">
                                                    {match.home_team_name?.[0] || 'H'}
                                                </span>
                                            </div>
                                        )}
                                        {homeWin && (
                                            <div className="absolute -top-1 -right-1 w-6 h-6 bg-green-500 rounded-full flex items-center justify-center">
                                                <TrendingUp className="w-4 h-4 text-white" />
                                            </div>
                                        )}
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <h3 className="font-bold text-lg text-gray-900 dark:text-white line-clamp-2 group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">
                                            {match.home_team_name || `Team ${match.home_team_id}`}
                                        </h3>
                                    </div>
                                </div>
                                <div className={`text-4xl font-black ml-4 ${homeWin ? 'text-green-600' :
                                        isLive ? 'text-red-500 animate-pulse' :
                                            'text-gray-900 dark:text-white'
                                    }`}>
                                    {match.home_score ?? '-'}
                                </div>
                            </div>

                            {/* Away Team */}
                            <div className={`flex items-center justify-between p-4 rounded-xl transition-all ${awayWin ? 'bg-green-50 dark:bg-green-900/20 ring-2 ring-green-500/50' :
                                    'bg-gray-50 dark:bg-gray-800/50'
                                }`}>
                                <div className="flex items-center gap-4 flex-1 min-w-0">
                                    <div className="relative w-14 h-14 flex-shrink-0">
                                        {match.away_team_logo ? (
                                            <img
                                                src={match.away_team_logo}
                                                alt={match.away_team_name || 'Away'}
                                                className="w-full h-full object-contain transition-transform group-hover:scale-110"
                                            />
                                        ) : (
                                            <div className="w-full h-full bg-gradient-to-br from-gray-200 to-gray-300 dark:from-gray-700 dark:to-gray-600 rounded-full flex items-center justify-center">
                                                <span className="text-2xl font-bold text-gray-400 dark:text-gray-500">
                                                    {match.away_team_name?.[0] || 'A'}
                                                </span>
                                            </div>
                                        )}
                                        {awayWin && (
                                            <div className="absolute -top-1 -right-1 w-6 h-6 bg-green-500 rounded-full flex items-center justify-center">
                                                <TrendingUp className="w-4 h-4 text-white" />
                                            </div>
                                        )}
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <h3 className="font-bold text-lg text-gray-900 dark:text-white line-clamp-2 group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">
                                            {match.away_team_name || `Team ${match.away_team_id}`}
                                        </h3>
                                    </div>
                                </div>
                                <div className={`text-4xl font-black ml-4 ${awayWin ? 'text-green-600' :
                                        isLive ? 'text-red-500 animate-pulse' :
                                            'text-gray-900 dark:text-white'
                                    }`}>
                                    {match.away_score ?? '-'}
                                </div>
                            </div>
                        </div>

                        {/* Prediction Badge */}
                        {match.prediction && (
                            <div className="mt-6 pt-4 border-t-2 border-gray-200 dark:border-gray-700">
                                <div className="flex items-center justify-between gap-2">
                                    <div className="flex-1 text-center">
                                        <div className="text-xs text-gray-500 dark:text-gray-400 mb-1 font-semibold">HOME</div>
                                        <div className="relative h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                                            <div
                                                className="absolute inset-y-0 left-0 bg-gradient-to-r from-blue-500 to-blue-600 rounded-full transition-all"
                                                style={{ width: `${match.prediction.home_win_prob * 100}%` }}
                                            />
                                        </div>
                                        <div className="text-sm font-black text-blue-600 dark:text-blue-400 mt-1">
                                            {(match.prediction.home_win_prob * 100).toFixed(0)}%
                                        </div>
                                    </div>
                                    <div className="flex-1 text-center">
                                        <div className="text-xs text-gray-500 dark:text-gray-400 mb-1 font-semibold">DRAW</div>
                                        <div className="relative h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                                            <div
                                                className="absolute inset-y-0 left-0 bg-gradient-to-r from-gray-500 to-gray-600 rounded-full transition-all"
                                                style={{ width: `${match.prediction.draw_prob * 100}%` }}
                                            />
                                        </div>
                                        <div className="text-sm font-black text-gray-600 dark:text-gray-400 mt-1">
                                            {(match.prediction.draw_prob * 100).toFixed(0)}%
                                        </div>
                                    </div>
                                    <div className="flex-1 text-center">
                                        <div className="text-xs text-gray-500 dark:text-gray-400 mb-1 font-semibold">AWAY</div>
                                        <div className="relative h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                                            <div
                                                className="absolute inset-y-0 left-0 bg-gradient-to-r from-red-500 to-red-600 rounded-full transition-all"
                                                style={{ width: `${match.prediction.away_win_prob * 100}%` }}
                                            />
                                        </div>
                                        <div className="text-sm font-black text-red-600 dark:text-red-400 mt-1">
                                            {(match.prediction.away_win_prob * 100).toFixed(0)}%
                                        </div>
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Hover Effect Border */}
                    <div className="absolute inset-0 border-2 border-transparent group-hover:border-blue-500 dark:group-hover:border-blue-400 rounded-lg transition-colors pointer-events-none"></div>
                </Card>
            </motion.div>
        </Link>
    );
};
