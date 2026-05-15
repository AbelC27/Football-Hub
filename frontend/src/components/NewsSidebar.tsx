"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Sparkles, Flame, Trophy, Clock } from "lucide-react";
import { getNews, type NewsArticle } from "@/lib/api";

const REFRESH_MS = 120_000;

function timeAgo(iso: string): string {
    const now = Date.now();
    const then = new Date(iso).getTime();
    const diff = Math.max(0, now - then);
    const minutes = Math.floor(diff / 60_000);
    if (minutes < 1) return "just now";
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
}

interface NewsSidebarProps {
    /** Optional league filter from the parent page. */
    leagueId?: number | null;
    /** Max articles to render. */
    limit?: number;
}

export const NewsSidebar = ({ leagueId, limit = 8 }: NewsSidebarProps) => {
    const [articles, setArticles] = useState<NewsArticle[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        let cancelled = false;

        const load = async () => {
            try {
                setError(null);
                const data = await getNews({
                    limit,
                    leagueId: leagueId ?? undefined,
                });
                if (!cancelled) setArticles(data);
            } catch (err) {
                if (!cancelled) {
                    setError(err instanceof Error ? err.message : "Failed to load news");
                }
            } finally {
                if (!cancelled) setLoading(false);
            }
        };

        load();
        const interval = setInterval(load, REFRESH_MS);
        return () => {
            cancelled = true;
            clearInterval(interval);
        };
    }, [leagueId, limit]);

    const featured = useMemo(() => articles[0], [articles]);
    const rest = useMemo(() => articles.slice(1), [articles]);

    return (
        <aside className="w-full bg-neutral-900/50 border border-neutral-800 rounded-3xl p-5 backdrop-blur-sm">
            <header className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-blue-400" />
                    <h2 className="text-sm font-bold tracking-widest uppercase text-neutral-200">
                        AI Newsroom
                    </h2>
                </div>
                <span className="text-[10px] uppercase tracking-wider text-neutral-500">
                    Auto-generated
                </span>
            </header>

            {loading && articles.length === 0 ? (
                <div className="space-y-3">
                    {Array.from({ length: 4 }).map((_, i) => (
                        <div key={i} className="animate-pulse">
                            <div className="h-3 w-1/3 bg-neutral-800 rounded mb-2" />
                            <div className="h-4 w-full bg-neutral-800 rounded mb-1" />
                            <div className="h-3 w-5/6 bg-neutral-800/70 rounded" />
                        </div>
                    ))}
                </div>
            ) : error ? (
                <p className="text-xs text-red-400">{error}</p>
            ) : articles.length === 0 ? (
                <p className="text-xs text-neutral-500">
                    No news yet. Stories appear here right after a match ends or before a big derby.
                </p>
            ) : (
                <div className="space-y-5">
                    {featured && <FeaturedCard article={featured} />}

                    <ul className="divide-y divide-neutral-800">
                        {rest.map((article) => (
                            <li key={article.id} className="py-3 first:pt-0 last:pb-0">
                                <ArticleRow article={article} />
                            </li>
                        ))}
                    </ul>
                </div>
            )}
        </aside>
    );
};

function NewsTypeChip({ type }: { type: NewsArticle["news_type"] }) {
    if (type === "pre_derby") {
        return (
            <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-orange-500/15 text-orange-300 border border-orange-500/30">
                <Flame className="w-3 h-3" /> Derby
            </span>
        );
    }
    return (
        <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-blue-500/15 text-blue-300 border border-blue-500/30">
            <Trophy className="w-3 h-3" /> Full Time
        </span>
    );
}

function articleHref(article: NewsArticle): string {
    if (article.related_fixture_id) {
        return `/match/${article.related_fixture_id}`;
    }
    return "#";
}

function FeaturedCard({ article }: { article: NewsArticle }) {
    return (
        <Link
            href={articleHref(article)}
            className="block group rounded-2xl border border-neutral-800 bg-neutral-950/60 p-4 hover:border-blue-500/40 transition-colors"
        >
            <div className="flex items-center justify-between mb-2">
                <NewsTypeChip type={article.news_type} />
                <span className="flex items-center gap-1 text-[11px] text-neutral-500">
                    <Clock className="w-3 h-3" />
                    {timeAgo(article.created_at)}
                </span>
            </div>
            <h3 className="text-base font-bold text-neutral-50 leading-snug mb-2 group-hover:text-blue-300 transition-colors">
                {article.title}
            </h3>
            <p className="text-sm text-neutral-400 line-clamp-3">{article.summary}</p>
            {(article.home_team || article.away_team) && (
                <p className="mt-3 text-[11px] uppercase tracking-wider text-neutral-500">
                    {article.home_team?.name}
                    {article.away_team ? ` vs ${article.away_team.name}` : ""}
                </p>
            )}
        </Link>
    );
}

function ArticleRow({ article }: { article: NewsArticle }) {
    return (
        <Link
            href={articleHref(article)}
            className="block group"
        >
            <div className="flex items-center justify-between mb-1">
                <NewsTypeChip type={article.news_type} />
                <span className="text-[11px] text-neutral-500">
                    {timeAgo(article.created_at)}
                </span>
            </div>
            <p className="text-sm font-semibold text-neutral-200 leading-snug group-hover:text-blue-300 transition-colors line-clamp-2">
                {article.title}
            </p>
            <p className="text-xs text-neutral-500 mt-1 line-clamp-2">{article.summary}</p>
        </Link>
    );
}
