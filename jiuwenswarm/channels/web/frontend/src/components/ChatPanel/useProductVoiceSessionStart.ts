import { useCallback, useEffect, useRef, useState } from 'react';
import { LiveVoiceProjectRequiredError } from '../../multi-session/state/createLiveVoiceConversation';

export type PrepareProductVoiceSession = (accept: (sessionId: string) => boolean) => Promise<string | null>;

/** Keep the click intent through Session allocation and formal route activation. */
export function useProductVoiceSessionStart(options: {
  sessionId: string | null;
  available: boolean;
  canPrepare: boolean;
  prepare?: PrepareProductVoiceSession;
  start: () => Promise<void>;
  activationTimeoutMs?: number;
}) {
  const latest = useRef(options);
  latest.current = options;
  const attempt = useRef<{ target: string | null } | null>(null);
  const [pending, setPending] = useState(false);
  const [failed, setFailed] = useState(false);
  const [projectRequired, setProjectRequired] = useState(false);
  const [target, setTarget] = useState<string | null>(null);
  const cancel = useCallback(() => {
    attempt.current = null;
    setPending(false);
    setTarget(null);
  }, []);

  useEffect(() => {
    setFailed(false);
    setProjectRequired(false);
  }, [options.sessionId]);

  useEffect(
    () => () => {
      attempt.current = null;
    },
    [],
  );
  useEffect(() => {
    const current = attempt.current;
    if (!current) return;
    if (options.sessionId !== 'new' && options.sessionId !== current.target) {
      cancel();
      return;
    }
    if (!options.canPrepare) {
      cancel();
      return;
    }
    if (current.target !== null && current.target === options.sessionId && options.available) {
      attempt.current = null;
      setPending(false);
      setTarget(null);
      void options.start();
    }
  }, [options.sessionId, options.available, options.canPrepare, options.start, pending, cancel]);
  useEffect(() => {
    if (target === null) return;
    const timer = setTimeout(() => {
      if (attempt.current?.target !== target) return;
      cancel();
      setFailed(true);
    }, options.activationTimeoutMs ?? 30_000);
    return () => clearTimeout(timer);
  }, [target, options.activationTimeoutMs, cancel]);

  const start = useCallback(async () => {
    if (attempt.current !== null) return;
    const input = latest.current;
    setFailed(false);
    setProjectRequired(false);
    if (input.sessionId !== 'new') {
      if (input.available) await input.start();
      return;
    }
    if (!input.canPrepare || !input.prepare) return;
    const current = { target: null as string | null };
    attempt.current = current;
    setPending(true);
    try {
      const sessionId = await input.prepare(id => {
        if (attempt.current !== current || latest.current.sessionId !== 'new' || !latest.current.canPrepare || !id.trim() || id === 'new') return false;
        // Install the exact destination before App changes its active Session.
        current.target = id;
        setTarget(id);
        return true;
      });
      if (attempt.current !== current) return;
      if (sessionId === null || sessionId !== current.target) cancel();
    } catch (error) {
      if (attempt.current !== current) return;
      cancel();
      setFailed(true);
      setProjectRequired(error instanceof LiveVoiceProjectRequiredError);
    }
  }, [cancel]);

  return { pending, failed, projectRequired, start, cancel };
}
