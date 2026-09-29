// Bundles the Blackboard frontend modules under test for Node, resolving packages from the web app
// as its Vite build does. Run by `npm run test:blackboard` in the web app.
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { WEB_APP, resolveFromWebApp, webAppRequire } from '../../host/docservice/build.mjs';

const { build } = webAppRequire('esbuild');
const here = path.dirname(fileURLToPath(import.meta.url));
const source = path.resolve(here, '../../frontend');

await build({
  entryPoints: [
    path.join(source, 'controller.ts'),
    path.join(source, 'inviteLink.ts'),
    path.join(source, 'chat/sessionLink.ts'),
    path.join(source, 'conversation.ts'),
    path.join(source, 'editor/session.ts'),
    path.join(here, 'editorKit.ts'),
  ],
  bundle: true,
  // Shared chunks, so every entry sees the same ProseMirror.
  splitting: true,
  platform: 'node',
  format: 'esm',
  entryNames: '[name]',
  outdir: path.join(WEB_APP, 'node_modules/.cache/blackboard'),
  plugins: [resolveFromWebApp],
  logLevel: 'warning',
});
