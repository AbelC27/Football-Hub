import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';

const API_BASE_URL = "http://localhost:8000/api/v1";

interface MatchEvent {
    id: number;
    match_id: number;
    minute: number;
    event_type: string;
    team_id: number;
    player_name: string;
    detail?: string;
}

export const MatchTimeline: React.FC<{ matchId: number }> = ({ matchId }) => {
    const [events, setEvents] = useState<MatchEvent[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetch(`${API_BASE_URL}/match/${matchId}/events`)
            .then(res => res.json())
            .then(setEvents)
            .catch(console.error)
            .finally(() => setLoading(false));
    }, [matchId]);

    const getEventIcon = (eventType: string) => {
        switch (eventType.toLowerCase()) {
            case 'goal':
                return '⚽';
            case 'card':
                return '🟨';
            case 'subst':
                return '🔄';
            default:
                return '📌';
        }
    };

    const getEventColor = (eventType: string, detail?: string) => {
        if (eventType.toLowerCase() === 'goal') return 'bg-green-100 text-green-800 border-green-300 dark:bg-green-900/30 dark:text-green-300 dark:border-green-800';
        if (eventType.toLowerCase() === 'card') {
            if (detail?.toLowerCase().includes('red')) return 'bg-red-100 text-red-800 border-red-300 dark:bg-red-900/30 dark:text-red-300 dark:border-red-800';
            return 'bg-yellow-100 text-yellow-800 border-yellow-300 dark:bg-yellow-900/30 dark:text-yellow-300 dark:border-yellow-800';
        }
        return 'bg-blue-100 text-blue-800 border-blue-300 dark:bg-blue-900/30 dark:text-blue-300 dark:border-blue-800';
    };

    if (loading) return <div className="text-center py-4">Loading events...</div>;
    if (events.length === 0) return <div className="text-center py-4 text-gray-500 dark:text-gray-400">No events recorded</div>;

    return (
        <div className="space-y-3">
            <h3 className="text-lg font-bold mb-4">Match Timeline</h3>
            {events.map((event, idx) => (
                <motion.div
                    key={event.id}
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: idx * 0.1 }}
                    className={`flex items-center gap-3 p-3 rounded-lg border-2 ${getEventColor(event.event_type, event.detail)}`}
                >
                    <div className="text-2xl">{getEventIcon(event.event_type)}</div>
                    <div className="flex-1">
                        <div className="font-bold text-sm">{event.minute}'</div>
                        <div className="text-sm">{event.player_name}</div>
                        {event.detail && <div className="text-xs opacity-75">{event.detail}</div>}
                    </div>
                    <div className="text-xs font-semibold uppercase px-2 py-1 bg-white/50 dark:bg-black/50 rounded">
                        {event.event_type}
                    </div>
                </motion.div>
            ))}
        </div>
    );
};
