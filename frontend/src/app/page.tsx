'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
    getLeagues,
    getLiveMatches,
    getMatchEventsBulk,
    League,
    Match,
    MatchEventEntry,
} from '@/lib/api';
import { EnhancedMatchCard } from '@/components/EnhancedMatchCard';
import { StandingsTable } from '@/components/StandingsTable';
import { LeagueSelector } from '@/components/LeagueSelector';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { NewsSidebar } from '@/components/NewsSidebar';
import { Calendar, Clock, Trophy, Activity, Sparkles, Loader2 } from 'lucide-react';

type TabType = 'live' | 'upcoming' | 'finished' | 'standings';
type MatchTab = Exclude<TabType, 'standings'>;

const PAGE_SIZE = 30;
const LIVE_POLL_MS = 30_000;

interface TabState {
    items: Match[];
    total: number;
    loadedKey: string | null;
    loading: boolean;
    error: string | null;
    hasMore: boolean;
}

const emptyTabState: TabState = {
    items: [],
    total: 0,
    loadedKey: null,
    loading: false,
    error: null,
    hasMore: true,
};

const tabOrder: Record<MatchTab, 'asc' | 'desc'> = {
    live: 'asc',
    upcoming: 'asc',
    finished: 'desc',
};

const getLeagueDedupKey = (league: League) => {
    const normalizedName = league.name.trim().toLowerCase();
    const normalizedCountry = (league.country || '').trim().toLowerCase();
    return `${normalizedName}|${normalizedCountry}`;
};

const dedupeLeagues = (leagues: League[]): League[] => {
    const seen = new Set<string>();
    return leagues.filter((league) => {
        const key = getLeagueDedupKey(league);
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
    });
};

export default function Home() {
    const [leagues, setLeagues] = useState<League[]>([]);
    const [selectedLeague, setSelectedLeague] = useState<number | null>(null);
    const [activeTab, setActiveTab] = useState<TabType>('upcoming');
    const [bootstrapping, setBootstrapping] = useState(true);

    const [tabStates, setTabStates] = useState<Record<MatchTab, TabState>>({
        live: { ...emptyTabState },
        upcoming: { ...emptyTabState },
        finished: { ...emptyTabState },
    });

    // Mirror the latest tab states into a ref so effects/callbacks can read
    // them without listing them as dependencies (which would loop).
    const tabStatesRef = useRef(tabStates);
    useEffect(() => {
        tabStatesRef.current = tabStates;
    }, [tabStates]);

    // Cache of MatchEvent rows keyed by local match id. We only fetch ids
    // we don't already have, and re-fetch live matches periodically so the
    // scorers strip on the homepage stays fresh.
    const [eventsByMatchId, setEventsByMatchId] = useState<Record<number, MatchEventEntry[]>>({});
    const eventsByMatchIdRef = useRef(eventsByMatchId);
    useEffect(() => {
        eventsByMatchIdRef.current = eventsByMatchId;
    }, [eventsByMatchId]);

    // Build a unique key per (tab, league) so we know when to refetch.
    const buildKey = useCallback((tab: MatchTab, leagueId: number | null) => {
        return `${tab}:${leagueId ?? 'all'}`;
    }, []);

    // Fetch totals for every tab whenever the league changes. Keeps the
    // count badges accurate without paying for full match payloads.
    useEffect(() => {
        if (!selectedLeague) return;

        const tabs: MatchTab[] = ['live', 'upcoming', 'finished'];
        const aborter = new AbortController();

        Promise.all(
            tabs.map((tab) =>
                getLiveMatches({
                    status: tab,
                    leagueId: selectedLeague,
                    limit: 1,
                    offset: 0,
                    signal: aborter.signal,
                }).then((res) => ({ tab, total: res.total }))
            )
        )
            .then((results) => {
                setTabStates((prev) => {
                    const next = { ...prev };
                    for (const { tab, total } of results) {
                        next[tab] = { ...next[tab], total };
                    }
                    return next;
                });
            })
            .catch((err) => {
                if (err?.name !== 'AbortError') console.error(err);
            });

        return () => aborter.abort();
    }, [selectedLeague]);

    // Initial bootstrap: leagues + first-page upcoming matches for the
    // default league so the page renders something quickly.
    useEffect(() => {
        let cancelled = false;

        const bootstrap = async () => {
            try {
                const leaguesData = await getLeagues();
                if (cancelled) return;

                const uniqueLeagues = dedupeLeagues(leaguesData);
                setLeagues(uniqueLeagues);

                if (uniqueLeagues.length > 0) {
                    const pl = uniqueLeagues.find(
                        (l) => l.name.trim().toLowerCase() === 'premier league'
                    );
                    setSelectedLeague(pl ? pl.id : uniqueLeagues[0].id);
                }
            } catch (error) {
                console.error(error);
            } finally {
                if (!cancelled) setBootstrapping(false);
            }
        };

        bootstrap();
        return () => {
            cancelled = true;
        };
    }, []);

    // Fetch first page for the active tab whenever tab or league changes.
    useEffect(() => {
        if (activeTab === 'standings' || !selectedLeague) return;
        const tab = activeTab as MatchTab;
        const key = buildKey(tab, selectedLeague);

        // Avoid re-fetching when we already have data for this (tab, league).
        const current = tabStatesRef.current[tab];
        if (current.loadedKey === key && current.items.length > 0) {
            return;
        }

        const aborter = new AbortController();

        setTabStates((prev) => ({
            ...prev,
            [tab]: { ...emptyTabState, loading: true, total: prev[tab].total },
        }));

        getLiveMatches({
            status: tab,
            leagueId: selectedLeague,
            limit: PAGE_SIZE,
            offset: 0,
            order: tabOrder[tab],
            signal: aborter.signal,
        })
            .then((res) => {
                setTabStates((prev) => ({
                    ...prev,
                    [tab]: {
                        items: res.items,
                        total: res.total,
                        loadedKey: key,
                        loading: false,
                        error: null,
                        hasMore: res.has_more,
                    },
                }));
            })
            .catch((err) => {
                if (err?.name === 'AbortError') return;
                console.error(err);
                setTabStates((prev) => ({
                    ...prev,
                    [tab]: { ...prev[tab], loading: false, error: 'Could not load matches.' },
                }));
            });

        return () => aborter.abort();
    }, [activeTab, selectedLeague, buildKey]);

    // Fetch event rows for any visible matches we don't yet have cached.
    // Re-runs whenever the visible match ids change (tab/league switch,
    // pagination, live polling). Cheap: one DB-only call against the
    // backend bulk endpoint, no external API hits.
    useEffect(() => {
        if (activeTab === 'standings' || !selectedLeague) return;
        const tab = activeTab as MatchTab;
        const visibleIds = tabStates[tab].items.map((m) => m.id);
        if (visibleIds.length === 0) return;

        const cached = eventsByMatchIdRef.current;
        const missing = visibleIds.filter((id) => !(id in cached));
        if (missing.length === 0) return;

        const aborter = new AbortController();
        getMatchEventsBulk(missing, aborter.signal)
            .then((map) => {
                setEventsByMatchId((prev) => {
                    const next = { ...prev };
                    for (const id of missing) {
                        const events = map[String(id)] ?? [];
                        next[id] = events;
                    }
                    return next;
                });
            })
            .catch((err) => {
                if (err?.name === 'AbortError') return;
                console.warn('Failed to load match events:', err);
            });

        return () => aborter.abort();
    }, [activeTab, selectedLeague, tabStates]);

    // Poll the live tab every 30s so scores stay fresh. Only re-fetches the
    // first page; the user can still scroll for more if they want.
    useEffect(() => {
        if (activeTab !== 'live' || !selectedLeague) return;

        const interval = setInterval(() => {
            getLiveMatches({
                status: 'live',
                leagueId: selectedLeague,
                limit: PAGE_SIZE,
                offset: 0,
                order: tabOrder.live,
            })
                .then((res) => {
                    setTabStates((prev) => ({
                        ...prev,
                        live: {
                            ...prev.live,
                            // Replace just the first page; preserve any extra
                            // pages the user already loaded.
                            items: [
                                ...res.items,
                                ...prev.live.items.slice(res.items.length),
                            ],
                            total: res.total,
                        },
                    }));
                    // Drop cached events for these live matches so the next
                    // bulk-fetch effect run picks up any new goals.
                    if (res.items.length > 0) {
                        setEventsByMatchId((prev) => {
                            const next = { ...prev };
                            for (const m of res.items) {
                                delete next[m.id];
                            }
                            return next;
                        });
                    }
                })
                .catch(console.error);
        }, LIVE_POLL_MS);

        return () => clearInterval(interval);
    }, [activeTab, selectedLeague]);

    const loadMore = useCallback(() => {
        if (activeTab === 'standings' || !selectedLeague) return;
        const tab = activeTab as MatchTab;
        const state = tabStatesRef.current[tab];
        if (state.loading || !state.hasMore) return;

        setTabStates((prev) => ({ ...prev, [tab]: { ...prev[tab], loading: true } }));

        getLiveMatches({
            status: tab,
            leagueId: selectedLeague,
            limit: PAGE_SIZE,
            offset: state.items.length,
            order: tabOrder[tab],
        })
            .then((res) => {
                setTabStates((prev) => ({
                    ...prev,
                    [tab]: {
                        items: [...prev[tab].items, ...res.items],
                        total: res.total,
                        loadedKey: prev[tab].loadedKey,
                        loading: false,
                        error: null,
                        hasMore: res.has_more,
                    },
                }));
            })
            .catch((err) => {
                console.error(err);
                setTabStates((prev) => ({
                    ...prev,
                    [tab]: { ...prev[tab], loading: false, error: 'Could not load more matches.' },
                }));
            });
    }, [activeTab, selectedLeague]);

    // Infinite scroll: observe a sentinel near the bottom of the list.
    const sentinelRef = useRef<HTMLDivElement | null>(null);
    useEffect(() => {
        if (activeTab === 'standings') return;
        const el = sentinelRef.current;
        if (!el) return;

        const observer = new IntersectionObserver(
            (entries) => {
                if (entries[0]?.isIntersecting) loadMore();
            },
            { rootMargin: '400px' }
        );
        observer.observe(el);
        return () => observer.disconnect();
    }, [loadMore, activeTab]);

    const activeMatchTab = activeTab === 'standings' ? null : (activeTab as MatchTab);
    const activeState = activeMatchTab ? tabStates[activeMatchTab] : null;
    const activeMatches = activeState?.items ?? [];

    // Group matches by date for the section headers.
    const groupedMatches = useMemo(() => {
        return activeMatches.reduce((acc, match) => {
            const date = new Date(match.start_time).toLocaleDateString(undefined, {
                weekday: 'long',
                year: 'numeric',
                month: 'long',
                day: 'numeric',
            });
            if (!acc[date]) acc[date] = [];
            acc[date].push(match);
            return acc;
        }, {} as Record<string, Match[]>);
    }, [activeMatches]);

    const sortedDates = useMemo(() => {
        const dates = Object.keys(groupedMatches);
        dates.sort((a, b) => new Date(a).getTime() - new Date(b).getTime());
        if (activeTab === 'finished') dates.reverse();
        return dates;
    }, [groupedMatches, activeTab]);

    const TabButton = ({
        id,
        label,
        icon: Icon,
        count,
    }: {
        id: TabType;
        label: string;
        icon: any;
        count?: number;
    }) => (
        <button
            onClick={() => setActiveTab(id)}
            className={`group relative px-6 py-3 rounded-full font-semibold transition-all duration-300 ${
                activeTab === id
                    ? 'bg-white text-black shadow-[0_0_20px_rgba(255,255,255,0.3)] scale-105'
                    : 'bg-neutral-900 text-neutral-400 hover:text-white hover:bg-neutral-800 border border-neutral-800'
            }`}
        >
            <div className="flex items-center gap-2">
                <Icon className="w-4 h-4" />
                <span>{label}</span>
                {typeof count === 'number' && count > 0 && (
                    <span
                        className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                            activeTab === id
                                ? 'bg-black text-white'
                                : 'bg-neutral-800 text-neutral-400'
                        }`}
                    >
                        {count}
                    </span>
                )}
            </div>
        </button>
    );

    if (bootstrapping) {
        return (
            <main className="min-h-screen bg-neutral-950 text-neutral-200 p-4 md:p-8">
                <div className="max-w-7xl mx-auto">
                    <LoadingSpinner />
                </div>
            </main>
        );
    }

    return (
        <main className="min-h-screen bg-neutral-950 text-neutral-200 p-4 md:p-8 relative overflow-hidden">
            <div className="absolute inset-0 z-0 pointer-events-none">
                <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-blue-900/20 via-neutral-950 to-neutral-950" />
            </div>

            <div className="max-w-7xl mx-auto relative z-10">
                <div className="mb-12 text-center">
                    <h1 className="text-5xl md:text-7xl font-black mb-6 bg-clip-text text-transparent bg-gradient-to-b from-neutral-50 to-neutral-400 flex items-center justify-center gap-4">
                        <Sparkles className="w-12 h-12 text-blue-500" />
                        TerraBall
                    </h1>
                    <p className="text-neutral-400 text-lg max-w-2xl mx-auto">
                        Experience the beautiful game with real-time updates, advanced statistics, and immersive comparisons.
                    </p>
                </div>

                <div className="mb-12">
                    <LeagueSelector
                        leagues={leagues}
                        selectedLeague={selectedLeague}
                        onSelectLeague={setSelectedLeague}
                    />
                </div>

                {selectedLeague && (
                    <>
                        <div className="mb-8">
                            <div className="flex flex-wrap gap-4 justify-center">
                                <TabButton id="live" label="Live" icon={Activity} count={tabStates.live.total} />
                                <TabButton id="upcoming" label="Upcoming" icon={Calendar} count={tabStates.upcoming.total} />
                                <TabButton id="finished" label="Finished" icon={Clock} count={tabStates.finished.total} />
                                <TabButton id="standings" label="Table" icon={Trophy} />
                            </div>
                        </div>

                        <div className="grid grid-cols-1 lg:grid-cols-[1fr_340px] gap-8">
                            <div>
                                {activeTab === 'standings' ? (
                                    <div className="bg-neutral-900/50 border border-neutral-800 rounded-3xl p-6 backdrop-blur-sm">
                                        <StandingsTable
                                            leagueId={selectedLeague}
                                            leagueName={leagues.find((l) => l.id === selectedLeague)?.name}
                                        />
                                    </div>
                                ) : (
                                    <div className="space-y-12">
                                        {activeState?.loading && activeMatches.length === 0 ? (
                                            <LoadingSpinner />
                                        ) : sortedDates.length > 0 ? (
                                            <>
                                                {sortedDates.map((date) => (
                                                    <div key={date}>
                                                        <div className="flex items-center gap-4 mb-6">
                                                            <div className="h-px flex-1 bg-gradient-to-r from-transparent via-neutral-800 to-transparent" />
                                                            <h3 className="text-xl font-bold text-neutral-400 uppercase tracking-widest">
                                                                {date}
                                                            </h3>
                                                            <div className="h-px flex-1 bg-gradient-to-r from-transparent via-neutral-800 to-transparent" />
                                                        </div>

                                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                                            {groupedMatches[date].map((match) => (
                                                                <EnhancedMatchCard
                                                                    key={match.id}
                                                                    match={match}
                                                                    events={eventsByMatchId[match.id] ?? null}
                                                                />
                                                            ))}
                                                        </div>
                                                    </div>
                                                ))}

                                                <div ref={sentinelRef} className="h-10 w-full" aria-hidden />

                                                {activeState?.loading && activeMatches.length > 0 && (
                                                    <div className="flex items-center justify-center gap-2 py-6 text-neutral-400">
                                                        <Loader2 className="w-4 h-4 animate-spin" />
                                                        <span className="text-sm">Loading more...</span>
                                                    </div>
                                                )}

                                                {!activeState?.hasMore && activeMatches.length >= PAGE_SIZE && (
                                                    <div className="text-center py-6 text-neutral-600 text-sm">
                                                        You've reached the end.
                                                    </div>
                                                )}

                                                {activeState?.error && (
                                                    <div className="text-center py-4 text-red-400 text-sm">
                                                        {activeState.error}
                                                    </div>
                                                )}
                                            </>
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
                            </div>

                            <div className="lg:sticky lg:top-6 lg:self-start">
                                <NewsSidebar leagueId={selectedLeague} />
                            </div>
                        </div>
                    </>
                )}
            </div>
        </main>
    );
}
