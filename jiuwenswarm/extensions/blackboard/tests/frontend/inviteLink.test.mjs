import assert from 'node:assert/strict';
import test from 'node:test';
import {
  isValidWorkspaceName,
  parseInviteLink,
  suggestWorkspaceName,
} from '../../../../channels/web/frontend/node_modules/.cache/blackboard/inviteLink.js';

const CODE = 'abcdefghijklmnopqrst';

test('an invite link gives the host base and the code', () => {
  assert.deepEqual(parseInviteLink(`http://127.0.0.1:19011/blackboard/join/${CODE}`), {
    base: 'http://127.0.0.1:19011',
    code: CODE,
  });
  assert.deepEqual(parseInviteLink(`  https://bb.example.com/blackboard/join/${CODE}/  `), {
    base: 'https://bb.example.com',
    code: CODE,
  });
});

test('a host behind a path prefix keeps the prefix in its base', () => {
  assert.deepEqual(parseInviteLink(`https://example.com/team/blackboard/join/${CODE}`), {
    base: 'https://example.com/team',
    code: CODE,
  });
});

test('anything else is not an invite link', () => {
  for (const text of [
    '',
    'not a url',
    `ftp://host/blackboard/join/${CODE}`,
    'https://host/blackboard/join/short',
    `https://host/other/${CODE}`,
    `https://host/blackboard/join/${CODE.toUpperCase()}`,
  ]) {
    assert.equal(parseInviteLink(text), null, text);
  }
});

test('workspace short names follow the host rule', () => {
  for (const name of ['abc', 'launch-plan', 'q4-2026', 'a'.repeat(40)]) assert.equal(isValidWorkspaceName(name), true, name);
  for (const name of ['ab', '-abc', 'abc-', 'a--b', 'ABC', 'a b c', 'a'.repeat(41)]) {
    assert.equal(isValidWorkspaceName(name), false, name);
  }
});

test('a short name is suggested from the title', () => {
  assert.equal(suggestWorkspaceName('Launch plan Q4'), 'launch-plan-q4');
  assert.equal(suggestWorkspaceName('  --Hello,   World!!  '), 'hello-world');
  const eAcute = String.fromCharCode(0xe9);
  assert.equal(suggestWorkspaceName(`Caf${eAcute} Menu`), 'cafe-menu');
  assert.equal(suggestWorkspaceName('中文标题'), '');
});
