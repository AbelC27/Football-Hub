import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';

describe('TeamCard', () => {
  it('displays team name and stadium', async () => {
    const { TeamCard } = await import('@/components/TeamCard');
    const team = { id: 1, name: 'FC Barcelona', stadium: 'Camp Nou', logo_url: '' } as any;
    render(<TeamCard team={team} />);
    expect(screen.getByText('FC Barcelona')).toBeInTheDocument();
    expect(screen.getByText('Camp Nou')).toBeInTheDocument();
  });
});
