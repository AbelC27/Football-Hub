'use client';

import React from 'react';
import { League } from '@/lib/api';
import { Trophy, ChevronRight } from 'lucide-react';

interface LeagueSelectorProps {
    leagues: League[];
    selectedLeague: number | null;
    onSelectLeague: (leagueId: number) => void;
}

export const LeagueSelector: React.FC<LeagueSelectorProps> = ({
    leagues,
    selectedLeague,
    onSelectLeague
}) => {
    return (
        <div className="mb-8">
            <h2 className="text-2xl font-bold mb-4 flex items-center gap-2 text-gray-900 dark:text-white">
                <Trophy className="w-6 h-6 text-yellow-500" />
                Select League
            </h2>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {leagues.map((league) => (
                    <button
                        key={league.id}
                        onClick={() => onSelectLeague(league.id)}
                        className={`group relative p-6 rounded-xl transition-all duration-300 ${selectedLeague === league.id
                                ? 'bg-gradient-to-br from-blue-600 to-purple-600 text-white shadow-2xl scale-105'
                                : 'bg-white dark:bg-gray-800 hover:shadow-xl hover:scale-102 border-2 border-gray-200 dark:border-gray-700'
                            }`}
                    >
                        <div className="flex items-center gap-4">
                            {/* League Logo */}
                            <div className={`w-16 h-16 rounded-full flex items-center justify-center ${selectedLeague === league.id
                                    ? 'bg-white/20'
                                    : 'bg-gradient-to-br from-gray-100 to-gray-200 dark:from-gray-700 dark:to-gray-600'
                                }`}>
                                {league.logo_url ? (
                                    <img
                                        src={league.logo_url}
                                        alt={league.name}
                                        className="w-12 h-12 object-contain"
                                        onError={(e) => {
                                            (e.target as HTMLImageElement).style.display = 'none';
                                        }}
                                    />
                                ) : (
                                    <Trophy className={`w-8 h-8 ${selectedLeague === league.id ? 'text-white' : 'text-gray-400'
                                        }`} />
                                )}
                            </div>

                            {/* League Info */}
                            <div className="flex-1 text-left">
                                <h3 className={`font-bold text-lg mb-1 ${selectedLeague === league.id
                                        ? 'text-white'
                                        : 'text-gray-900 dark:text-white'
                                    }`}>
                                    {league.name}
                                </h3>
                                <p className={`text-sm ${selectedLeague === league.id
                                        ? 'text-white/80'
                                        : 'text-gray-500 dark:text-gray-400'
                                    }`}>
                                    {league.country}
                                </p>
                            </div>

                            {/* Arrow Icon */}
                            <ChevronRight className={`w-6 h-6 transition-transform ${selectedLeague === league.id
                                    ? 'text-white translate-x-1'
                                    : 'text-gray-400 group-hover:translate-x-1'
                                }`} />
                        </div>

                        {/* Selection Indicator */}
                        {selectedLeague === league.id && (
                            <div className="absolute -top-1 -right-1 w-8 h-8 bg-green-500 rounded-full flex items-center justify-center shadow-lg">
                                <svg className="w-5 h-5 text-white" fill="none" strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" viewBox="0 0 24 24" stroke="currentColor">
                                    <path d="M5 13l4 4L19 7"></path>
                                </svg>
                            </div>
                        )}
                    </button>
                ))}
            </div>
        </div>
    );
};
