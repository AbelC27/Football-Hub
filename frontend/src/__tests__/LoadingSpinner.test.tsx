import { render } from '@testing-library/react';
import { describe, it, expect } from 'vitest';

describe('LoadingSpinner', () => {
  it('renders without crashing', async () => {
    const { LoadingSpinner } = await import('@/components/LoadingSpinner');
    const { container } = render(<LoadingSpinner />);
    expect(container.querySelector('.animate-spin')).toBeInTheDocument();
  });
});

describe('MatchCardSkeleton', () => {
  it('renders placeholder skeleton', async () => {
    const { MatchCardSkeleton } = await import('@/components/LoadingSpinner');
    const { container } = render(<MatchCardSkeleton />);
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument();
  });
});
