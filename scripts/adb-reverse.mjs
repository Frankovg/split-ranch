#!/usr/bin/env node
/**
 * Keeps `adb reverse` applied so the Android emulator (or a USB phone) reaches Metro and the
 * API on the PC's localhost. Emulators drop these rules on every restart.
 *
 *   node scripts/adb-reverse.mjs            apply once to every connected device
 *   node scripts/adb-reverse.mjs --watch    keep applying while devices come and go
 *
 * No adb or no device is not an error: the script waits (watch) or exits quietly (once).
 */
import { execFile } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';

const run = promisify(execFile);

/** Metro (8081) and the FastAPI backend (8000). Supabase is in the cloud: no local port. */
export const PORTS = [8081, 8000];
const WATCH_INTERVAL_MS = 3000;

function adbPath() {
  const sdk = process.env.ANDROID_HOME || process.env.ANDROID_SDK_ROOT;
  if (sdk) {
    const candidate = join(sdk, 'platform-tools', process.platform === 'win32' ? 'adb.exe' : 'adb');
    if (existsSync(candidate)) return candidate;
  }
  return 'adb'; // rely on PATH
}

const ADB = adbPath();

async function adb(args) {
  const { stdout } = await run(ADB, args, { timeout: 10_000, windowsHide: true });
  return stdout;
}

/** Serials of devices that are online ("device" state; skips "offline"/"unauthorized"). */
async function onlineDevices() {
  const out = await adb(['devices']);
  return out
    .split(/\r?\n/)
    .slice(1)
    .map((line) => line.trim().split(/\s+/))
    .filter(([serial, state]) => serial && state === 'device')
    .map(([serial]) => serial);
}

/** Applies the missing rules on one device. Returns the ports it had to add. */
async function ensureReverse(serial) {
  const existing = await adb(['-s', serial, 'reverse', '--list']);
  const missing = PORTS.filter((port) => !existing.includes(`tcp:${port} tcp:${port}`));
  for (const port of missing) {
    await adb(['-s', serial, 'reverse', `tcp:${port}`, `tcp:${port}`]);
  }
  return missing;
}

/** One pass over all devices. Logs only when something changed. */
export async function applyOnce({ quiet = false } = {}) {
  let devices;
  try {
    devices = await onlineDevices();
  } catch (error) {
    if (!quiet) console.log(`[adb-reverse] adb not available (${error.code ?? error.message}); skipping`);
    return false;
  }
  if (devices.length === 0 && !quiet) console.log('[adb-reverse] no Android device connected yet');
  for (const serial of devices) {
    try {
      const added = await ensureReverse(serial);
      if (added.length > 0) console.log(`[adb-reverse] ${serial}: forwarded tcp ${added.join(', ')}`);
    } catch (error) {
      // The device may still be booting; the next pass retries.
      console.log(`[adb-reverse] ${serial}: failed (${error.message.split('\n')[0]}), retrying`);
    }
  }
  return true;
}

/** Re-checks every few seconds; returns a function that stops the loop. */
export function watch() {
  let stopped = false;
  let timer;
  const tick = async () => {
    await applyOnce({ quiet: true });
    if (!stopped) timer = setTimeout(tick, WATCH_INTERVAL_MS);
  };
  void applyOnce().then(() => {
    if (!stopped) timer = setTimeout(tick, WATCH_INTERVAL_MS);
  });
  return () => {
    stopped = true;
    clearTimeout(timer);
  };
}

const isMain = process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) {
  if (process.argv.includes('--watch')) {
    console.log(`[adb-reverse] watching devices, forwarding tcp ${PORTS.join(', ')}`);
    watch();
  } else {
    await applyOnce();
  }
}
