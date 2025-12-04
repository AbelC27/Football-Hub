"use client";

import { Player } from '@/lib/api';
import { User, Activity, Flag } from 'lucide-react';

interface PlayerCardProps {
    player: Player;
}

export const PlayerCard = ({ player }: PlayerCardProps) => {
    return (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md hover:shadow-xl transition-all duration-300 overflow-hidden group cursor-pointer transform hover:-translate-y-1">
            <div className="p-6">
                {/* Player Icon and Name */}
                <div className="flex items-center gap-4 mb-4">
                    <div className="w-16 h-16 bg-gradient-to-br from-blue-500 to-purple-600 rounded-full flex items-center justify-center">
                        <User className="w-8 h-8 text-white" />
                    </div>
                    <div className="flex-1">
                        <h3 className="font-bold text-lg text-gray-900 dark:text-white group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">
                            {player.name}
                        </h3>
                        {player.team && (
                            <div className="flex items-center gap-2 mt-1">
                                {player.team.logo_url && (
                                    <img
                                        src={player.team.logo_url}
                                        alt={player.team.name}
                                        className="w-4 h-4 object-contain"
                                    />
                                )}
                                <p className="text-sm text-gray-500 dark:text-gray-400">
                                    {player.team.name}
                                </p>
                            </div>
                        )}
                    </div>
                </div>

                {/* Player Details */}
                <div className="space-y-2 pt-3 border-t border-gray-200 dark:border-gray-700">
                    {/* Position */}
                    {player.position && (
                        <div className="flex items-center gap-2 text-sm">
                            <Activity className="w-4 h-4 text-blue-500" />
                            <span className="text-gray-600 dark:text-gray-300">
                                <span className="font-medium">Position:</span> {player.position}
                            </span>
                        </div>
                    )}

                    {/* Nationality and Height */}
                    <div className="flex items-center gap-4 text-sm text-gray-600 dark:text-gray-300">
                        {player.nationality && (
                            <div className="flex items-center gap-2">
                                <Flag className="w-4 h-4 text-green-500" />
                                <span>{player.nationality}</span>
                            </div>
                        )}
                        {player.height && (
                            <span className="text-gray-500 dark:text-gray-400">
                                {player.height}
                            </span>
                        )}
                    </div>
                </div>
            </div>

            {/* Hover Effect Line */}
            <div className="h-1 bg-gradient-to-r from-green-500 to-blue-500 transform scale-x-0 group-hover:scale-x-100 transition-transform duration-300 origin-left"></div>
        </div>
    );
};
