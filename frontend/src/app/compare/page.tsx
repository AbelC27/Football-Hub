'use client';

import { useState } from 'react';
import { Search } from 'lucide-react';
import Link from 'next/link';
import { getTeams, getPlayers, TeamDetailed, PlayerDetailed } from '@/lib/api';
import { SearchableSelect } from '@/components/SearchableSelect';

export default function ComparePage() {
    const [searchType, setSearchType] = useState<'teams' | 'players'>('teams');
    const [searchQuery1, setSearchQuery1] = useState('');
    const [searchQuery2, setSearchQuery2] = useState('');
    const [selected1, setSelected1] = useState<{ id: number; name: string; image_url?: string; subtitle?: string } | null>(null);
    const [selected2, setSelected2] = useState<{ id: number; name: string; image_url?: string; subtitle?: string } | null>(null);

    const handleCompare = () => {
        if (!selected1 || !selected2) return;

        if (searchType === 'teams') {
            window.location.href = `/compare/teams/${selected1.id}/vs/${selected2.id}`;
        } else {
            window.location.href = `/compare/players/${selected1.id}/vs/${selected2.id}`;
        }
    };

    return (
        <main className="min-h-screen bg-neutral-950 text-neutral-200 p-4 md:p-8 relative overflow-hidden">
            {/* Background Beams/Gradient */}
            <div className="absolute inset-0 z-0 pointer-events-none">
                <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-purple-900/20 via-neutral-950 to-neutral-950" />
            </div>

            <div className="max-w-4xl mx-auto relative z-10">
                <div className="mb-12 text-center">
                    <h1 className="text-5xl font-black mb-6 bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-purple-600">
                        Head-to-Head Comparison
                    </h1>
                    <p className="text-neutral-400 text-lg">
                        Compare two teams or players side by side to see who comes out on top.
                    </p>
                </div>

                {/* Type Selector */}
                <div className="flex gap-4 mb-12 justify-center">
                    <button
                        onClick={() => {
                            setSearchType('teams');
                            setSelected1(null);
                            setSelected2(null);
                        }}
                        className={`px-8 py-3 rounded-full font-bold transition-all duration-300 border ${searchType === 'teams'
                            ? 'bg-white text-black border-white shadow-[0_0_20px_rgba(255,255,255,0.3)]'
                            : 'bg-neutral-900 text-neutral-400 border-neutral-800 hover:border-neutral-600 hover:text-neutral-200'
                            }`}
                    >
                        Compare Teams
                    </button>
                    <button
                        onClick={() => {
                            setSearchType('players');
                            setSelected1(null);
                            setSelected2(null);
                        }}
                        className={`px-8 py-3 rounded-full font-bold transition-all duration-300 border ${searchType === 'players'
                            ? 'bg-white text-black border-white shadow-[0_0_20px_rgba(255,255,255,0.3)]'
                            : 'bg-neutral-900 text-neutral-400 border-neutral-800 hover:border-neutral-600 hover:text-neutral-200'
                            }`}
                    >
                        Compare Players
                    </button>
                </div>

                <div className="bg-neutral-900/50 border border-neutral-800 rounded-3xl p-8 backdrop-blur-sm shadow-2xl">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-8 items-center">
                        {/* Selection 1 */}
                        <SearchableSelect
                            label={searchType === 'teams' ? "First Team" : "First Player"}
                            placeholder={searchType === 'teams' ? "Search for a team..." : "Search for a player..."}
                            selectedOption={selected1}
                            onSearch={async (query) => {
                                if (searchType === 'teams') {
                                    const res = await getTeams(undefined, query);
                                    return res.map(t => ({ id: t.id, name: t.name, image_url: t.logo_url, subtitle: t.league?.name }));
                                } else {
                                    const res = await getPlayers(undefined, undefined, query);
                                    return res.map(p => ({ id: p.id, name: p.name, image_url: p.team?.logo_url, subtitle: p.team?.name }));
                                }
                            }}
                            onSelect={setSelected1}
                        />

                        {/* VS Badge */}
                        <div className="hidden md:flex justify-center">
                            <div className="w-12 h-12 rounded-full bg-gradient-to-r from-blue-600 to-purple-600 flex items-center justify-center font-black text-white shadow-lg z-10">
                                VS
                            </div>
                        </div>

                        {/* Selection 2 */}
                        <SearchableSelect
                            label={searchType === 'teams' ? "Second Team" : "Second Player"}
                            placeholder={searchType === 'teams' ? "Search for a team..." : "Search for a player..."}
                            selectedOption={selected2}
                            onSearch={async (query) => {
                                if (searchType === 'teams') {
                                    const res = await getTeams(undefined, query);
                                    return res.map(t => ({ id: t.id, name: t.name, image_url: t.logo_url, subtitle: t.league?.name }));
                                } else {
                                    const res = await getPlayers(undefined, undefined, query);
                                    return res.map(p => ({ id: p.id, name: p.name, image_url: p.team?.logo_url, subtitle: p.team?.name }));
                                }
                            }}
                            onSelect={setSelected2}
                        />
                    </div>

                    <div className="mt-12 flex justify-center">
                        <button
                            onClick={handleCompare}
                            disabled={!selected1 || !selected2}
                            className={`px-12 py-4 rounded-full font-bold text-lg transition-all duration-300 ${selected1 && selected2
                                ? 'bg-white text-black shadow-[0_0_30px_rgba(255,255,255,0.3)] hover:scale-105'
                                : 'bg-neutral-800 text-neutral-500 cursor-not-allowed'
                                }`}
                        >
                            Start Comparison
                        </button>
                    </div>
                </div>
            </div>
        </main>
    );
}
