import { createRequire } from 'node:module';
import { cp, mkdir, readdir, readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const root = fileURLToPath(new URL('.', import.meta.url));
const frontend = resolve(root, '../../jiuwenswarm/channels/web/frontend');
const require = createRequire(resolve(frontend, 'package.json'));
const { build } = require('esbuild');
const source = resolve(frontend, 'src/features/live-voice/formal');
const out = resolve(root, 'dist');
await mkdir(out, { recursive: true });
await build({ entryPoints: [resolve(source, 'headlessNativeVoice.ts')], outfile: resolve(out, 'index.js'),
  bundle: true, format: 'esm', platform: 'browser', target: 'chrome107', sourcemap: true });
const types = spawnSync(process.execPath, [require.resolve('typescript/bin/tsc'), resolve(source, 'headlessNativeVoice.ts'),
  '--declaration', '--emitDeclarationOnly', '--outDir', out, '--rootDir', source,
  '--target', 'ES2022', '--module', 'ES2020', '--moduleResolution', 'Bundler', '--skipLibCheck', '--strict',
  '--noUnusedLocals', '--noUnusedParameters'], { stdio: 'inherit' });
if (types.status !== 0) throw new Error('Live Voice client declaration build failed');
for (const entry of await readdir(out, { recursive: true })) {
  if (!entry.endsWith('.d.ts')) continue;
  const path = resolve(out, entry);
  await writeFile(path, (await readFile(path, 'utf8')).replace(/(from\s+['"])(\.{1,2}\/[^'"]+)(['"])/g,
    (_, before, name, after) => before + (name.endsWith('.js') ? name : name + '.js') + after));
}
await cp(resolve(source, 'adapters/liveVoiceCaptureProcessor.js'), resolve(out, 'liveVoiceCaptureProcessor.js'));
await cp(resolve(root, '../../LICENSE'), resolve(root, 'LICENSE'));
