import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';

describe('PlayerCard', () => {
  it('displays player name and position', async () => {
    const { PlayerCard } = await import('@/components/PlayerCard');
    const player = { id: 1, name: 'Lionel Messi', position: 'Forward', team_id: 10 } as any;
    render(<PlayerCard player={player} />);
    expect(screen.getByText('Lionel Messi')).toBeInTheDocument();
    expect(screen.getByText(/Forward/)).toBeInTheDocument();
  });
});
