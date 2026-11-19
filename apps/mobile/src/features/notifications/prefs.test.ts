import { describe, expect, it } from 'vitest';
import { applyPrefs } from './prefs';

const ALL_ON = {
  enabled: true,
  expense_created: true,
  expense_changed: true,
  payments: true,
  member_joined: true,
};

describe('applyPrefs', () => {
  it('changes only the fields sent', () => {
    expect(applyPrefs(ALL_ON, { payments: false })).toEqual({ ...ALL_ON, payments: false });
    expect(applyPrefs(ALL_ON, { enabled: false, member_joined: null })).toEqual({ ...ALL_ON, enabled: false });
  });

  it('does not mutate the input', () => {
    const prefs = { ...ALL_ON };
    applyPrefs(prefs, { enabled: false });
    expect(prefs.enabled).toBe(true);
  });
});
