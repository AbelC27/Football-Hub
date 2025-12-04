"use client";

import { useState, useEffect } from 'react';
import { useAuth } from '@/context/AuthContext';
import { useRouter } from 'next/navigation';
import Image from 'next/image';

interface Team {
    id: number;
    name: string;
    logo_url: string;
}

interface LeaderboardEntry {
    username: string;
    points: number;
    teams: string[];
}

export default function FantasyPage() {
    const { isAuthenticated, loading: authLoading, token } = useAuth();
    const router = useRouter();
    const [teams, setTeams] = useState<Team[]>([]);
    const [selectedTeams, setSelectedTeams] = useState<number[]>([]);
    const [myTeams, setMyTeams] = useState<Team[]>([]);
    const [myPoints, setMyPoints] = useState(0);
    const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[]>([]);
    const [saving, setSaving] = useState(false);
    const [message, setMessage] = useState('');
    const [activeTab, setActiveTab] = useState<'select' | 'leaderboard'>('select');

    useEffect(() => {
        if (!authLoading && !isAuthenticated) {
            router.push('/login');
        }
    }, [authLoading, isAuthenticated, router]);

    useEffect(() => {
        if (isAuthenticated && token) {
            // Fetch all teams
            fetch('http://localhost:8000/api/v1/teams')
                .then(res => res.json())
                .then(data => setTeams(data))
                .catch(err => console.error('Failed to fetch teams:', err));

            // Fetch my selected teams
            fetch('http://localhost:8000/api/v1/fantasy/my-teams', {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            })
                .then(res => res.json())
                .then(data => {
                    setMyTeams(data);
                    setSelectedTeams(data.map((t: Team) => t.id));
                })
                .catch(err => console.error('Failed to fetch my teams:', err));

            // Fetch my points
            fetch('http://localhost:8000/api/v1/fantasy/my-points', {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            })
                .then(res => res.json())
                .then(data => setMyPoints(data.points))
                .catch(err => console.error('Failed to fetch points:', err));

            // Fetch leaderboard
            fetch('http://localhost:8000/api/v1/fantasy/leaderboard')
                .then(res => res.json())
                .then(data => setLeaderboard(data))
                .catch(err => console.error('Failed to fetch leaderboard:', err));
        }
    }, [isAuthenticated, token]);

    const handleTeamToggle = (teamId: number) => {
        if (selectedTeams.includes(teamId)) {
            setSelectedTeams(selectedTeams.filter(id => id !== teamId));
        } else {
            if (selectedTeams.length < 5) {
                setSelectedTeams([...selectedTeams, teamId]);
            } else {
                setMessage('You can only select 5 teams');
                setTimeout(() => setMessage(''), 3000);
            }
        }
    };

    const handleSaveTeams = async () => {
        if (selectedTeams.length !== 5) {
            setMessage('You must select exactly 5 teams');
            return;
        }

        setSaving(true);
        setMessage('');

        try {
            const response = await fetch('http://localhost:8000/api/v1/fantasy/select-teams', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({ team_ids: selectedTeams })
            });

            if (response.ok) {
                setMessage('Teams saved successfully!');
                // Refresh data
                window.location.reload();
            } else {
                setMessage('Failed to save teams');
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

    return (
        <div className="container mx-auto px-4 py-8 max-w-7xl">
            <div className="mb-8">
                <h1 className="text-4xl font-bold text-gray-900 dark:text-white mb-2">
                    ⚽ Fantasy League
                </h1>
                <p className="text-gray-600 dark:text-gray-400">
                    Pick 5 teams and compete for the top spot!
                </p>
            </div>

            {/* My Points Card */}
            <div className="bg-gradient-to-r from-blue-600 to-indigo-600 rounded-lg shadow-lg p-6 mb-8 text-white">
                <h2 className="text-2xl font-bold mb-2">Your Points</h2>
                <p className="text-5xl font-bold">{myPoints}</p>
                <p className="text-sm mt-2 opacity-90">Win = 3 pts | Draw = 1 pt | Loss = 0 pts</p>
            </div>

            {/* Tabs */}
            <div className="flex gap-4 mb-6">
                <button
                    onClick={() => setActiveTab('select')}
                    className={`px-6 py-3 rounded-lg font-medium transition ${activeTab === 'select'
                            ? 'bg-blue-600 text-white'
                            : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300'
                        }`}
                >
                    Select Teams
                </button>
                <button
                    onClick={() => setActiveTab('leaderboard')}
                    className={`px-6 py-3 rounded-lg font-medium transition ${activeTab === 'leaderboard'
                            ? 'bg-blue-600 text-white'
                            : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300'
                        }`}
                >
                    Leaderboard
                </button>
            </div>

            {message && (
                <div className={`mb-4 p-3 rounded ${message.includes('success') ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                    {message}
                </div>
            )}

            {activeTab === 'select' ? (
                <div>
                    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 mb-6">
                        <h2 className="text-xl font-semibold mb-4 text-gray-900 dark:text-white">
                            Your Selected Teams ({selectedTeams.length}/5)
                        </h2>
                        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-4">
                            {selectedTeams.map((teamId, index) => {
                                const team = teams.find(t => t.id === teamId);
                                return team ? (
                                    <div key={teamId} className="flex flex-col items-center p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
                                        <Image src={team.logo_url} alt={team.name} width={48} height={48} className="mb-2" />
                                        <span className="text-xs text-center font-medium">{team.name}</span>
                                    </div>
                                ) : (
                                    <div key={index} className="flex items-center justify-center p-3 bg-gray-100 dark:bg-gray-700 rounded-lg border-2 border-dashed border-gray-300 dark:border-gray-600">
                                        <span className="text-gray-400 text-sm">Empty Slot</span>
                                    </div>
                                );
                            })}
                            {Array.from({ length: 5 - selectedTeams.length }).map((_, index) => (
                                <div key={`empty-${index}`} className="flex items-center justify-center p-3 bg-gray-100 dark:bg-gray-700 rounded-lg border-2 border-dashed border-gray-300 dark:border-gray-600">
                                    <span className="text-gray-400 text-sm">Empty Slot</span>
                                </div>
                            ))}
                        </div>
                        <button
                            onClick={handleSaveTeams}
                            disabled={saving || selectedTeams.length !== 5}
                            className="w-full px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded hover:bg-blue-700 transition disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            {saving ? 'Saving...' : 'Save My Teams'}
                        </button>
                    </div>

                    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
                        <h2 className="text-xl font-semibold mb-4 text-gray-900 dark:text-white">
                            Available Teams
                        </h2>
                        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-4">
                            {teams.map(team => (
                                <div
                                    key={team.id}
                                    onClick={() => handleTeamToggle(team.id)}
                                    className={`cursor-pointer p-4 rounded-lg border-2 transition ${selectedTeams.includes(team.id)
                                            ? 'border-blue-600 bg-blue-50 dark:bg-blue-900/20'
                                            : 'border-gray-300 dark:border-gray-600 hover:border-blue-400'
                                        }`}
                                >
                                    <div className="flex flex-col items-center">
                                        <Image src={team.logo_url} alt={team.name} width={64} height={64} className="mb-2" />
                                        <span className="text-sm text-center font-medium">{team.name}</span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            ) : (
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden">
                    <table className="w-full">
                        <thead className="bg-gray-100 dark:bg-gray-700">
                            <tr>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase">Rank</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase">Player</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase">Points</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-700 dark:text-gray-300 uppercase">Teams</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                            {leaderboard.map((entry, index) => (
                                <tr key={entry.username} className={index < 3 ? 'bg-yellow-50 dark:bg-yellow-900/10' : ''}>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <span className="text-2xl font-bold text-gray-900 dark:text-white">
                                            {index === 0 ? '🥇' : index === 1 ? '🥈' : index === 2 ? '🥉' : `#${index + 1}`}
                                        </span>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <span className="font-medium text-gray-900 dark:text-white">{entry.username}</span>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <span className="text-lg font-bold text-blue-600 dark:text-blue-400">{entry.points}</span>
                                    </td>
                                    <td className="px-6 py-4">
                                        <div className="text-sm text-gray-600 dark:text-gray-400">
                                            {entry.teams.join(', ')}
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                    {leaderboard.length === 0 && (
                        <div className="text-center py-12 text-gray-500 dark:text-gray-400">
                            No players yet. Be the first to join!
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
