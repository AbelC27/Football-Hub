import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';

describe('PredictionBadge', () => {
  it('normalizes probabilities to 100%', async () => {
    const { PredictionBadge } = await import('@/components/PredictionBadge');
    render(<PredictionBadge homeProb={50} drawProb={30} awayProb={20} />);
    expect(screen.getByText('50.00%')).toBeInTheDocument();
    expect(screen.getByText('30.00%')).toBeInTheDocument();
    expect(screen.getByText('20.00%')).toBeInTheDocument();
  });

  it('handles zero totals without crashing', async () => {
    const { PredictionBadge } = await import('@/components/PredictionBadge');
    const { container } = render(<PredictionBadge homeProb={0} drawProb={0} awayProb={0} />);
    expect(container).toBeInTheDocument();
  });
});
