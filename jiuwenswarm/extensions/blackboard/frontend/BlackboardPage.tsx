import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link2, Server, Users } from 'lucide-react';

import { Button, Tabs, toast } from '../../../channels/web/frontend/src/components/ui';
import { FormDialog } from '../../../channels/web/frontend/src/components/form';
import { canEdit, currentDoc, currentHost, currentWorkspace } from './controller';
import { describeError } from './errors';
import type { DocView, InviteView, MemberView, ReferenceView } from './types';
import { useController } from './useController';
import { MembersPanel } from './components/MembersPanel';
import { ReferencePreview, ReferencesPanel } from './components/ReferencesPanel';
import { Sidebar } from './components/Sidebar';
import { WorkspacePane, type DocActions } from './components/WorkspacePane';
import {
  ConfirmDialog,
  InviteDialog,
  JoinDialog,
  NewWorkspaceDialog,
  RenameDialog,
  SettingsDialog,
} from './components/dialogs';
import { ImportMarkdownDialog, MarkdownDialog, NewDocumentDialog } from './components/docDialogs';
import './blackboard.css';

// The file as base64, for the upload RPC.
function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).replace(/^data:[^,]*,/, ''));
    reader.onerror = () => reject(reader.error ?? new Error('read failed'));
    reader.readAsDataURL(file);
  });
}

type Confirm = {
  title: string;
  message: string;
  confirmLabel: string;
  danger?: boolean;
  action: () => Promise<unknown>;
  testId: string;
};

type Open = 'join' | 'new' | 'rename' | 'invite' | 'settings' | 'newDoc' | null;
type DocDialog = { kind: 'rename' | 'import' | 'markdown'; doc: DocView } | null;
type RailTab = 'members' | 'references';

export function BlackboardPage() {
  const { t } = useTranslation();
  const { controller, state } = useController();
  const [open, setOpen] = useState<Open>(null);
  const [confirm, setConfirm] = useState<Confirm | null>(null);
  const [docDialog, setDocDialog] = useState<DocDialog>(null);
  const [railTab, setRailTab] = useState<RailTab>('members');
  const [preview, setPreview] = useState<{ reference: ReferenceView; url: string } | null>(null);
  const host = currentHost(state);
  const workspace = currentWorkspace(state);
  const doc = currentDoc(state);
  const editable = canEdit(state);
  const close = () => setOpen(null);
  const names = useMemo(() => new Map(state.members.map((m) => [m.user_id, m.display_name])), [state.members]);
  const me = state.me ? { id: state.me.user_id, name: state.me.display_name } : null;
  const fetchToken = useCallback((docId: string) => controller.docToken(docId), [controller, state.hostId]);

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

  const docActions: DocActions = {
    rename: (d) => setDocDialog({ kind: 'rename', doc: d }),
    setPinned: (d, pinned) => void controller.setDocPinned(d.id, pinned).catch(report),
    setInstructions: (d) => void controller.setInstructions(d.id).catch(report),
    importMarkdown: (d) => setDocDialog({ kind: 'import', doc: d }),
    viewMarkdown: (d) => setDocDialog({ kind: 'markdown', doc: d }),
    archive: (d) =>
      setConfirm({
        title: t('blackboard.docs.archive'),
        message: t('blackboard.docs.archiveConfirm', { title: d.title }),
        confirmLabel: t('blackboard.docs.archive'),
        danger: true,
        action: () => controller.archiveDoc(d.id),
        testId: 'blackboard-archive-doc-dialog',
      }),
  };

  const markdownDocId = docDialog?.kind === 'markdown' ? docDialog.doc.id : null;
  const loadMarkdown = useCallback(
    () => (markdownDocId ? controller.readDoc(markdownDocId) : Promise.resolve('')),
    [controller, markdownDocId],
  );

  const uploadFiles = async (files: File[]) => {
    for (const file of files) {
      if (file.size > state.maxUploadMb * 1024 * 1024) {
        report(new Error(t('blackboard.references.tooBig', { name: file.name, mb: state.maxUploadMb })));
        continue;
      }
      try {
        const data = await fileToBase64(file);
        await controller.uploadReference({ name: file.name, mime: file.type || 'application/octet-stream', data });
        toast.open({ content: t('blackboard.references.uploaded', { name: file.name }), variant: 'success' });
      } catch (error) {
        report(error);
      }
    }
  };

  const openReference = async (reference: ReferenceView) => {
    try {
      const url = await controller.referenceUrl(reference.id);
      if (reference.kind === 'image' || reference.mime === 'application/pdf') setPreview({ reference, url });
      else window.open(url, '_blank', 'noopener');
    } catch (error) {
      report(error);
    }
  };

  const askRemoveReference = (reference: ReferenceView) =>
    setConfirm({
      title: t('blackboard.references.remove'),
      message: t('blackboard.references.removeConfirm', { name: reference.name }),
      confirmLabel: t('blackboard.references.remove'),
      danger: true,
      action: () => controller.removeReference(reference.id),
      testId: 'blackboard-remove-reference-dialog',
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
            onSelectDoc={(id) => controller.selectDoc(id)}
            onNewDoc={() => setOpen('newDoc')}
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
                doc={doc}
                hasDocs={state.docs.length > 0}
                canEdit={editable}
                docservice={state.docservice}
                me={me}
                names={names}
                fetchToken={fetchToken}
                docActions={docActions}
                onNewDoc={() => setOpen('newDoc')}
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
            <aside className="bb-rail" data-testid="blackboard-rail">
              <Tabs<RailTab>
                items={[
                  { value: 'members', label: t('blackboard.members.tab'), testId: 'blackboard-rail-tab-members' },
                  { value: 'references', label: t('blackboard.references.tab'), testId: 'blackboard-rail-tab-references' },
                ]}
                value={railTab}
                onChange={setRailTab}
                bordered
                wrapperTestId="blackboard-rail-tabs"
              />
              {railTab === 'members' ? (
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
              ) : (
                <ReferencesPanel
                  references={state.references}
                  canEdit={editable}
                  maxUploadMb={state.maxUploadMb}
                  onUpload={uploadFiles}
                  onOpen={(reference) => void openReference(reference)}
                  onRemove={askRemoveReference}
                  onSetNote={(reference, note) =>
                    controller.setReferenceNote(reference.id, note).catch((error) => {
                      report(error);
                    })
                  }
                />
              )}
            </aside>
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
      <NewDocumentDialog open={open === 'newDoc'} onCreate={(title, markdown) => controller.createDoc(title, markdown)} onClose={close} />
      <RenameDialog
        open={docDialog?.kind === 'rename'}
        current={docDialog?.doc.title ?? ''}
        heading={t('blackboard.docs.renameTitle')}
        testId="blackboard-rename-doc"
        onRename={(title) => controller.renameDoc(docDialog!.doc.id, title)}
        onClose={() => setDocDialog(null)}
      />
      <ImportMarkdownDialog
        open={docDialog?.kind === 'import'}
        docTitle={docDialog?.doc.title ?? ''}
        onImport={(markdown) => controller.importMarkdown(docDialog!.doc.id, markdown)}
        onClose={() => setDocDialog(null)}
      />
      <MarkdownDialog
        open={docDialog?.kind === 'markdown'}
        docTitle={docDialog?.doc.title ?? ''}
        load={loadMarkdown}
        onClose={() => setDocDialog(null)}
      />
      <FormDialog
        open={preview !== null}
        title={preview?.reference.name ?? ''}
        confirmLabel={t('common.close')}
        cancelLabel={t('common.cancel')}
        dialogClassName="bb-dialog--close-only bb-dialog--preview"
        testIdPrefix="blackboard-preview-dialog"
        onConfirm={() => setPreview(null)}
        onCancel={() => setPreview(null)}
      >
        {preview ? <ReferencePreview reference={preview.reference} url={preview.url} /> : null}
      </FormDialog>
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
