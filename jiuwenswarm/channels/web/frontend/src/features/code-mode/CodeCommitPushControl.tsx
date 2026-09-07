import { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { CheckCircle2, LoaderCircle, Plus, Upload, X } from 'lucide-react';
import type { ProjectInfo } from '../../types';
import { gitClient } from './gitClient';
import { defaultCommitMessage, gitPublishErrorMessage, remoteNames, type GitPublishOperation } from './gitPublishState';
import type { GitRepoStatus } from './types';
import './CodeMode.css';

interface CodeCommitPushControlProps {
  project: ProjectInfo;
  branch: string | null;
  hasChanges: boolean;
  filesChanged: number;
  isGit: boolean;
  transient: boolean;
  isProcessing: boolean;
  variant: 'environment' | 'review';
  onSuccess: () => void | Promise<void>;
}

function operationIncludesCommit(operation: GitPublishOperation): boolean {
  return operation === 'commit' || operation === 'commit_push';
}

function operationIncludesPush(operation: GitPublishOperation): boolean {
  return operation === 'push' || operation === 'commit_push';
}

export function CodeCommitPushControl({
  project,
  branch,
  hasChanges,
  filesChanged,
  isGit,
  transient,
  isProcessing,
  variant,
  onSuccess,
}: CodeCommitPushControlProps) {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<GitRepoStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [creatingBranch, setCreatingBranch] = useState(false);
  const [operation, setOperation] = useState<GitPublishOperation>(hasChanges ? 'commit_push' : 'push');
  const [message, setMessage] = useState('');
  const [selectedBranch, setSelectedBranch] = useState(branch ?? '');
  const [remote, setRemote] = useState('origin');
  const [includeUnstaged, setIncludeUnstaged] = useState(true);
  const [setUpstream, setSetUpstream] = useState(false);
  const [branchCreateOpen, setBranchCreateOpen] = useState(false);
  const [branchDraft, setBranchDraft] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 3000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  useEffect(() => {
    if (!open) return;
    let disposed = false;
    setLoading(true);
    setStatus(null);
    setError(null);
    setMessage('');
    setIncludeUnstaged(true);
    setBranchCreateOpen(false);
    setBranchDraft('');
    void gitClient
      .status(project.project_id)
      .then(nextStatus => {
        if (disposed) return;
        const currentBranch = nextStatus.repo.branch || '';
        setStatus(nextStatus);
        setSelectedBranch(currentBranch);
        setRemote(remoteNames(nextStatus.branches.remotes)[0]);
        setSetUpstream(!nextStatus.repo.upstream);
        setOperation(nextStatus.working_tree.is_dirty ? (nextStatus.repo.detached ? 'commit' : 'commit_push') : 'push');
      })
      .catch(nextError => {
        if (!disposed) setError(gitPublishErrorMessage(nextError, 'Could not load Git status. Please try again.'));
      })
      .finally(() => {
        if (!disposed) setLoading(false);
      });
    return () => {
      disposed = true;
    };
  }, [open, project.project_id]);

  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || submitting || creatingBranch) return;
      if (branchCreateOpen) {
        setBranchCreateOpen(false);
        setBranchDraft('');
      } else {
        setOpen(false);
      }
    };
    document.addEventListener('keydown', closeOnEscape);
    return () => document.removeEventListener('keydown', closeOnEscape);
  }, [branchCreateOpen, creatingBranch, open, submitting]);

  const repositoryHasChanges = status?.working_tree.is_dirty ?? hasChanges;
  const currentBranch = status?.repo.branch || branch || '';
  const localBranches = useMemo(() => {
    const branches = status?.branches.locals ?? [];
    return [...new Set([currentBranch, ...branches].filter(Boolean))];
  }, [currentBranch, status?.branches.locals]);
  const remotes = useMemo(() => remoteNames(status?.branches.remotes ?? []), [status?.branches.remotes]);
  const includesCommit = operationIncludesCommit(operation);
  const includesPush = operationIncludesPush(operation);
  const resolvedCommitMessage = message.trim() || defaultCommitMessage(filesChanged);
  const isUnbornHead = Boolean(status?.repo.is_git && currentBranch && !status.repo.head);
  const triggerDisabled = isProcessing || !isGit || transient;
  const disabledReason = isProcessing
    ? 'Stop the running task before using this action'
    : !isGit
      ? 'This project is not a Git repository'
      : transient
        ? 'Another Git operation is in progress'
        : 'Commit or push';
  const canSubmit = Boolean(
    status && !loading && !submitting && !creatingBranch && (!includesCommit || repositoryHasChanges) && (!includesPush || (selectedBranch && remote.trim())),
  );

  const createBranch = async () => {
    const nextBranch = branchDraft.trim();
    if (!status || !nextBranch || creatingBranch || submitting) return;
    setCreatingBranch(true);
    setError(null);
    try {
      const result = await gitClient.createBranch(project.project_id, nextBranch);
      setStatus(result.status);
      setSelectedBranch(result.branch);
      setSetUpstream(!result.status.repo.upstream);
      setBranchCreateOpen(false);
      setBranchDraft('');
      void Promise.resolve(onSuccess()).catch(() => undefined);
    } catch (nextError) {
      setError(gitPublishErrorMessage(nextError, 'Could not create the branch. Please try again.'));
    } finally {
      setCreatingBranch(false);
    }
  };

  const submit = async () => {
    if (!status || !canSubmit) return;
    setSubmitting(true);
    setError(null);
    let committedHash: string | null = null;
    let phase: 'commit' | 'push' = includesCommit ? 'commit' : 'push';
    try {
      let pushBranch = selectedBranch;
      if (includesCommit) {
        const commitResult = await gitClient.commit(project.project_id, resolvedCommitMessage, {
          stageAll: includeUnstaged,
        });
        committedHash = commitResult.commit_hash;
        pushBranch = commitResult.status.repo.branch || pushBranch;
      }
      if (includesPush) {
        phase = 'push';
        await gitClient.push(project.project_id, {
          remote: remote.trim(),
          branch: pushBranch,
          setUpstream,
        });
      }

      void Promise.resolve(onSuccess()).catch(() => undefined);
      setOpen(false);
      const hashSuffix = committedHash ? ` (${committedHash})` : '';
      setNotice(operation === 'commit' ? `Committed${hashSuffix}` : operation === 'push' ? 'Pushed' : `Committed and pushed${hashSuffix}`);
    } catch (nextError) {
      const detail = gitPublishErrorMessage(nextError, phase === 'commit' ? 'Commit failed. Please try again.' : 'Push failed. Please try again.');
      if (committedHash && phase === 'push') {
        void Promise.resolve(onSuccess()).catch(() => undefined);
        setOperation('push');
        setError(`Committed (${committedHash}), but the push failed: ${detail}`);
      } else {
        setError(detail);
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      {variant === 'environment' ? (
        <button
          type="button"
          className="code-environment__row code-environment__row--publish"
          onClick={() => setOpen(true)}
          disabled={triggerDisabled}
          title={disabledReason}
        >
          <Upload size={15} />
          <span>Commit or push</span>
        </button>
      ) : (
        <button type="button" className="code-review__publish-button" onClick={() => setOpen(true)} disabled={triggerDisabled} title={disabledReason}>
          Commit or push
        </button>
      )}

      {notice
        ? createPortal(
            <div className="code-publish-toast" role="status" aria-live="polite">
              <CheckCircle2 size={17} aria-hidden="true" />
              <span>{notice}</span>
            </div>,
            document.body,
          )
        : null}

      {open
        ? createPortal(
            <div
              className="code-publish-backdrop"
              role="presentation"
              onMouseDown={event => event.target === event.currentTarget && !submitting && setOpen(false)}
            >
              <form
                className="code-publish-dialog"
                role="dialog"
                aria-modal="true"
                aria-labelledby="code-publish-title"
                onSubmit={event => {
                  event.preventDefault();
                  void submit();
                }}
              >
                <header className="code-publish-dialog__header">
                  <h3 id="code-publish-title">Commit or push</h3>
                  <button type="button" onClick={() => setOpen(false)} disabled={submitting || creatingBranch} aria-label="Close">
                    <X size={18} />
                  </button>
                </header>

                {loading ? (
                  <div className="code-publish-dialog__loading">
                    <LoaderCircle className="code-mode-spin" size={18} />
                    <span>Loading Git status…</span>
                  </div>
                ) : (
                  <div className="code-publish-dialog__fields">
                    <div className="code-publish-field">
                      <span>Target branch</span>
                      <div className="code-publish-branch-picker">
                        <select
                          value={selectedBranch}
                          onChange={event => {
                            setSelectedBranch(event.target.value);
                            if (event.target.value !== currentBranch) setSetUpstream(true);
                          }}
                          disabled={submitting || creatingBranch || includesCommit}
                          aria-label="Target branch"
                        >
                          {localBranches.map(localBranch => (
                            <option key={localBranch} value={localBranch}>
                              {localBranch}
                            </option>
                          ))}
                        </select>
                        <button
                          type="button"
                          className="code-publish-branch-create-trigger"
                          onClick={() => {
                            setBranchCreateOpen(true);
                            setError(null);
                          }}
                          disabled={submitting || creatingBranch || Boolean(status?.repo.transient) || isUnbornHead}
                          title={isUnbornHead ? 'Make the first commit before creating additional branches' : 'Create and check out a new branch'}
                        >
                          <Plus size={15} />
                          <span>New branch</span>
                        </button>
                      </div>
                      {branchCreateOpen ? (
                        <div className="code-publish-branch-create">
                          <input
                            value={branchDraft}
                            onChange={event => setBranchDraft(event.target.value)}
                            onKeyDown={event => {
                              if (event.key === 'Enter') {
                                event.preventDefault();
                                void createBranch();
                              }
                            }}
                            placeholder="e.g. feature/code-mode"
                            maxLength={255}
                            disabled={creatingBranch || submitting}
                            aria-label="New branch name"
                            autoFocus
                          />
                          <button
                            type="button"
                            className="code-mode-button"
                            onClick={() => {
                              setBranchCreateOpen(false);
                              setBranchDraft('');
                            }}
                            disabled={creatingBranch}
                          >
                            Cancel
                          </button>
                          <button
                            type="button"
                            className="code-mode-button code-mode-button--primary"
                            onClick={() => void createBranch()}
                            disabled={!branchDraft.trim() || creatingBranch || submitting}
                          >
                            {creatingBranch ? <LoaderCircle className="code-mode-spin" size={14} /> : null}
                            {creatingBranch ? 'Creating' : 'Create'}
                          </button>
                        </div>
                      ) : null}
                    </div>

                    {includesPush ? (
                      <label className="code-publish-field">
                        <span>Remote</span>
                        <select value={remote} onChange={event => setRemote(event.target.value)} disabled={submitting}>
                          {remotes.map(remoteName => (
                            <option key={remoteName} value={remoteName}>
                              {remoteName}
                            </option>
                          ))}
                        </select>
                      </label>
                    ) : null}

                    {includesCommit ? (
                      <label className="code-publish-field code-publish-field--message">
                        <span>Commit message</span>
                        <textarea
                          value={message}
                          onChange={event => setMessage(event.target.value)}
                          placeholder={`Leave blank to use: ${defaultCommitMessage(filesChanged)}`}
                          maxLength={200}
                          disabled={submitting}
                        />
                        <small>{message.length}/200</small>
                      </label>
                    ) : null}

                    <fieldset className="code-publish-operations">
                      <legend>Operation</legend>
                      {(
                        [
                          ['commit', 'Commit'],
                          ['commit_push', 'Commit and push'],
                          ['push', 'Push'],
                        ] as const
                      ).map(([value, label]) => (
                        <label key={value}>
                          <input
                            type="radio"
                            name="git-publish-operation"
                            value={value}
                            checked={operation === value}
                            onChange={() => setOperation(value)}
                            disabled={submitting || (value !== 'push' && !repositoryHasChanges)}
                          />
                          <span>{label}</span>
                        </label>
                      ))}
                    </fieldset>

                    <div className="code-publish-options">
                      {includesCommit ? (
                        <label>
                          <input type="checkbox" checked={includeUnstaged} onChange={event => setIncludeUnstaged(event.target.checked)} disabled={submitting} />
                          <span>Include unstaged changes</span>
                        </label>
                      ) : null}
                      {includesPush ? (
                        <label>
                          <input type="checkbox" checked={setUpstream} onChange={event => setSetUpstream(event.target.checked)} disabled={submitting} />
                          <span>Set upstream branch</span>
                        </label>
                      ) : null}
                    </div>
                  </div>
                )}

                {error ? (
                  <div className="code-publish-dialog__error" role="alert">
                    {error}
                  </div>
                ) : null}

                <footer className="code-publish-dialog__actions">
                  <button type="button" className="code-mode-button" onClick={() => setOpen(false)} disabled={submitting || creatingBranch}>
                    Cancel
                  </button>
                  <button type="submit" className="code-mode-button code-mode-button--primary" disabled={!canSubmit}>
                    {submitting ? <LoaderCircle className="code-mode-spin" size={15} /> : null}
                    {submitting ? (operation === 'push' ? 'Pushing' : 'Processing') : 'Confirm'}
                  </button>
                </footer>
              </form>
            </div>,
            document.body,
          )
        : null}
    </>
  );
}
