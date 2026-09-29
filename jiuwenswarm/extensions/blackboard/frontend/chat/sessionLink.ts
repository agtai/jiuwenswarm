// A chat session's links to Blackboard workspaces, as the chat input shows and changes them.
import type { HostsPayload, MeView, Rpc, SessionAttachmentView } from '../types';

export interface WorkspaceChoice {
  host: string;
  hostName: string;
  workspaceId: string;
  title: string;
}

// Workspaces this person can give an agent, on every host they joined: editor or owner, not
// archived. A host that does not answer is left out.
export async function workspaceChoices(rpc: Rpc): Promise<WorkspaceChoice[]> {
  const payload = await rpc<HostsPayload>('blackboard.hosts.list');
  const perHost = await Promise.all(
    (payload.hosts ?? []).map(async (host) => {
      try {
        const me = await rpc<MeView>('blackboard.me', { host: host.id });
        return (me.workspaces ?? [])
          .filter((w) => !w.archived && (w.role === 'owner' || w.role === 'editor'))
          .map((w) => ({ host: host.id, hostName: host.name, workspaceId: w.id, title: w.title }));
      } catch {
        return [];
      }
    }),
  );
  return perHost.flat();
}

export async function sessionAttachments(rpc: Rpc, sessionId: string): Promise<SessionAttachmentView[]> {
  const result = await rpc<{ sessions?: SessionAttachmentView[] }>('blackboard.session.list', { session_id: sessionId });
  return result.sessions ?? [];
}

export function isAttached(attachments: SessionAttachmentView[], choice: WorkspaceChoice): boolean {
  return attachments.some((a) => a.host === choice.host && a.workspace_id === choice.workspaceId);
}

// Add the workspace to the session's, or take it away when the session already works there.
export async function toggleAttachment(
  rpc: Rpc,
  sessionId: string,
  choice: WorkspaceChoice,
  attachments: SessionAttachmentView[],
): Promise<SessionAttachmentView[]> {
  const target = { host: choice.host, workspace_id: choice.workspaceId, session_id: sessionId };
  if (isAttached(attachments, choice)) {
    await rpc('blackboard.session.detach', target);
    return attachments.filter((a) => !(a.host === choice.host && a.workspace_id === choice.workspaceId));
  }
  const result = await rpc<{ session: SessionAttachmentView }>('blackboard.session.attach', target);
  return [...attachments, { ...result.session, host_name: choice.hostName }];
}
