import { describe, expect, it } from 'vitest';
import { invitationCode } from './invitation';

describe('invitationCode', () => {
  it('normalises a bare code', () => {
    expect(invitationCode(' h5nk66uh ')).toBe('H5NK66UH');
  });

  it('drops control characters added by the clipboard', () => {
    expect(invitationCode('H5NK66UH\u0000')).toBe('H5NK66UH');
  });

  it('reads the code from the share message', () => {
    expect(
      invitationCode('Únete a mi grupo «Rancholandia» en Split Ranch con este código: H5NK66UH'),
    ).toBe('H5NK66UH');
  });

  it('reads the code from a link', () => {
    expect(invitationCode('splitranch://join/H5NK66UH/')).toBe('H5NK66UH');
  });

  it('returns an empty string without a valid code', () => {
    expect(invitationCode('H5NK')).toBe('');
    expect(invitationCode('H5NK66U1')).toBe('');
  });
});
