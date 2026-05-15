import { z } from "zod";

export const FANTASY_BUDGET_CAP = 100;
export const FANTASY_SQUAD_SIZE = 15;

export const FANTASY_POSITION_LIMITS = {
  GK: 2,
  DEF: 5,
  MID: 5,
  FWD: 3,
} as const;

export const FANTASY_STARTING_LIMITS = {
  GK: { min: 1, max: 1 },
  DEF: { min: 3, max: 5 },
  MID: { min: 2, max: 5 },
  FWD: { min: 1, max: 3 },
} as const;

export const fantasySelectedPlayerSchema = z.object({
  player_id: z.number().int().positive(),
  position_key: z.enum(["GK", "DEF", "MID", "FWD"]),
  team_id: z.number().int().positive(),
  price: z.number().nonnegative(),
});

export const fantasySquadBuilderSchema = z
  .object({
    selected_players: z.array(fantasySelectedPlayerSchema),
  })
  .superRefine((payload, ctx) => {
    const players = payload.selected_players;

    if (players.length !== FANTASY_SQUAD_SIZE) {
      ctx.addIssue({
        code: "custom",
        message: `Select exactly ${FANTASY_SQUAD_SIZE} players.`,
      });
    }

    const ids = players.map((player) => player.player_id);
    if (new Set(ids).size !== ids.length) {
      ctx.addIssue({
        code: "custom",
        message: "Duplicate players are not allowed.",
      });
    }

    const positionCounts = players.reduce<Record<string, number>>((acc, player) => {
      acc[player.position_key] = (acc[player.position_key] || 0) + 1;
      return acc;
    }, {});

    for (const [position, required] of Object.entries(FANTASY_POSITION_LIMITS)) {
      if ((positionCounts[position] || 0) !== required) {
        ctx.addIssue({
          code: "custom",
          message: `Squad must include ${required} ${position} players.`,
        });
      }
    }

    const teamCounts = players.reduce<Record<number, number>>((acc, player) => {
      acc[player.team_id] = (acc[player.team_id] || 0) + 1;
      return acc;
    }, {});

    if (Object.values(teamCounts).some((count) => count > 3)) {
      ctx.addIssue({
        code: "custom",
        message: "Maximum 3 players from the same team.",
      });
    }

    const spent = players.reduce((total, player) => total + player.price, 0);
    if (spent > FANTASY_BUDGET_CAP) {
      ctx.addIssue({
        code: "custom",
        message: `Budget exceeded. Spent ${spent.toFixed(2)} / ${FANTASY_BUDGET_CAP.toFixed(2)}.`,
      });
    }
  });

export const fantasyMatchdayPickSchema = z.object({
  player_id: z.number().int().positive(),
  position_key: z.enum(["GK", "DEF", "MID", "FWD"]),
  role: z.enum(["starter", "bench"]),
  bench_order: z.number().int().min(1).max(4).nullable().optional(),
  is_captain: z.boolean(),
  is_vice_captain: z.boolean(),
});

export const fantasyMatchdayPicksSchema = z
  .object({
    picks: z.array(fantasyMatchdayPickSchema),
  })
  .superRefine((payload, ctx) => {
    if (payload.picks.length !== FANTASY_SQUAD_SIZE) {
      ctx.addIssue({
        code: "custom",
        message: "Matchday picks must include 15 squad players.",
      });
      return;
    }

    const starterPicks = payload.picks.filter((pick) => pick.role === "starter");
    const benchPicks = payload.picks.filter((pick) => pick.role === "bench");

    if (starterPicks.length !== 11 || benchPicks.length !== 4) {
      ctx.addIssue({
        code: "custom",
        message: "You need 11 starters and 4 bench players.",
      });
    }

    const benchOrders = benchPicks.map((pick) => pick.bench_order ?? 0).sort((a, b) => a - b);
    const validBenchOrders = [1, 2, 3, 4];
    if (JSON.stringify(benchOrders) !== JSON.stringify(validBenchOrders)) {
      ctx.addIssue({
        code: "custom",
        message: "Bench order must include 1, 2, 3, and 4 exactly once.",
      });
    }

    const captainPicks = payload.picks.filter((pick) => pick.is_captain);
    if (captainPicks.length !== 1) {
      ctx.addIssue({
        code: "custom",
        message: "Exactly one captain is required.",
      });
    }

    if (captainPicks.length === 1 && captainPicks[0].role !== "starter") {
      ctx.addIssue({
        code: "custom",
        message: "Captain must be part of the starting lineup.",
      });
    }

    const viceCaptainPicks = payload.picks.filter((pick) => pick.is_vice_captain);
    if (viceCaptainPicks.length > 1) {
      ctx.addIssue({
        code: "custom",
        message: "At most one vice-captain is allowed.",
      });
    }

    if (
      captainPicks.length === 1 &&
      viceCaptainPicks.length === 1 &&
      captainPicks[0].player_id === viceCaptainPicks[0].player_id
    ) {
      ctx.addIssue({
        code: "custom",
        message: "Captain and vice-captain must be different players.",
      });
    }

    const starterCounts = starterPicks.reduce<Record<string, number>>((acc, pick) => {
      acc[pick.position_key] = (acc[pick.position_key] || 0) + 1;
      return acc;
    }, {});

    for (const [position, limits] of Object.entries(FANTASY_STARTING_LIMITS)) {
      const count = starterCounts[position] || 0;
      if (count < limits.min || count > limits.max) {
        ctx.addIssue({
          code: "custom",
          message: `Starting lineup must include ${limits.min}-${limits.max} ${position} players.`,
        });
      }
    }
  });

export type FantasySquadBuilderFormValues = z.infer<typeof fantasySquadBuilderSchema>;
export type FantasyMatchdayPicksFormValues = z.infer<typeof fantasyMatchdayPicksSchema>;
