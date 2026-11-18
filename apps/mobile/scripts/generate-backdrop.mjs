// Generates the screen backdrop images used by ScreenBackground
// (assets/backdrop-light.png, assets/backdrop-dark.png).
//
// The backdrop is a diagonal gradient between colours only a few 8-bit levels apart, so
// any renderer that rounds each pixel to the nearest level draws visible bands (and,
// because R/G/B step at different places, faintly tinted ones). Here every pixel gets a
// little random noise *before* rounding (dithering), which turns the band edges into an
// invisible grain. Neither react-native-svg nor the native gradient dither on Android.
//
// Colours come from src/theme/tokens.ts (light mode overrides its ends in stopsFor):
// re-run after changing card, background or accent.
// Run: node scripts/generate-backdrop.mjs
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { deflateSync } from 'node:zlib';

// Stretched to the screen. 9:20 like most current phones, at half their pixel size: the
// grain stays below what the eye can see.
const WIDTH = 540;
const HEIGHT = 1200;
const NOISE = 1.5; // dither amplitude in 8-bit levels (triangular distribution)
// Diagonal position (0..1) of the pure background stop: the start colour fades into it,
// then it blends into the end colour. Lower values give the green more of the screen.
const MID_STOP = 0.25;

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

/** Reads `name: 'H S% L%'` for one scheme block of src/theme/tokens.ts. */
function readTokens() {
  const source = readFileSync(join(root, 'src/theme/tokens.ts'), 'utf8');
  const tokens = {};
  for (const scheme of ['light', 'dark']) {
    const block = source.match(new RegExp(`\\n  ${scheme}: \\{([\\s\\S]*?)\\n  \\}`));
    if (!block) throw new Error(`Scheme "${scheme}" not found in tokens.ts`);
    tokens[scheme] = {};
    for (const [, name, h, s, l] of block[1].matchAll(
      /'?([\w-]+)'?: '([\d.]+) ([\d.]+)% ([\d.]+)%'/g,
    )) {
      tokens[scheme][name] = hslToRgb(Number(h), Number(s) / 100, Number(l) / 100);
    }
  }
  return tokens;
}

function hslToRgb(h, s, l) {
  const k = (n) => (n + h / 30) % 12;
  const a = s * Math.min(l, 1 - l);
  const f = (n) => l - a * Math.max(-1, Math.min(k(n) - 3, 9 - k(n), 1));
  return [f(0) * 255, f(8) * 255, f(4) * 255];
}

const mix = (a, b, t) => a.map((v, i) => v + (b[i] - v) * t);

// Small seeded PRNG (mulberry32) so the output is reproducible.
function prng(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Stops along the top-left → bottom-right diagonal: start at 0, mid at MID_STOP, end at 1. */
function colourAt(t, { start, mid, end }) {
  if (t >= MID_STOP) return mix(mid, end, (t - MID_STOP) / (1 - MID_STOP));
  return mix(start, mid, t / MID_STOP);
}

/**
 * Gradient stops per scheme. Dark uses the theme tokens as they are (card → background →
 * accent). Light has backdrop-only ends, because its card and accent tokens are too close
 * to the background to read as a gradient: a light grey corner and a deeper mint.
 */
function stopsFor(scheme, tokens) {
  const { card, background, accent } = tokens[scheme];
  if (scheme === 'dark') return { start: card, mid: background, end: accent };
  return { start: hslToRgb(150, 0.05, 0.89), mid: background, end: hslToRgb(162, 0.42, 0.82) };
}

const crcTable = Array.from({ length: 256 }, (_, n) => {
  let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});

function crc32(buf) {
  let c = 0xffffffff;
  for (const byte of buf) c = crcTable[(c ^ byte) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function chunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type, 'ascii'), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body));
  return Buffer.concat([len, body, crc]);
}

function backdropPng(stops, seed) {
  const rand = prng(seed);
  const stride = WIDTH * 3 + 1;
  const raw = Buffer.alloc(HEIGHT * stride);
  for (let y = 0; y < HEIGHT; y++) {
    raw[y * stride] = 0; // filter: none
    for (let x = 0; x < WIDTH; x++) {
      // Projection on the top-left → bottom-right diagonal in pixel space, matching how
      // react-native-svg drew x1=0 y1=0 → x2=1 y2=1 (exact for a 9:20 screen).
      const t = (x * WIDTH + y * HEIGHT) / (WIDTH * WIDTH + HEIGHT * HEIGHT);
      const colour = colourAt(t, stops);
      // One noise value for all channels: dithers luminance without adding colour speckle.
      const noise = (rand() + rand() - 1) * NOISE;
      for (let c = 0; c < 3; c++) {
        raw[y * stride + 1 + x * 3 + c] = Math.max(0, Math.min(255, Math.round(colour[c] + noise)));
      }
    }
  }
  const header = Buffer.alloc(13);
  header.writeUInt32BE(WIDTH, 0);
  header.writeUInt32BE(HEIGHT, 4);
  header[8] = 8; // bit depth
  header[9] = 2; // colour type: RGB
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', header),
    chunk('IDAT', deflateSync(raw, { level: 9 })),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}

const tokens = readTokens();
for (const [scheme, seed] of [
  ['light', 0x11],
  ['dark', 0xda],
]) {
  const name = `backdrop-${scheme}.png`;
  const png = backdropPng(stopsFor(scheme, tokens), seed);
  writeFileSync(join(root, 'assets', name), png);
  process.stdout.write(`Wrote assets/${name} (${Math.round(png.length / 1024)} KB)\n`);
}
