import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { AlertCircle, Check, ChevronDown, GitBranch, LoaderCircle, Plus, Search, X } from 'lucide-react';
import type { ProjectInfo, WebError } from '../../types';
import { useWorkspaceStore } from '../../stores';
import { gitClient } from './gitClient';
import type { GitDiffRepoInfo, GitRepoStatus } from './types';
import './CodeMode.css';

interface CodeBranchSelectorProps {
  project: ProjectInfo | null;
  compact?: boolean;
  disabled?: boolean;
  variant?: 'default' | 'environment';
  liveRepo?: GitDiffRepoInfo | null;
}

function getErrorMessage(error: unknown): string {
  const webError = error as WebError;
  switch (webError.code) {
    case 'WORKTREE_DIRTY':
      return 'Resolve uncommitted changes before switching branches.';
    case 'GIT_TRANSIENT_STATE':
      return 'Finish the merge or rebase before switching branches.';
    case 'BRANCH_NOT_FOUND':
      return 'Branch not found. Refresh and try again.';
    case 'BRANCH_ALREADY_EXISTS':
      return 'This branch name already exists.';
    case 'GIT_NOT_FOUND':
      return 'Git is not installed. Branch operations are unavailable.';
    default:
      return webError.message || 'Git operation failed. Please try again.';
  }
}

export function CodeBranchSelector({ project, compact = false, disabled = false, variant = 'default', liveRepo = null }: CodeBranchSelectorProps) {
  const [status, setStatus] = useState<GitRepoStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [operating, setOperating] = useState(false);
  const [notGit, setNotGit] = useState(false);
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [branchDraft, setBranchDraft] = useState('');
  const rootRef = useRef<HTMLDivElement>(null);
  const unbornHintId = useId();
  const loadProjects = useWorkspaceStore(state => state.loadProjects);

  const closeMenu = useCallback(() => {
    setOpen(false);
    setError(null);
  }, []);

  const loadStatus = useCallback(async () => {
    if (!project || project.work_mode !== 'code' || project.is_default) {
      setStatus(null);
      return;
    }
    setLoading(true);
    setError(null);
    setNotGit(false);
    try {
      const nextStatus =
        project.git.status === 'ready' || project.git.enabled ? await gitClient.status(project.project_id) : await gitClient.probe(project.project_id);
      setStatus(nextStatus);
      setNotGit(!nextStatus.repo.is_git);
    } catch (nextError) {
      setStatus(null);
      if ((nextError as WebError).code === 'NOT_GIT_REPOSITORY') {
        setNotGit(true);
      } else {
        setError(getErrorMessage(nextError));
      }
    } finally {
      setLoading(false);
    }
  }, [project]);

  useEffect(() => {
    void loadStatus();
  }, [loadStatus]);

  useEffect(() => {
    if (!liveRepo || !project || project.work_mode !== 'code' || project.is_default) return;
    setNotGit(!liveRepo.is_git);
    setStatus(previous => {
      if (!previous) return previous;
      return {
        ...previous,
        repo: {
          ...previous.repo,
          is_git: liveRepo.is_git,
          repo_root: liveRepo.repo_root,
          branch: liveRepo.branch,
          head: liveRepo.head,
          transient: liveRepo.transient,
        },
        branches: {
          ...previous.branches,
          current: liveRepo.branch,
        },
      };
    });
  }, [liveRepo, project]);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) closeMenu();
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeMenu();
    };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, [closeMenu, open]);

  const branches = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    return (status?.branches.locals ?? []).filter(branch => !query || branch.toLocaleLowerCase().includes(query));
  }, [search, status]);

  const isNotGit = notGit || status?.repo.is_git === false || Boolean(!loading && !status && project?.git.status === 'not_git');
  const currentBranch = liveRepo?.branch || status?.branches.current || project?.git.branch || '';
  const branchWritesBlocked = Boolean(status?.repo.transient || status?.repo.detached);
  const isUnbornHead = Boolean(status?.repo.is_git && currentBranch && !status.repo.head);

  const openMenu = () => {
    setOpen(true);
    void loadStatus();
  };

  const initializeGit = async () => {
    if (!project) return;
    setOperating(true);
    setError(null);
    try {
      const nextStatus = await gitClient.init(project.project_id, 'main');
      setStatus(nextStatus);
      setNotGit(false);
      await loadProjects();
      setOpen(true);
    } catch (nextError) {
      setError(getErrorMessage(nextError));
    } finally {
      setOperating(false);
    }
  };

  const switchBranch = async (branch: string) => {
    if (!project || branch === currentBranch) {
      closeMenu();
      return;
    }
    setOperating(true);
    setError(null);
    try {
      const result = await gitClient.switchBranch(project.project_id, branch);
      setStatus(result.status);
      closeMenu();
      await loadProjects();
    } catch (nextError) {
      setError(getErrorMessage(nextError));
    } finally {
      setOperating(false);
    }
  };

  const createBranch = async () => {
    if (!project || !branchDraft.trim()) return;
    setOperating(true);
    setError(null);
    try {
      const result = await gitClient.createBranch(project.project_id, branchDraft.trim(), currentBranch || undefined);
      setStatus(result.status);
      setBranchDraft('');
      setCreateOpen(false);
      closeMenu();
      await loadProjects();
    } catch (nextError) {
      setError(getErrorMessage(nextError));
    } finally {
      setOperating(false);
    }
  };

  if (!project || project.work_mode !== 'code' || project.is_default) return null;

  return (
    <div ref={rootRef} className={`code-branch${compact ? ' code-branch--compact' : ''}${variant === 'environment' ? ' code-branch--environment' : ''}`}>
      {isNotGit ? (
        <button
          type='button'
          className='code-branch__trigger code-branch__trigger--warning'
          onClick={() => void initializeGit()}
          disabled={disabled || operating}
          title='This directory is not a Git repository'
        >
          {operating ? <LoaderCircle className='code-mode-spin' size={15} /> : <GitBranch size={15} />}
          <span>Initialize Git</span>
        </button>
      ) : (
        <button
          type='button'
          className='code-branch__trigger'
          onClick={() => (open ? closeMenu() : openMenu())}
          disabled={disabled || loading || operating || !status}
          aria-haspopup='menu'
          aria-expanded={open}
          title={currentBranch || 'Loading branches'}
        >
          {loading || operating ? <LoaderCircle className='code-mode-spin' size={15} /> : <GitBranch size={15} />}
          <span>{currentBranch || 'Loading branches'}</span>
          <ChevronDown size={14} className={open ? 'code-branch__chevron is-open' : 'code-branch__chevron'} />
        </button>
      )}

      {open && status ? (
        <div className='code-branch__menu' role='menu'>
          <label className='code-branch__search'>
            <Search size={15} />
            <input value={search} onChange={event => setSearch(event.target.value)} placeholder='Search branches' autoFocus />
          </label>
          <div className='code-branch__section-label'>Branches</div>
          <div className='code-branch__list'>
            {branches.map(branch => (
              <button
                type='button'
                key={branch}
                className={branch === currentBranch ? 'code-branch__option is-active' : 'code-branch__option'}
                onClick={() => void switchBranch(branch)}
                disabled={branchWritesBlocked}
                role='menuitemradio'
                aria-checked={branch === currentBranch}
              >
                <GitBranch size={15} />
                <span>{branch}</span>
                {branch === currentBranch ? <Check size={16} /> : null}
              </button>
            ))}
            {branches.length === 0 ? <div className='code-branch__empty'>No matching local branches</div> : null}
          </div>
          {branchWritesBlocked ? (
            <div className='code-branch__menu-error' role='status'>
              <AlertCircle size={14} />
              <span>{status.repo.transient ? 'Finish the merge or rebase before switching branches.' : 'Branch switching is unavailable in detached HEAD state.'}</span>
            </div>
          ) : null}
          {error ? (
            <div className='code-branch__menu-error' role='alert'>
              <AlertCircle size={14} />
              <span>{error}</span>
              <button type='button' onClick={() => setError(null)} aria-label='Dismiss message'>
                <X size={13} />
              </button>
            </div>
          ) : null}
          <div
            className={isUnbornHead ? 'code-branch__create-wrap is-disabled' : 'code-branch__create-wrap'}
            tabIndex={isUnbornHead ? 0 : undefined}
            aria-describedby={isUnbornHead ? unbornHintId : undefined}
          >
            <button type='button' className='code-branch__create' onClick={() => setCreateOpen(true)} disabled={branchWritesBlocked || isUnbornHead}>
              <Plus size={16} />
              <span>Create and check out a new branch</span>
            </button>
            {isUnbornHead ? (
              <span id={unbornHintId} className='code-branch__create-hint' role='tooltip'>
                Make the first commit before creating additional branches
              </span>
            ) : null}
          </div>
        </div>
      ) : null}

      {!open && branchWritesBlocked ? (
        <div className='code-branch__error' role='status'>
          <AlertCircle size={14} />
          <span>{status?.repo.transient ? 'Finish the merge or rebase before switching branches.' : 'Branch switching is unavailable in detached HEAD state.'}</span>
        </div>
      ) : null}

      {!open && error ? (
        <div className='code-branch__error' role='alert'>
          <AlertCircle size={14} />
          <span>{error}</span>
          <button type='button' onClick={() => setError(null)} aria-label='Dismiss message'>
            <X size={13} />
          </button>
        </div>
      ) : null}

      {createOpen ? (
        <div className='code-mode-dialog-backdrop' role='presentation'>
          <form
            className='code-mode-dialog'
            onSubmit={event => {
              event.preventDefault();
              void createBranch();
            }}
          >
            <div className='code-mode-dialog__header'>
              <h3>Create and check out branch</h3>
              <button type='button' onClick={() => setCreateOpen(false)} aria-label='Close'>
                <X size={18} />
              </button>
            </div>
            <input value={branchDraft} onChange={event => setBranchDraft(event.target.value)} placeholder='Enter a branch name, e.g. feature/code-mode' autoFocus />
            {error ? <div className='code-mode-dialog__error'>{error}</div> : null}
            <div className='code-mode-dialog__actions'>
              <button type='button' className='code-mode-button' onClick={() => setCreateOpen(false)}>
                Cancel
              </button>
              <button type='submit' className='code-mode-button code-mode-button--primary' disabled={!branchDraft.trim() || operating}>
                {operating ? 'Creating…' : 'Confirm'}
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </div>
  );
}
