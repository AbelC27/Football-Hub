import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

describe('SearchBar', () => {
  it('renders input with placeholder', async () => {
    const { SearchBar } = await import('@/components/SearchBar');
    const onSearch = vi.fn();
    render(<SearchBar onSearch={onSearch} placeholder="Search..." />);
    expect(screen.getByPlaceholderText('Search...')).toBeInTheDocument();
  });
});
