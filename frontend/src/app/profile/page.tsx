"use client";

import { useState, useEffect } from 'react';
import { useAuth } from '@/context/AuthContext';
import { useRouter } from 'next/navigation';

interface Team {
    id: number;
    name: string;
    logo_url: string;
}

interface Player {
    id: number;
    name: string;
    position: string;
    team_id: number;
}

export default function ProfilePage() {
    const { user, isAuthenticated, loading: authLoading } = useAuth();
    const router = useRouter();
    const [teams, setTeams] = useState<Team[]>([]);
    const [players, setPlayers] = useState<Player[]>([]);
    const [selectedTeam, setSelectedTeam] = useState<number | null>(null);
    const [selectedPlayer, setSelectedPlayer] = useState<number | null>(null);
    const [saving, setSaving] = useState(false);
    const [message, setMessage] = useState('');

    useEffect(() => {
        if (!authLoading && !isAuthenticated) {
            router.push('/login');
        }
    }, [authLoading, isAuthenticated, router]);

    useEffect(() => {
        if (user) {
            setSelectedTeam(user.favorite_team_id || null);
            setSelectedPlayer(user.favorite_player_id || null);
        }
    }, [user]);

    useEffect(() => {
        // Fetch teams
        fetch('http://localhost:8000/api/v1/teams')
            .then(res => res.json())
            .then(data => setTeams(data))
            .catch(err => console.error('Failed to fetch teams:', err));

        // Fetch players
        fetch('http://localhost:8000/api/v1/players')
            .then(res => res.json())
            .then(data => setPlayers(data))
            .catch(err => console.error('Failed to fetch players:', err));
    }, []);

    const handleSave = async () => {
        setSaving(true);
        setMessage('');

        try {
            const response = await fetch('http://localhost:8000/api/v1/user/favorites', {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${localStorage.getItem('token')}`
                },
                body: JSON.stringify({
                    favorite_team_id: selectedTeam,
                    favorite_player_id: selectedPlayer
                })
            });

            if (response.ok) {
                setMessage('Favorites updated successfully!');
            } else {
                setMessage('Failed to update favorites');
            }
        } catch (err) {
            setMessage('An error occurred');
        } finally {
            setSaving(false);
        }
    };

    if (authLoading) {
        return <div className="flex justify-center items-center min-h-screen">Loading...</div>;
    }

    if (!isAuthenticated) {
        return null;
    }

    // Filter players by selected team
    const filteredPlayers = selectedTeam
        ? players.filter(p => p.team_id === selectedTeam)
        : players;

    return (
        <div className="container mx-auto px-4 py-8 max-w-4xl">
            <h1 className="text-3xl font-bold mb-8 text-gray-900 dark:text-white">
                My Profile
            </h1>

            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 mb-6">
                <h2 className="text-xl font-semibold mb-4 text-gray-900 dark:text-white">
                    Account Information
                </h2>
                <div className="space-y-2 text-gray-700 dark:text-gray-300">
                    <p><span className="font-medium">Username:</span> {user?.username}</p>
                    <p><span className="font-medium">Email:</span> {user?.email}</p>
                </div>
            </div>

            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
                <h2 className="text-xl font-semibold mb-4 text-gray-900 dark:text-white">
                    Favorites
                </h2>

                {message && (
                    <div className={`mb-4 p-3 rounded ${message.includes('success') ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                        {message}
                    </div>
                )}

                <div className="space-y-6">
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                            Favorite Team
                        </label>
                        <select
                            value={selectedTeam || ''}
                            onChange={(e) => setSelectedTeam(e.target.value ? parseInt(e.target.value) : null)}
                            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-blue-500 focus:border-blue-500"
                        >
                            <option value="">Select a team</option>
                            {teams.map(team => (
                                <option key={team.id} value={team.id}>
                                    {team.name}
                                </option>
                            ))}
                        </select>
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                            Favorite Player
                        </label>
                        <select
                            value={selectedPlayer || ''}
                            onChange={(e) => setSelectedPlayer(e.target.value ? parseInt(e.target.value) : null)}
                            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-blue-500 focus:border-blue-500"
                            disabled={!selectedTeam}
                        >
                            <option value="">Select a player</option>
                            {filteredPlayers.map(player => (
                                <option key={player.id} value={player.id}>
                                    {player.name} ({player.position})
                                </option>
                            ))}
                        </select>
                        {!selectedTeam && (
                            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                                Select a team first to choose a player
                            </p>
                        )}
                    </div>

                    <button
                        onClick={handleSave}
                        disabled={saving}
                        className="w-full px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded hover:bg-blue-700 transition disabled:opacity-50"
                    >
                        {saving ? 'Saving...' : 'Save Favorites'}
                    </button>
                </div>
            </div>
        </div>
    );
}
