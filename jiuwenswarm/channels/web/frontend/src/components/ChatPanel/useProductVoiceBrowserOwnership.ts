import { useCallback, useEffect, useMemo, useRef, useState, type MutableRefObject } from 'react';

import {
  createBrowserLiveVoiceOwnership,
  createBrowserLiveVoiceOwnershipBarrier,
  type BrowserLiveVoiceOwnership,
  type BrowserLiveVoiceOwnershipBarrier,
} from '../../features/live-voice/formal/browserLiveVoiceOwnership';
import type { ProductLiveVoiceSurfaceControl } from './LiveVoiceIntegratedRoutePanel';

export type ProductVoiceBrowserOwnershipOptions = Readonly<{
  activeSessionId: string | null;
  controlRef: MutableRefObject<ProductLiveVoiceSurfaceControl | null>;
  getActiveSessionId: () => string | null;
  createOwnership?: () => BrowserLiveVoiceOwnership;
}>;

export type ProductVoiceBrowserOwnershipLifecycle = Readonly<{
  active: boolean;
  start(): Promise<void>;
  stop(): Promise<void>;
}>;

export function useProductVoiceBrowserOwnership(
  options: ProductVoiceBrowserOwnershipOptions,
): ProductVoiceBrowserOwnershipLifecycle {
  const ownershipFactoryRef = useRef(options.createOwnership ?? createBrowserLiveVoiceOwnership);
  const browserOwnershipRef = useRef<BrowserLiveVoiceOwnership | null>(null);
  if (browserOwnershipRef.current === null) {
    browserOwnershipRef.current = ownershipFactoryRef.current();
  }
  const ownershipBarrierRef = useRef<BrowserLiveVoiceOwnershipBarrier | null>(null);
  if (ownershipBarrierRef.current === null) {
    ownershipBarrierRef.current = createBrowserLiveVoiceOwnershipBarrier();
  }
  const intentRef = useRef(0);
  const cleanupRef = useRef<Promise<void>>(Promise.resolve());
  const cleanupSessionRef = useRef<string | null>(null);
  const cleanupControlRef = useRef<ProductLiveVoiceSurfaceControl | null>(null);
  const unmountedRef = useRef(false);
  const sessionRef = useRef(options.activeSessionId);
  const getActiveSessionIdRef = useRef(options.getActiveSessionId);
  getActiveSessionIdRef.current = options.getActiveSessionId;
  const [active, setActive] = useState(false);

  const closeSessionForBrowserOwnership = useCallback(async (sessionId: string) => {
    const cleanupSessionId = cleanupSessionRef.current ?? sessionId;
    cleanupSessionRef.current = cleanupSessionId;
    const priorCleanup = cleanupRef.current;
    const control = cleanupControlRef.current;
    if (control === null) {
      try {
        await priorCleanup;
      } catch {
        throw new Error('FORMAL_P1_CLEANUP_PENDING');
      }
      if (cleanupSessionRef.current === cleanupSessionId) {
        cleanupSessionRef.current = null;
      }
      return null;
    }
    const cleanup = (async () => {
      try {
        await priorCleanup;
      } catch {
        // A later explicit ownership operation retries the exact retained owner.
      }
      await control.closeSession(cleanupSessionId);
    })();
    cleanupRef.current = cleanup;
    try {
      await cleanup;
      if (cleanupSessionRef.current === cleanupSessionId) {
        cleanupSessionRef.current = null;
      }
      return control;
    } catch {
      throw new Error('FORMAL_P1_CLEANUP_PENDING');
    }
  }, []);

  const closeForBrowserOwnership = useCallback(async () => {
    const priorCleanup = cleanupRef.current;
    const control = cleanupControlRef.current;
    if (control === null) {
      try {
        await priorCleanup;
      } catch {
        throw new Error('FORMAL_P1_CLEANUP_PENDING');
      }
      return;
    }
    const cleanup = (async () => {
      try {
        await priorCleanup;
      } catch {
        // Full Exit/takeover still retries any retained old-Session capture
        // before closing the current surface and releasing browser ownership.
      }
      const cleanupSessionId = cleanupSessionRef.current;
      if (cleanupSessionId !== null) {
        await control.closeSession(cleanupSessionId);
        if (cleanupSessionRef.current === cleanupSessionId) {
          cleanupSessionRef.current = null;
        }
      }
      await control.close();
    })();
    cleanupRef.current = cleanup;
    await cleanup;
    if (cleanupControlRef.current === control) {
      cleanupControlRef.current = null;
    }
  }, []);

  const start = useCallback(async () => {
    const browserOwnership = browserOwnershipRef.current;
    const ownershipBarrier = ownershipBarrierRef.current;
    if (browserOwnership === null || ownershipBarrier === null) return;
    const intent = intentRef.current + 1;
    intentRef.current = intent;
    const requestedSessionId = options.activeSessionId;
    try {
      await ownershipBarrier.wait();
      await cleanupRef.current;
    } catch {
      try {
        await ownershipBarrier.run(async () => {
          const cleanupSessionId = cleanupSessionRef.current;
          let cleanedControl: ProductLiveVoiceSurfaceControl | null = null;
          if (cleanupSessionId === null) {
            await closeForBrowserOwnership();
          } else {
            cleanedControl = await closeSessionForBrowserOwnership(cleanupSessionId);
          }
          await browserOwnership.release();
          if (cleanedControl !== null && cleanupControlRef.current === cleanedControl) {
            cleanupControlRef.current = null;
          }
        });
      } catch {
        return;
      }
    }
    if (intentRef.current !== intent) return;
    const cleanupControl = options.controlRef.current;
    if (cleanupControl === null) return;
    if (cleanupControlRef.current === null) {
      cleanupControlRef.current = cleanupControl;
    }
    try {
      await browserOwnership.acquire(async () => {
        intentRef.current += 1;
        setActive(false);
        await closeForBrowserOwnership();
        if (unmountedRef.current) browserOwnership.disposeAfterRelease();
      });
    } catch {
      if (intentRef.current === intent) setActive(false);
      return;
    }
    if (
      intentRef.current !== intent ||
      getActiveSessionIdRef.current() !== requestedSessionId
    ) {
      return;
    }
    const control = options.controlRef.current;
    if (control === null) {
      setActive(false);
      try {
        await ownershipBarrier.run(async () => {
          await closeForBrowserOwnership();
          await browserOwnership.release();
        });
      } catch {
        return;
      }
      return;
    }
    if (cleanupControlRef.current === null) {
      cleanupControlRef.current = control;
    }
    setActive(true);
    try {
      await control.start();
    } catch {
      // The formal route publishes the exact retryable/terminal failure state.
      // Retain browser ownership until Exit or takeover so another tab cannot
      // race a still-cleaning local capture.
    }
  }, [closeForBrowserOwnership, closeSessionForBrowserOwnership, options.activeSessionId, options.controlRef]);

  const stop = useCallback(async () => {
    intentRef.current += 1;
    setActive(false);
    const browserOwnership = browserOwnershipRef.current;
    const ownershipBarrier = ownershipBarrierRef.current;
    if (ownershipBarrier === null) return;
    try {
      await ownershipBarrier.run(async () => {
        await closeForBrowserOwnership();
        await browserOwnership?.release();
      });
    } catch {
      return;
    }
  }, [closeForBrowserOwnership]);

  const stopSessionAndReleaseBrowserOwnership = useCallback(async (sessionId: string | null) => {
    intentRef.current += 1;
    setActive(false);
    const browserOwnership = browserOwnershipRef.current;
    const ownershipBarrier = ownershipBarrierRef.current;
    if (ownershipBarrier === null) return;
    try {
      await ownershipBarrier.run(async () => {
        const cleanedControl = sessionId === null
          ? null
          : await closeSessionForBrowserOwnership(sessionId);
        await browserOwnership?.release();
        if (cleanedControl !== null && cleanupControlRef.current === cleanedControl) {
          cleanupControlRef.current = null;
        }
      });
    } catch {
      return;
    }
  }, [closeSessionForBrowserOwnership]);

  useEffect(() => {
    setActive(false);
    if (sessionRef.current === options.activeSessionId) return;
    const previousSessionId = sessionRef.current;
    sessionRef.current = options.activeSessionId;
    void stopSessionAndReleaseBrowserOwnership(previousSessionId);
  }, [options.activeSessionId, stopSessionAndReleaseBrowserOwnership]);

  useEffect(() => {
    unmountedRef.current = false;
    return () => {
      unmountedRef.current = true;
      intentRef.current += 1;
      const browserOwnership = browserOwnershipRef.current;
      const cleanupControl = cleanupControlRef.current ?? options.controlRef.current;
      if (cleanupControl !== null && cleanupControlRef.current === null) {
        cleanupControlRef.current = cleanupControl;
      }
      void closeForBrowserOwnership().then(
        () => browserOwnership?.disposeAfterRelease(),
        () => {
          // Keep the exact control, coordinator, Web Lock and takeover callback
          // alive. A later takeover retries this same cleanup owner and only a
          // proven success may release and dispose the browser-wide authority.
        },
      );
    };
  }, [closeForBrowserOwnership, options.controlRef]);

  return useMemo(() => Object.freeze({ active, start, stop }), [active, start, stop]);
}
