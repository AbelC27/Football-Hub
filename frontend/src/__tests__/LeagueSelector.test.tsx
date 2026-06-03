import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

describe('LeagueSelector', () => {
  it('renders leagues and handles selection', async () => {
    const { LeagueSelector } = await import('@/components/LeagueSelector');
    const leagues = [
      { id: 1, name: 'Premier League', country: 'England', logo_url: '' },
      { id: 2, name: 'La Liga', country: 'Spain', logo_url: '' },
    ] as any[];
    const onSelect = vi.fn();
    render(<LeagueSelector leagues={leagues} selectedLeague={null} onSelectLeague={onSelect} />);
    expect(screen.getByText('Premier League')).toBeInTheDocument();
    fireEvent.click(screen.getByText('La Liga'));
    expect(onSelect).toHaveBeenCalledWith(2);
  });
});
