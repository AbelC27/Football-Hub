import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

vi.mock('@/context/AuthContext', () => ({
  useAuth: () => ({ user: null, logout: vi.fn(), isAuthenticated: false, loading: false }),
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

describe('Navbar', () => {
  it('renders app name and navigation links', async () => {
    const { Navbar } = await import('@/components/Navbar');
    render(<Navbar />);
    expect(screen.getByText('TerraBall')).toBeInTheDocument();
    expect(screen.getByText('Live Matches')).toBeInTheDocument();
    expect(screen.getByText('Teams')).toBeInTheDocument();
  });
});
