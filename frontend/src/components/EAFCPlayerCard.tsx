'use client';

import React from 'react';
import { PlayerDetailed } from '@/lib/api';
import { Trophy, MapPin, User } from 'lucide-react';

interface EAFCPlayerCardProps {
    player: PlayerDetailed;
}

const getPositionColor = (position: string) => {
    if (!position) return { bg: 'from-gray-600 to-gray-700', text: 'text-gray-300' };

    if (position.includes('Goalkeeper') || position.includes('GK'))
        return { bg: 'from-yellow-500 via-yellow-600 to-orange-600', text: 'text-yellow-900' };
    if (position.includes('Defender') || position.includes('Defence') || position.includes('Back'))
        return { bg: 'from-blue-500 via-blue-600 to-cyan-600', text: 'text-blue-900' };
    if (position.includes('Midfielder') || position.includes('Midfield'))
        return { bg: 'from-green-500 via-green-600 to-emerald-600', text: 'text-green-900' };
    if (position.includes('Attacker') || position.includes('Forward') || position.includes('Striker') || position.includes('Winger'))
        return { bg: 'from-red-500 via-red-600 to-pink-600', text: 'text-red-900' };

    return { bg: 'from-gray-600 to-gray-700', text: 'text-gray-300' };
};

const getPositionAbbr = (position: string) => {
    if (!position) return 'N/A';
    if (position.includes('Goalkeeper') || position.includes('GK')) return 'GK';
    if (position.includes('Centre-Back') || position.includes('Central Defender')) return 'CB';
    if (position.includes('Left-Back') || position.includes('Left Defender')) return 'LB';
    if (position.includes('Right-Back') || position.includes('Right Defender')) return 'RB';
    if (position.includes('Defensive Midfield')) return 'CDM';
    if (position.includes('Central Midfield')) return 'CM';
    if (position.includes('Attacking Midfield')) return 'CAM';
    if (position.includes('Left Midfield') || position.includes('Left Winger')) return 'LM';
    if (position.includes('Right Midfield') || position.includes('Right Winger')) return 'RM';
    if (position.includes('Striker') || position.includes('Centre-Forward')) return 'ST';
    if (position.includes('Left Wing')) return 'LW';
    if (position.includes('Right Wing')) return 'RW';
    return position.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 3);
};

// Generate a pseudo-rating based on position (for demo purposes)
const generateRating = (position: string) => {
    const base = 70;
    const random = Math.floor(Math.random() * 15);
    return base + random;
};

export const EAFCPlayerCard: React.FC<EAFCPlayerCardProps> = ({ player }) => {
    const colors = getPositionColor(player.position);
    const positionAbbr = getPositionAbbr(player.position);
    const rating = generateRating(player.position);

    return (
        <div className="relative w-full max-w-sm mx-auto perspective-1000">
            {/* EA FC Card */}
            <div className="relative">
                {/* Card Background with Gradient */}
                <div className={`relative bg-gradient-to-br ${colors.bg} rounded-3xl p-1 shadow-2xl transform transition-transform hover:scale-105 hover:rotate-1`}>
                    {/* Inner Card */}
                    <div className="bg-black/20 backdrop-blur-sm rounded-3xl p-6 relative overflow-hidden">
                        {/* Decorative Pattern */}
                        <div className="absolute inset-0 opacity-10">
                            <div className="absolute top-0 right-0 w-64 h-64 bg-white rounded-full -translate-y-1/2 translate-x-1/2"></div>
                            <div className="absolute bottom-0 left-0 w-48 h-48 bg-white rounded-full translate-y-1/2 -translate-x-1/2"></div>
                        </div>

                        <div className="relative z-10">
                            {/* Top Section - Rating & Position */}
                            <div className="flex items-start justify-between mb-6">
                                <div className="text-center">
                                    <div className="text-6xl font-black text-white drop-shadow-lg mb-1">
                                        {rating}
                                    </div>
                                    <div className="text-xl font-bold text-white/90 drop-shadow">
                                        {positionAbbr}
                                    </div>
                                </div>

                                {/* Team Logo */}
                                <div className="w-16 h-16 bg-white/90 rounded-full p-2 shadow-xl">
                                    {player.team?.logo_url ? (
                                        <img
                                            src={player.team.logo_url}
                                            alt={player.team.name}
                                            className="w-full h-full object-contain"
                                        />
                                    ) : (
                                        <Trophy className="w-full h-full text-gray-400" />
                                    )}
                                </div>
                            </div>

                            {/* Player Photo Placeholder */}
                            <div className="flex justify-center mb-6">
                                <div className="w-32 h-32 bg-white/10 backdrop-blur rounded-full flex items-center justify-center border-4 border-white/20">
                                    <User className="w-16 h-16 text-white/50" />
                                </div>
                            </div>

                            {/* Player Name */}
                            <div className="text-center mb-6">
                                <h2 className="text-3xl font-black text-white drop-shadow-lg uppercase tracking-wide">
                                    {player.name}
                                </h2>
                            </div>

                            {/* Stats Grid */}
                            <div className="grid grid-cols-3 gap-4 mb-4">
                                {/* Nationality */}
                                <div className="text-center">
                                    <div className="text-xs text-white/70 uppercase font-semibold mb-1">Nation</div>
                                    <div className="text-sm font-bold text-white">{player.nationality || 'N/A'}</div>
                                </div>

                                {/* Height */}
                                <div className="text-center">
                                    <div className="text-xs text-white/70 uppercase font-semibold mb-1">Height</div>
                                    <div className="text-sm font-bold text-white">{player.height || 'N/A'}</div>
                                </div>

                                {/* League */}
                                <div className="text-center">
                                    <div className="text-xs text-white/70 uppercase font-semibold mb-1">League</div>
                                    <div className="text-xs font-bold text-white line-clamp-1">
                                        {player.league?.name?.split(' ').pop() || 'N/A'}
                                    </div>
                                </div>
                            </div>

                            {/* Team Name */}
                            <div className="text-center pt-4 border-t border-white/20">
                                <div className="flex items-center justify-center gap-2 text-white/90">
                                    <MapPin className="w-4 h-4" />
                                    <span className="text-sm font-semibold">{player.team?.name || 'Free Agent'}</span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Glow Effect */}
                <div className={`absolute inset-0 bg-gradient-to-br ${colors.bg} rounded-3xl blur-xl opacity-50 -z-10`}></div>
            </div>
        </div>
    );
};
