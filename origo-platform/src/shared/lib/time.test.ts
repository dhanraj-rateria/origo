import { describe, expect, it } from 'vitest';
import { formatUtc, relativeTime } from './time';

describe('relativeTime', () => {
  it('formats recent seconds and minutes', () => {
    expect(relativeTime('2026-08-06T09:14:00Z', Date.parse('2026-08-06T09:14:10Z'))).toBe('now');
    expect(relativeTime('2026-08-06T09:13:00Z', Date.parse('2026-08-06T09:14:00Z'))).toBe('1m ago');
  });

  it('formats hours and days', () => {
    expect(relativeTime('2026-08-06T07:14:00Z', Date.parse('2026-08-06T09:14:00Z'))).toBe('2h ago');
    expect(relativeTime('2026-08-04T09:14:00Z', Date.parse('2026-08-06T09:14:00Z'))).toBe('2d ago');
  });
});

describe('formatUtc', () => {
  it('appends UTC', () => {
    expect(formatUtc('2026-08-06T09:14:00Z')).toContain('UTC');
  });
});
