import type { WebError } from '../../types';

export type GitPublishOperation = 'commit' | 'commit_push' | 'push';

export function defaultCommitMessage(filesChanged: number): string {
  if (filesChanged <= 0) return 'Update project files';
  return filesChanged === 1 ? 'Update 1 file' : `Update ${filesChanged} files`;
}

export function remoteNames(remoteBranches: string[]): string[] {
  const names = remoteBranches.map(branch => branch.split('/', 1)[0]?.trim()).filter((name): name is string => Boolean(name));
  return [...new Set(names.length > 0 ? names : ['origin'])];
}

const ERROR_MESSAGES: Record<string, string> = {
  NOTHING_TO_COMMIT: 'Nothing to commit. Select "Include unstaged changes" if your changes are not staged.',
  GIT_TRANSIENT_STATE: 'Finish the current Git operation, merge or rebase before retrying.',
  DETACHED_HEAD: 'Select a local branch before pushing from detached HEAD state.',
  BRANCH_ALREADY_EXISTS: 'This branch name already exists. Choose another name.',
  BRANCH_INVALID: 'Invalid Git branch name. Check it and try again.',
  REMOTE_NOT_FOUND: 'Remote not found. Check the remote name or Git configuration.',
  PUSH_REJECTED: 'Push rejected. Sync remote changes and check branch protection or permissions.',
  GIT_COMMAND_TIMEOUT: 'Git operation timed out. Check repository status and the network before retrying.',
  NOT_GIT_REPOSITORY: 'This project is not a Git repository.',
  GIT_NOT_FOUND: 'Git is not installed.',
  PROJECT_DIR_MISSING: 'The project directory does not exist.',
};

export function gitPublishErrorMessage(error: unknown, fallback: string): string {
  const webError = error as WebError | null;
  if (webError?.code && ERROR_MESSAGES[webError.code]) return ERROR_MESSAGES[webError.code];
  if (webError instanceof Error && webError.message.trim()) return webError.message;
  return fallback;
}
