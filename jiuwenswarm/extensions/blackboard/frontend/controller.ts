// State and actions of the Blackboard page, without React, so the logic can be
// tested in Node with a fake RPC client and a fake event source.
import type {
  HostStatus,
  HostsPayload,
  HostView,
  InviteRole,
  InviteView,
  MeView,
  MemberView,
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
  hostStatus: null,
  loaded: false,
  loadError: null,
};

const HOST_EVENTS = [
  'blackboard.hosts.updated',
  'blackboard.host.status_changed',
  'blackboard.workspace.updated',
  'blackboard.member.updated',
  'blackboard.me.updated',
  'blackboard.member.role_changed',
] as const;

export function currentWorkspace(state: BlackboardState): WorkspaceView | null {
  return state.workspaces.find((w) => w.id === state.workspaceId) ?? null;
}

export function currentHost(state: BlackboardState): HostView | null {
  return state.hosts.find((h) => h.id === state.hostId) ?? null;
}

export function isOwner(state: BlackboardState): boolean {
  return currentWorkspace(state)?.role === 'owner';
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
        this.set({ me: null, workspaces: [], workspaceId: null, members: [], invites: [] });
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
      if (!keep) this.set({ members: [], invites: [] });
      else await this.refreshMembers();
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

  // ---- selection ----

  async selectHost(hostId: string): Promise<void> {
    if (hostId === this.state.hostId) return;
    this.set({ hostId, me: null, workspaces: [], workspaceId: null, members: [], invites: [], loadError: null });
    await this.refreshWorkspaces();
  }

  async selectWorkspace(workspaceId: string | null): Promise<void> {
    this.set({ workspaceId, members: [], invites: [] });
    if (workspaceId) await this.refreshMembers();
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
        this.set({ workspaceId: null, members: [], invites: [] });
      }
      await this.refreshWorkspaces();
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
    this.set({ workspaceId: null, members: [], invites: [] });
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
      this.set({ workspaceId: null, members: [], invites: [] });
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
