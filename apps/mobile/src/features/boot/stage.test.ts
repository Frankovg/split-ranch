import { describe, expect, it } from 'vitest';
import { bootStage, needsBootScreen, PREPARING_AFTER_MS, SLOW_AFTER_MS, WAKING_AFTER_MS } from './stage';

describe('bootStage', () => {
  it('escalates the message with the elapsed time', () => {
    expect(bootStage(0, 'waking')).toBe('quiet');
    expect(bootStage(PREPARING_AFTER_MS, 'waking')).toBe('preparing');
    expect(bootStage(WAKING_AFTER_MS, 'waking')).toBe('waking');
    expect(bootStage(SLOW_AFTER_MS, 'waking')).toBe('slow');
  });

  it('reports an unreachable API right away', () => {
    expect(bootStage(0, 'unreachable')).toBe('unreachable');
    expect(bootStage(SLOW_AFTER_MS, 'unreachable')).toBe('unreachable');
  });
});

describe('needsBootScreen', () => {
  it('shows while the API has not answered and nothing is cached', () => {
    expect(needsBootScreen('waking', false)).toBe(true);
    expect(needsBootScreen('unreachable', false)).toBe(true);
  });

  it('is skipped with cached data or an API that already answered', () => {
    expect(needsBootScreen('waking', true)).toBe(false);
    expect(needsBootScreen('awake', false)).toBe(false);
    expect(needsBootScreen('idle', false)).toBe(false);
  });
});
