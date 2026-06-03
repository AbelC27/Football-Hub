import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';

describe('Badge', () => {
  it('renders with correct tone class', async () => {
    const { Badge } = await import('@/components/ui/badge');
    const { container } = render(<Badge tone="success">Active</Badge>);
    expect(screen.getByText('Active')).toBeInTheDocument();
    expect(container.firstChild).toHaveClass('bg-emerald-100');
  });
});
