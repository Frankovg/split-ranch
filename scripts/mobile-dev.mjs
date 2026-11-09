#!/usr/bin/env node
/**
 * `pnpm mobile:dev`: starts Metro (expo start --dev-client) and, alongside it, keeps
 * `adb reverse` applied for the emulator. Metro keeps the terminal (keys a, r, j... work).
 */
import { spawn } from 'node:child_process';
import { PORTS, watch } from './adb-reverse.mjs';

console.log(`[adb-reverse] watching devices, forwarding tcp ${PORTS.join(', ')}`);
const stopWatching = watch();

// shell: true resolves pnpm.cmd on Windows.
const metro = spawn('pnpm --filter @split-ranch/mobile start', process.argv.slice(2), {
  stdio: 'inherit',
  shell: true,
});

const shutdown = (signal) => {
  stopWatching();
  if (!metro.killed) metro.kill(signal);
};
process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));

metro.on('exit', (code, signal) => {
  stopWatching();
  process.exit(code ?? (signal ? 1 : 0));
});
