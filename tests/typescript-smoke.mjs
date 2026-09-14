import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

function fixture(run) {
  const directory = mkdtempSync(join(tmpdir(), 'safeexecute-typescript-'));
  try { run(directory); } finally { rmSync(directory, { recursive: true, force: true }); }
}

test('official compiler accepts valid code and rejects a real type mismatch', () => {
  fixture(directory => {
    const file = join(directory, 'check.ts');
    const compile = () => spawnSync('tsc', ['--noEmit', '--strict', '--target', 'ES2020', file], {
      cwd: directory, encoding: 'utf8', timeout: 30000,
    });
    writeFileSync(file, 'const answer: number = 42;\n');
    const valid = compile();
    assert.equal(valid.error, undefined);
    assert.equal(valid.status, 0, valid.stdout + valid.stderr);
    writeFileSync(file, 'const answer: number = "wrong type";\n');
    const invalid = compile();
    assert.equal(invalid.error, undefined);
    assert.notEqual(invalid.status, 0);
    assert.match(invalid.stdout + invalid.stderr, /TS2322/);
  });
});

test('npm scripts prefer project-local tools over the fallback and preserve failures', () => {
  fixture(directory => {
    mkdirSync(join(directory, 'node_modules', '.bin'), { recursive: true });
    writeFileSync(join(directory, 'package.json'), JSON.stringify({
      private: true, scripts: { typecheck: 'tsc' },
    }));
    // A sentinel verifies resolution only; the test above verifies compilation.
    writeFileSync(join(directory, 'node_modules', '.bin', 'tsc'),
      '#!/usr/bin/env node\nconsole.log("project-local-compiler"); process.exit(23);\n', { mode: 0o755 });
    const result = spawnSync('npm', ['run', 'typecheck', '--silent'], {
      cwd: directory, encoding: 'utf8', timeout: 30000,
    });
    assert.equal(result.error, undefined);
    assert.equal(result.status, 23, result.stdout + result.stderr);
    assert.match(result.stdout, /project-local-compiler/);
  });
});
