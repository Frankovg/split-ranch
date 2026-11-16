/**
 * The 8-character join code from what the user typed or pasted: a bare code, a link
 * ending in it, or the whole share message. Anything around it is ignored, including
 * control characters some clipboards add (the Android emulator appends a NUL byte).
 */
export function invitationCode(input: string): string {
  const tokens = input.toUpperCase().split(/[^A-Z0-9]+/);
  // The code is the last token in the share message, so search from the end
  return [...tokens].reverse().find((token) => /^[A-Z2-7]{8}$/.test(token)) ?? '';
}
