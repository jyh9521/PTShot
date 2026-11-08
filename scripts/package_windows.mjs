import fs from 'node:fs/promises';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
if (process.platform !== 'win32') throw new Error('Build on Windows x64');
const destination = path.join(root, 'dist', 'PTShot-M3E');
const resources = path.join(destination, 'resources');
const application = path.join(resources, 'app');
function python(args) {
  const result = spawnSync(process.env.PTSHOT_PYTHON || 'python', args, { cwd: root, stdio: 'inherit', windowsHide: true,
    env: { ...process.env, PYTHONUTF8: '1' } });
  if (result.status !== 0) throw new Error(`Python step failed: ${args.join(' ')}`);
}
python(['scripts/prepare_electron.py']);
python(['scripts/build_worker.py']);
// Merge only: rebuilding must never delete a user's output folder in the portable directory.
await fs.mkdir(application, { recursive: true });
await fs.cp(path.join(root, 'node_modules', 'electron', 'dist'), destination, { recursive: true });
await fs.copyFile(path.join(destination, 'electron.exe'), path.join(destination, 'PTShot.exe'));
await fs.unlink(path.join(destination, 'electron.exe'));
await fs.cp(path.join(root, 'desktop'), path.join(application, 'desktop'), { recursive: true });
await fs.cp(path.join(root, 'frontend-dist'), path.join(application, 'frontend-dist'), { recursive: true });
await fs.writeFile(path.join(application, 'package.json'), JSON.stringify({ name: 'ptshot', productName: 'PTShot', version: '0.2.0', main: 'desktop/main.cjs' }));
await fs.cp(path.join(root, 'build', 'desktop-worker', 'PTShotWorker'), path.join(resources, 'worker'), { recursive: true });
python(['scripts/bundle_tools.py', resources]);
for (const name of ['README.md', 'THIRD_PARTY.md', 'dependencies.lock.json']) await fs.copyFile(path.join(root, name), path.join(destination, name));
let notices = '';
for (const packageDirectory of await fs.readdir(path.join(root, 'node_modules'), { withFileTypes: true })) {
  if (!packageDirectory.isDirectory() || packageDirectory.name.startsWith('.')) continue;
  const parent = path.join(root, 'node_modules', packageDirectory.name);
  const packages = packageDirectory.name.startsWith('@') ? (await fs.readdir(parent)).map(name => path.join(parent, name)) : [parent];
  for (const directory of packages) {
    let metadata;
    try { metadata = JSON.parse(await fs.readFile(path.join(directory, 'package.json'), 'utf8')); } catch { continue; }
    for (const name of await fs.readdir(directory)) {
      if (!/^(LICENSE|LICENCE|NOTICE|COPYING)(\.|$)/i.test(name)) continue;
      try { notices += `\n\n===== ${metadata.name} ${metadata.version} / ${name} =====\n${await fs.readFile(path.join(directory, name), 'utf8')}`; } catch {}
    }
  }
}
for (const name of await fs.readdir(path.join(root, 'node_modules', '@kyralabs', 'm3e-tokens', 'fonts'))) {
  if (/license|ofl|notice/i.test(name)) notices += `\n\n===== Font license: ${name} =====\n${await fs.readFile(path.join(root, 'node_modules', '@kyralabs', 'm3e-tokens', 'fonts', name), 'utf8')}`;
}
await fs.writeFile(path.join(destination, 'THIRD_PARTY_LICENSES.txt'), notices);
console.log(`EXE=${path.join(destination, 'PTShot.exe')}`);
console.log('PACKAGE PASS');
