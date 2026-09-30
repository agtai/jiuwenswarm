import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Bot, CircleHelp, History, Link2, MessageSquare, MessagesSquare, PanelLeftOpen, Paperclip, Server, Users } from 'lucide-react';

import { Button, toast } from '../../../channels/web/frontend/src/components/ui';
import { FormDialog } from '../../../channels/web/frontend/src/components/form';
import { canEdit, currentDoc, currentHost, currentWorkspace, type RailTab } from './controller';
import { describeError } from './errors';
import type { AnchorDraft, DocView, InviteView, MandateView, MemberView, ReferenceView, Role, WorkspaceView } from './types';
import { useController } from './useController';
import { AgentsPanel } from './components/AgentsPanel';
import { ChatPanel } from './components/ChatPanel';
import { CommentDraft, CommentsPanel, ThreadCard, type CommentsActions, type ThreadProps } from './components/CommentsPanel';
import { DecisionsPanel, type DecisionActions } from './components/Decisions';
import { ActivityBar, Dock, type DockPanel } from './components/Dock';
import { Resizer } from './components/Resizer';
import { HistoryPanel } from './components/HistoryPanel';
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
import { ExportDialog, ImportMarkdownDialog, MarkdownDialog, NewDocumentDialog } from './components/docDialogs';
import type { VersionActions } from './editor/VersionView';
import { LIMITS, clamp, openChat, updateLayout, useLayout } from './layout';
import { AgentChat } from './components/AgentChat';
import { DocSwitcher, ShortcutsDialog, useShortcuts } from './components/Shortcuts';
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

const RAIL_ICONS: Record<RailTab, typeof Users> = {
  chat: MessageSquare,
  comments: MessagesSquare,
  decisions: CircleHelp,
  history: History,
  agents: Bot,
  references: Paperclip,
  members: Users,
};
const RAIL_ORDER: RailTab[] = ['chat', 'comments', 'decisions', 'history', 'agents', 'references', 'members'];
const RAIL_LABELS: Record<RailTab, string> = {
  chat: 'blackboard.messages.tab',
  comments: 'blackboard.comments.tab',
  decisions: 'blackboard.decisions.tab',
  history: 'blackboard.history.tab',
  agents: 'blackboard.agents.tab',
  references: 'blackboard.references.tab',
  members: 'blackboard.members.tab',
};

// Commenters and above may comment and post in the chat, unless the workspace is archived.
function canTalk(role: Role | undefined, archived: boolean): boolean {
  return !archived && (role === 'owner' || role === 'editor' || role === 'commenter');
}
type DocDialog = { kind: 'import' | 'markdown' | 'export'; doc: DocView } | null;

// Opens a download the browser saves as a file (the host sends it as an attachment).
function download(url: string): void {
  const link = document.createElement('a');
  link.href = url;
  link.rel = 'noopener';
  document.body.append(link);
  link.click();
  link.remove();
}

export function BlackboardPage() {
  const { t } = useTranslation();
  const { controller, state } = useController();
  const [open, setOpen] = useState<Open>(null);
  const [confirm, setConfirm] = useState<Confirm | null>(null);
  const [docDialog, setDocDialog] = useState<DocDialog>(null);
  const layout = useLayout();
  const sidebarWidthAtStart = useRef(layout.sidebarWidth);
  const [switcher, setSwitcher] = useState(false);
  const [help, setHelp] = useState(false);
  const [preview, setPreview] = useState<{ reference: ReferenceView; url: string } | null>(null);
  const host = currentHost(state);
  const workspace = currentWorkspace(state);
  const doc = currentDoc(state);
  const editable = canEdit(state);
  const close = () => setOpen(null);
  const names = useMemo(() => new Map(state.members.map((m) => [m.user_id, m.display_name])), [state.members]);
  const me = state.me ? { id: state.me.user_id, name: state.me.display_name } : null;
  const fetchToken = useCallback((docId: string) => controller.docToken(docId), [controller, state.hostId]);
  const instructions = useMemo(() => new Map(state.mandates.map((m) => [m.id, m.instruction])), [state.mandates]);
  const mandatesById = useMemo(() => new Map(state.mandates.map((m) => [m.id, m])), [state.mandates]);
  const decisionsById = useMemo(() => new Map(state.decisions.map((d) => [d.id, d])), [state.decisions]);
  const docTitles = useMemo(() => new Map(state.docs.map((d) => [d.id, d.title])), [state.docs]);
  const talk = canTalk(workspace?.role, Boolean(workspace?.archived));
  const commentable = talk && Boolean(doc && !doc.archived);
  const threadAnchors = useMemo(
    () =>
      state.threads
        .filter((th) => !th.resolved_at)
        .map((th) => ({ id: th.id, start: th.anchor.start, end: th.anchor.end, quote: th.anchor.quote, status: th.anchor.status })),
    [state.threads],
  );
  const suggestionActions = useMemo(
    () => ({
      decide:
        editable && doc
          ? (ids: string[], action: 'accept' | 'reject') => controller.decideSuggestions(doc.id, ids, action).catch(report)
          : null,
      decideRun:
        editable && doc
          ? (mandateId: string, action: 'accept' | 'reject') =>
              controller.decideMandate(doc.id, mandateId, action).then(() => undefined, report)
          : null,
      instructions,
    }),
    [controller, doc, editable, instructions],
  );

  const report = (error: unknown): void => {
    toast.open({ content: describeError(t, error), variant: 'error' });
  };

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
    rename: (d, title) =>
      controller.renameDoc(d.id, title).catch((error) => {
        report(error);
        throw error;
      }),
    setPinned: (d, pinned) => void controller.setDocPinned(d.id, pinned).catch(report),
    setInstructions: (d) => void controller.setInstructions(d.id).catch(report),
    importMarkdown: (d) => setDocDialog({ kind: 'import', doc: d }),
    viewMarkdown: (d) => setDocDialog({ kind: 'markdown', doc: d }),
    showHistory: () => controller.selectRail('history'),
    exportDoc: (d) => setDocDialog({ kind: 'export', doc: d }),
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

  const askCancelMandate = (mandate: MandateView) =>
    setConfirm({
      title: t('blackboard.agents.cancel'),
      message: t('blackboard.agents.cancelConfirm', { name: mandate.requester_name ?? mandate.requester_id }),
      confirmLabel: t('blackboard.agents.cancel'),
      danger: true,
      action: () => controller.cancelMandate(mandate.id),
      testId: 'blackboard-cancel-mandate-dialog',
    });

  const decideRun = (mandate: MandateView, docId: string, action: 'accept' | 'reject') =>
    void controller
      .decideMandate(docId, mandate.id, action)
      .then((count) => toast.open({ content: t(`blackboard.agents.decided.${action}`, { count }), variant: 'success' }))
      .catch(report);

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

  const decisionActions: DecisionActions = {
    answer: editable ? (id, answer) => controller.answerDecision(id, answer).catch((error) => report(error)) : null,
    accept: (id) => controller.acceptDecision(id).catch((error) => report(error)),
    cancel: (id) => controller.cancelDecision(id).catch((error) => report(error)),
    openDoc: (docId) => controller.selectDoc(docId),
  };

  // Errors reach the person; the composers keep their text by seeing the failure.
  const rethrow = (error: unknown): never => {
    report(error);
    throw error;
  };

  const threadActions: CommentsActions = {
    create: ({ body, wholeDocument, sessionId }) =>
      controller.createComment(body, { wholeDocument, sessionId }).then(() => undefined, rethrow),
    cancelDraft: () => controller.cancelComment(),
    reply: (threadId, { body, wholeDocument, sessionId }) =>
      controller.replyThread(threadId, body, { wholeDocument, sessionId }).catch(rethrow),
    edit: (commentId, body) => controller.editComment(commentId, body).catch(rethrow),
    setResolved: (threadId, resolved) => controller.setThreadResolved(threadId, resolved).catch(report),
    open: (threadId) => controller.openThread(threadId),
    showResolved: (show) => controller.setShowResolved(show),
  };

  const threadProps: ThreadProps = {
    members: state.members,
    meId: state.me?.user_id ?? null,
    canComment: commentable,
    canTask: editable,
    sessions: state.sessions,
    mandates: mandatesById,
    decisions: decisionsById,
    docTitles,
    decisionActions,
    actions: threadActions,
  };

  // Open threads and the comment being written, as cards in the editor's margin.
  const commentActions = {
    threads: threadAnchors,
    active: state.activeThread,
    draft: state.draftAnchor,
    onOpenThread: (id: string | null) => controller.openThread(id),
    onComment: commentable ? (anchor: AnchorDraft) => controller.startComment(anchor) : null,
    renderThread: (id: string, active: boolean) => {
      const thread = state.threads.find((th) => th.id === id);
      return thread ? <ThreadCard thread={thread} active={active} variant="margin" {...threadProps} /> : null;
    },
    renderDraft: () => <CommentDraft {...threadProps} />,
  };

  const openVersion = state.history.find((v) => v.id === state.openVersion) ?? null;
  const versionActions: VersionActions = {
    content: (id) => controller.versionContent(id),
    diff: (to, from) => controller.versionDiff(to, from),
    markdown: (id) => controller.versionMarkdown(id),
    restore:
      editable && doc && !doc.archived
        ? (version) =>
            setConfirm({
              title: t('blackboard.history.restoreTitle'),
              message: t('blackboard.history.restoreConfirm', {
                time: new Date(version.created_at).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }),
              }),
              confirmLabel: t('blackboard.history.restore'),
              action: () => controller.restoreVersion(version.id),
              testId: 'blackboard-restore-dialog',
            })
        : null,
    close: () => controller.openVersion(null),
  };

  const openThreadFromChat = (docId: string, threadId: string) => {
    controller.selectDoc(docId);
    controller.openThread(threadId);
  };

  // The panels on the right; any number of them are open at once, stacked.
  const renderPanel = (tab: RailTab, ws: WorkspaceView): ReactNode =>
    tab === 'chat' ? (
      <ChatPanel
        messages={state.chat}
        hasMore={state.chatHasMore}
        members={state.members}
        meId={state.me?.user_id ?? null}
        canPost={talk}
        canTask={editable}
        sessions={state.sessions}
        mandates={mandatesById}
        decisions={decisionsById}
        docTitles={docTitles}
        decisionActions={decisionActions}
        onLoadOlder={() => controller.loadOlderChat().catch(report)}
        onPost={({ body, sessionId }) => controller.postChat(body, sessionId).then(() => undefined, rethrow)}
        onOpenThread={openThreadFromChat}
      />
    ) : tab === 'comments' ? (
      <CommentsPanel
        doc={doc}
        threads={state.threads}
        activeThread={state.activeThread}
        showResolved={state.showResolved}
        members={state.members}
        meId={state.me?.user_id ?? null}
        canComment={commentable}
        canTask={editable}
        sessions={state.sessions}
        mandates={mandatesById}
        decisions={decisionsById}
        docTitles={docTitles}
        decisionActions={decisionActions}
        actions={threadActions}
      />
    ) : tab === 'decisions' ? (
      <DecisionsPanel
        decisions={state.decisions}
        meId={state.me?.user_id ?? null}
        docTitles={docTitles}
        actions={decisionActions}
      />
    ) : tab === 'history' ? (
      <HistoryPanel
        doc={doc}
        versions={state.history}
        hasMore={state.historyHasMore}
        openVersion={state.openVersion}
        canSave={editable && Boolean(doc && !doc.archived)}
        onOpen={(id) => controller.openVersion(id)}
        onSave={(label) => controller.saveVersion(label).then(() => undefined, rethrow)}
        onMore={() => void controller.loadOlderHistory().catch(report)}
      />
    ) : tab === 'members' ? (
      <MembersPanel
        workspace={ws}
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
    ) : tab === 'agents' ? (
      <AgentsPanel
        mandates={state.mandates}
        sessions={state.sessions}
        docs={state.docs}
        meId={state.me?.user_id ?? null}
        canEdit={editable}
        sessionTitles={state.sessionTitles}
        onStart={() => controller.startAgentSession().then(openChat, report)}
        onLoadAttachable={() => controller.attachableSessions().catch((error) => (report(error), []))}
        onAttach={(sessionId) => controller.attachSession(sessionId).catch(report)}
        onChat={openChat}
        onRename={(sessionId, title) => controller.renameSession(sessionId, title).catch(rethrow)}
        onOpen={(sessionId) => controller.openSession(sessionId)}
        onDetach={(sessionId) => void controller.detachSession(sessionId).catch(report)}
        onCancel={askCancelMandate}
        onDecide={decideRun}
        onResolveUnknown={(mandate, status) => void controller.resolveUnknown(mandate.id, status).catch(report)}
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
    );

  const openDecisions = state.decisions.filter((d) => d.status === 'open' || d.status === 'proposed').length;
  const dockPanels: DockPanel[] = RAIL_ORDER.map((tab, index) => ({
    id: tab,
    label: t(RAIL_LABELS[tab]),
    icon: RAIL_ICONS[tab],
    badge: tab === 'decisions' ? openDecisions : tab === 'chat' ? state.chatUnread : 0,
    shortcut: `Ctrl+Alt+${index + 1}`,
    fill: tab === 'chat',
    render: () => (workspace ? renderPanel(tab, workspace) : null),
  }));

  const chatInView = Boolean(workspace) && !layout.dockHidden && state.panels.includes('chat') && !layout.collapsed.includes('chat');
  useEffect(() => controller.setChatInView(chatInView), [controller, chatInView]);

  useShortcuts(
    {
      showPanel: (index, split) => {
        const tab = RAIL_ORDER[index];
        if (!tab) return;
        if (layout.dockHidden) {
          updateLayout({ dockHidden: false });
          if (!state.panels.includes(tab)) controller.showPanel(tab);
        } else if (!split) {
          controller.showPanel(tab);
        } else if (state.panels.includes(tab)) {
          controller.closePanel(tab);
        } else {
          controller.movePanel(tab, state.panels.length);
        }
      },
      toggleSidebar: () => updateLayout({ sidebarHidden: !layout.sidebarHidden }),
      toggleDock: () => updateLayout({ dockHidden: !layout.dockHidden }),
      toggleChat: () => {
        if (layout.chats.length) updateLayout({ chatMinimized: !layout.chatMinimized });
        else if (state.sessions.length) openChat(state.sessions[0].session_id);
        else toast.open({ content: t('blackboard.agentChat.noSession') });
      },
      newDoc: () => editable && setOpen('newDoc'),
      goToDoc: () => setSwitcher(true),
      help: () => setHelp(true),
    },
    Boolean(workspace),
  );

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
          {layout.sidebarHidden ? (
            <div className="bb-sidebar-strip">
              <Button
                size="sm"
                variant="quiet"
                icon={<PanelLeftOpen size={16} />}
                aria-label={t('blackboard.layout.showSidebar')}
                title={`${t('blackboard.layout.showSidebar')} (Ctrl+Alt+S)`}
                data-testid="blackboard-sidebar-show-btn"
                onClick={() => updateLayout({ sidebarHidden: false })}
              />
            </div>
          ) : (
            <>
          <Sidebar
            width={layout.sidebarWidth}
            onHide={() => updateLayout({ sidebarHidden: true })}
            state={state}
            onSelectHost={(id) => void controller.selectHost(id)}
            onSelectWorkspace={(id) => void controller.selectWorkspace(id)}
            onSelectDoc={(id) => controller.selectDoc(id)}
            onNewDoc={() => setOpen('newDoc')}
            onJoin={() => setOpen('join')}
            onNewWorkspace={() => setOpen('new')}
            onSettings={() => setOpen('settings')}
          />
              <Resizer
                orientation="vertical"
                label={t('blackboard.layout.resizeSidebar')}
                testId="blackboard-sidebar-resizer"
                onStart={() => (sidebarWidthAtStart.current = layout.sidebarWidth)}
                onResize={(delta) => updateLayout({ sidebarWidth: clamp(sidebarWidthAtStart.current + delta, LIMITS.sidebar) })}
              />
            </>
          )}
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
                suggestionActions={suggestionActions}
                commentActions={commentActions}
                openVersion={openVersion}
                versions={state.history}
                versionActions={versionActions}
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
            <>
              <Dock
                panels={dockPanels}
                open={state.panels}
                active={state.rail}
                onClose={(tab) => controller.closePanel(tab)}
                onMove={(tab, index) => controller.movePanel(tab, index)}
              />
              <ActivityBar
                panels={dockPanels}
                open={state.panels}
                onShow={(tab) => controller.showPanel(tab)}
                onHelp={() => setHelp(true)}
              />
            </>
          ) : null}
        </>
      )}

      {workspace ? (
        <AgentChat
          workspace={workspace}
          doc={doc}
          titles={(id) => state.sessionTitles[id] ?? t('blackboard.agentChat.untitled')}
          onOpenFull={(id) => controller.openSession(id)}
          onRename={(id, title) => controller.renameSession(id, title).catch(rethrow)}
          onNew={editable ? () => controller.startAgentSession().then(openChat, report) : null}
        />
      ) : null}
      <DocSwitcher open={switcher} docs={state.docs} onPick={(id) => controller.selectDoc(id)} onClose={() => setSwitcher(false)} />
      <ShortcutsDialog open={help} onClose={() => setHelp(false)} />
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
        hostUrl={host?.url ?? null}
        displayName={state.me?.display_name ?? ''}
        hostStatus={state.hostStatus}
        isOperator={Boolean(state.me?.is_operator)}
        profile={state.me}
        im={{
          accounts: () => controller.imAccounts(),
          linkCode: () => controller.imLinkCode(),
          unlink: (platform, externalId) => controller.imUnlink(platform, externalId),
          bots: () => controller.hostBots(),
          createBot: (name) => controller.createBot(name),
          revokeBot: (botId) => controller.revokeBot(botId),
          botLinks: () => controller.botLinks(),
          connectBot: (link) => controller.connectBot(link),
          removeBotLink: (id) => controller.removeBotLink(id),
        }}
        onHealth={() => controller.hostHealth()}
        access={{
          rotateToken: () => controller.rotateToken(),
          users: () => controller.hostUsers(),
          setUserStatus: (userId, status) => controller.setUserStatus(userId, status),
        }}
        onSaveName={(name) => controller.setDisplayName(name)}
        onApplyHosting={(settings) => controller.setHostSettings(settings)}
        onClose={close}
      />
      <NewDocumentDialog open={open === 'newDoc'} onCreate={(title, markdown) => controller.createDoc(title, markdown)} onClose={close} />
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
      <ExportDialog
        open={docDialog?.kind === 'export'}
        docTitle={docDialog?.doc.title ?? ''}
        onExport={async (format, includeDecisions) => {
          const result = await controller.exportDoc(format, { includeDecisions });
          download(result.url);
        }}
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
