import { useEffect, useSyncExternalStore } from 'react';

import { createConversationSession } from '../../../channels/web/frontend/src/multi-session/state/createConversationSession';
import { webClient, webRequest } from '../../../channels/web/frontend/src/services/webClient';
import { generateUuidV4 } from '../../../channels/web/frontend/src/utils/uuid';
import { BlackboardController, type BlackboardState, type SelectionMemory, type SessionPort } from './controller';
import type { Rpc, Subscribe } from './types';

const RPC_TIMEOUT_MS = 20_000;
const SELECTION_KEY = 'blackboard.selection';

export const rpc: Rpc = (method, params) => webRequest(method, params ?? {}, { timeoutMs: RPC_TIMEOUT_MS });
// webClient hands the whole event frame to its handlers; the controller wants the payload.
export const subscribe: Subscribe = (event, handler) =>
  webClient.on<Record<string, unknown>>(event, (frame) => handler(frame.payload ?? {}));

// Chat sessions, created and opened the way the app's own "new conversation" and sidebar do.
const sessionPort: SessionPort = {
  create: async (title) => {
    const created = await createConversationSession(webRequest, {
      create_token: generateUuidV4(),
      mode: 'agent',
      is_swarm: false,
      title: title.slice(0, 100),
      work_mode: 'work',
      persist_session: false,
    });
    return created.session_id;
  },
  open: (sessionId) => {
    window.dispatchEvent(new CustomEvent('jiuwen:open-session', { detail: { sessionId, mode: 'agent' } }));
  },
  recent: async () => {
    const result = await webRequest<{ sessions?: Array<{ session_id: string; title?: string }> }>('session.list', { limit: 50 });
    return (result.sessions ?? []).map((s) => ({ session_id: s.session_id, title: s.title || s.session_id }));
  },
};

// Per browser; storage may be unavailable (private windows, blocked site data).
const selectionMemory: SelectionMemory = {
  load: () => {
    try {
      const raw = window.localStorage.getItem(SELECTION_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  },
  save: (selection) => {
    try {
      window.localStorage.setItem(SELECTION_KEY, JSON.stringify(selection));
    } catch {
      // Nothing to remember then.
    }
  },
};

let shared: BlackboardController | null = null;

// One controller for the app's lifetime, so leaving the page and coming back keeps its place.
export function sharedController(): BlackboardController {
  shared ??= new BlackboardController(rpc, subscribe, sessionPort, selectionMemory);
  return shared;
}

export function openBlackboard(): void {
  window.dispatchEvent(new CustomEvent('jiuwen:nav', { detail: 'app:blackboard' }));
}

export function useController(): { controller: BlackboardController; state: BlackboardState } {
  const controller = sharedController();
  const state = useSyncExternalStore(controller.subscribe, controller.getState);
  useEffect(() => {
    void controller.start();
    return () => controller.stop();
  }, [controller]);
  return { controller, state };
}
