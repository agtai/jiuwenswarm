import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link2, Server, Users } from 'lucide-react';

import { Button, toast } from '../../../channels/web/frontend/src/components/ui';
import { currentHost, currentWorkspace } from './controller';
import { describeError } from './errors';
import type { InviteView, MemberView } from './types';
import { useController } from './useController';
import { MembersPanel } from './components/MembersPanel';
import { Sidebar } from './components/Sidebar';
import { WorkspacePane } from './components/WorkspacePane';
import {
  ConfirmDialog,
  InviteDialog,
  JoinDialog,
  NewWorkspaceDialog,
  RenameDialog,
  SettingsDialog,
} from './components/dialogs';
import './blackboard.css';

type Confirm = {
  title: string;
  message: string;
  confirmLabel: string;
  danger?: boolean;
  action: () => Promise<unknown>;
  testId: string;
};

type Open = 'join' | 'new' | 'rename' | 'invite' | 'settings' | null;

export function BlackboardPage() {
  const { t } = useTranslation();
  const { controller, state } = useController();
  const [open, setOpen] = useState<Open>(null);
  const [confirm, setConfirm] = useState<Confirm | null>(null);
  const host = currentHost(state);
  const workspace = currentWorkspace(state);
  const close = () => setOpen(null);

  const report = (error: unknown) => toast.open({ content: describeError(t, error), variant: 'error' });

  const copy = async (invite: InviteView) => {
    try {
      await navigator.clipboard.writeText(invite.url);
      toast.open({ content: t('blackboard.invites.copied'), variant: 'success' });
    } catch (error) {
      report(error);
    }
  };

  const askRemove = (member: MemberView) =>
    workspace &&
    setConfirm({
      title: t('blackboard.members.remove'),
      message: t('blackboard.members.removeConfirm', { name: member.display_name, title: workspace.title }),
      confirmLabel: t('blackboard.members.remove'),
      danger: true,
      action: () => controller.removeMember(member.user_id),
      testId: 'blackboard-remove-member-dialog',
    });

  const askLeave = () =>
    workspace &&
    state.me &&
    setConfirm({
      title: t('blackboard.workspace.leave'),
      message: t('blackboard.workspace.leaveConfirm', { title: workspace.title }),
      confirmLabel: t('blackboard.workspace.leave'),
      danger: true,
      action: () => controller.removeMember(state.me!.user_id),
      testId: 'blackboard-leave-dialog',
    });

  const askDelete = () =>
    workspace &&
    setConfirm({
      title: t('blackboard.workspace.delete'),
      message: t('blackboard.workspace.deleteConfirm', { title: workspace.title }),
      confirmLabel: t('blackboard.workspace.delete'),
      danger: true,
      action: () => controller.deleteWorkspace(),
      testId: 'blackboard-delete-dialog',
    });

  const askRevoke = (invite: InviteView) =>
    setConfirm({
      title: t('blackboard.invites.revoke'),
      message: t('blackboard.invites.revokeConfirm'),
      confirmLabel: t('blackboard.invites.revoke'),
      danger: true,
      action: () => controller.revokeInvite(invite.code),
      testId: 'blackboard-revoke-dialog',
    });

  const reachable = host?.is_self ? Boolean(state.hostStatus?.reachable_from_other_machines) : true;

  return (
    <div className="bb-page" data-testid="blackboard-page">
      {state.loaded && state.hosts.length === 0 ? (
        <div className="bb-welcome" data-testid="blackboard-welcome">
          <Users className="bb-welcome__icon" aria-hidden="true" />
          <h2>{t('blackboard.welcome.title')}</h2>
          <p className="bb-muted">{t('blackboard.welcome.body')}</p>
          <div className="bb-welcome__actions">
            <Button variant="primary" icon={<Link2 size={16} />} data-testid="blackboard-welcome-join-btn" onClick={() => setOpen('join')}>
              {t('blackboard.welcome.join')}
            </Button>
            <Button icon={<Server size={16} />} data-testid="blackboard-welcome-host-btn" onClick={() => setOpen('settings')}>
              {t('blackboard.welcome.host')}
            </Button>
          </div>
        </div>
      ) : (
        <>
          <Sidebar
            state={state}
            onSelectHost={(id) => void controller.selectHost(id)}
            onSelectWorkspace={(id) => void controller.selectWorkspace(id)}
            onJoin={() => setOpen('join')}
            onNewWorkspace={() => setOpen('new')}
            onSettings={() => setOpen('settings')}
          />
          <main className="bb-main">
            {state.loadError ? (
              <p className="bb-notice bb-notice--error" role="alert" data-testid="blackboard-load-error">
                {state.loadError}
              </p>
            ) : null}
            {workspace ? (
              <WorkspacePane
                workspace={workspace}
                onRename={() => setOpen('rename')}
                onArchive={() => void controller.setArchived(true).catch(report)}
                onUnarchive={() => void controller.setArchived(false).catch(report)}
                onDelete={askDelete}
              />
            ) : (
              <div className="bb-empty" data-testid="blackboard-pick-workspace">
                <p>{t('blackboard.workspaces.pick')}</p>
              </div>
            )}
          </main>
          {workspace ? (
            <MembersPanel
              workspace={workspace}
              members={state.members}
              invites={state.invites}
              meId={state.me?.user_id ?? null}
              onSetRole={(member, role) => void controller.setRole(member.user_id, role).catch(report)}
              onRemove={askRemove}
              onLeave={askLeave}
              onInvite={() => setOpen('invite')}
              onCopy={(invite) => void copy(invite)}
              onRevoke={askRevoke}
            />
          ) : null}
        </>
      )}

      <JoinDialog open={open === 'join'} onJoin={(url, name) => controller.join(url, name)} onClose={close} />
      <NewWorkspaceDialog open={open === 'new'} onCreate={(name, title) => controller.createWorkspace(name, title)} onClose={close} />
      <RenameDialog
        open={open === 'rename'}
        current={workspace?.title ?? ''}
        onRename={(title) => controller.renameWorkspace(title)}
        onClose={close}
      />
      <InviteDialog
        open={open === 'invite'}
        workspaceTitle={workspace?.title ?? ''}
        reachable={reachable}
        onCreate={(role, days, uses) => controller.createInvite(role, days, uses)}
        onCopy={(invite) => void copy(invite)}
        onClose={close}
      />
      <SettingsDialog
        open={open === 'settings'}
        hostName={host?.name ?? null}
        displayName={state.me?.display_name ?? ''}
        hostStatus={state.hostStatus}
        onSaveName={(name) => controller.setDisplayName(name)}
        onApplyHosting={(settings) => controller.setHostSettings(settings)}
        onClose={close}
      />
      <ConfirmDialog
        open={confirm !== null}
        title={confirm?.title ?? ''}
        message={confirm?.message ?? ''}
        confirmLabel={confirm?.confirmLabel ?? ''}
        danger={confirm?.danger}
        testId={confirm?.testId ?? 'blackboard-confirm-dialog'}
        onConfirm={() => (confirm ? confirm.action() : Promise.resolve())}
        onClose={() => setConfirm(null)}
      />
    </div>
  );
}
