import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { TOKENS } from './tokens';

function parseBlock(css: string, selector: string): Record<string, string> {
  const start = css.indexOf(`${selector} {`);
  if (start === -1) throw new Error(`selector ${selector} not found`);
  const end = css.indexOf('}', start);
  const body = css.slice(start, end);
  const out: Record<string, string> = {};
  for (const m of body.matchAll(/--([\w-]+):\s*([^;]+);/g)) {
    if (m[1] && m[2] && m[1] !== 'radius') out[m[1]] = m[2].trim();
  }
  return out;
}

describe('theme tokens', () => {
  const css = readFileSync(resolve(__dirname, '../../global.css'), 'utf8');

  it('light tokens match global.css :root', () => {
    expect(parseBlock(css, ':root')).toEqual(TOKENS.light);
  });

  it('dark tokens match global.css .dark:root', () => {
    expect(parseBlock(css, '.dark:root')).toEqual(TOKENS.dark);
  });
});
