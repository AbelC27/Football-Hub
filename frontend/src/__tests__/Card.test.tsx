import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';

describe('Card', () => {
  it('renders children inside card content', async () => {
    const { Card, CardContent } = await import('@/components/ui/card');
    render(<Card><CardContent>Hello Card</CardContent></Card>);
    expect(screen.getByText('Hello Card')).toBeInTheDocument();
  });
});

describe('CardHeader + CardTitle', () => {
  it('renders title text', async () => {
    const { Card, CardHeader, CardTitle } = await import('@/components/ui/card');
    render(<Card><CardHeader><CardTitle>My Title</CardTitle></CardHeader></Card>);
    expect(screen.getByText('My Title')).toBeInTheDocument();
  });
});
