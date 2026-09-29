import { useEffect, useState } from 'react';

import type { ApplicationPluginTaskInputTagProps } from '../../../../channels/web/frontend/src/applicationPlugins/types';
import { useAdaptiveTooltip } from '../../../../channels/web/frontend/src/hooks/useAdaptiveTooltip';
import { BlackboardIcon } from '../BlackboardIcon';
import type { SessionAttachmentView } from '../types';
import { openBlackboard, rpc, sharedController, subscribe } from '../useController';
import { sessionAttachments } from './sessionLink';

const REFRESH_EVENTS = ['blackboard.sessions.updated', 'blackboard.hosts.updated'];

// Shows in the chat input when the session works on Blackboard workspaces; hover names them, a click
// opens the first on the Agents tab.
export function BlackboardTaskInputTag({ sessionId }: ApplicationPluginTaskInputTagProps) {
  const [attachments, setAttachments] = useState<SessionAttachmentView[]>([]);
  const { tooltip, handlers } = useAdaptiveTooltip({ placement: 'top', maxWidth: 480 });

  useEffect(() => {
    setAttachments([]);
    if (!sessionId) return;
    let alive = true;
    const load = () =>
      sessionAttachments(rpc, sessionId).then(
        (found) => alive && setAttachments(found),
        () => alive && setAttachments([]),
      );
    void load();
    const offs = REFRESH_EVENTS.map((event) => subscribe(event, () => void load()));
    return () => {
      alive = false;
      for (const off of offs) off();
    };
  }, [sessionId]);

  const [first] = attachments;
  if (!first) return null;
  const label = attachments.map((a) => a.title).join(', ');
  return (
    <div className="bb-chat-tag" data-testid="blackboard-chat-tag" data-variant={first.workspace_id}>
      <button
        type="button"
        className="chat-mode-select__trigger"
        data-testid="blackboard-chat-tag-open-btn"
        aria-label={label}
        data-tooltip={label}
        {...handlers}
        onClick={() => {
          sharedController().openWorkspace(first.host, first.workspace_id);
          openBlackboard();
        }}
      >
        <span className="chat-mode-select__value">
          <span className="chat-mode-select__icon" aria-hidden="true">
            <BlackboardIcon width={14} height={14} />
          </span>
        </span>
      </button>
      {tooltip}
    </div>
  );
}
