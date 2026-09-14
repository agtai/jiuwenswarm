import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { webClient } from '../../services/webClient';
import type { WebRequestOptions } from '../../types';
import { useFormalTaskStore } from '../../stores/formalTaskStore';
import { inspectProductP3TaskTarget } from '../live-voice/formal/productP3TaskTargetJournal';
import { FormalP3TaskExperienceOwner, type FormalP3TaskExperienceSnapshot } from './formalP3TaskExperience';

type Request = (method: string, params?: Record<string, unknown>, options?: WebRequestOptions) => Promise<unknown>;
const requestHost: Request = (method, params, options) => webClient.request(method, params, options);
const idle: FormalP3TaskExperienceSnapshot = Object.freeze({
  status: 'idle',
  session_id: null,
  tasks: Object.freeze([]),
  selected_task_id: null,
  collection_operations: Object.freeze([]),
  command: null,
  reason: null,
});
const disabled: FormalP3TaskExperienceSnapshot = Object.freeze({
  ...idle,
  status: 'disabled',
  reason: 'FORMAL_P3_TASK_EXPERIENCE_DISABLED',
});
const TaskSessionContext = createContext<
  Readonly<{
    owner: FormalP3TaskExperienceOwner | null;
    snapshot: FormalP3TaskExperienceSnapshot;
  }>
>({ owner: null, snapshot: disabled });

export const useFormalTaskSession = () => useContext(TaskSessionContext);

// ChatPanel owns this reader. Voice and the Task panel only consume its state;
// removing a speech consumer does not retire the session's retained RPC.
export function FormalTaskSessionProvider({
  sessionId,
  connected,
  enabled,
  request = requestHost,
  children,
}: {
  sessionId: string | null;
  connected: boolean;
  enabled: boolean;
  request?: Request;
  children?: ReactNode;
}) {
  const ownerRef = useRef<FormalP3TaskExperienceOwner | null>(null);
  const current = useRef({ sessionId, connected, request });
  current.current = { sessionId, connected, request };
  const [fallback, setFallback] = useState(enabled ? idle : disabled);
  const entry = useFormalTaskStore((state) => state.entries[sessionId ?? '']);

  useEffect(() => {
    if (!enabled || sessionId === null || !sessionId.trim() || sessionId === 'new') {
      setFallback(enabled ? idle : disabled);
      return;
    }
    // Compatibility barrier: unreadable old target metadata must not silently
    // become a fresh task selection or gain list/mutation authority.
    if (inspectProductP3TaskTarget({ session_id: sessionId }).status === 'invalid') {
      setFallback({
        ...idle,
        status: 'failed',
        session_id: sessionId,
        reason: 'PRODUCT_P3_TASK_TARGET_RECOVERY_REQUIRED',
      });
      return;
    }
    const owner = new FormalP3TaskExperienceOwner({
      enabled: true,
      request: (method, params, requestId) => request(method, params, { requestId }),
      on_snapshot: (snapshot) => {
        if (
          ownerRef.current !== owner ||
          current.current.sessionId !== sessionId ||
          current.current.request !== request
        )
          return;
        useFormalTaskStore.getState().publish(sessionId, owner, snapshot);
      },
    });
    ownerRef.current = owner;
    useFormalTaskStore.getState().bind(sessionId, owner);
    return () => {
      ownerRef.current = null;
      useFormalTaskStore.getState().release(sessionId, owner);
      owner.close();
    };
  }, [enabled, sessionId, request]);

  useEffect(() => {
    const owner = ownerRef.current;
    if (owner === null || sessionId === null) return;
    if (!connected) {
      owner.disconnect();
      return;
    }
    let closed = false;
    let timer: ReturnType<typeof setTimeout>;
    const isCurrent = () =>
      !closed &&
      current.current.connected &&
      current.current.sessionId === sessionId &&
      current.current.request === request &&
      ownerRef.current === owner;
    // Read revalidation never replays a retained mutation automatically.
    void owner.refresh(sessionId, isCurrent).catch(() => {});
    const refresh = async () => {
      if (!isCurrent()) return;
      try {
        await owner.refreshLiveTasks(sessionId, isCurrent);
      } catch {
        /* Reader owns failure state. */
      }
      if (isCurrent())
        timer = setTimeout(
          () => {
            void refresh();
          },
          owner.snapshot().status === 'failed' ? 15_000 : 5_000,
        );
    };
    timer = setTimeout(() => {
      void refresh();
    }, 5_000);
    return () => {
      closed = true;
      clearTimeout(timer);
    };
  }, [enabled, sessionId, request, connected]);

  const ownedEntry = entry?.owner === ownerRef.current ? entry : undefined;
  return (
    <TaskSessionContext.Provider
      value={{ owner: ownedEntry?.owner ?? null, snapshot: ownedEntry?.snapshot ?? fallback }}
    >
      {children}
    </TaskSessionContext.Provider>
  );
}
