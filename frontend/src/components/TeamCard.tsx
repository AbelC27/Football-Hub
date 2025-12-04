"use client";

import { Team } from '@/lib/api';
import { Building2, MapPin } from 'lucide-react';

interface TeamCardProps {
    team: Team;
}

export const TeamCard = ({ team }: TeamCardProps) => {
    return (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md hover:shadow-xl transition-all duration-300 overflow-hidden group cursor-pointer transform hover:-translate-y-1">
            <div className="p-6">
                {/* Team Logo and Name */}
                <div className="flex items-center gap-4 mb-4">
                    {team.logo_url ? (
                        <img
                            src={team.logo_url}
                            alt={team.name}
                            className="w-16 h-16 object-contain group-hover:scale-110 transition-transform duration-300"
                        />
                    ) : (
                        <div className="w-16 h-16 bg-gray-200 dark:bg-gray-700 rounded-full flex items-center justify-center">
                            <Building2 className="w-8 h-8 text-gray-400" />
                        </div>
                    )}
                    <div className="flex-1">
                        <h3 className="font-bold text-lg text-gray-900 dark:text-white group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">
                            {team.name}
                        </h3>
                        {team.league && (
                            <p className="text-sm text-gray-500 dark:text-gray-400 flex items-center gap-1">
                                {team.league.logo_url && (
                                    <img
                                        src={team.league.logo_url}
                                        alt={team.league.name}
                                        className="w-4 h-4 object-contain"
                                    />
                                )}
                                {team.league.name}
                            </p>
                        )}
                    </div>
                </div>

                {/* Stadium */}
                {team.stadium && (
                    <div className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300 mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
                        <MapPin className="w-4 h-4 text-blue-500" />
                        <span>{team.stadium}</span>
                    </div>
                )}
            </div>

            {/* Hover Effect Line */}
            <div className="h-1 bg-gradient-to-r from-blue-500 to-purple-500 transform scale-x-0 group-hover:scale-x-100 transition-transform duration-300 origin-left"></div>
        </div>
    );
};
