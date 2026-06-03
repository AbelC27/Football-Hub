import { describe, it, expect } from 'vitest';

describe('fantasySquadBuilderSchema', () => {
  it('rejects empty squad', async () => {
    const { fantasySquadBuilderSchema } = await import('@/lib/fantasyValidation');
    const result = fantasySquadBuilderSchema.safeParse({ selected_players: [] });
    expect(result.success).toBe(false);
  });

  it('rejects duplicate players', async () => {
    const { fantasySquadBuilderSchema } = await import('@/lib/fantasyValidation');
    const player = { player_id: 1, position_key: 'MID', team_id: 1, price: 5 };
    const players = Array(15).fill(player);
    const result = fantasySquadBuilderSchema.safeParse({ selected_players: players });
    expect(result.success).toBe(false);
  });

  it('accepts valid squad', async () => {
    const { fantasySquadBuilderSchema } = await import('@/lib/fantasyValidation');
    const squad = [
      ...Array.from({ length: 2 }, (_, i) => ({ player_id: i + 1, position_key: 'GK' as const, team_id: i + 1, price: 5 })),
      ...Array.from({ length: 5 }, (_, i) => ({ player_id: i + 3, position_key: 'DEF' as const, team_id: i + 3, price: 5 })),
      ...Array.from({ length: 5 }, (_, i) => ({ player_id: i + 8, position_key: 'MID' as const, team_id: i + 8, price: 6 })),
      ...Array.from({ length: 3 }, (_, i) => ({ player_id: i + 13, position_key: 'FWD' as const, team_id: i + 13, price: 5 })),
    ];
    const result = fantasySquadBuilderSchema.safeParse({ selected_players: squad });
    expect(result.success).toBe(true);
  });
});

describe('Fantasy constants', () => {
  it('budget cap is 100', async () => {
    const { FANTASY_BUDGET_CAP, FANTASY_SQUAD_SIZE } = await import('@/lib/fantasyValidation');
    expect(FANTASY_BUDGET_CAP).toBe(100);
    expect(FANTASY_SQUAD_SIZE).toBe(15);
  });
});
