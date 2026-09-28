export type Role = 'owner' | 'editor' | 'commenter' | 'viewer';
export type InviteRole = Exclude<Role, 'owner'>;
export type LinkStatus = 'connecting' | 'connected' | 'offline' | 'unauthorized' | 'stopped';

export interface HostView {
  id: string;
  host_uid: string;
  name: string;
  url: string;
  user_id: string;
  display_name: string;
  is_self: boolean;
  is_default: boolean;
  status: LinkStatus;
}

export interface HostsPayload {
  hosts: HostView[];
  default_host: string;
}

export interface WorkspaceView {
  id: string;
  name: string;
  title: string;
  created_at: string;
  archived: boolean;
  role: Role;
}

export interface MeView {
  user_id: string;
  display_name: string;
  is_operator: boolean;
  workspaces: WorkspaceView[];
}

export interface MemberView {
  user_id: string;
  display_name: string;
  role: Role;
  joined_at: string;
  disabled: boolean;
}

export interface InviteView {
  code: string;
  role: InviteRole;
  created_at: string;
  expires_at: string | null; // null: never expires
  max_uses: number | null; // null: no limit
  uses: number;
  state: 'active' | 'expired' | 'used_up' | 'revoked';
  url: string;
}

export interface HostSettingsView {
  enabled: boolean;
  name: string;
  bind: string;
  port: number;
  public_url: string;
  operator_name: string;
  [key: string]: unknown;
}

export interface HostStatus {
  running: boolean;
  enabled: boolean;
  // The name members see, while the host runs.
  name?: string | null;
  settings: HostSettingsView;
  base_url: string;
  listening?: string | null;
  error: string | null;
  reachable_from_other_machines: boolean;
}

export interface DocView {
  id: string;
  workspace_id: string;
  title: string;
  is_instructions: boolean;
  is_pinned: boolean;
  created_by: string;
  created_at: string;
  archived: boolean;
}

export type DocServiceState = 'stopped' | 'starting' | 'running' | 'restarting' | 'unavailable';

export interface DocServiceStatus {
  status: DocServiceState;
  // not_built | node_missing | node_too_old | start_failed | exited | not_configured
  reason?: string | null;
  detail?: string;
}

export interface ReferenceView {
  id: string;
  workspace_id: string;
  kind: 'file' | 'image';
  name: string;
  mime: string;
  size: number;
  note: string;
  uploaded_by: string;
  uploaded_by_name: string | null;
  uploaded_at: string;
}

export interface DocToken {
  token: string;
  url: string;
  role: Role;
  // The document or its workspace is archived: it opens read-only.
  frozen: boolean;
  expires_in: number;
}

export type Rpc = <T = unknown>(method: string, params?: Record<string, unknown>) => Promise<T>;
export type Subscribe = (event: string, handler: (payload: Record<string, unknown>) => void) => () => void;
