'use client';

import { motion } from 'framer-motion';
import { Shield, Users2, Trophy, Activity } from 'lucide-react';

interface EnhancedPlayerCardProps {
    player: any; // Using any for flexibility with the enhanced data structure
}

const getPositionColor = (position: string) => {
    if (!position) return 'from-gray-500 to-slate-500';
    if (position.includes('Goalkeeper') || position.includes('GK')) return 'from-yellow-500 to-orange-500';
    if (position.includes('Defender') || position.includes('Defence') || position.includes('Back')) return 'from-blue-500 to-cyan-500';
    if (position.includes('Midfielder') || position.includes('Midfield')) return 'from-green-500 to-emerald-500';
    if (position.includes('Attacker') || position.includes('Forward') || position.includes('Striker') || position.includes('Winger')) return 'from-red-500 to-pink-500';
    return 'from-gray-500 to-slate-500';
};

const getPositionAbbreviation = (position: string) => {
    if (!position) return 'N/A';

    const pos = position.toUpperCase();

    // Goalkeeper
    if (pos.includes('GOALKEEPER') || pos === 'GK') return 'GK';

    // Defenders
    if (pos.includes('LEFT-BACK') || pos.includes('LEFT BACK')) return 'LB';
    if (pos.includes('RIGHT-BACK') || pos.includes('RIGHT BACK')) return 'RB';
    if (pos.includes('CENTRE-BACK') || pos.includes('CENTER BACK') || pos.includes('CENTRAL DEFENDER')) return 'CB';
    if (pos.includes('DEFENDER') || pos.includes('DEFENCE')) return 'DEF';

    // Midfielders
    if (pos.includes('DEFENSIVE MIDFIELD') || pos === 'CDM') return 'CDM';
    if (pos.includes('CENTRAL MIDFIELD') || pos === 'CM') return 'CM';
    if (pos.includes('ATTACKING MIDFIELD') || pos === 'CAM') return 'CAM';
    if (pos.includes('LEFT MIDFIELD') || pos === 'LM') return 'LM';
    if (pos.includes('RIGHT MIDFIELD') || pos === 'RM') return 'RM';
    if (pos.includes('MIDFIELD')) return 'MID';

    // Attackers
    if (pos.includes('LEFT WINGER') || pos === 'LW') return 'LW';
    if (pos.includes('RIGHT WINGER') || pos === 'RW') return 'RW';
    if (pos.includes('STRIKER') || pos === 'ST') return 'ST';
    if (pos.includes('CENTRE-FORWARD') || pos.includes('CENTER FORWARD') || pos === 'CF') return 'CF';
    if (pos.includes('FORWARD') || pos.includes('ATTACKER')) return 'FW';

    // Fallback: take first 3 characters
    return position.substring(0, 3).toUpperCase();
};

const getRatingColor = (rating: number) => {
    if (rating >= 85) return 'text-yellow-400'; // Gold
    if (rating >= 75) return 'text-gray-300';   // Silver
    return 'text-orange-400';                   // Bronze
};

export const EnhancedPlayerCard: React.FC<EnhancedPlayerCardProps> = ({ player }) => {
    const positionColor = getPositionColor(player.position);
    // Use enhanced stats if available, otherwise fallback or random
    const rating = player.stats?.rating ? Math.round(parseFloat(player.stats.rating) * 10) : (player.id % 15 + 70);
    const goals = player.stats?.goals || 0;
    const assists = player.stats?.assists || 0;

    return (
        <div className="relative w-full max-w-sm mx-auto perspective-1000">
            <motion.div
                initial={{ rotateY: 180, opacity: 0 }}
                animate={{ rotateY: 0, opacity: 1 }}
                transition={{ duration: 0.8, type: "spring" }}
                className={`relative overflow-hidden rounded-[2rem] bg-gradient-to-br ${positionColor} p-1 shadow-2xl`}
            >
                {/* Card Inner */}
                <div className="relative h-full bg-gradient-to-b from-gray-900 via-gray-800 to-gray-900 rounded-[1.8rem] p-6 text-white overflow-hidden">

                    {/* Background Pattern */}
                    <div className="absolute inset-0 opacity-10 bg-[url('/patterns/circuit.svg')] bg-repeat" />
                    <div className="absolute top-0 right-0 w-64 h-64 bg-white/5 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2" />

                    {/* Header: Rating & Position */}
                    <div className="flex justify-between items-start mb-4 relative z-10">
                        <div className="flex flex-col items-center">
                            <span className={`text-5xl font-black ${getRatingColor(rating)} drop-shadow-lg`}>
                                {rating}
                            </span>
                            <span className="text-xl font-bold uppercase tracking-wider opacity-90">
                                {getPositionAbbreviation(player.position || '')}
                            </span>
                        </div>

                        {/* Team Logo */}
                        {player.team?.logo_url && (
                            <div className="w-12 h-12 bg-white/10 rounded-full p-2 backdrop-blur-sm">
                                <img
                                    src={player.team.logo_url}
                                    alt={player.team.name}
                                    className="w-full h-full object-contain"
                                />
                            </div>
                        )}
                    </div>

                    {/* Player Image */}
                    <div className="relative h-48 mb-4 flex items-center justify-center z-10">
                        {player.photo_url ? (
                            <img
                                src={player.photo_url}
                                alt={player.name}
                                className="h-full object-contain drop-shadow-2xl"
                            />
                        ) : (
                            <div className="w-32 h-32 bg-gradient-to-br from-gray-700 to-gray-600 rounded-full flex items-center justify-center border-4 border-white/10">
                                <span className="text-4xl font-bold text-gray-400">
                                    {player.name?.[0]}
                                </span>
                            </div>
                        )}
                    </div>

                    {/* Player Name */}
                    <div className="text-center mb-6 relative z-10">
                        <h2 className="text-2xl font-black uppercase tracking-tight truncate px-2">
                            {player.name}
                        </h2>
                        <div className="flex items-center justify-center gap-2 text-sm text-gray-400 mt-1">
                            {player.nationality && (
                                <span className="uppercase font-semibold tracking-wider">
                                    {player.nationality}
                                </span>
                            )}
                            {player.height && (
                                <>
                                    <span>•</span>
                                    <span>{player.height}</span>
                                </>
                            )}
                        </div>
                    </div>

                    {/* Stats Grid */}
                    <div className="grid grid-cols-2 gap-4 relative z-10 border-t border-white/10 pt-4">
                        <div className="bg-white/5 rounded-lg p-2 text-center">
                            <div className="text-xs text-gray-400 uppercase font-bold mb-1">Goals</div>
                            <div className="text-2xl font-black text-white">{player.stats?.goals || 0}</div>
                        </div>
                        <div className="bg-white/5 rounded-lg p-2 text-center">
                            <div className="text-xs text-gray-400 uppercase font-bold mb-1">Assists</div>
                            <div className="text-2xl font-black text-white">{player.stats?.assists || 0}</div>
                        </div>
                        <div className="bg-white/5 rounded-lg p-2 text-center">
                            <div className="text-xs text-gray-400 uppercase font-bold mb-1">Minutes</div>
                            <div className="text-xl font-bold text-white">{player.stats?.minutes || 0}</div>
                        </div>
                        <div className="bg-white/5 rounded-lg p-2 text-center">
                            <div className="text-xs text-gray-400 uppercase font-bold mb-1">Rating</div>
                            <div className={`text-xl font-bold ${getRatingColor(rating)}`}>{player.stats?.rating || '-'}</div>
                        </div>
                    </div>

                    {/* Real Stats Badge */}
                    {(goals > 0 || assists > 0) && (
                        <div className="mt-4 flex justify-center gap-4 relative z-10">
                            <div className="bg-green-500/20 px-3 py-1 rounded-full flex items-center gap-1">
                                <Activity className="w-3 h-3 text-green-400" />
                                <span className="text-xs font-bold text-green-400">{goals} Goals</span>
                            </div>
                            <div className="bg-blue-500/20 px-3 py-1 rounded-full flex items-center gap-1">
                                <Users2 className="w-3 h-3 text-blue-400" />
                                <span className="text-xs font-bold text-blue-400">{assists} Assists</span>
                            </div>
                        </div>
                    )}
                </div>
            </motion.div>
        </div>
    );
};
