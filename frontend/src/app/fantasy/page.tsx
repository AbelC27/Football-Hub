"use client";

import { useEffect, useMemo, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import { useAuth } from "@/context/AuthContext";
import {
  FantasyMatchdayPick,
  FantasyPlayerPoolItem,
  FantasySquadPlayer,
  FantasyTransferItem,
  applyFantasyTransfers,
  getFantasyMatchdayPicks,
  getFantasyMatchdayPoints,
  getFantasyPlayerModeLeaderboard,
  getFantasyPlayerModeRules,
  getFantasyPlayerPool,
  getFantasyPlayerSquad,
  getTeams,
  saveFantasyMatchdayPicks,
  saveFantasyPlayerSquad,
} from "@/lib/api";
import {
  FANTASY_BUDGET_CAP,
  FANTASY_POSITION_LIMITS,
  FANTASY_SQUAD_SIZE,
  fantasyMatchdayPicksSchema,
  fantasySquadBuilderSchema,
  type FantasyMatchdayPicksFormValues,
  type FantasySquadBuilderFormValues,
} from "@/lib/fantasyValidation";

type FantasyTab = "squad" | "matchday" | "points" | "leaderboard" | "legacy";

type LegacyTeam = {
  id: number;
  name: string;
  logo_url: string;
};

type LegacyLeaderboardEntry = {
  username: string;
  points: number;
  teams: string[];
};

const API_BASE = "http://localhost:8000/api/v1";

function todayMatchdayKey(): string {
  return new Date().toISOString().slice(0, 10);
}

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}

async function legacyAuthedFetch<T>(token: string, path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...(init?.headers || {}),
      Authorization: `Bearer ${token}`,
    },
  });

  if (!res.ok) {
    const payload = await res.json().catch(() => null);
    throw new Error(payload?.detail || "Legacy fantasy request failed");
  }

  return res.json();
}

async function legacyFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);

  if (!res.ok) {
    const payload = await res.json().catch(() => null);
    throw new Error(payload?.detail || "Legacy fantasy request failed");
  }

  return res.json();
}

function normalizeBenchOrders(picks: FantasyMatchdayPick[]): FantasyMatchdayPick[] {
  const starters = picks
    .filter((pick) => pick.role === "starter")
    .map((pick) => ({ ...pick, bench_order: null }));

  const bench = picks
    .filter((pick) => pick.role === "bench")
    .sort((a, b) => {
      const aOrder = a.bench_order ?? 99;
      const bOrder = b.bench_order ?? 99;
      return aOrder - bOrder;
    })
    .map((pick, index) => ({ ...pick, bench_order: index + 1 }));

  return [...starters, ...bench];
}

function countByPosition(players: Array<{ position_key: string }>): Record<string, number> {
  return players.reduce<Record<string, number>>((acc, player) => {
    acc[player.position_key] = (acc[player.position_key] || 0) + 1;
    return acc;
  }, {});
}

function PlayerMiniBadge({
  name,
  logo,
}: {
  name: string;
  logo?: string | null;
}) {
  return (
    <div className="flex items-center gap-2 rounded-md border border-neutral-200 bg-white px-2 py-1 text-xs text-neutral-700 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-200">
      {logo ? (
        <Image src={logo} alt={name} width={18} height={18} className="h-[18px] w-[18px] rounded-full object-contain" />
      ) : (
        <div className="h-[18px] w-[18px] rounded-full bg-neutral-300 dark:bg-neutral-600" />
      )}
      <span className="truncate">{name}</span>
    </div>
  );
}

function MetricCard({
  title,
  value,
  subtitle,
}: {
  title: string;
  value: string | number;
  subtitle?: string;
}) {
  return (
    <div className="rounded-xl border border-neutral-200/80 bg-white/90 p-4 shadow-sm dark:border-neutral-800 dark:bg-neutral-900/70">
      <p className="text-xs uppercase tracking-wide text-neutral-500 dark:text-neutral-400">{title}</p>
      <p className="mt-2 text-2xl font-black text-neutral-900 dark:text-neutral-100">{value}</p>
      {subtitle ? <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">{subtitle}</p> : null}
    </div>
  );
}

export default function FantasyPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { isAuthenticated, loading: authLoading, token } = useAuth();

  const [activeTab, setActiveTab] = useState<FantasyTab>("squad");
  const [matchdayKey, setMatchdayKey] = useState<string>(todayMatchdayKey());
  const [poolSearch, setPoolSearch] = useState<string>("");
  const [positionFilter, setPositionFilter] = useState<string>("ALL");

  const [transferOutId, setTransferOutId] = useState<number | null>(null);
  const [transferInId, setTransferInId] = useState<number | null>(null);
  const [pendingTransfers, setPendingTransfers] = useState<FantasyTransferItem[]>([]);

  const [legacySelectedTeamIds, setLegacySelectedTeamIds] = useState<number[]>([]);

  const squadForm = useForm<FantasySquadBuilderFormValues>({
    resolver: zodResolver(fantasySquadBuilderSchema),
    defaultValues: {
      selected_players: [],
    },
  });

  const picksForm = useForm<FantasyMatchdayPicksFormValues>({
    resolver: zodResolver(fantasyMatchdayPicksSchema),
    defaultValues: {
      picks: [],
    },
  });

  const selectedSquadPlayers = squadForm.watch("selected_players");
  const watchedPicks = picksForm.watch("picks");

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push("/login");
    }
  }, [authLoading, isAuthenticated, router]);

  const rulesQuery = useQuery({
    queryKey: ["fantasy-player-mode-rules"],
    queryFn: getFantasyPlayerModeRules,
    enabled: isAuthenticated,
    staleTime: 120_000,
  });

  const poolQuery = useQuery({
    queryKey: ["fantasy-player-pool", poolSearch, positionFilter],
    queryFn: () =>
      getFantasyPlayerPool({
        search: poolSearch || undefined,
        position: positionFilter === "ALL" ? undefined : positionFilter,
        limit: 350,
      }),
    enabled: isAuthenticated,
    staleTime: 60_000,
  });

  const squadQuery = useQuery({
    queryKey: ["fantasy-player-squad", token],
    queryFn: () => getFantasyPlayerSquad(token as string),
    enabled: Boolean(token) && isAuthenticated,
    staleTime: 20_000,
  });

  const picksQuery = useQuery({
    queryKey: ["fantasy-player-picks", token, matchdayKey],
    queryFn: () => getFantasyMatchdayPicks(token as string, matchdayKey),
    enabled:
      Boolean(token) &&
      isAuthenticated &&
      (activeTab === "matchday" || activeTab === "points") &&
      (squadQuery.data?.players.length || 0) === FANTASY_SQUAD_SIZE,
    staleTime: 10_000,
  });

  const pointsQuery = useQuery({
    queryKey: ["fantasy-player-points", token, matchdayKey],
    queryFn: () => getFantasyMatchdayPoints(token as string, matchdayKey, true),
    enabled:
      Boolean(token) &&
      isAuthenticated &&
      activeTab === "points" &&
      (squadQuery.data?.players.length || 0) === FANTASY_SQUAD_SIZE,
    staleTime: 5_000,
  });

  const leaderboardQuery = useQuery({
    queryKey: ["fantasy-player-leaderboard", matchdayKey],
    queryFn: () => getFantasyPlayerModeLeaderboard(matchdayKey, true),
    enabled: isAuthenticated && activeTab === "leaderboard",
    staleTime: 15_000,
  });

  const legacyTeamsQuery = useQuery({
    queryKey: ["legacy-fantasy-teams"],
    queryFn: () => getTeams(),
    enabled: isAuthenticated && activeTab === "legacy",
    staleTime: 60_000,
  });

  const legacyMyTeamsQuery = useQuery({
    queryKey: ["legacy-fantasy-my-teams", token],
    queryFn: () => legacyAuthedFetch<LegacyTeam[]>(token as string, "/fantasy/my-teams"),
    enabled: Boolean(token) && isAuthenticated && activeTab === "legacy",
    staleTime: 20_000,
  });

  const legacyPointsQuery = useQuery({
    queryKey: ["legacy-fantasy-my-points", token],
    queryFn: () => legacyAuthedFetch<{ points: number }>(token as string, "/fantasy/my-points"),
    enabled: Boolean(token) && isAuthenticated && activeTab === "legacy",
    staleTime: 20_000,
  });

  const legacyLeaderboardQuery = useQuery({
    queryKey: ["legacy-fantasy-leaderboard"],
    queryFn: () => legacyFetch<LegacyLeaderboardEntry[]>("/fantasy/leaderboard"),
    enabled: isAuthenticated && activeTab === "legacy",
    staleTime: 20_000,
  });

  useEffect(() => {
    if (!squadQuery.data) return;

    const mapped = squadQuery.data.players.map((player) => ({
      player_id: player.player_id,
      position_key: player.position_key as "GK" | "DEF" | "MID" | "FWD",
      team_id: player.team_id,
      price: player.purchase_price,
    }));

    squadForm.reset({ selected_players: mapped });
  }, [squadForm, squadQuery.data]);

  useEffect(() => {
    if (!picksQuery.data) return;

    const mapped = picksQuery.data.picks.map((pick) => ({
      player_id: pick.player_id,
      position_key: pick.position_key as "GK" | "DEF" | "MID" | "FWD",
      role: pick.role,
      bench_order: pick.bench_order ?? null,
      is_captain: pick.is_captain,
      is_vice_captain: pick.is_vice_captain,
    }));

    picksForm.reset({ picks: mapped });
  }, [picksForm, picksQuery.data]);

  useEffect(() => {
    if (!legacyMyTeamsQuery.data) return;
    setLegacySelectedTeamIds(legacyMyTeamsQuery.data.map((team) => team.id));
  }, [legacyMyTeamsQuery.data]);

  const poolById = useMemo(() => {
    const map = new Map<number, FantasyPlayerPoolItem>();
    for (const player of poolQuery.data || []) {
      map.set(player.player_id, player);
    }
    return map;
  }, [poolQuery.data]);

  const squadById = useMemo(() => {
    const map = new Map<number, FantasySquadPlayer>();
    for (const player of squadQuery.data?.players || []) {
      map.set(player.player_id, player);
    }
    return map;
  }, [squadQuery.data?.players]);

  const budgetCap = rulesQuery.data?.budget_cap ?? FANTASY_BUDGET_CAP;
  const currentSpent = selectedSquadPlayers.reduce((total, player) => total + player.price, 0);
  const currentRemaining = budgetCap - currentSpent;
  const selectedPositionCounts = countByPosition(selectedSquadPlayers);

  const startersCount = watchedPicks.filter((pick) => pick.role === "starter").length;
  const benchCount = watchedPicks.filter((pick) => pick.role === "bench").length;

  const saveSquadMutation = useMutation({
    mutationFn: async (formValues: FantasySquadBuilderFormValues) => {
      if (!token) throw new Error("Authentication token missing");
      const playerIds = formValues.selected_players.map((player) => player.player_id);
      return saveFantasyPlayerSquad(token, playerIds);
    },
    onSuccess: () => {
      toast.success("Player squad saved successfully.");
      setPendingTransfers([]);
      setTransferInId(null);
      setTransferOutId(null);
      queryClient.invalidateQueries({ queryKey: ["fantasy-player-squad"] });
      queryClient.invalidateQueries({ queryKey: ["fantasy-player-picks"] });
      queryClient.invalidateQueries({ queryKey: ["fantasy-player-points"] });
      queryClient.invalidateQueries({ queryKey: ["fantasy-player-leaderboard"] });
    },
    onError: (error) => {
      toast.error(getErrorMessage(error, "Could not save squad"));
    },
  });

  const savePicksMutation = useMutation({
    mutationFn: async (values: FantasyMatchdayPicksFormValues) => {
      if (!token) throw new Error("Authentication token missing");
      const normalized = normalizeBenchOrders(values.picks as FantasyMatchdayPick[]);
      return saveFantasyMatchdayPicks(token, matchdayKey, normalized);
    },
    onSuccess: () => {
      toast.success("Matchday picks saved.");
      queryClient.invalidateQueries({ queryKey: ["fantasy-player-picks"] });
      queryClient.invalidateQueries({ queryKey: ["fantasy-player-points"] });
      queryClient.invalidateQueries({ queryKey: ["fantasy-player-leaderboard"] });
    },
    onError: (error) => {
      toast.error(getErrorMessage(error, "Could not save picks"));
    },
  });

  const transferMutation = useMutation({
    mutationFn: async (transfers: FantasyTransferItem[]) => {
      if (!token) throw new Error("Authentication token missing");
      return applyFantasyTransfers(token, matchdayKey, transfers);
    },
    onSuccess: (payload) => {
      toast.success(`Transfers applied. Total matchday penalty: ${payload.penalty_points} pts.`);
      setPendingTransfers([]);
      setTransferInId(null);
      setTransferOutId(null);
      queryClient.invalidateQueries({ queryKey: ["fantasy-player-squad"] });
      queryClient.invalidateQueries({ queryKey: ["fantasy-player-picks"] });
      queryClient.invalidateQueries({ queryKey: ["fantasy-player-points"] });
      queryClient.invalidateQueries({ queryKey: ["fantasy-player-leaderboard"] });
    },
    onError: (error) => {
      toast.error(getErrorMessage(error, "Could not apply transfers"));
    },
  });

  const saveLegacyMutation = useMutation({
    mutationFn: async (teamIds: number[]) => {
      if (!token) throw new Error("Authentication token missing");
      return legacyAuthedFetch<{ message: string }>(token, "/fantasy/select-teams", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ team_ids: teamIds }),
      });
    },
    onSuccess: () => {
      toast.success("Legacy team selection saved.");
      queryClient.invalidateQueries({ queryKey: ["legacy-fantasy-my-teams"] });
      queryClient.invalidateQueries({ queryKey: ["legacy-fantasy-my-points"] });
      queryClient.invalidateQueries({ queryKey: ["legacy-fantasy-leaderboard"] });
    },
    onError: (error) => {
      toast.error(getErrorMessage(error, "Could not save legacy team selection"));
    },
  });

  const onSubmitSquad = squadForm.handleSubmit(
    (values) => {
      saveSquadMutation.mutate(values);
    },
    () => {
      const message = squadForm.formState.errors.selected_players?.message;
      toast.error(message || "Squad validation failed. Check positions, budget, and team limits.");
    }
  );

  const onSubmitPicks = picksForm.handleSubmit(
    (values) => {
      savePicksMutation.mutate(values);
    },
    () => {
      const message = picksForm.formState.errors.picks?.message;
      toast.error(message || "Matchday picks are invalid.");
    }
  );

  const togglePoolPlayer = (player: FantasyPlayerPoolItem) => {
    const current = squadForm.getValues("selected_players");
    const exists = current.some((selected) => selected.player_id === player.player_id);

    if (exists) {
      const next = current.filter((selected) => selected.player_id !== player.player_id);
      squadForm.setValue("selected_players", next, { shouldDirty: true });
      return;
    }

    if (current.length >= FANTASY_SQUAD_SIZE) {
      toast.error(`You can only select ${FANTASY_SQUAD_SIZE} players.`);
      return;
    }

    const next = [
      ...current,
      {
        player_id: player.player_id,
        position_key: player.position_key as "GK" | "DEF" | "MID" | "FWD",
        team_id: player.team_id,
        price: player.price,
      },
    ];

    squadForm.setValue("selected_players", next, { shouldDirty: true });
  };

  const setPickRole = (playerId: number, role: "starter" | "bench") => {
    const current = picksForm.getValues("picks");
    const next = current.map((pick) => {
      if (pick.player_id !== playerId) {
        return pick;
      }
      return {
        ...pick,
        role,
        bench_order: role === "bench" ? pick.bench_order ?? 4 : null,
      };
    });

    picksForm.setValue("picks", normalizeBenchOrders(next), { shouldDirty: true });
  };

  const setCaptain = (playerId: number) => {
    const current = picksForm.getValues("picks");
    const next = current.map((pick) => ({
      ...pick,
      is_captain: pick.player_id === playerId,
    }));
    picksForm.setValue("picks", next, { shouldDirty: true });
  };

  const setViceCaptain = (playerId: number) => {
    const current = picksForm.getValues("picks");
    const next = current.map((pick) => ({
      ...pick,
      is_vice_captain: pick.player_id === playerId,
    }));
    picksForm.setValue("picks", next, { shouldDirty: true });
  };

  const addTransferPair = () => {
    if (!transferOutId || !transferInId) {
      toast.error("Choose both outgoing and incoming players.");
      return;
    }

    const duplicateOut = pendingTransfers.some((item) => item.out_player_id === transferOutId);
    const duplicateIn = pendingTransfers.some((item) => item.in_player_id === transferInId);

    if (duplicateOut || duplicateIn) {
      toast.error("Transfer list already contains one of these players.");
      return;
    }

    setPendingTransfers((prev) => [...prev, { out_player_id: transferOutId, in_player_id: transferInId }]);
    setTransferOutId(null);
    setTransferInId(null);
  };

  const removeTransferPair = (index: number) => {
    setPendingTransfers((prev) => prev.filter((_, idx) => idx !== index));
  };

  const saveTransfers = () => {
    if (pendingTransfers.length === 0) {
      toast.error("Add at least one transfer before submitting.");
      return;
    }
    transferMutation.mutate(pendingTransfers);
  };

  const toggleLegacyTeam = (teamId: number) => {
    setLegacySelectedTeamIds((prev) => {
      if (prev.includes(teamId)) {
        return prev.filter((id) => id !== teamId);
      }
      if (prev.length >= 5) {
        toast.error("Legacy mode allows exactly 5 teams.");
        return prev;
      }
      return [...prev, teamId];
    });
  };

  if (authLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[radial-gradient(circle_at_top,_#edf6ff_0%,_#f6f8fb_42%,_#eef1f5_100%)] text-neutral-700 dark:bg-[radial-gradient(circle_at_top,_#162233_0%,_#0f1118_40%,_#0b0d11_100%)] dark:text-neutral-300">
        Loading fantasy hub...
      </main>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  const squadSize = selectedSquadPlayers.length;
  const hasFullSquad = squadSize === FANTASY_SQUAD_SIZE;

  const transferOutPlayer = transferOutId ? squadById.get(transferOutId) : null;
  const activeSquadIds = new Set((squadQuery.data?.players || []).map((player) => player.player_id));

  const incomingCandidates = (poolQuery.data || []).filter((player) => {
    if (activeSquadIds.has(player.player_id)) return false;
    if (!transferOutPlayer) return true;
    return player.position_key === transferOutPlayer.position_key;
  });

  const legacyTeams = (legacyTeamsQuery.data || []).map((team) => ({
    id: team.id,
    name: team.name,
    logo_url: team.logo_url,
  }));

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top,_#edf6ff_0%,_#f6f8fb_42%,_#eef1f5_100%)] px-4 py-6 dark:bg-[radial-gradient(circle_at_top,_#162233_0%,_#0f1118_40%,_#0b0d11_100%)] md:px-8 md:py-10">
      <div className="mx-auto max-w-7xl space-y-6">
        <header className="rounded-2xl border border-sky-100/70 bg-white/85 p-6 shadow-lg shadow-sky-100/40 backdrop-blur dark:border-sky-900/30 dark:bg-neutral-900/70 dark:shadow-none">
          <h1 className="text-3xl font-black tracking-tight text-neutral-900 dark:text-neutral-100 md:text-4xl">
            Fantasy Manager
          </h1>
          <p className="mt-2 text-sm text-neutral-600 dark:text-neutral-300">
            Player-based salary cap mode for Top 5 leagues plus UCL. Drag-and-drop is intentionally skipped for now to keep the core flow stable.
          </p>
        </header>

        <section className="grid gap-3 md:grid-cols-4">
          <MetricCard title="Budget Spent" value={currentSpent.toFixed(2)} subtitle={`Cap ${budgetCap.toFixed(2)}`} />
          <MetricCard title="Budget Left" value={currentRemaining.toFixed(2)} subtitle={currentRemaining >= 0 ? "In range" : "Over budget"} />
          <MetricCard title="Squad Size" value={`${squadSize}/${FANTASY_SQUAD_SIZE}`} subtitle="Target 15 players" />
          <MetricCard title="Matchday" value={matchdayKey} subtitle="UTC date window" />
        </section>

        <section className="rounded-2xl border border-neutral-200 bg-white/90 p-4 shadow-sm dark:border-neutral-800 dark:bg-neutral-900/75">
          <div className="flex flex-wrap gap-2">
            {([
              ["squad", "Squad Builder"],
              ["matchday", "Matchday Picks & Transfers"],
              ["points", "Matchday Points"],
              ["leaderboard", "Leaderboard"],
              ["legacy", "Legacy Team Mode"],
            ] as Array<[FantasyTab, string]>).map(([tabKey, label]) => (
              <button
                key={tabKey}
                onClick={() => setActiveTab(tabKey)}
                className={`rounded-lg px-4 py-2 text-sm font-semibold transition ${
                  activeTab === tabKey
                    ? "bg-sky-600 text-white"
                    : "bg-neutral-100 text-neutral-700 hover:bg-sky-100 dark:bg-neutral-800 dark:text-neutral-200 dark:hover:bg-neutral-700"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </section>

        <section className="rounded-2xl border border-neutral-200 bg-white/90 p-5 shadow-sm dark:border-neutral-800 dark:bg-neutral-900/75">
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <label className="text-sm font-medium text-neutral-600 dark:text-neutral-300">Matchday</label>
            <input
              type="date"
              value={matchdayKey}
              onChange={(event) => setMatchdayKey(event.target.value)}
              className="rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-700 dark:border-neutral-700 dark:bg-neutral-950 dark:text-neutral-200"
            />
          </div>

          {activeTab === "squad" && (
            <div className="space-y-6">
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                {Object.entries(FANTASY_POSITION_LIMITS).map(([position, limit]) => (
                  <MetricCard
                    key={position}
                    title={`${position} Slots`}
                    value={`${selectedPositionCounts[position] || 0}/${limit}`}
                    subtitle="Required by rules"
                  />
                ))}
              </div>

              <form onSubmit={onSubmitSquad} className="space-y-4">
                <div className="flex flex-wrap items-center gap-3">
                  <input
                    type="text"
                    placeholder="Search player"
                    value={poolSearch}
                    onChange={(event) => setPoolSearch(event.target.value)}
                    className="min-w-[220px] rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-700 dark:border-neutral-700 dark:bg-neutral-950 dark:text-neutral-200"
                  />

                  <select
                    value={positionFilter}
                    onChange={(event) => setPositionFilter(event.target.value)}
                    className="rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-700 dark:border-neutral-700 dark:bg-neutral-950 dark:text-neutral-200"
                  >
                    <option value="ALL">All positions</option>
                    <option value="GK">GK</option>
                    <option value="DEF">DEF</option>
                    <option value="MID">MID</option>
                    <option value="FWD">FWD</option>
                  </select>

                  <button
                    type="submit"
                    disabled={saveSquadMutation.isPending}
                    className="rounded-md bg-sky-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-sky-700 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {saveSquadMutation.isPending ? "Saving..." : "Save Squad"}
                  </button>
                </div>

                {squadForm.formState.errors.selected_players?.message ? (
                  <p className="text-sm text-red-600 dark:text-red-400">{squadForm.formState.errors.selected_players.message}</p>
                ) : null}

                <div className="max-h-[420px] overflow-auto rounded-xl border border-neutral-200 dark:border-neutral-800">
                  <table className="w-full text-left text-sm">
                    <thead className="sticky top-0 bg-neutral-100 dark:bg-neutral-800">
                      <tr>
                        <th className="px-3 py-2">Player</th>
                        <th className="px-3 py-2">Pos</th>
                        <th className="px-3 py-2">Team</th>
                        <th className="px-3 py-2">Price</th>
                        <th className="px-3 py-2">Form</th>
                        <th className="px-3 py-2">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(poolQuery.data || []).map((player) => {
                        const isSelected = selectedSquadPlayers.some((entry) => entry.player_id === player.player_id);
                        return (
                          <tr key={player.player_id} className="border-t border-neutral-200 dark:border-neutral-800">
                            <td className="px-3 py-2 font-medium text-neutral-800 dark:text-neutral-100">{player.player_name}</td>
                            <td className="px-3 py-2">{player.position_key}</td>
                            <td className="px-3 py-2">
                              <div className="flex items-center gap-2">
                                {player.team_logo ? (
                                  <Image
                                    src={player.team_logo}
                                    alt={player.team_name}
                                    width={18}
                                    height={18}
                                    className="h-[18px] w-[18px] rounded-full object-contain"
                                  />
                                ) : null}
                                <span>{player.team_name}</span>
                              </div>
                            </td>
                            <td className="px-3 py-2">{player.price.toFixed(2)}</td>
                            <td className="px-3 py-2 text-xs text-neutral-500 dark:text-neutral-400">
                              G {player.goals_season} | A {player.assists_season} | Min {player.minutes_played}
                            </td>
                            <td className="px-3 py-2">
                              <button
                                type="button"
                                onClick={() => togglePoolPlayer(player)}
                                className={`rounded px-3 py-1 text-xs font-semibold transition ${
                                  isSelected
                                    ? "bg-red-100 text-red-700 hover:bg-red-200 dark:bg-red-900/40 dark:text-red-300"
                                    : "bg-sky-100 text-sky-700 hover:bg-sky-200 dark:bg-sky-900/40 dark:text-sky-300"
                                }`}
                              >
                                {isSelected ? "Remove" : "Add"}
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                {poolQuery.isLoading ? <p className="text-sm text-neutral-500">Loading player pool...</p> : null}
                {poolQuery.isError ? (
                  <p className="text-sm text-red-600 dark:text-red-400">{getErrorMessage(poolQuery.error, "Could not load pool")}</p>
                ) : null}

                <div className="grid gap-2 rounded-xl border border-neutral-200 bg-neutral-50 p-3 dark:border-neutral-800 dark:bg-neutral-950/40 md:grid-cols-3">
                  {selectedSquadPlayers.map((selected) => {
                    const poolItem = poolById.get(selected.player_id);
                    const fallbackName = `Player #${selected.player_id}`;
                    return (
                      <div key={selected.player_id} className="flex items-center justify-between rounded-md border border-neutral-200 bg-white px-3 py-2 text-xs dark:border-neutral-800 dark:bg-neutral-900">
                        <div>
                          <p className="font-semibold text-neutral-800 dark:text-neutral-100">{poolItem?.player_name || fallbackName}</p>
                          <p className="text-neutral-500 dark:text-neutral-400">{selected.position_key} • {poolItem?.team_name || "Team"}</p>
                        </div>
                        <p className="font-semibold text-neutral-700 dark:text-neutral-200">{selected.price.toFixed(2)}</p>
                      </div>
                    );
                  })}
                </div>
              </form>
            </div>
          )}

          {activeTab === "matchday" && (
            <div className="space-y-6">
              {!hasFullSquad ? (
                <p className="rounded-md bg-amber-100 px-3 py-2 text-sm text-amber-800 dark:bg-amber-900/30 dark:text-amber-200">
                  Build and save a full 15-player squad first.
                </p>
              ) : null}

              <div className="grid gap-4 md:grid-cols-2">
                <MetricCard title="Starters" value={`${startersCount}/11`} subtitle="Formation rules apply" />
                <MetricCard title="Bench" value={`${benchCount}/4`} subtitle="Bench order 1 to 4" />
              </div>

              <form onSubmit={onSubmitPicks} className="space-y-4">
                <div className="max-h-[420px] overflow-auto rounded-xl border border-neutral-200 dark:border-neutral-800">
                  <table className="w-full text-left text-sm">
                    <thead className="sticky top-0 bg-neutral-100 dark:bg-neutral-800">
                      <tr>
                        <th className="px-3 py-2">Player</th>
                        <th className="px-3 py-2">Pos</th>
                        <th className="px-3 py-2">Role</th>
                        <th className="px-3 py-2">Bench</th>
                        <th className="px-3 py-2">Captain</th>
                        <th className="px-3 py-2">Vice</th>
                      </tr>
                    </thead>
                    <tbody>
                      {watchedPicks.map((pick) => {
                        const squadPlayer = squadById.get(pick.player_id);
                        const displayName = squadPlayer?.player_name || `Player #${pick.player_id}`;
                        return (
                          <tr key={pick.player_id} className="border-t border-neutral-200 dark:border-neutral-800">
                            <td className="px-3 py-2 font-medium text-neutral-800 dark:text-neutral-100">{displayName}</td>
                            <td className="px-3 py-2">{pick.position_key}</td>
                            <td className="px-3 py-2">
                              <select
                                value={pick.role}
                                onChange={(event) => setPickRole(pick.player_id, event.target.value as "starter" | "bench")}
                                className="rounded border border-neutral-300 bg-white px-2 py-1 text-xs dark:border-neutral-700 dark:bg-neutral-900"
                              >
                                <option value="starter">Starter</option>
                                <option value="bench">Bench</option>
                              </select>
                            </td>
                            <td className="px-3 py-2">
                              {pick.role === "bench" ? (
                                <input
                                  type="number"
                                  min={1}
                                  max={4}
                                  value={pick.bench_order ?? 4}
                                  onChange={(event) => {
                                    const value = Number(event.target.value);
                                    const current = picksForm.getValues("picks");
                                    const next = current.map((entry) =>
                                      entry.player_id === pick.player_id
                                        ? { ...entry, bench_order: Number.isFinite(value) ? value : 4 }
                                        : entry
                                    );
                                    picksForm.setValue("picks", normalizeBenchOrders(next), { shouldDirty: true });
                                  }}
                                  className="w-16 rounded border border-neutral-300 bg-white px-2 py-1 text-xs dark:border-neutral-700 dark:bg-neutral-900"
                                />
                              ) : (
                                <span className="text-neutral-400">-</span>
                              )}
                            </td>
                            <td className="px-3 py-2">
                              <input
                                type="radio"
                                name="captain"
                                checked={pick.is_captain}
                                onChange={() => setCaptain(pick.player_id)}
                                disabled={pick.role !== "starter"}
                              />
                            </td>
                            <td className="px-3 py-2">
                              <input
                                type="radio"
                                name="vice-captain"
                                checked={pick.is_vice_captain}
                                onChange={() => setViceCaptain(pick.player_id)}
                              />
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                {picksForm.formState.errors.picks?.message ? (
                  <p className="text-sm text-red-600 dark:text-red-400">{picksForm.formState.errors.picks.message}</p>
                ) : null}

                <div className="flex flex-wrap gap-3">
                  <button
                    type="submit"
                    disabled={savePicksMutation.isPending || picksQuery.data?.is_locked}
                    className="rounded-md bg-sky-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-sky-700 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {savePicksMutation.isPending ? "Saving picks..." : "Save Matchday Picks"}
                  </button>

                  <button
                    type="button"
                    onClick={() => picksQuery.refetch()}
                    className="rounded-md bg-neutral-200 px-4 py-2 text-sm font-semibold text-neutral-700 hover:bg-neutral-300 dark:bg-neutral-800 dark:text-neutral-200 dark:hover:bg-neutral-700"
                  >
                    Reload Picks
                  </button>

                  {picksQuery.data?.is_locked ? (
                    <p className="self-center text-sm text-red-600 dark:text-red-400">Deadline locked for this matchday.</p>
                  ) : null}
                </div>
              </form>

              <div className="space-y-3 rounded-xl border border-neutral-200 bg-neutral-50 p-4 dark:border-neutral-800 dark:bg-neutral-950/40">
                <h3 className="text-lg font-bold text-neutral-800 dark:text-neutral-100">Transfers</h3>
                <p className="text-xs text-neutral-500 dark:text-neutral-400">
                  Transfer rules are enforced server-side: position-for-position swaps, budget cap, max 3 from the same team, and deadline lock.
                </p>

                <div className="grid gap-3 md:grid-cols-3">
                  <select
                    value={transferOutId ?? ""}
                    onChange={(event) => setTransferOutId(event.target.value ? Number(event.target.value) : null)}
                    className="rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900"
                  >
                    <option value="">Outgoing player</option>
                    {(squadQuery.data?.players || []).map((player) => (
                      <option key={player.player_id} value={player.player_id}>
                        {player.player_name} ({player.position_key})
                      </option>
                    ))}
                  </select>

                  <select
                    value={transferInId ?? ""}
                    onChange={(event) => setTransferInId(event.target.value ? Number(event.target.value) : null)}
                    className="rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900"
                  >
                    <option value="">Incoming player</option>
                    {incomingCandidates.map((player) => (
                      <option key={player.player_id} value={player.player_id}>
                        {player.player_name} ({player.position_key}) - {player.price.toFixed(2)}
                      </option>
                    ))}
                  </select>

                  <button
                    type="button"
                    onClick={addTransferPair}
                    className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700"
                  >
                    Add Transfer
                  </button>
                </div>

                <div className="space-y-2">
                  {pendingTransfers.map((transfer, index) => {
                    const outPlayer = squadById.get(transfer.out_player_id);
                    const inPlayer = poolById.get(transfer.in_player_id);
                    return (
                      <div key={`${transfer.out_player_id}-${transfer.in_player_id}`} className="flex items-center justify-between rounded-md border border-neutral-200 bg-white px-3 py-2 text-sm dark:border-neutral-800 dark:bg-neutral-900">
                        <span>
                          {outPlayer?.player_name || transfer.out_player_id} ➜ {inPlayer?.player_name || transfer.in_player_id}
                        </span>
                        <button
                          type="button"
                          onClick={() => removeTransferPair(index)}
                          className="rounded bg-red-100 px-2 py-1 text-xs font-semibold text-red-700 hover:bg-red-200 dark:bg-red-900/40 dark:text-red-300"
                        >
                          Remove
                        </button>
                      </div>
                    );
                  })}
                </div>

                <button
                  type="button"
                  onClick={saveTransfers}
                  disabled={transferMutation.isPending || picksQuery.data?.is_locked}
                  className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {transferMutation.isPending ? "Applying transfers..." : "Apply Transfers"}
                </button>
              </div>
            </div>
          )}

          {activeTab === "points" && (
            <div className="space-y-4">
              {pointsQuery.isLoading ? <p className="text-sm text-neutral-500">Computing points...</p> : null}
              {pointsQuery.isError ? (
                <p className="text-sm text-red-600 dark:text-red-400">
                  {getErrorMessage(pointsQuery.error, "Could not load matchday points")}
                </p>
              ) : null}

              {pointsQuery.data ? (
                <>
                  <div className="grid gap-3 md:grid-cols-3">
                    <MetricCard title="Total Points" value={pointsQuery.data.total_points} subtitle={pointsQuery.data.matchday_key} />
                    <MetricCard title="Transfer Penalty" value={pointsQuery.data.transfer_penalty} subtitle="Already deducted" />
                    <MetricCard title="Captain" value={pointsQuery.data.captain_player_id ?? "N/A"} subtitle="Player ID" />
                  </div>

                  <div className="max-h-[420px] overflow-auto rounded-xl border border-neutral-200 dark:border-neutral-800">
                    <table className="w-full text-left text-sm">
                      <thead className="sticky top-0 bg-neutral-100 dark:bg-neutral-800">
                        <tr>
                          <th className="px-3 py-2">Player</th>
                          <th className="px-3 py-2">Reason</th>
                          <th className="px-3 py-2">Match</th>
                          <th className="px-3 py-2">Points</th>
                        </tr>
                      </thead>
                      <tbody>
                        {pointsQuery.data.entries.map((entry, index) => (
                          <tr key={`${entry.player_id || "penalty"}-${index}`} className="border-t border-neutral-200 dark:border-neutral-800">
                            <td className="px-3 py-2">{entry.player_name || "Team"}</td>
                            <td className="px-3 py-2">{entry.reason}</td>
                            <td className="px-3 py-2">{entry.match_id ?? "-"}</td>
                            <td className={`px-3 py-2 font-semibold ${entry.points >= 0 ? "text-emerald-600" : "text-red-600"}`}>{entry.points}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              ) : null}
            </div>
          )}

          {activeTab === "leaderboard" && (
            <div className="space-y-4">
              {leaderboardQuery.isLoading ? <p className="text-sm text-neutral-500">Refreshing leaderboard...</p> : null}
              {leaderboardQuery.isError ? (
                <p className="text-sm text-red-600 dark:text-red-400">
                  {getErrorMessage(leaderboardQuery.error, "Could not load leaderboard")}
                </p>
              ) : null}

              {leaderboardQuery.data ? (
                <div className="max-h-[520px] overflow-auto rounded-xl border border-neutral-200 dark:border-neutral-800">
                  <table className="w-full text-left text-sm">
                    <thead className="sticky top-0 bg-neutral-100 dark:bg-neutral-800">
                      <tr>
                        <th className="px-3 py-2">Rank</th>
                        <th className="px-3 py-2">Manager</th>
                        <th className="px-3 py-2">Total</th>
                        <th className="px-3 py-2">Matchday</th>
                        <th className="px-3 py-2">Squad</th>
                      </tr>
                    </thead>
                    <tbody>
                      {leaderboardQuery.data.entries.map((entry) => (
                        <tr key={entry.username} className="border-t border-neutral-200 dark:border-neutral-800">
                          <td className="px-3 py-2 font-semibold">#{entry.rank}</td>
                          <td className="px-3 py-2">{entry.username}</td>
                          <td className="px-3 py-2 font-semibold text-sky-700 dark:text-sky-300">{entry.total_points}</td>
                          <td className="px-3 py-2">{entry.matchday_points}</td>
                          <td className="px-3 py-2">{entry.squad_size}/15</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}
            </div>
          )}

          {activeTab === "legacy" && (
            <div className="space-y-5">
              <div className="rounded-md border border-neutral-200 bg-neutral-50 px-3 py-2 text-sm text-neutral-600 dark:border-neutral-800 dark:bg-neutral-950/40 dark:text-neutral-300">
                Legacy team-based mode is preserved for compatibility while the new player-based manager mode is active.
              </div>

              <div className="grid gap-3 md:grid-cols-2">
                <MetricCard title="Legacy Teams" value={`${legacySelectedTeamIds.length}/5`} />
                <MetricCard title="Legacy Points" value={legacyPointsQuery.data?.points ?? 0} subtitle="Win 3 / Draw 1" />
              </div>

              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={() => saveLegacyMutation.mutate(legacySelectedTeamIds)}
                  disabled={legacySelectedTeamIds.length !== 5 || saveLegacyMutation.isPending}
                  className="rounded-md bg-sky-600 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-700 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {saveLegacyMutation.isPending ? "Saving..." : "Save Legacy Teams"}
                </button>
              </div>

              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {legacyTeams.map((team) => {
                  const selected = legacySelectedTeamIds.includes(team.id);
                  return (
                    <button
                      key={team.id}
                      type="button"
                      onClick={() => toggleLegacyTeam(team.id)}
                      className={`rounded-lg border p-3 text-left transition ${
                        selected
                          ? "border-sky-500 bg-sky-50 dark:border-sky-400 dark:bg-sky-900/20"
                          : "border-neutral-200 bg-white hover:border-sky-300 dark:border-neutral-800 dark:bg-neutral-900"
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        {team.logo_url ? (
                          <Image src={team.logo_url} alt={team.name} width={22} height={22} className="h-[22px] w-[22px] object-contain" />
                        ) : null}
                        <span className="text-sm font-medium text-neutral-800 dark:text-neutral-100">{team.name}</span>
                      </div>
                    </button>
                  );
                })}
              </div>

              <div className="max-h-[360px] overflow-auto rounded-xl border border-neutral-200 dark:border-neutral-800">
                <table className="w-full text-left text-sm">
                  <thead className="sticky top-0 bg-neutral-100 dark:bg-neutral-800">
                    <tr>
                      <th className="px-3 py-2">Rank</th>
                      <th className="px-3 py-2">Manager</th>
                      <th className="px-3 py-2">Points</th>
                      <th className="px-3 py-2">Teams</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(legacyLeaderboardQuery.data || []).map((entry, index) => (
                      <tr key={entry.username} className="border-t border-neutral-200 dark:border-neutral-800">
                        <td className="px-3 py-2">#{index + 1}</td>
                        <td className="px-3 py-2">{entry.username}</td>
                        <td className="px-3 py-2">{entry.points}</td>
                        <td className="px-3 py-2">
                          <div className="flex flex-wrap gap-1">
                            {entry.teams.map((teamName) => (
                              <PlayerMiniBadge key={`${entry.username}-${teamName}`} name={teamName} />
                            ))}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
