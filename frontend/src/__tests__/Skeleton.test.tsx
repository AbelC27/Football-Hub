import { render } from '@testing-library/react';
import { describe, it, expect } from 'vitest';

describe('Skeleton', () => {
  it('renders with animate-pulse', async () => {
    const { Skeleton } = await import('@/components/ui/skeleton');
    const { container } = render(<Skeleton />);
    expect(container.firstChild).toHaveClass('animate-pulse');
  });
});
