import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

vi.mock('next/link', () => ({
  default: ({ children, href }: any) => <a href={href}>{children}</a>,
}));

describe('MatchCard', () => {
  it('displays team names and score', async () => {
    const { MatchCard } = await import('@/components/MatchCard');
    const match = {
      id: 1,
      home_team_id: 10,
      away_team_id: 20,
      home_team_name: 'Real Madrid',
      away_team_name: 'Atletico Madrid',
      home_score: 2,
      away_score: 1,
      start_time: '2025-05-01T20:00:00Z',
      status: 'FT',
    } as any;
    render(<MatchCard match={match} />);
    expect(screen.getByText('Real Madrid')).toBeInTheDocument();
    expect(screen.getByText('Atletico Madrid')).toBeInTheDocument();
    expect(screen.getByText('FT')).toBeInTheDocument();
  });
});
