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

export type MandateStatus = 'queued' | 'running' | 'waiting_for_answer' | 'done' | 'failed' | 'cancelled' | 'refused' | 'unknown';

export interface ReceiptView {
  id: string;
  mandate_id: string;
  doc_id: string;
  status: 'pending' | 'applied' | 'aborted';
  note: string;
  suggestion_ids: string[];
  error: { code: string; message: string } | null;
  created_at: string;
}

export interface MandateView {
  id: string;
  workspace_id: string;
  origin: 'comment' | 'workspace_chat' | 'workspace_session';
  requester_id: string;
  requester_name: string | null;
  instruction: string;
  status: MandateStatus;
  status_reason: string | null;
  created_at: string;
  last_activity_at: string | null;
  receipts: ReceiptView[];
  // Doc id -> this run's suggestions nobody has decided on yet.
  pending: Record<string, string[]>;
  // Where the task was given: {thread_id, comment_id} or {message_id} or {session_id}.
  origin_ref?: Record<string, string>;
  scope?: { doc_id?: string; block_from?: string; block_to?: string };
  turn_count?: number;
  // A comment task waiting for its document: 1 is next.
  queue_position?: number | null;
}

// A session of this person's that works on a workspace with an agent.
export interface SessionAttachmentView {
  session_id: string;
  host: string;
  workspace_id: string;
  attached_at: string;
  // The workspace's title when it was attached.
  title: string;
  host_name?: string;
}

export interface SuggestionView {
  id: string;
  types: string[];
  author: { id: string; kind: 'person' | 'agent'; mandate?: string | null } | null;
  inserted: string;
  deleted: string;
  blockIds: string[];
}

export type Mention = { kind: 'agent' } | { kind: 'user'; id: string };
export type AuthorKind = 'person' | 'agent' | 'system';

export interface ChatMessageView {
  id: string;
  workspace_id: string;
  author_id: string;
  author_kind: AuthorKind;
  author_name: string | null;
  // message and answer are people's text; question the agent's; notice and summary are JSON codes.
  kind: 'message' | 'notice' | 'summary' | 'question' | 'answer';
  body: string;
  mentions: Mention[];
  mandate_id: string | null;
  decision_id: string | null;
  created_at: string;
}

export type AnchorStatus = 'ok' | 'drifted' | 'orphaned';

// A passage of a document: its first and last block, its ends as Yjs relative positions (base64),
// and the text it quoted.
export interface AnchorDraft {
  block_id: string;
  block_to: string;
  digest: string | null;
  start: string;
  end: string;
  quote: string;
  offset: number;
  length: number;
}

export interface AnchorView extends AnchorDraft {
  status: AnchorStatus;
}

export interface CommentView {
  id: string;
  thread_id: string;
  author_id: string;
  author_kind: AuthorKind;
  author_name: string | null;
  body: string;
  mentions: Mention[];
  scope_switch: boolean;
  mandate_id: string | null;
  decision_id: string | null;
  created_at: string;
  edited_at: string | null;
  mandate_status?: MandateStatus | null;
}

export interface ThreadView {
  id: string;
  workspace_id: string;
  doc_id: string;
  anchor: AnchorView;
  created_by: string;
  created_by_name: string | null;
  created_at: string;
  resolved_at: string | null;
  resolved_by: string | null;
  position: number | null;
  comments: CommentView[];
}

export type DecisionStatus = 'open' | 'proposed' | 'answered' | 'cancelled';

export interface DecisionView {
  id: string;
  workspace_id: string;
  mandate_id: string;
  requester_id: string;
  requester_name: string | null;
  doc_id: string | null;
  block_id: string | null;
  quote: string | null;
  question: string;
  options: Array<{ label: string; description: string }>;
  recommended: number | null;
  status: DecisionStatus;
  answer: { option: number | null; text: string | null } | null;
  answer_label: string;
  answered_by: string | null;
  answered_by_name: string | null;
  accepted_by: string | null;
  accepted_by_name: string | null;
  created_at: string;
  passage_changed?: boolean;
}

export type VersionReason = 'created' | 'agent_turn' | 'idle' | 'import' | 'restore' | 'manual';

export interface VersionView {
  id: string;
  doc_id: string;
  created_at: string;
  reason: VersionReason;
  authors: Array<{ id: string; kind: 'person' | 'agent'; name: string }>;
  mandate_id: string | null;
  mandate_instruction: string | null;
  restored_from: string | null;
  label: string | null;
  size: number;
}

export type DiffStatus = 'unchanged' | 'changed' | 'added' | 'removed' | 'moved';

export interface DiffBlockView {
  id: string | null;
  type: string;
  status: DiffStatus;
  markdown: string;
  inline: Array<{ op: 'eq' | 'ins' | 'del'; text: string }> | null;
  pending: boolean;
  was_pending: boolean;
}

export interface DiffView {
  from: string | null;
  to: string;
  blocks: DiffBlockView[];
  summary: Partial<Record<DiffStatus, number>>;
}

export type ExportFormat = 'md' | 'docx' | 'pdf';

// An IM account connected to this person's user on a host (milestone 7).
export interface IdentityView {
  platform: string;
  external_id: string;
  display_name: string | null;
  linked_at: string;
}

// A shared bot made by the host's operator.
export interface BotView {
  id: string;
  name: string;
  created_at: string;
  last_used_at: string | null;
  revoked: boolean;
}

// A bot link this jiuwenswarm keeps, to answer IM messages as a shared bot.
export interface BotLinkView {
  id: string;
  host_uid: string;
  host_name: string;
  url: string;
  bot_id: string;
  bot_name: string;
  added_at: string;
}

export type Rpc = <T = unknown>(method: string, params?: Record<string, unknown>) => Promise<T>;
export type Subscribe = (event: string, handler: (payload: Record<string, unknown>) => void) => () => void;
