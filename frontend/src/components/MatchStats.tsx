import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';

const API_BASE_URL = "http://localhost:8000/api/v1";

interface MatchStatistics {
    possession_home?: number;
    possession_away?: number;
    shots_on_home?: number;
    shots_on_away?: number;
    shots_off_home?: number;
    shots_off_away?: number;
    corners_home?: number;
    corners_away?: number;
    fouls_home?: number;
    fouls_away?: number;
}

const StatRow: React.FC<{ label: string; homeValue: number; awayValue: number }> = ({ label, homeValue, awayValue }) => {
    const total = homeValue + awayValue;
    const homePerc = total > 0 ? (homeValue / total) * 100 : 50;

    return (
        <div className="mb-4">
            <div className="flex justify-between text-sm mb-1">
                <span className="font-medium dark:text-gray-200">{homeValue}</span>
                <span className="text-gray-500 dark:text-gray-400">{label}</span>
                <span className="font-medium dark:text-gray-200">{awayValue}</span>
            </div>
            <div className="w-full h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden flex">
                <div
                    className="bg-blue-500 h-full transition-all duration-500"
                    style={{ width: `${homePerc}%` }}
                />
                <div
                    className="bg-red-500 h-full transition-all duration-500"
                    style={{ width: `${100 - homePerc}%` }}
                />
            </div>
        </div>
    );
};

export const MatchStats: React.FC<{ matchId: number }> = ({ matchId }) => {
    const [stats, setStats] = useState<MatchStatistics | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(false);

    useEffect(() => {
        fetch(`${API_BASE_URL}/match/${matchId}/statistics`)
            .then(res => {
                if (!res.ok) throw new Error('No stats');
                return res.json();
            })
            .then(setStats)
            .catch(() => setError(true))
            .finally(() => setLoading(false));
    }, [matchId]);

    if (loading) return <Card><CardContent className="p-6">Loading statistics...</CardContent></Card>;
    if (error || !stats) return (
        <Card>
            <CardHeader>
                <CardTitle>Match Statistics</CardTitle>
            </CardHeader>
            <CardContent className="p-6 text-center text-gray-500 dark:text-gray-400">
                <p>Match statistics are not available for this match.</p>
                <p className="text-xs mt-2 text-gray-400 dark:text-gray-500">(Requires Premium API Plan)</p>
            </CardContent>
        </Card>
    );

    return (
        <Card>
            <CardHeader>
                <CardTitle>Match Statistics</CardTitle>
            </CardHeader>
            <CardContent>
                {stats.possession_home !== undefined && stats.possession_away !== undefined && (
                    <StatRow label="Possession %" homeValue={stats.possession_home} awayValue={stats.possession_away} />
                )}

                {stats.shots_on_home !== undefined && stats.shots_on_away !== undefined && (
                    <StatRow label="Shots on Target" homeValue={stats.shots_on_home} awayValue={stats.shots_on_away} />
                )}

                {stats.shots_off_home !== undefined && stats.shots_off_away !== undefined && (
                    <StatRow label="Shots off Target" homeValue={stats.shots_off_home} awayValue={stats.shots_off_away} />
                )}

                {stats.corners_home !== undefined && stats.corners_away !== undefined && (
                    <StatRow label="Corners" homeValue={stats.corners_home} awayValue={stats.corners_away} />
                )}

                {stats.fouls_home !== undefined && stats.fouls_away !== undefined && (
                    <StatRow label="Fouls" homeValue={stats.fouls_home} awayValue={stats.fouls_away} />
                )}
            </CardContent>
        </Card>
    );
};
