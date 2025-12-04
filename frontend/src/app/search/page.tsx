'use client';

import { useState, useCallback } from 'react';
import { SearchBar } from '@/components/SearchBar';
import { TeamCard } from '@/components/TeamCard';
import { PlayerCard } from '@/components/PlayerCard';
import { searchAll, Team, Player, SearchResults } from '@/lib/api';
import { Users, Building2, Search as SearchIcon } from 'lucide-react';

type TabType = 'all' | 'teams' | 'players';

export default function SearchPage() {
    const [results, setResults] = useState<SearchResults>({ teams: [], players: [] });
    const [loading, setLoading] = useState(false);
    const [activeTab, setActiveTab] = useState<TabType>('all');
    const [hasSearched, setHasSearched] = useState(false);

    const handleSearch = useCallback(async (query: string) => {
        if (!query.trim()) {
            setResults({ teams: [], players: [] });
            setHasSearched(false);
            return;
        }

        setLoading(true);
        try {
            const data = await searchAll(query);
            setResults(data);
            setHasSearched(true);
        } catch (error) {
            console.error('Search failed:', error);
            setResults({ teams: [], players: [] });
        } finally {
            setLoading(false);
        }
    }, []);

    const TabButton = ({ id, label, icon: Icon, count }: {
        id: TabType,
        label: string,
        icon: any,
        count?: number
    }) => (
        <button
            onClick={() => setActiveTab(id)}
            className={`flex items-center gap-2 px-6 py-3 rounded-full font-medium transition-all ${activeTab === id
                    ? 'bg-blue-600 text-white shadow-lg scale-105'
                    : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
                }`}
        >
            <Icon className="w-4 h-4" />
            {label}
            {count !== undefined && count > 0 && (
                <span className={`ml-1 text-xs px-2 py-0.5 rounded-full ${activeTab === id ? 'bg-blue-500 text-white' : 'bg-gray-200 dark:bg-gray-700'
                    }`}>
                    {count}
                </span>
            )}
        </button>
    );

    const filteredTeams = activeTab === 'all' || activeTab === 'teams' ? results.teams : [];
    const filteredPlayers = activeTab === 'all' || activeTab === 'players' ? results.players : [];

    return (
        <main className="min-h-screen p-4 md:p-8 bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-white">
            <div className="max-w-7xl mx-auto">
                {/* Header */}
                <div className="text-center mb-8">
                    <h1 className="text-4xl md:text-5xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-600 to-purple-600 mb-4">
                        Search Teams & Players
                    </h1>
                    <p className="text-gray-600 dark:text-gray-400 text-lg">
                        Discover your favorite teams and players
                    </p>
                </div>

                {/* Search Bar */}
                <div className="mb-8">
                    <SearchBar onSearch={handleSearch} loading={loading} />
                </div>

                {/* Tabs */}
                {hasSearched && (
                    <div className="flex flex-wrap gap-2 justify-center mb-8">
                        <TabButton
                            id="all"
                            label="All Results"
                            icon={SearchIcon}
                            count={results.teams.length + results.players.length}
                        />
                        <TabButton
                            id="teams"
                            label="Teams"
                            icon={Building2}
                            count={results.teams.length}
                        />
                        <TabButton
                            id="players"
                            label="Players"
                            icon={Users}
                            count={results.players.length}
                        />
                    </div>
                )}

                {/* Results */}
                {hasSearched ? (
                    <div className="space-y-8">
                        {/* Teams Section */}
                        {filteredTeams.length > 0 && (
                            <div>
                                <h2 className="text-2xl font-bold mb-4 flex items-center gap-2">
                                    <Building2 className="w-6 h-6 text-blue-500" />
                                    Teams
                                    <span className="text-sm font-normal text-gray-500 dark:text-gray-400">
                                        ({filteredTeams.length} {filteredTeams.length === 1 ? 'result' : 'results'})
                                    </span>
                                </h2>
                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                                    {filteredTeams.map((team) => (
                                        <TeamCard key={team.id} team={team} />
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* Players Section */}
                        {filteredPlayers.length > 0 && (
                            <div>
                                <h2 className="text-2xl font-bold mb-4 flex items-center gap-2">
                                    <Users className="w-6 h-6 text-green-500" />
                                    Players
                                    <span className="text-sm font-normal text-gray-500 dark:text-gray-400">
                                        ({filteredPlayers.length} {filteredPlayers.length === 1 ? 'result' : 'results'})
                                    </span>
                                </h2>
                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                                    {filteredPlayers.map((player) => (
                                        <PlayerCard key={player.id} player={player} />
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* No Results */}
                        {filteredTeams.length === 0 && filteredPlayers.length === 0 && (
                            <div className="text-center py-20">
                                <SearchIcon className="w-16 h-16 text-gray-400 mx-auto mb-4" />
                                <h3 className="text-2xl font-semibold text-gray-600 dark:text-gray-400 mb-2">
                                    No results found
                                </h3>
                                <p className="text-gray-500 dark:text-gray-500">
                                    Try searching with different keywords or check your spelling
                                </p>
                            </div>
                        )}
                    </div>
                ) : (
                    /* Welcome State */
                    <div className="text-center py-20">
                        <div className="mb-6 flex justify-center gap-4">
                            <div className="w-20 h-20 bg-gradient-to-br from-blue-500 to-purple-600 rounded-full flex items-center justify-center transform hover:scale-110 transition-transform">
                                <Building2 className="w-10 h-10 text-white" />
                            </div>
                            <div className="w-20 h-20 bg-gradient-to-br from-green-500 to-blue-500 rounded-full flex items-center justify-center transform hover:scale-110 transition-transform">
                                <Users className="w-10 h-10 text-white" />
                            </div>
                        </div>
                        <h3 className="text-2xl font-semibold text-gray-600 dark:text-gray-400 mb-3">
                            Start searching for teams and players
                        </h3>
                        <p className="text-gray-500 dark:text-gray-500 max-w-md mx-auto">
                            Enter a team name like "Manchester United" or a player name like "Cristiano Ronaldo"
                            to discover detailed information
                        </p>
                    </div>
                )}
            </div>
        </main>
    );
}
