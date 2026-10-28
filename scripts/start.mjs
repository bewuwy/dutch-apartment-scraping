#!/usr/bin/env node
import { spawn, execSync } from 'node:child_process';
import { existsSync } from 'node:fs';

if (!existsSync('web/dist/index.html')) {
  console.log('[start] Web bundle not found. Building frontend...');
  execSync('pnpm --dir web build', { stdio: 'inherit' });
}

const pythonBin = existsSync('.venv/bin/python') ? '.venv/bin/python' : 'python3';
console.log(`[start] Starting server with ${pythonBin}...`);

const server = spawn(pythonBin, ['server.py', ...process.argv.slice(2)], {
  stdio: 'inherit',
});

function cleanup() {
  server.kill('SIGINT');
  process.exit(0);
}

process.on('SIGINT', cleanup);
process.on('SIGTERM', cleanup);

server.on('close', (code) => {
  process.exit(code ?? 0);
});
