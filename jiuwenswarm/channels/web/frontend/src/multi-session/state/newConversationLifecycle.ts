import {
  ensureSessionRuntimes,
  useChatStore,
  useGoalStore,
  useHarnessStore,
  usePlanStore,
  useSessionStore,
  useTodoStore,
} from '../../stores';
import type { AgentMode, Session } from '../../types';
import { toDisplaySessionTitle } from '../../utils/documentMessage';

export const NEW_CONVERSATION_ID = 'new';

/** Copy product selections for a newly created text or voice conversation.
 * Callers retain ownership of draft text, goal activation and placeholder cleanup.
 */
export function copyNewConversationSelections(
  sessionId: string,
  pendingRuntime = useSessionStore.getState().getRuntime(NEW_CONVERSATION_ID),
): void {
  const sessions = useSessionStore.getState();
  for (const skill of pendingRuntime?.selectedSkills ?? []) sessions.addSelectedSkill(sessionId, skill);
  for (const plugin of pendingRuntime?.enabledPlugins ?? []) sessions.addEnabledPlugin(sessionId, plugin);
  for (const mcp of pendingRuntime?.enabledMcps ?? []) sessions.addEnabledMcp(sessionId, mcp);
  if (pendingRuntime?.metadata) sessions.setSessionMetadata(sessionId, pendingRuntime.metadata);
  sessions.setAgentSelectionIntent(sessionId, pendingRuntime?.agentSelectionIntent ?? { kind: 'keep' });
  if (pendingRuntime?.enableSwarmflow) {
    sessions.setSwarmflowActive(sessionId, true, pendingRuntime.swarmflowBudget);
  }
  const plan = usePlanStore.getState();
  if (plan.isActive(NEW_CONVERSATION_ID)) {
    plan.setActive(sessionId, true, {
      explicitEntry: plan.hasPendingExplicitEntry(NEW_CONVERSATION_ID),
      entrySource: plan.getPendingEntrySource(NEW_CONVERSATION_ID) ?? undefined,
    });
  }
}

interface ConversationRuntimeSettings {
  mode: AgentMode;
  selectedModelName: string | null;
  projectDir?: string | null;
  persistSession?: boolean;
}

export type NewConversationEntrySettings = Pick<ConversationRuntimeSettings, 'mode' | 'selectedModelName'>;

export function resolveNewConversationEntrySettings(
  targetMode: AgentMode,
  defaultModelName: string | null,
  currentModelName: string | null,
  pendingSettings?: NewConversationEntrySettings | null,
): NewConversationEntrySettings {
  if (pendingSettings) return pendingSettings;
  return {
    mode: targetMode,
    selectedModelName: defaultModelName ?? currentModelName ?? null,
  };
}

const locallyCreatedConversations = new Map<string, Session>();

export function createConversationTitle(content: string): string {
  return toDisplaySessionTitle(content.replace(/\{\{skill:[^}]+\}\}/g, ''));
}

function applyRuntimeSettings(
  sessionId: string,
  { mode, selectedModelName, projectDir, persistSession = false }: ConversationRuntimeSettings,
): void {
  ensureSessionRuntimes(sessionId);
  useSessionStore.getState().setMode(sessionId, mode);
  if (selectedModelName) {
    useSessionStore.getState().setSelectedModelName(sessionId, selectedModelName);
  }
  if (projectDir) {
    useSessionStore.getState().setProjectDirectory(sessionId, projectDir);
  }
  useSessionStore.getState().setPersistSession(sessionId, persistSession);
}

export function resetNewConversationRuntime(settings: ConversationRuntimeSettings): void {
  const preservedDraft = useChatStore.getState().getRuntime(NEW_CONVERSATION_ID)?.inputValue ?? '';
  useChatStore.getState().removeRuntime(NEW_CONVERSATION_ID);
  useSessionStore.getState().removeRuntime(NEW_CONVERSATION_ID);
  useTodoStore.getState().removeRuntime(NEW_CONVERSATION_ID);
  useHarnessStore.getState().removeRuntime(NEW_CONVERSATION_ID);
  useGoalStore.getState().removeRuntime(NEW_CONVERSATION_ID);
  usePlanStore.getState().removeRuntime(NEW_CONVERSATION_ID);
  applyRuntimeSettings(NEW_CONVERSATION_ID, settings);
  if (preservedDraft) {
    useChatStore.getState().setInputValue(NEW_CONVERSATION_ID, preservedDraft);
  }
  useChatStore.getState().setActiveSessionId(NEW_CONVERSATION_ID);
}

export function registerCreatedConversation(
  sessionId: string,
  settings: ConversationRuntimeSettings,
  createdAt = Date.now(),
  initialContent = '',
  workContext: Partial<Pick<Session, 'project_id' | 'project_dir' | 'work_mode' | 'persist_session'>> = {},
  processing = true,
): Session {
  applyRuntimeSettings(sessionId, settings);
  useChatStore.getState().setProcessing(sessionId, processing);

  const timestamp = new Date(createdAt).toISOString();
  const session: Session = {
    session_id: sessionId,
    title: createConversationTitle(initialContent),
    project_id: workContext.project_id || '',
    project_dir: workContext.project_dir || settings.projectDir || '',
    persist_session: workContext.persist_session === true,
    work_mode: workContext.work_mode,
    mode: settings.mode,
    status: 'active',
    message_count: 0,
    created_at: timestamp,
    updated_at: timestamp,
    last_message_at: createdAt,
    last_user_message_at: createdAt,
    is_processing: processing,
  };
  locallyCreatedConversations.set(sessionId, session);
  useSessionStore.getState().addSession(session);
  return session;
}

export function forgetCreatedConversation(sessionId: string): void {
  locallyCreatedConversations.delete(sessionId);
}

export function isConversationMissing(
  sessionId: string,
  initialDataLoaded: boolean,
  sessions: Session[],
): boolean {
  return initialDataLoaded
    && !locallyCreatedConversations.has(sessionId)
    && !sessions.some((session) => session.session_id === sessionId);
}
