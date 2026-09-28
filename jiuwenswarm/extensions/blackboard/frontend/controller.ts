// State and actions of the Blackboard page, without React, so the logic can be
// tested in Node with a fake RPC client and a fake event source.
import type {
  DocServiceStatus,
  DocToken,
  DocView,
  HostStatus,
  HostsPayload,
  HostView,
  InviteRole,
  InviteView,
  MeView,
  MemberView,
  ReferenceView,
  Role,
  Rpc,
  Subscribe,
  WorkspaceView,
} from './types';

export interface BlackboardState {
  hosts: HostView[];
  defaultHost: string;
  hostId: string | null;
  me: MeView | null;
  workspaces: WorkspaceView[];
  workspaceId: string | null;
  members: MemberView[];
  invites: InviteView[];
  docs: DocView[];
  docId: string | null;
  docservice: DocServiceStatus | null;
  references: ReferenceView[];
  maxUploadMb: number;
  hostStatus: HostStatus | null;
  loaded: boolean;
  loadError: string | null;
}

export const INITIAL_STATE: BlackboardState = {
  hosts: [],
  defaultHost: '',
  hostId: null,
  me: null,
  workspaces: [],
  workspaceId: null,
  members: [],
  invites: [],
  docs: [],
  docId: null,
  docservice: null,
  references: [],
  maxUploadMb: 25,
  hostStatus: null,
  loaded: false,
  loadError: null,
};

// What belongs to the selected workspace; cleared whenever the selection changes.
const WORKSPACE_CONTENT = { members: [], invites: [], docs: [], docId: null, docservice: null, references: [] };

const HOST_EVENTS = [
  'blackboard.hosts.updated',
  'blackboard.host.status_changed',
  'blackboard.workspace.updated',
  'blackboard.member.updated',
  'blackboard.me.updated',
  'blackboard.member.role_changed',
  'blackboard.doc.updated',
  'blackboard.reference.updated',
] as const;

export function currentWorkspace(state: BlackboardState): WorkspaceView | null {
  return state.workspaces.find((w) => w.id === state.workspaceId) ?? null;
}

export function currentHost(state: BlackboardState): HostView | null {
  return state.hosts.find((h) => h.id === state.hostId) ?? null;
}

export function currentDoc(state: BlackboardState): DocView | null {
  return state.docs.find((d) => d.id === state.docId) ?? null;
}

export function isOwner(state: BlackboardState): boolean {
  return currentWorkspace(state)?.role === 'owner';
}

// Editors and owners change documents and references, unless the workspace is archived.
export function canEdit(state: BlackboardState): boolean {
  const workspace = currentWorkspace(state);
  return Boolean(workspace && !workspace.archived && (workspace.role === 'owner' || workspace.role === 'editor'));
}

export function errorText(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return String(error);
}

export class BlackboardController {
  private state: BlackboardState = INITIAL_STATE;
  private readonly listeners = new Set<() => void>();
  private unsubscribes: Array<() => void> = [];

  constructor(
    private readonly rpc: Rpc,
    private readonly subscribeEvent: Subscribe,
  ) {}

  // ---- store ----

  getState = (): BlackboardState => this.state;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  private set(patch: Partial<BlackboardState>): void {
    this.state = { ...this.state, ...patch };
    for (const listener of this.listeners) listener();
  }

  // ---- lifecycle ----

  async start(): Promise<void> {
    this.stop();
    this.unsubscribes = HOST_EVENTS.map((event) =>
      this.subscribeEvent(event, (payload) => {
        void this.onEvent(event, payload);
      }),
    );
    await Promise.all([this.refreshHosts(), this.refreshHostStatus()]);
    this.set({ loaded: true });
  }

  stop(): void {
    for (const unsubscribe of this.unsubscribes) unsubscribe();
    this.unsubscribes = [];
  }

  // ---- loading ----

  async refreshHosts(): Promise<void> {
    try {
      const payload = await this.rpc<HostsPayload>('blackboard.hosts.list');
      const hosts = payload.hosts ?? [];
      const keep = hosts.some((h) => h.id === this.state.hostId);
      const hostId = keep ? this.state.hostId : payload.default_host || hosts[0]?.id || null;
      const hostChanged = hostId !== this.state.hostId;
      this.set({ hosts, defaultHost: payload.default_host ?? '', hostId, loadError: null });
      if (hostChanged) {
        this.set({ me: null, workspaces: [], workspaceId: null, ...WORKSPACE_CONTENT });
        if (hostId) await this.refreshWorkspaces();
      }
    } catch (error) {
      this.set({ loadError: errorText(error) });
    }
  }

  async refreshHostStatus(): Promise<void> {
    try {
      const status = await this.rpc<HostStatus>('blackboard.host.status');
      this.set({ hostStatus: status });
    } catch {
      // The status card simply stays empty.
    }
  }

  async refreshWorkspaces(): Promise<void> {
    const hostId = this.state.hostId;
    if (!hostId) return;
    try {
      const me = await this.rpc<MeView>('blackboard.me', { host: hostId });
      if (hostId !== this.state.hostId) return;
      const workspaces = me.workspaces ?? [];
      const keep = workspaces.some((w) => w.id === this.state.workspaceId);
      const workspaceId = keep ? this.state.workspaceId : null;
      this.set({ me, workspaces, workspaceId, loadError: null });
      if (!keep) this.set(WORKSPACE_CONTENT);
      else await this.refreshWorkspaceContent();
    } catch (error) {
      if (hostId === this.state.hostId) this.set({ loadError: errorText(error), me: null, workspaces: [] });
    }
  }

  async refreshMembers(): Promise<void> {
    const { hostId, workspaceId } = this.state;
    if (!hostId || !workspaceId) return;
    const owner = isOwner(this.state);
    try {
      const [members, invites] = await Promise.all([
        this.rpc<{ members: MemberView[] }>('blackboard.member.list', { host: hostId, workspace_id: workspaceId }),
        owner
          ? this.rpc<{ invites: InviteView[] }>('blackboard.invite.list', { host: hostId, workspace_id: workspaceId })
          : Promise.resolve({ invites: [] as InviteView[] }),
      ]);
      if (hostId !== this.state.hostId || workspaceId !== this.state.workspaceId) return;
      this.set({ members: members.members ?? [], invites: invites.invites ?? [] });
    } catch (error) {
      this.set({ loadError: errorText(error) });
    }
  }

  async refreshWorkspaceContent(): Promise<void> {
    await Promise.all([this.refreshMembers(), this.refreshDocs(), this.refreshReferences()]);
  }

  async refreshDocs(): Promise<void> {
    const { hostId, workspaceId } = this.state;
    if (!hostId || !workspaceId) return;
    try {
      const result = await this.rpc<{ docs: DocView[]; docservice: DocServiceStatus }>('blackboard.doc.list', {
        host: hostId,
        workspace_id: workspaceId,
      });
      if (hostId !== this.state.hostId || workspaceId !== this.state.workspaceId) return;
      const docs = result.docs ?? [];
      // An archived or deleted document closes; otherwise the first one opens.
      const keep = docs.some((d) => d.id === this.state.docId);
      this.set({ docs, docservice: result.docservice ?? null, docId: keep ? this.state.docId : (docs[0]?.id ?? null) });
    } catch (error) {
      this.set({ loadError: errorText(error) });
    }
  }

  async refreshReferences(): Promise<void> {
    const { hostId, workspaceId } = this.state;
    if (!hostId || !workspaceId) return;
    try {
      const result = await this.rpc<{ references: ReferenceView[]; max_upload_mb: number }>('blackboard.reference.list', {
        host: hostId,
        workspace_id: workspaceId,
      });
      if (hostId !== this.state.hostId || workspaceId !== this.state.workspaceId) return;
      this.set({ references: result.references ?? [], maxUploadMb: result.max_upload_mb ?? this.state.maxUploadMb });
    } catch (error) {
      this.set({ loadError: errorText(error) });
    }
  }

  // ---- selection ----

  async selectHost(hostId: string): Promise<void> {
    if (hostId === this.state.hostId) return;
    this.set({ hostId, me: null, workspaces: [], workspaceId: null, ...WORKSPACE_CONTENT, loadError: null });
    await this.refreshWorkspaces();
  }

  async selectWorkspace(workspaceId: string | null): Promise<void> {
    if (workspaceId === this.state.workspaceId) return;
    this.set({ workspaceId, ...WORKSPACE_CONTENT });
    if (workspaceId) await this.refreshWorkspaceContent();
  }

  selectDoc(docId: string | null): void {
    this.set({ docId });
  }

  // ---- events ----

  async onEvent(event: string, payload: Record<string, unknown>): Promise<void> {
    const host = typeof payload.host === 'string' ? payload.host : null;
    const workspaceId = typeof payload.workspace_id === 'string' ? payload.workspace_id : null;
    switch (event) {
      case 'blackboard.hosts.updated':
        await this.refreshHosts();
        return;
      case 'blackboard.host.status_changed':
        this.set({ hostStatus: payload as unknown as HostStatus });
        return;
      default:
        break;
    }
    if (!host || host !== this.state.hostId) return;
    if (event === 'blackboard.workspace.updated') {
      if ((payload.deleted || payload.removed) && workspaceId === this.state.workspaceId) {
        this.set({ workspaceId: null, ...WORKSPACE_CONTENT });
      }
      await this.refreshWorkspaces();
    } else if (event === 'blackboard.doc.updated') {
      if (workspaceId === this.state.workspaceId) await this.refreshDocs();
    } else if (event === 'blackboard.reference.updated') {
      if (workspaceId === this.state.workspaceId) await this.refreshReferences();
    } else if (event === 'blackboard.member.updated' || event === 'blackboard.member.role_changed') {
      if (event === 'blackboard.member.role_changed') await this.refreshWorkspaces();
      else if (workspaceId === this.state.workspaceId) await this.refreshMembers();
    } else if (event === 'blackboard.me.updated') {
      await this.refreshWorkspaces();
    }
  }

  // ---- actions (they throw, so dialogs can show the error) ----

  private requireHost(): string {
    if (!this.state.hostId) throw new Error('No host selected');
    return this.state.hostId;
  }

  private requireWorkspace(): { host: string; workspace_id: string } {
    const host = this.requireHost();
    if (!this.state.workspaceId) throw new Error('No workspace selected');
    return { host, workspace_id: this.state.workspaceId };
  }

  async join(url: string, displayName: string): Promise<{ host: string; workspace?: WorkspaceView }> {
    const result = await this.rpc<{ host: string; workspace?: WorkspaceView }>('blackboard.hosts.join', {
      url,
      display_name: displayName,
    });
    await this.refreshHosts();
    if (result.host) await this.selectHost(result.host);
    if (result.workspace?.id) {
      await this.refreshWorkspaces();
      await this.selectWorkspace(result.workspace.id);
    }
    return result;
  }

  async createWorkspace(name: string, title: string): Promise<WorkspaceView> {
    const host = this.requireHost();
    const result = await this.rpc<{ workspace: WorkspaceView }>('blackboard.workspace.create', { host, name, title });
    await this.refreshWorkspaces();
    await this.selectWorkspace(result.workspace.id);
    return result.workspace;
  }

  async renameWorkspace(title: string): Promise<void> {
    await this.rpc('blackboard.workspace.rename', { ...this.requireWorkspace(), title });
    await this.refreshWorkspaces();
  }

  async setArchived(archived: boolean): Promise<void> {
    await this.rpc(archived ? 'blackboard.workspace.archive' : 'blackboard.workspace.unarchive', this.requireWorkspace());
    await this.refreshWorkspaces();
  }

  async deleteWorkspace(): Promise<void> {
    await this.rpc('blackboard.workspace.delete', this.requireWorkspace());
    this.set({ workspaceId: null, ...WORKSPACE_CONTENT });
    await this.refreshWorkspaces();
  }

  async setRole(userId: string, role: Role): Promise<void> {
    await this.rpc('blackboard.member.set_role', { ...this.requireWorkspace(), user_id: userId, role });
    await this.refreshMembers();
  }

  async removeMember(userId: string): Promise<void> {
    const target = this.requireWorkspace();
    await this.rpc('blackboard.member.remove', { ...target, user_id: userId });
    if (userId === this.state.me?.user_id) {
      this.set({ workspaceId: null, ...WORKSPACE_CONTENT });
      await this.refreshWorkspaces();
    } else {
      await this.refreshMembers();
    }
  }

  // null means never expires or no limit on uses.
  async createInvite(role: InviteRole, expiresInMinutes: number | null, maxUses: number | null): Promise<InviteView> {
    const result = await this.rpc<{ invite: InviteView }>('blackboard.invite.create', {
      ...this.requireWorkspace(),
      role,
      expires_in_minutes: expiresInMinutes,
      max_uses: maxUses,
    });
    await this.refreshMembers();
    return result.invite;
  }

  async revokeInvite(code: string): Promise<void> {
    await this.rpc('blackboard.invite.revoke', { ...this.requireWorkspace(), code });
    await this.refreshMembers();
  }

  // ---- documents ----

  async createDoc(title: string, markdown?: string): Promise<{ doc: DocView; raw_html: boolean }> {
    const result = await this.rpc<{ doc: DocView; raw_html: boolean }>('blackboard.doc.create', {
      ...this.requireWorkspace(),
      title,
      ...(markdown !== undefined ? { markdown } : {}),
    });
    await this.refreshDocs();
    this.selectDoc(result.doc.id);
    return result;
  }

  async renameDoc(docId: string, title: string): Promise<void> {
    await this.rpc('blackboard.doc.rename', { host: this.requireHost(), doc_id: docId, title });
    await this.refreshDocs();
  }

  async archiveDoc(docId: string): Promise<void> {
    await this.rpc('blackboard.doc.archive', { host: this.requireHost(), doc_id: docId });
    await this.refreshDocs();
  }

  async setDocPinned(docId: string, pinned: boolean): Promise<void> {
    await this.rpc('blackboard.doc.pin', { host: this.requireHost(), doc_id: docId, pinned });
    await this.refreshDocs();
  }

  async setInstructions(docId: string): Promise<void> {
    await this.rpc('blackboard.doc.set_instructions', { host: this.requireHost(), doc_id: docId });
    await this.refreshDocs();
  }

  async importMarkdown(docId: string, markdown: string): Promise<{ raw_html: boolean }> {
    return this.rpc<{ raw_html: boolean }>('blackboard.doc.import_markdown', { host: this.requireHost(), doc_id: docId, markdown });
  }

  // The agent view: Markdown with a block id comment before every top-level block.
  async readDoc(docId: string): Promise<string> {
    const result = await this.rpc<{ markdown: string }>('blackboard.doc.read', { host: this.requireHost(), doc_id: docId });
    return result.markdown ?? '';
  }

  docToken = (docId: string): Promise<DocToken> =>
    this.rpc<DocToken>('blackboard.doc.token', { host: this.requireHost(), doc_id: docId });

  // ---- references ----

  async uploadReference(file: { name: string; mime: string; data: string }, note = ''): Promise<ReferenceView> {
    const result = await this.rpc<{ reference: ReferenceView }>('blackboard.reference.upload', {
      ...this.requireWorkspace(),
      ...file,
      note,
    });
    await this.refreshReferences();
    return result.reference;
  }

  async removeReference(referenceId: string): Promise<void> {
    await this.rpc('blackboard.reference.remove', { host: this.requireHost(), reference_id: referenceId });
    await this.refreshReferences();
  }

  async setReferenceNote(referenceId: string, note: string): Promise<void> {
    await this.rpc('blackboard.reference.set_note', { host: this.requireHost(), reference_id: referenceId, note });
    await this.refreshReferences();
  }

  async referenceUrl(referenceId: string): Promise<string> {
    const result = await this.rpc<{ url: string }>('blackboard.reference.url', { host: this.requireHost(), reference_id: referenceId });
    return result.url;
  }

  async setDisplayName(displayName: string): Promise<void> {
    await this.rpc('blackboard.me.set_name', { host: this.requireHost(), display_name: displayName });
    await this.refreshWorkspaces();
  }

  async setHostSettings(settings: Record<string, unknown>): Promise<HostStatus> {
    const status = await this.rpc<HostStatus>('blackboard.host.set_settings', { settings });
    this.set({ hostStatus: status });
    await this.refreshHosts();
    return status;
  }

  async removeHost(hostId: string): Promise<void> {
    await this.rpc('blackboard.hosts.remove', { host: hostId });
    await this.refreshHosts();
  }

  async setDefaultHost(hostId: string): Promise<void> {
    await this.rpc('blackboard.hosts.set_default', { host: hostId });
    await this.refreshHosts();
  }
}
