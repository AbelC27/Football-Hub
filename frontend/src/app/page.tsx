'use client';

import { useEffect, useState } from 'react';
import { Match, getLiveMatches, getLeagues, League } from '@/lib/api';
import { EnhancedMatchCard } from '@/components/EnhancedMatchCard';
import { StandingsTable } from '@/components/StandingsTable';
import { LeagueSelector } from '@/components/LeagueSelector';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { Calendar, Clock, Trophy, Activity, Sparkles } from 'lucide-react';

type TabType = 'live' | 'upcoming' | 'finished' | 'standings';

export default function Home() {
    const [matches, setMatches] = useState<Match[]>([]);
    const [leagues, setLeagues] = useState<League[]>([]);
    const [selectedLeague, setSelectedLeague] = useState<number | null>(null);
    const [activeTab, setActiveTab] = useState<TabType>('live');
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchData = async () => {
            try {
                const [matchesData, leaguesData] = await Promise.all([
                    getLiveMatches(),
                    getLeagues()
                ]);
                setMatches(matchesData);
                setLeagues(leaguesData);

                // Set default league if available
                if (leaguesData.length > 0 && !selectedLeague) {
                    const pl = leaguesData.find(l => l.name === 'Premier League');
                    setSelectedLeague(pl ? pl.id : leaguesData[0].id);
                }

                // Auto-select tab based on available matches
                const hasLive = matchesData.some(m => ['LIVE', 'HT', 'ET', 'P'].includes(m.status));
                if (hasLive && activeTab !== 'live') setActiveTab('live');
            } catch (error) {
                console.error(error);
            } finally {
                setLoading(false);
            }
        };
        fetchData();

        // Poll for live matches every 30 seconds
        const interval = setInterval(() => {
            getLiveMatches()
                .then(matchesData => {
                    setMatches(matchesData);
                })
                .catch(console.error);
        }, 30000); // 30 seconds

        return () => clearInterval(interval);
    }, []);

    // Filter matches by selected league and tab
    const filteredMatches = matches.filter(match => {
        // Filter by league
        if (selectedLeague && match.league_id && match.league_id !== selectedLeague) {
            return false;
        }

        // Filter by status/tab
        if (activeTab === 'live') return ['LIVE', 'HT', 'ET', 'P'].includes(match.status);
        if (activeTab === 'upcoming') return ['NS', 'TBD', 'PST'].includes(match.status);
        if (activeTab === 'finished') return ['FT', 'AET', 'PEN'].includes(match.status);
        return false;
    });

    // Group matches by date
    const groupedMatches = filteredMatches.reduce((acc, match) => {
        const date = new Date(match.start_time).toLocaleDateString(undefined, {
            weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
        });
        if (!acc[date]) acc[date] = [];
        acc[date].push(match);
        return acc;
    }, {} as Record<string, Match[]>);

    // Sort dates
    const sortedDates = Object.keys(groupedMatches).sort((a, b) => {
        return new Date(a).getTime() - new Date(b).getTime();
    });

    if (activeTab === 'finished') {
        sortedDates.reverse();
    }

    const TabButton = ({ id, label, icon: Icon, count }: { id: TabType, label: string, icon: any, count?: number }) => (
        <button
            onClick={() => setActiveTab(id)}
            className={`group relative px-6 py-3 rounded-full font-semibold transition-all duration-300 ${activeTab === id
                ? 'bg-white text-black shadow-[0_0_20px_rgba(255,255,255,0.3)] scale-105'
                : 'bg-neutral-900 text-neutral-400 hover:text-white hover:bg-neutral-800 border border-neutral-800'
                }`}
        >
            <div className="flex items-center gap-2">
                <Icon className="w-4 h-4" />
                <span>{label}</span>
                {count !== undefined && count > 0 && (
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${activeTab === id
                        ? 'bg-black text-white'
                        : 'bg-neutral-800 text-neutral-400'
                        }`}>
                        {count}
                    </span>
                )}
            </div>
        </button>
    );

    const liveCount = matches.filter(m => selectedLeague ? (m.league_id === selectedLeague && ['LIVE', 'HT', 'ET', 'P'].includes(m.status)) : ['LIVE', 'HT', 'ET', 'P'].includes(m.status)).length;
    const upcomingCount = matches.filter(m => selectedLeague ? (m.league_id === selectedLeague && ['NS', 'TBD', 'PST'].includes(m.status)) : ['NS', 'TBD', 'PST'].includes(m.status)).length;
    const finishedCount = matches.filter(m => selectedLeague ? (m.league_id === selectedLeague && ['FT', 'AET', 'PEN'].includes(m.status)) : ['FT', 'AET', 'PEN'].includes(m.status)).length;

    if (loading) {
        return (
            <main className="min-h-screen bg-gradient-to-br from-gray-50 via-blue-50 to-purple-50 dark:from-gray-900 dark:via-gray-900 dark:to-gray-900 p-4 md:p-8">
                <div className="max-w-7xl mx-auto">
                    <LoadingSpinner />
                </div>
            </main>
        );
    }

    return (
        <main className="min-h-screen bg-neutral-950 text-neutral-200 p-4 md:p-8 relative overflow-hidden">
            {/* Background Beams/Gradient */}
            <div className="absolute inset-0 z-0 pointer-events-none">
                <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-blue-900/20 via-neutral-950 to-neutral-950" />
            </div>

            <div className="max-w-7xl mx-auto relative z-10">
                {/* Header */}
                <div className="mb-12 text-center">
                    <h1 className="text-5xl md:text-7xl font-black mb-6 bg-clip-text text-transparent bg-gradient-to-b from-neutral-50 to-neutral-400 flex items-center justify-center gap-4">
                        <Sparkles className="w-12 h-12 text-blue-500" />
                        Football Hub
                    </h1>
                    <p className="text-neutral-400 text-lg max-w-2xl mx-auto">
                        Experience the beautiful game with real-time updates, advanced statistics, and immersive comparisons.
                    </p>
                </div>

                {/* League Selector */}
                <div className="mb-12">
                    <LeagueSelector
                        leagues={leagues}
                        selectedLeague={selectedLeague}
                        onSelectLeague={setSelectedLeague}
                    />
                </div>

                {/* Match Tabs */}
                {selectedLeague && (
                    <>
                        <div className="mb-8">
                            <div className="flex flex-wrap gap-4 justify-center">
                                <TabButton id="live" label="Live" icon={Activity} count={liveCount} />
                                <TabButton id="upcoming" label="Upcoming" icon={Calendar} count={upcomingCount} />
                                <TabButton id="finished" label="Finished" icon={Clock} count={finishedCount} />
                                <TabButton id="standings" label="Table" icon={Trophy} />
                            </div>
                        </div>

                        {/* Content */}
                        {activeTab === 'standings' ? (
                            <div className="bg-neutral-900/50 border border-neutral-800 rounded-3xl p-6 backdrop-blur-sm">
                                <StandingsTable
                                    leagueId={selectedLeague}
                                    leagueName={leagues.find(l => l.id === selectedLeague)?.name}
                                />
                            </div>
                        ) : (
                            <div className="space-y-12">
                                {sortedDates.length > 0 ? (
                                    sortedDates.map(date => (
                                        <div key={date}>
                                            <div className="flex items-center gap-4 mb-6">
                                                <div className="h-px flex-1 bg-gradient-to-r from-transparent via-neutral-800 to-transparent" />
                                                <h3 className="text-xl font-bold text-neutral-400 uppercase tracking-widest">{date}</h3>
                                                <div className="h-px flex-1 bg-gradient-to-r from-transparent via-neutral-800 to-transparent" />
                                            </div>

                                            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
                                                {groupedMatches[date].map(match => (
                                                    <EnhancedMatchCard key={match.id} match={match} />
                                                ))}
                                            </div>
                                        </div>
                                    ))
                                ) : (
                                    <div className="text-center py-32 bg-neutral-900/30 border border-neutral-800 rounded-3xl">
                                        <div className="mb-6">
                                            <div className="w-24 h-24 bg-neutral-800 rounded-full mx-auto flex items-center justify-center">
                                                {activeTab === 'live' && <Activity className="w-12 h-12 text-neutral-600" />}
                                                {activeTab === 'upcoming' && <Calendar className="w-12 h-12 text-neutral-600" />}
                                                {activeTab === 'finished' && <Clock className="w-12 h-12 text-neutral-600" />}
                                            </div>
                                        </div>
                                        <h3 className="text-2xl font-bold text-neutral-300 mb-2">
                                            No {activeTab} matches
                                        </h3>
                                        <p className="text-neutral-500">
                                            {activeTab === 'live' && 'There are no live matches at the moment.'}
                                            {activeTab === 'upcoming' && 'No upcoming matches scheduled.'}
                                            {activeTab === 'finished' && 'No finished matches to display.'}
                                        </p>
                                    </div>
                                )}
                            </div>
                        )}
                    </>
                )}
            </div>
        </main>
    );
}
