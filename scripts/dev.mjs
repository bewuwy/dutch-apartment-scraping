#!/usr/bin/env node
import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';

const pythonBin = existsSync('.venv/bin/python') ? '.venv/bin/python' : 'python3';

console.log(`[dev] Starting backend server with ${pythonBin}...`);
const server = spawn(pythonBin, ['server.py'], {
  stdio: 'inherit',
});

console.log('[dev] Starting frontend dev server (Vite)...');
const vite = spawn('pnpm', ['--dir', 'web', 'dev'], {
  stdio: 'inherit',
});

function cleanup() {
  console.log('\n[dev] Shutting down development servers...');
  server.kill('SIGINT');
  vite.kill('SIGINT');
  process.exit(0);
}

process.on('SIGINT', cleanup);
process.on('SIGTERM', cleanup);
process.on('exit', cleanup);

server.on('close', (code) => {
  if (code !== 0 && code !== null) {
    console.error(`[dev] Backend server exited with code ${code}`);
  }
});

vite.on('close', (code) => {
  if (code !== 0 && code !== null) {
    console.error(`[dev] Frontend server exited with code ${code}`);
  }
});
