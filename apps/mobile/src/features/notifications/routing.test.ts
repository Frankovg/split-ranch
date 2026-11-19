import { describe, expect, it } from 'vitest';
import { notificationTarget } from './routing';

const G = '0193a7c2-0000-7000-8000-00000000aaaa';
const E = '0193a7c2-0000-7000-8000-00000000bbbb';

describe('notificationTarget', () => {
  it('accepts the group screens the API links to', () => {
    expect(notificationTarget({ url: `/group/${G}`, type: 'member_joined' })).toEqual({
      url: `/group/${G}`,
      groupId: G,
      type: 'member_joined',
    });
    expect(notificationTarget({ url: `/group/${G}/settle` })?.groupId).toBe(G);
    expect(notificationTarget({ url: `/group/${G}/expense/${E}`, type: 'expense_created' })).toEqual({
      url: `/group/${G}/expense/${E}`,
      groupId: G,
      type: 'expense_created',
    });
  });

  it('rejects anything else', () => {
    expect(notificationTarget(null)).toBeNull();
    expect(notificationTarget('x')).toBeNull();
    expect(notificationTarget({})).toBeNull();
    expect(notificationTarget({ url: 42 })).toBeNull();
    expect(notificationTarget({ url: 'https://evil.example' })).toBeNull();
    expect(notificationTarget({ url: `/group/${G}/settings` })).toBeNull();
    expect(notificationTarget({ url: `/group/not-a-uuid` })).toBeNull();
    expect(notificationTarget({ url: `/group/${G}/expense/${E}/extra` })).toBeNull();
  });
});
