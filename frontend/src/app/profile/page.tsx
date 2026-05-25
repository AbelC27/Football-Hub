"use client";

import { useState, useEffect, useRef } from 'react';
import { useAuth } from '@/context/AuthContext';
import { useRouter } from 'next/navigation';

interface TeamResult {
    id: number;
    name: string;
    logo_url: string;
    league?: { id: number; name: string; country: string; logo_url: string } | null;
}

interface PlayerResult {
    id: number;
    name: string;
    position: string;
    team?: { id: number; name: string; logo_url: string } | null;
}

function useDebounce(value: string, delay: number) {
    const [debounced, setDebounced] = useState(value);
    useEffect(() => {
        const timer = setTimeout(() => setDebounced(value), delay);
        return () => clearTimeout(timer);
    }, [value, delay]);
    return debounced;
}

export default function ProfilePage() {
    const { user, isAuthenticated, loading: authLoading } = useAuth();
    const router = useRouter();

    // Team search state
    const [teamQuery, setTeamQuery] = useState('');
    const [teamResults, setTeamResults] = useState<TeamResult[]>([]);
    const [selectedTeam, setSelectedTeam] = useState<TeamResult | null>(null);
    const [showTeamDropdown, setShowTeamDropdown] = useState(false);
    const teamRef = useRef<HTMLDivElement>(null);

    // Player search state
    const [playerQuery, setPlayerQuery] = useState('');
    const [playerResults, setPlayerResults] = useState<PlayerResult[]>([]);
    const [selectedPlayer, setSelectedPlayer] = useState<PlayerResult | null>(null);
    const [showPlayerDropdown, setShowPlayerDropdown] = useState(false);
    const playerRef = useRef<HTMLDivElement>(null);

    const [saving, setSaving] = useState(false);
    const [message, setMessage] = useState('');

    const debouncedTeamQuery = useDebounce(teamQuery, 300);
    const debouncedPlayerQuery = useDebounce(playerQuery, 300);

    useEffect(() => {
        if (!authLoading && !isAuthenticated) {
            router.push('/login');
        }
    }, [authLoading, isAuthenticated, router]);

    // Close dropdowns on outside click
    useEffect(() => {
        function handleClick(e: MouseEvent) {
            if (teamRef.current && !teamRef.current.contains(e.target as Node)) {
                setShowTeamDropdown(false);
            }
            if (playerRef.current && !playerRef.current.contains(e.target as Node)) {
                setShowPlayerDropdown(false);
            }
        }
        document.addEventListener('mousedown', handleClick);
        return () => document.removeEventListener('mousedown', handleClick);
    }, []);

    // Search teams
    useEffect(() => {
        if (debouncedTeamQuery.length < 2) {
            setTeamResults([]);
            return;
        }
        fetch(`http://localhost:8000/api/v1/search/teams?q=${encodeURIComponent(debouncedTeamQuery)}`)
            .then(res => res.json())
            .then(data => setTeamResults(data))
            .catch(() => setTeamResults([]));
    }, [debouncedTeamQuery]);

    // Search players
    useEffect(() => {
        if (debouncedPlayerQuery.length < 2) {
            setPlayerResults([]);
            return;
        }
        fetch(`http://localhost:8000/api/v1/search/players?q=${encodeURIComponent(debouncedPlayerQuery)}`)
            .then(res => res.json())
            .then(data => setPlayerResults(data))
            .catch(() => setPlayerResults([]));
    }, [debouncedPlayerQuery]);

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
                    favorite_team_id: selectedTeam?.id || null,
                    favorite_player_id: selectedPlayer?.id || null
                })
            });

            if (response.ok) {
                setMessage('Favorites updated successfully!');
            } else {
                setMessage('Failed to update favorites');
            }
        } catch {
            setMessage('An error occurred');
        } finally {
            setSaving(false);
        }
    };

    if (authLoading) {
        return <div className="flex justify-center items-center min-h-screen bg-neutral-950 text-neutral-200">Loading...</div>;
    }

    if (!isAuthenticated) {
        return null;
    }

    return (
        <main className="min-h-screen bg-neutral-950 text-neutral-200 p-4 md:p-8">
            <div className="container mx-auto px-4 py-8 max-w-4xl">
                <h1 className="text-3xl font-bold mb-8 text-white">My Profile</h1>

                <div className="bg-gray-800 rounded-lg shadow-md p-6 mb-6">
                    <h2 className="text-xl font-semibold mb-4 text-white">Account Information</h2>
                    <div className="space-y-2 text-gray-300">
                        <p><span className="font-medium">Username:</span> {user?.username}</p>
                        <p><span className="font-medium">Email:</span> {user?.email}</p>
                    </div>
                </div>

                <div className="bg-gray-800 rounded-lg shadow-md p-6">
                    <h2 className="text-xl font-semibold mb-4 text-white">Favorites</h2>

                    {message && (
                        <div className={`mb-4 p-3 rounded ${message.includes('success') ? 'bg-green-900/50 text-green-300' : 'bg-red-900/50 text-red-300'}`}>
                            {message}
                        </div>
                    )}

                    <div className="space-y-6">
                        {/* Team Search */}
                        <div ref={teamRef} className="relative">
                            <label className="block text-sm font-medium text-gray-300 mb-2">
                                Favorite Team
                            </label>
                            {selectedTeam ? (
                                <div className="flex items-center gap-3 p-3 bg-gray-700 rounded-md">
                                    {selectedTeam.logo_url && (
                                        <img src={selectedTeam.logo_url} alt="" className="w-8 h-8 object-contain" />
                                    )}
                                    <div className="flex-1">
                                        <div className="font-medium text-white">{selectedTeam.name}</div>
                                        {selectedTeam.league && (
                                            <div className="text-xs text-gray-400">{selectedTeam.league.name}</div>
                                        )}
                                    </div>
                                    <button
                                        onClick={() => { setSelectedTeam(null); setTeamQuery(''); }}
                                        className="text-gray-400 hover:text-white text-sm"
                                    >
                                        ✕
                                    </button>
                                </div>
                            ) : (
                                <input
                                    type="text"
                                    value={teamQuery}
                                    onChange={(e) => { setTeamQuery(e.target.value); setShowTeamDropdown(true); }}
                                    onFocus={() => setShowTeamDropdown(true)}
                                    placeholder="Search for a team..."
                                    className="w-full px-3 py-2 border border-gray-600 rounded-md bg-gray-700 text-white placeholder-gray-400 focus:ring-blue-500 focus:border-blue-500"
                                />
                            )}
                            {showTeamDropdown && teamResults.length > 0 && !selectedTeam && (
                                <ul className="absolute z-10 mt-1 w-full bg-gray-700 border border-gray-600 rounded-md shadow-lg max-h-60 overflow-y-auto">
                                    {teamResults.map(team => (
                                        <li
                                            key={team.id}
                                            role="option"
                                            tabIndex={0}
                                            onKeyDown={(e) => { if (e.key === 'Enter') { setSelectedTeam(team); setTeamQuery(''); setShowTeamDropdown(false); } }}
                                            onClick={() => {
                                                setSelectedTeam(team);
                                                setTeamQuery('');
                                                setShowTeamDropdown(false);
                                            }}
                                            className="flex items-center gap-3 px-3 py-2 cursor-pointer hover:bg-gray-600"
                                        >
                                            {team.logo_url && (
                                                <img src={team.logo_url} alt="" className="w-6 h-6 object-contain" />
                                            )}
                                            <div>
                                                <div className="text-sm text-white">{team.name}</div>
                                                {team.league && (
                                                    <div className="text-xs text-gray-400">{team.league.name}</div>
                                                )}
                                            </div>
                                        </li>
                                    ))}
                                </ul>
                            )}
                        </div>

                        {/* Player Search */}
                        <div ref={playerRef} className="relative">
                            <label className="block text-sm font-medium text-gray-300 mb-2">
                                Favorite Player
                            </label>
                            {selectedPlayer ? (
                                <div className="flex items-center gap-3 p-3 bg-gray-700 rounded-md">
                                    <div className="flex-1">
                                        <div className="font-medium text-white">{selectedPlayer.name}</div>
                                        <div className="text-xs text-gray-400">
                                            {selectedPlayer.position}
                                            {selectedPlayer.team && ` · ${selectedPlayer.team.name}`}
                                        </div>
                                    </div>
                                    <button
                                        onClick={() => { setSelectedPlayer(null); setPlayerQuery(''); }}
                                        className="text-gray-400 hover:text-white text-sm"
                                    >
                                        ✕
                                    </button>
                                </div>
                            ) : (
                                <input
                                    type="text"
                                    value={playerQuery}
                                    onChange={(e) => { setPlayerQuery(e.target.value); setShowPlayerDropdown(true); }}
                                    onFocus={() => setShowPlayerDropdown(true)}
                                    placeholder="Search for a player..."
                                    className="w-full px-3 py-2 border border-gray-600 rounded-md bg-gray-700 text-white placeholder-gray-400 focus:ring-blue-500 focus:border-blue-500"
                                />
                            )}
                            {showPlayerDropdown && playerResults.length > 0 && !selectedPlayer && (
                                <ul className="absolute z-10 mt-1 w-full bg-gray-700 border border-gray-600 rounded-md shadow-lg max-h-60 overflow-y-auto">
                                    {playerResults.map(player => (
                                        <li
                                            key={player.id}
                                            role="option"
                                            tabIndex={0}
                                            onKeyDown={(e) => { if (e.key === 'Enter') { setSelectedPlayer(player); setPlayerQuery(''); setShowPlayerDropdown(false); } }}
                                            onClick={() => {
                                                setSelectedPlayer(player);
                                                setPlayerQuery('');
                                                setShowPlayerDropdown(false);
                                            }}
                                            className="flex items-center gap-3 px-3 py-2 cursor-pointer hover:bg-gray-600"
                                        >
                                            <div>
                                                <div className="text-sm text-white">{player.name}</div>
                                                <div className="text-xs text-gray-400">
                                                    {player.position}
                                                    {player.team && ` · ${player.team.name}`}
                                                </div>
                                            </div>
                                        </li>
                                    ))}
                                </ul>
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
        </main>
    );
}
