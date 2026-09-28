// Blackboard's own strings: zh and en have the same keys, and every static
// t('blackboard.x') in the plugin's frontend exists in both.
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PLUGIN_FRONTEND = path.resolve(HERE, '../../frontend');
const LOCALES = path.resolve(HERE, '../../../../channels/web/frontend/src/i18n/locales');

function flatten(value, prefix = '', out = new Set()) {
  for (const [key, child] of Object.entries(value)) {
    const full = prefix ? `${prefix}.${key}` : key;
    out.add(full);
    if (child && typeof child === 'object') flatten(child, full, out);
  }
  return out;
}

const load = (name) => JSON.parse(readFileSync(path.join(LOCALES, name), 'utf8'));
const zh = flatten(load('zh.json').blackboard ?? {}, 'blackboard');
const en = flatten(load('en.json').blackboard ?? {}, 'blackboard');

function sources(dir, out = []) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) sources(full, out);
    else if (/\.tsx?$/.test(entry.name)) out.push(full);
  }
  return out;
}

test('zh and en have the same blackboard keys', () => {
  assert.ok(en.size > 50);
  assert.deepEqual([...zh].filter((k) => !en.has(k)).sort(), []);
  assert.deepEqual([...en].filter((k) => !zh.has(k)).sort(), []);
});

// A plural key (t('x', { count })) exists as x_one and x_other.
const has = (keys, key) => keys.has(key) || (keys.has(`${key}_one`) && keys.has(`${key}_other`));

test('every static blackboard key used in the frontend exists', () => {
  const missing = [];
  for (const file of sources(PLUGIN_FRONTEND)) {
    const text = readFileSync(file, 'utf8');
    for (const match of text.matchAll(/\bt\(\s*'(blackboard\.[A-Za-z0-9_.]+)'/g)) {
      if (!has(zh, match[1]) || !has(en, match[1])) missing.push(`${path.basename(file)}: ${match[1]}`);
    }
  }
  assert.deepEqual(missing, []);
});

test('the keys built at runtime exist for every value they take', () => {
  for (const role of ['owner', 'editor', 'commenter', 'viewer']) assert.ok(en.has(`blackboard.roles.${role}`), role);
  for (const status of ['connecting', 'connected', 'offline', 'unauthorized', 'stopped']) {
    assert.ok(en.has(`blackboard.host.status.${status}`), status);
  }
  for (const code of ['unauthorized', 'not_member', 'forbidden', 'not_found', 'expired', 'disabled', 'unavailable', 'internal']) {
    assert.ok(en.has(`blackboard.errors.${code}`), code);
  }
  for (const value of ['30', '60', '360', '720', '1440', '10080', 'never']) {
    assert.ok(en.has(`blackboard.invites.expiryOptions.${value}`), value);
  }
  for (const value of ['none', '1', '5', '10', '25', '50', '100']) {
    assert.ok(en.has(`blackboard.invites.usesOptions.${value}`), value);
  }
  for (const status of ['connecting', 'syncing', 'saved', 'offline', 'unavailable', 'closed']) {
    assert.ok(en.has(`blackboard.editor.status.${status}`), status);
  }
  const tools = ['undo', 'redo', 'h1', 'h2', 'h3', 'bold', 'italic', 'strike', 'code'];
  for (const tool of [...tools, 'bulletList', 'orderedList', 'taskList', 'blockquote', 'codeBlock', 'table']) {
    assert.ok(en.has(`blackboard.editor.tools.${tool}`), tool);
  }
  for (const kind of ['insertion', 'deletion']) assert.ok(en.has(`blackboard.editor.suggested.${kind}`), kind);
  for (const reason of ['not_built', 'node_missing', 'node_too_old', 'start_failed', 'exited', 'not_configured', 'stopped', 'starting']) {
    assert.ok(en.has(`blackboard.docservice.${reason}`), reason);
  }
});
