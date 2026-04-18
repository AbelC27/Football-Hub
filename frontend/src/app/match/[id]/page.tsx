'use client';

import { useEffect, useMemo, useRef } from 'react';
import { useParams } from 'next/navigation';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import {
    getMatchExperience,
    getMatchNextEventsPrediction,
    getMatchXGLive,
    getMatchXGPreMatch,
    MatchExperience,
} from '@/lib/api';
import { useWebSocket } from '@/hooks/useWebSocket';
import { MatchExperienceView } from '@/components/MatchExperienceView';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';

const WS_URL = 'ws://localhost:8000/ws/live';

function MatchPageLoadingState() {
    return (
        <main className="min-h-screen bg-[radial-gradient(circle_at_top,_#eef8ff_0%,_#f6f7fb_42%,_#f1f1f5_100%)] px-4 py-6 dark:bg-[radial-gradient(circle_at_top,_#1a2433_0%,_#0f1115_42%,_#0b0c0f_100%)] md:px-8 md:py-10">
            <div className="mx-auto max-w-6xl space-y-5">
                <Skeleton className="h-5 w-44" />
                <Card>
                    <CardContent className="space-y-4 p-6 md:p-8">
                        <Skeleton className="h-6 w-48" />
                        <Skeleton className="h-14 w-56" />
                        <Skeleton className="h-24 w-full" />
                    </CardContent>
                </Card>
                <div className="grid gap-4 md:grid-cols-2">
                    <Card>
                        <CardContent className="space-y-3 p-6">
                            <Skeleton className="h-5 w-32" />
                            <Skeleton className="h-16 w-full" />
                        </CardContent>
                    </Card>
                    <Card>
                        <CardContent className="space-y-3 p-6">
                            <Skeleton className="h-5 w-32" />
                            <Skeleton className="h-16 w-full" />
                        </CardContent>
                    </Card>
                </div>
            </div>
        </main>
    );
}

function MatchPageErrorState({
    message,
    onRetry,
}: {
    message: string;
    onRetry: () => void;
}) {
    return (
        <main className="min-h-screen bg-[radial-gradient(circle_at_top,_#eef8ff_0%,_#f6f7fb_42%,_#f1f1f5_100%)] px-4 py-6 dark:bg-[radial-gradient(circle_at_top,_#1a2433_0%,_#0f1115_42%,_#0b0c0f_100%)] md:px-8 md:py-10">
            <div className="mx-auto max-w-2xl">
                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2 text-red-600 dark:text-red-400">
                            <AlertTriangle className="h-5 w-5" />
                            Match Experience Unavailable
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4 text-sm text-neutral-600 dark:text-neutral-300">
                        <p>{message}</p>
                        <button
                            onClick={onRetry}
                            className="inline-flex items-center gap-2 rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-neutral-700 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-300"
                        >
                            <RefreshCw className="h-4 w-4" />
                            Retry
                        </button>
                    </CardContent>
                </Card>
            </div>
        </main>
    );
}

export default function MatchDetailsPage() {
    const params = useParams();
    const queryClient = useQueryClient();
    const lastMessage = useWebSocket(WS_URL);

    const successToastShown = useRef(false);
    const lastErrorToast = useRef<string | null>(null);
    const lastPartialToastKey = useRef('');

    const matchId = useMemo(() => {
        const rawId = Array.isArray(params.id) ? params.id[0] : params.id;
        const parsed = Number(rawId);

        return Number.isFinite(parsed) ? parsed : null;
    }, [params.id]);

    const query = useQuery({
        queryKey: ['match-experience', matchId],
        queryFn: () => getMatchExperience(matchId as number),
        enabled: typeof matchId === 'number' && matchId > 0,
        staleTime: 20_000,
        refetchInterval: (currentQuery) => {
            const status = currentQuery.state.data?.header.status?.toUpperCase();
            return status && ['LIVE', 'HT', 'ET', 'P'].includes(status) ? 15_000 : false;
        },
    });

    const nextEventsQuery = useQuery({
        queryKey: ['match-next-events', matchId],
        queryFn: () => getMatchNextEventsPrediction(matchId as number),
        enabled: typeof matchId === 'number' && matchId > 0,
        staleTime: 10_000,
        retry: false,
        refetchInterval: () => {
            const status = query.data?.header.status?.toUpperCase();
            return status && ['LIVE', 'HT', 'ET', 'P', '1H', '2H'].includes(status) ? 12_000 : false;
        },
    });

    const xgPreMatchQuery = useQuery({
        queryKey: ['match-xg-pre-match', matchId],
        queryFn: () => getMatchXGPreMatch(matchId as number),
        enabled: typeof matchId === 'number' && matchId > 0,
        staleTime: 60_000,
        retry: false,
    });

    const xgLiveQuery = useQuery({
        queryKey: ['match-xg-live', matchId],
        queryFn: () => getMatchXGLive(matchId as number),
        enabled: typeof matchId === 'number' && matchId > 0,
        staleTime: 8_000,
        retry: false,
        refetchInterval: () => {
            const status = query.data?.header.status?.toUpperCase();
            return status && ['LIVE', 'HT', 'ET', 'P', '1H', '2H'].includes(status) ? 12_000 : false;
        },
    });

    useEffect(() => {
        if (query.isSuccess && !successToastShown.current) {
            successToastShown.current = true;
            toast.success('Match data loaded successfully.');
        }
    }, [query.isSuccess]);

    useEffect(() => {
        if (!query.isError) return;

        const message = query.error instanceof Error ? query.error.message : 'Failed to load match data.';
        if (lastErrorToast.current === message) return;

        lastErrorToast.current = message;
        toast.error(message);
    }, [query.error, query.isError]);

    useEffect(() => {
        if (!query.data || query.data.partial_failures.length === 0) return;

        const partialKey = query.data.partial_failures.map((failure) => `${failure.section}:${failure.message}`).join('|');
        if (lastPartialToastKey.current === partialKey) return;

        lastPartialToastKey.current = partialKey;
        toast.warning('Some match sections are temporarily unavailable.');
    }, [query.data]);

    useEffect(() => {
        if (!matchId || !lastMessage || lastMessage.type !== 'match_update') return;
        if (Number(lastMessage?.data?.match_id) !== matchId) return;

        queryClient.setQueryData<MatchExperience>(['match-experience', matchId], (current) => {
            if (!current) return current;

            return {
                ...current,
                header: {
                    ...current.header,
                    status: lastMessage.data.status || current.header.status,
                    score: {
                        home:
                            typeof lastMessage.data.home_score === 'number'
                                ? lastMessage.data.home_score
                                : current.header.score.home,
                        away:
                            typeof lastMessage.data.away_score === 'number'
                                ? lastMessage.data.away_score
                                : current.header.score.away,
                    },
                },
            };
        });

        queryClient.invalidateQueries({ queryKey: ['match-next-events', matchId] });
        queryClient.invalidateQueries({ queryKey: ['match-xg-live', matchId] });
    }, [lastMessage, matchId, queryClient]);

    if (!matchId || matchId <= 0) {
        return (
            <MatchPageErrorState
                message="The match id is invalid. Please open this page from a valid match link."
                onRetry={() => query.refetch()}
            />
        );
    }

    if (query.isPending) {
        return <MatchPageLoadingState />;
    }

    if (query.isError) {
        const errorMessage = query.error instanceof Error ? query.error.message : 'Failed to load match data.';
        return <MatchPageErrorState message={errorMessage} onRetry={() => query.refetch()} />;
    }

    if (!query.data) {
        return (
            <MatchPageErrorState
                message="No match payload was returned by the server."
                onRetry={() => query.refetch()}
            />
        );
    }

    const nextEventsError = nextEventsQuery.isError
        ? nextEventsQuery.error instanceof Error
            ? nextEventsQuery.error.message
            : 'Could not load next-goal and next-assist predictions.'
        : null;

    const xgError = xgLiveQuery.isError
        ? xgLiveQuery.error instanceof Error
            ? xgLiveQuery.error.message
            : 'Could not load live xG updates.'
        : xgPreMatchQuery.isError
            ? xgPreMatchQuery.error instanceof Error
                ? xgPreMatchQuery.error.message
                : 'Could not load pre-match xG forecast.'
            : null;

    return (
        <MatchExperienceView
            data={query.data}
            nextEventPrediction={nextEventsQuery.data || null}
            nextEventPredictionLoading={nextEventsQuery.isPending}
            nextEventPredictionError={nextEventsError}
            xgPreMatch={xgPreMatchQuery.data || null}
            xgLive={xgLiveQuery.data || null}
            xgLoading={xgPreMatchQuery.isPending || xgLiveQuery.isPending}
            xgError={xgError}
        />
    );
}
