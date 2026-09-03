import { useChatStore, useGoalStore, usePlanStore, useSessionStore } from '../../stores';
import { createConversationSession, type SessionCreateRequestFn } from './createConversationSession';
import { NEW_CONVERSATION_ID, registerCreatedConversation } from './newConversationLifecycle';

export class LiveVoiceProjectRequiredError extends Error {}

/** Allocate an empty conversation; this entry never sends a user/Agent message. */
export async function createLiveVoiceConversation(input: {
  request: SessionCreateRequestFn;
  params: Record<string, unknown>;
  settings: Parameters<typeof registerCreatedConversation>[1];
  accept: (sessionId: string) => boolean;
}) {
  // The existing formal authority requires a registered Code project. This is
  // early UX feedback only; the server still decides project authorization.
  if (input.params.work_mode !== 'code' || !input.params.project_id || !input.params.project_dir) {
    throw new LiveVoiceProjectRequiredError('Select a Code project before starting Live Voice');
  }
  const created = await createConversationSession(input.request, input.params);
  if (created.session_id === NEW_CONVERSATION_ID) throw new Error('session.create returned a placeholder');
  if (!input.accept(created.session_id)) return null;
  const session = registerCreatedConversation(
    created.session_id,
    {
      ...input.settings,
      projectDir: created.project_dir ?? input.settings.projectDir,
    },
    Date.now(),
    String(input.params.title || ''),
    {
      project_id: created.project_id || String(input.params.project_id || ''),
      project_dir: created.project_dir || String(input.params.project_dir || ''),
      work_mode: created.work_mode ?? input.params.work_mode,
    },
    false,
  );
  const chat = useChatStore.getState();
  const sessions = useSessionStore.getState();
  const draft = chat.getRuntime(NEW_CONVERSATION_ID)?.inputValue ?? '';
  chat.setInputValue(session.session_id, draft);
  chat.setInputValue(NEW_CONVERSATION_ID, '');
  for (const skill of sessions.getRuntime(NEW_CONVERSATION_ID)?.selectedSkills ?? []) {
    sessions.addSelectedSkill(session.session_id, skill);
  }
  sessions.clearSelectedSkills(NEW_CONVERSATION_ID);
  const plan = usePlanStore.getState();
  if (plan.isActive(NEW_CONVERSATION_ID)) {
    plan.setActive(session.session_id, true, { explicitEntry: plan.hasPendingExplicitEntry(NEW_CONVERSATION_ID) });
  }
  plan.removeRuntime(NEW_CONVERSATION_ID);
  const goal = useGoalStore.getState();
  goal.setArmed(session.session_id, goal.runtimes[NEW_CONVERSATION_ID]?.armed ?? false);
  goal.setArmed(NEW_CONVERSATION_ID, false);
  return session;
}
