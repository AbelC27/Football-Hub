'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ArrowLeft, Trophy, Target } from 'lucide-react';
import Link from 'next/link';
import { motion } from 'framer-motion';

const API_BASE_URL = "http://localhost:8000/api/v1";

// --- Types ---

interface TeamStanding {
    position: number;
    rank?: number;
    team_id: number;
    team_name: string;
    team_logo: string;
    played: number;
    won: number;
    drawn: number;
    lost: number;
    goals_for: number;
    goals_against: number;
    goal_difference: number;
    points: number;
    form: string;
}

interface GroupData {
    name: string;
    table: TeamStanding[];
}

interface TournamentStandings {
    type: "tournament";
    groups: GroupData[];
}

interface BracketTeam {
    id: number;
    name: string;
    logo: string;
}

interface BracketMatch {
    id: number;
    home_team: BracketTeam | null;
    away_team: BracketTeam | null;
    home_score: number | null;
    away_score: number | null;
    status: string;
    start_time: string | null;
}

interface BracketRound {
    name: string;
    stage: string;
    matches: BracketMatch[];
}

interface BracketData {
    rounds: BracketRound[];
}

interface Scorer {
    player_name: string;
    player_id: number;
    team_name: string;
    team_id: number;
    team_logo: string;
    goals: number;
    assists: number;
    penalties: number;
}

// --- API calls ---

async function getStandings(leagueId: number) {
    const res = await fetch(`${API_BASE_URL}/league/${leagueId}/standings`);
    if (!res.ok) throw new Error("Failed to fetch standings");
    return res.json();
}

async function getBracket(leagueId: number): Promise<BracketData> {
    const res = await fetch(`${API_BASE_URL}/league/${leagueId}/bracket`);
    if (!res.ok) return { rounds: [] };
    return res.json();
}

async function getScorers(leagueId: number): Promise<Scorer[]> {
    const res = await fetch(`${API_BASE_URL}/league/${leagueId}/scorers`);
    if (!res.ok) return [];
    return res.json();
}

// --- Components ---

const FormIndicator = ({ form }: { form: string }) => (
    <div className="flex gap-0.5">
        {form.split('').map((r, i) => (
            <div key={i} className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold ${
                r === 'W' ? 'bg-green-500 text-white' : r === 'D' ? 'bg-yellow-500 text-white' : 'bg-red-500 text-white'
            }`}>{r}</div>
        ))}
    </div>
);

function GroupTable({ group }: { group: GroupData }) {
    return (
        <Card className="bg-neutral-900 border-neutral-800">
            <CardHeader className="py-3 px-4">
                <CardTitle className="text-sm font-semibold text-neutral-200">{group.name}</CardTitle>
            </CardHeader>
            <CardContent className="px-2 pb-3">
                <table className="w-full text-xs">
                    <thead>
                        <tr className="text-neutral-500 border-b border-neutral-800">
                            <th className="text-left pl-2 py-1">#</th>
                            <th className="text-left py-1">Team</th>
                            <th className="text-center py-1">P</th>
                            <th className="text-center py-1">W</th>
                            <th className="text-center py-1">D</th>
                            <th className="text-center py-1">L</th>
                            <th className="text-center py-1">GD</th>
                            <th className="text-center py-1 font-bold">Pts</th>
                            <th className="text-center py-1">Form</th>
                        </tr>
                    </thead>
                    <tbody>
                        {group.table.map((row) => (
                            <tr key={row.team_id} className={`border-b border-neutral-800/50 ${
                                row.position <= 2 ? 'bg-green-900/10' : row.position === 3 ? 'bg-yellow-900/10' : ''
                            }`}>
                                <td className="pl-2 py-1.5 font-medium">{row.position}</td>
                                <td className="py-1.5">
                                    <Link href={`/team/${row.team_id}`} className="flex items-center gap-1.5 hover:text-blue-400">
                                        {row.team_logo && <img src={row.team_logo} alt="" className="w-4 h-4" />}
                                        <span className="truncate max-w-[100px]">{row.team_name}</span>
                                    </Link>
                                </td>
                                <td className="text-center py-1.5">{row.played}</td>
                                <td className="text-center py-1.5">{row.won}</td>
                                <td className="text-center py-1.5">{row.drawn}</td>
                                <td className="text-center py-1.5">{row.lost}</td>
                                <td className="text-center py-1.5">{row.goal_difference > 0 ? '+' : ''}{row.goal_difference}</td>
                                <td className="text-center py-1.5 font-bold">{row.points}</td>
                                <td className="py-1.5"><FormIndicator form={row.form} /></td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </CardContent>
        </Card>
    );
}

function BracketMatchCard({ match }: { match: BracketMatch }) {
    const isFinished = match.status === 'FT' || match.status === 'AET' || match.status === 'PEN';
    const isLive = ['LIVE', 'HT', '1H', '2H', 'ET'].includes(match.status);
    const homeWin = isFinished && match.home_score !== null && match.away_score !== null && match.home_score > match.away_score;
    const awayWin = isFinished && match.home_score !== null && match.away_score !== null && match.away_score > match.home_score;

    const TeamRow = ({ team, score, isWinner, dim }: { team: BracketTeam | null; score: number | null; isWinner: boolean; dim: boolean }) => (
        <div className={`flex items-center justify-between px-2.5 py-1.5 ${isWinner ? 'bg-green-900/20' : ''}`}>
            <div className="flex items-center gap-2 min-w-0">
                {team?.logo
                    ? <img src={team.logo} alt="" className="w-4 h-4 flex-shrink-0 object-contain" />
                    : <div className="w-4 h-4 flex-shrink-0 rounded-sm bg-neutral-800" />}
                <span className={`text-[13px] truncate ${isWinner ? 'font-bold text-white' : dim ? 'text-neutral-500' : 'text-neutral-300'} ${!team ? 'text-neutral-600 italic' : ''}`}>
                    {team?.name || 'TBD'}
                </span>
            </div>
            <span className={`text-[13px] font-mono ml-2 tabular-nums ${isWinner ? 'font-bold text-white' : 'text-neutral-400'}`}>
                {score !== null ? score : ''}
            </span>
        </div>
    );

    return (
        <Link href={match.id ? `/match/${match.id}` : '#'} className="block group">
            <div className={`rounded-md bg-neutral-900 border border-neutral-800 overflow-hidden w-[210px] shadow-sm group-hover:border-blue-500/60 transition-colors ${isLive ? 'ring-1 ring-red-500/60' : ''}`}>
                <TeamRow team={match.home_team} score={match.home_score} isWinner={homeWin} dim={awayWin} />
                <div className="border-t border-neutral-800" />
                <TeamRow team={match.away_team} score={match.away_score} isWinner={awayWin} dim={homeWin} />
            </div>
            <div className="mt-1 px-1 flex items-center justify-between">
                {isLive ? (
                    <span className="text-[10px] text-red-400 font-bold">● LIVE</span>
                ) : isFinished && match.status !== 'FT' ? (
                    <span className="text-[10px] text-amber-500">{match.status === 'AET' ? 'a.e.t.' : 'pens'}</span>
                ) : match.start_time && !isFinished ? (
                    <span className="text-[10px] text-neutral-600">
                        {new Date(match.start_time).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                    </span>
                ) : <span />}
            </div>
        </Link>
    );
}

// One match cell with optional connector lines (Flashscore style).
function BracketCell({
    match, matchIdx, hasPrev, hasNext,
}: { match: BracketMatch; matchIdx: number; hasPrev: boolean; hasNext: boolean }) {
    const isTop = matchIdx % 2 === 0;
    return (
        <div className="flex-1 flex items-center min-h-[64px]">
            {/* Incoming line from previous round */}
            {hasPrev && <div className="w-5 border-t border-neutral-700 flex-shrink-0" />}

            <BracketMatchCard match={match} />

            {/* Outgoing elbow toward next round */}
            {hasNext && (
                <div className="w-5 self-stretch relative flex-shrink-0">
                    {/* horizontal stub out of the card, at vertical center */}
                    <div className="absolute top-1/2 left-0 right-0 border-t border-neutral-700" />
                    {/* vertical line: top match goes down, bottom match goes up, meeting at the column edge */}
                    <div
                        className={`absolute right-0 border-r border-neutral-700 ${isTop ? 'top-1/2 bottom-0' : 'top-0 bottom-1/2'}`}
                    />
                </div>
            )}
        </div>
    );
}

function KnockoutBracket({ bracket }: { bracket: BracketData }) {
    if (!bracket.rounds.length) return null;

    // Third-place playoff is rendered separately so it doesn't break the
    // halving structure of the main knockout tree.
    const mainRounds = bracket.rounds.filter((r) => r.stage !== 'THIRD_PLACE');
    const thirdPlace = bracket.rounds.find((r) => r.stage === 'THIRD_PLACE');

    return (
        <div className="space-y-8">
            <div className="overflow-x-auto pb-2">
                <div className="flex min-w-max">
                    {mainRounds.map((round, roundIdx) => {
                        const hasPrev = roundIdx > 0;
                        const hasNext = roundIdx < mainRounds.length - 1;
                        const isFinalRound = round.stage === 'FINAL';
                        return (
                            <div key={round.stage} className="flex flex-col">
                                <h3 className={`text-[11px] font-bold uppercase tracking-wider text-center mb-3 ${isFinalRound ? 'text-amber-400' : 'text-neutral-500'}`}>
                                    {isFinalRound && '🏆 '}{round.name}
                                </h3>
                                <div className="flex flex-col flex-1 justify-around">
                                    {round.matches.map((m, i) => (
                                        <BracketCell
                                            key={m.id}
                                            match={m}
                                            matchIdx={i}
                                            hasPrev={hasPrev}
                                            hasNext={hasNext}
                                        />
                                    ))}
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>

            {/* Third-place playoff */}
            {thirdPlace && thirdPlace.matches.length > 0 && (
                <div className="border-t border-neutral-800 pt-6">
                    <h3 className="text-[11px] font-bold uppercase tracking-wider text-neutral-500 mb-3">
                        🥉 {thirdPlace.name}
                    </h3>
                    <div className="flex">
                        {thirdPlace.matches.map((m) => (
                            <BracketMatchCard key={m.id} match={m} />
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}

function TopScorers({ scorers }: { scorers: Scorer[] }) {
    if (!scorers.length) return null;

    return (
        <div className="space-y-6">
            {/* Golden Boot leader highlight */}
            {scorers[0] && (
                <Card className="bg-gradient-to-br from-amber-900/30 to-neutral-900 border-amber-700/50">
                    <CardContent className="p-6">
                        <div className="flex items-center gap-4">
                            <div className="w-16 h-16 rounded-full bg-gradient-to-br from-amber-500 to-yellow-600 flex items-center justify-center text-2xl shadow-lg shadow-amber-500/20">
                                🥇
                            </div>
                            <div className="flex-1">
                                <div className="text-xs text-amber-400 font-semibold uppercase tracking-wider mb-1">Golden Boot Leader</div>
                                <div className="text-xl font-bold text-white">{scorers[0].player_name}</div>
                                <div className="flex items-center gap-2 mt-1">
                                    {scorers[0].team_logo && <img src={scorers[0].team_logo} alt="" className="w-4 h-4" />}
                                    <span className="text-sm text-neutral-400">{scorers[0].team_name}</span>
                                </div>
                            </div>
                            <div className="text-right">
                                <div className="text-3xl font-black text-amber-400">{scorers[0].goals}</div>
                                <div className="text-xs text-neutral-500">goals</div>
                                {scorers[0].assists > 0 && (
                                    <div className="text-sm text-neutral-400 mt-1">{scorers[0].assists} assists</div>
                                )}
                            </div>
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Full scorers table */}
            <Card className="bg-neutral-900 border-neutral-800">
                <CardHeader className="pb-2">
                    <CardTitle className="text-lg flex items-center gap-2">
                        <Target className="w-5 h-5 text-amber-400" /> Tournament Scorers
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <table className="w-full">
                        <thead>
                            <tr className="text-neutral-500 border-b border-neutral-800 text-sm">
                                <th className="text-left pl-3 py-2 w-8">#</th>
                                <th className="text-left py-2">Player</th>
                                <th className="text-left py-2">Team</th>
                                <th className="text-center py-2 w-16">Goals</th>
                                <th className="text-center py-2 w-16">Assists</th>
                                <th className="text-center py-2 w-16">Pens</th>
                            </tr>
                        </thead>
                        <tbody>
                            {scorers.map((s, idx) => (
                                <tr key={s.player_id || idx} className={`border-b border-neutral-800/50 hover:bg-neutral-800/50 transition-colors ${idx < 3 ? 'bg-amber-900/5' : ''}`}>
                                    <td className="pl-3 py-3">
                                        <span className={`text-sm font-bold ${idx === 0 ? 'text-amber-400' : idx === 1 ? 'text-neutral-300' : idx === 2 ? 'text-orange-400' : 'text-neutral-500'}`}>
                                            {idx + 1}
                                        </span>
                                    </td>
                                    <td className="py-3">
                                        <span className="text-sm font-semibold text-neutral-200">{s.player_name}</span>
                                    </td>
                                    <td className="py-3">
                                        <div className="flex items-center gap-2">
                                            {s.team_logo && <img src={s.team_logo} alt="" className="w-5 h-5 object-contain" />}
                                            <span className="text-sm text-neutral-400">{s.team_name}</span>
                                        </div>
                                    </td>
                                    <td className="text-center py-3">
                                        <span className="text-sm font-bold text-white bg-green-900/40 px-2 py-0.5 rounded">{s.goals}</span>
                                    </td>
                                    <td className="text-center py-3">
                                        <span className="text-sm text-neutral-300">{s.assists || 0}</span>
                                    </td>
                                    <td className="text-center py-3">
                                        <span className="text-sm text-neutral-500">{s.penalties || 0}</span>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </CardContent>
            </Card>
        </div>
    );
}

// --- Regular league standings (backward-compatible) ---

function LeagueStandingsTable({ standings }: { standings: TeamStanding[] }) {
    return (
        <Card>
            <CardHeader>
                <CardTitle className="text-2xl">League Standings</CardTitle>
            </CardHeader>
            <CardContent>
                <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="border-b-2 border-gray-200 dark:border-gray-700">
                                <th className="text-left p-3">#</th>
                                <th className="text-left p-3">Team</th>
                                <th className="text-center p-3">P</th>
                                <th className="text-center p-3">W</th>
                                <th className="text-center p-3">D</th>
                                <th className="text-center p-3">L</th>
                                <th className="text-center p-3">GF</th>
                                <th className="text-center p-3">GA</th>
                                <th className="text-center p-3">GD</th>
                                <th className="text-center p-3 font-bold">Pts</th>
                                <th className="text-center p-3">Form</th>
                            </tr>
                        </thead>
                        <tbody>
                            {standings.map((team, idx) => (
                                <motion.tr
                                    key={team.team_id}
                                    initial={{ opacity: 0, x: -20 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    transition={{ delay: idx * 0.05 }}
                                    className={`border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800 ${
                                        (team.position || team.rank || 0) <= 4 ? 'bg-blue-50 dark:bg-blue-900/20' :
                                        (team.position || team.rank || 0) >= standings.length - 2 ? 'bg-red-50 dark:bg-red-900/20' : ''
                                    }`}
                                >
                                    <td className="p-3 font-bold">{team.position || team.rank}</td>
                                    <td className="p-3">
                                        <Link href={`/team/${team.team_id}`} className="font-medium hover:text-blue-400">
                                            {team.team_name}
                                        </Link>
                                    </td>
                                    <td className="text-center p-3">{team.played}</td>
                                    <td className="text-center p-3">{team.won}</td>
                                    <td className="text-center p-3">{team.drawn}</td>
                                    <td className="text-center p-3">{team.lost}</td>
                                    <td className="text-center p-3">{team.goals_for}</td>
                                    <td className="text-center p-3">{team.goals_against}</td>
                                    <td className="text-center p-3 font-semibold">{team.goal_difference > 0 ? '+' : ''}{team.goal_difference}</td>
                                    <td className="text-center p-3 font-bold text-lg">{team.points}</td>
                                    <td className="p-3"><FormIndicator form={team.form} /></td>
                                </motion.tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </CardContent>
        </Card>
    );
}

// --- Main page ---

export default function LeaguePage() {
    const params = useParams();
    const leagueId = Number(params.id);

    const [standings, setStandings] = useState<any>(null);
    const [bracket, setBracket] = useState<BracketData | null>(null);
    const [scorers, setScorers] = useState<Scorer[]>([]);
    const [loading, setLoading] = useState(true);
    const [activeTab, setActiveTab] = useState<'groups' | 'bracket' | 'scorers'>('groups');

    const isTournament = standings?.type === 'tournament';

    useEffect(() => {
        if (!leagueId) return;

        Promise.all([
            getStandings(leagueId),
            getBracket(leagueId),
            getScorers(leagueId),
        ])
            .then(([s, b, sc]) => {
                setStandings(s);
                setBracket(b);
                setScorers(sc);
            })
            .catch(console.error)
            .finally(() => setLoading(false));
    }, [leagueId]);

    if (loading) return <div className="p-8 text-center text-neutral-400">Loading...</div>;

    // Regular league — flat standings
    if (!isTournament) {
        const flatStandings = Array.isArray(standings) ? standings : [];
        return (
            <main className="min-h-screen p-4 md:p-8 bg-neutral-950 text-neutral-200">
                <div className="max-w-6xl mx-auto">
                    <Link href="/" className="inline-flex items-center text-blue-600 hover:underline mb-6">
                        <ArrowLeft className="w-4 h-4 mr-2" /> Back to Matches
                    </Link>
                    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
                        <LeagueStandingsTable standings={flatStandings} />
                    </motion.div>
                </div>
            </main>
        );
    }

    // Tournament mode
    return (
        <main className="min-h-screen p-4 md:p-8 bg-neutral-950 text-neutral-200">
            <div className="max-w-7xl mx-auto">
                <Link href="/" className="inline-flex items-center text-blue-600 hover:underline mb-4">
                    <ArrowLeft className="w-4 h-4 mr-2" /> Back to Matches
                </Link>

                <div className="flex items-center gap-3 mb-6">
                    <Trophy className="w-6 h-6 text-yellow-500" />
                    <h1 className="text-2xl font-bold">FIFA World Cup 2026</h1>
                </div>

                {/* Tabs */}
                <div className="flex gap-1 mb-6 bg-neutral-900 rounded-lg p-1 w-fit">
                    {(['groups', 'bracket', 'scorers'] as const).map((tab) => (
                        <button
                            key={tab}
                            onClick={() => setActiveTab(tab)}
                            className={`px-4 py-2 text-sm rounded-md transition-colors ${
                                activeTab === tab
                                    ? 'bg-neutral-700 text-white font-medium'
                                    : 'text-neutral-400 hover:text-neutral-200'
                            }`}
                        >
                            {tab === 'groups' ? 'Groups' : tab === 'bracket' ? 'Bracket' : 'Top Scorers'}
                        </button>
                    ))}
                </div>

                {/* Groups tab */}
                {activeTab === 'groups' && (
                    <motion.div
                        initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                        className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4"
                    >
                        {standings.groups.map((g: GroupData) => (
                            <GroupTable key={g.name} group={g} />
                        ))}
                    </motion.div>
                )}

                {/* Bracket tab */}
                {activeTab === 'bracket' && bracket && (
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                        <Card className="bg-neutral-900 border-neutral-800">
                            <CardHeader>
                                <CardTitle className="text-lg">Knockout Stage</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <KnockoutBracket bracket={bracket} />
                            </CardContent>
                        </Card>
                    </motion.div>
                )}

                {/* Scorers tab */}
                {activeTab === 'scorers' && (
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="max-w-4xl">
                        <TopScorers scorers={scorers} />
                    </motion.div>
                )}
            </div>
        </main>
    );
}
