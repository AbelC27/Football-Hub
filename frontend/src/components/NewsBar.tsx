"use client";

import { useEffect, useState } from "react";
import { Newspaper, Flame } from "lucide-react";
import { getNewsTicker, type NewsArticleSummary } from "@/lib/api";

const REFRESH_MS = 60_000;

export const NewsBar = () => {
    const [items, setItems] = useState<NewsArticleSummary[]>([]);
    const [hidden, setHidden] = useState(false);

    useEffect(() => {
        let cancelled = false;

        const load = async () => {
            try {
                const data = await getNewsTicker(15);
                if (!cancelled) setItems(data);
            } catch (err) {
                console.error("NewsBar: failed to load ticker", err);
            }
        };

        load();
        const interval = setInterval(load, REFRESH_MS);
        return () => {
            cancelled = true;
            clearInterval(interval);
        };
    }, []);

    if (hidden || items.length === 0) {
        return null;
    }

    // Duplicate the list so the marquee animation loops seamlessly.
    const reel = [...items, ...items];

    return (
        <div className="relative w-full bg-gradient-to-r from-blue-950 via-neutral-950 to-blue-950 border-y border-blue-900/40 overflow-hidden">
            <div className="flex items-center gap-3 px-4 py-2">
                <div className="flex items-center gap-2 shrink-0 px-3 py-1 rounded-full bg-blue-600/20 border border-blue-500/30">
                    <Newspaper className="w-3.5 h-3.5 text-blue-300" />
                    <span className="text-[10px] font-bold tracking-widest uppercase text-blue-200">
                        AI News
                    </span>
                </div>

                <div className="flex-1 overflow-hidden relative">
                    <div className="flex gap-10 animate-marquee whitespace-nowrap will-change-transform">
                        {reel.map((item, idx) => (
                            <a
                                key={`${item.id}-${idx}`}
                                href={item.related_fixture_id ? `/match/${item.related_fixture_id}` : "#"}
                                className="group inline-flex items-center gap-2 text-sm text-neutral-200 hover:text-white transition-colors"
                            >
                                {item.news_type === "pre_derby" && (
                                    <Flame className="w-3.5 h-3.5 text-orange-400 shrink-0" />
                                )}
                                <span className="font-semibold text-blue-300 uppercase text-[10px] tracking-wider">
                                    {item.news_type === "pre_derby" ? "Derby" : "Full Time"}
                                </span>
                                <span className="text-neutral-300 group-hover:text-white">
                                    {item.summary}
                                </span>
                                <span className="text-neutral-600">•</span>
                            </a>
                        ))}
                    </div>
                </div>

                <button
                    type="button"
                    onClick={() => setHidden(true)}
                    aria-label="Dismiss news bar"
                    className="shrink-0 text-neutral-500 hover:text-neutral-200 text-xs px-2"
                >
                    ✕
                </button>
            </div>

            <style jsx>{`
                @keyframes marquee {
                    0% { transform: translateX(0); }
                    100% { transform: translateX(-50%); }
                }
                .animate-marquee {
                    animation: marquee 60s linear infinite;
                }
                .animate-marquee:hover {
                    animation-play-state: paused;
                }
            `}</style>
        </div>
    );
};
