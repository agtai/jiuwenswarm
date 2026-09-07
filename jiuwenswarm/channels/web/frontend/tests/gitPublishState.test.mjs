import assert from 'node:assert/strict';
import test from 'node:test';
import { defaultCommitMessage, gitPublishErrorMessage, remoteNames } from '../node_modules/.cache/git-publish-state/features/code-mode/gitPublishState.js';

test('generates a fallback commit message from the changed file count', () => {
  assert.equal(defaultCommitMessage(0), 'Update project files');
  assert.equal(defaultCommitMessage(1), 'Update 1 file');
  assert.equal(defaultCommitMessage(3), 'Update 3 files');
});

test('derives unique remote names and falls back to origin', () => {
  assert.deepEqual(remoteNames(['origin/main', 'upstream/main', 'origin/dev']), ['origin', 'upstream']);
  assert.deepEqual(remoteNames([]), ['origin']);
});

test('maps known backend errors and preserves useful unknown errors', () => {
  assert.match(gitPublishErrorMessage({ code: 'NOTHING_TO_COMMIT' }, 'fallback'), /Nothing to commit/);
  assert.match(gitPublishErrorMessage({ code: 'BRANCH_ALREADY_EXISTS' }, 'fallback'), /already exists/);
  assert.match(gitPublishErrorMessage({ code: 'BRANCH_INVALID' }, 'fallback'), /Invalid Git branch name/);
  assert.equal(gitPublishErrorMessage(new Error('custom failure'), 'fallback'), 'custom failure');
  assert.equal(gitPublishErrorMessage(null, 'fallback'), 'fallback');
});
