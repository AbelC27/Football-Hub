import { describe, it, expect } from 'vitest';

describe('cn utility', () => {
  it('merges tailwind classes correctly', async () => {
    const { cn } = await import('@/lib/utils');
    const result = cn('px-4 py-2', 'px-6');
    expect(result).toContain('px-6');
    expect(result).toContain('py-2');
    expect(result).not.toContain('px-4');
  });
});
