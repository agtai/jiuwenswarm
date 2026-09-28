import { useEffect, useMemo, useSyncExternalStore } from 'react';

import { webClient, webRequest } from '../../../channels/web/frontend/src/services/webClient';
import { BlackboardController, type BlackboardState } from './controller';
import type { Rpc, Subscribe } from './types';

const RPC_TIMEOUT_MS = 20_000;

const rpc: Rpc = (method, params) => webRequest(method, params ?? {}, { timeoutMs: RPC_TIMEOUT_MS });
// webClient hands the whole event frame to its handlers; the controller wants the payload.
const subscribe: Subscribe = (event, handler) =>
  webClient.on<Record<string, unknown>>(event, (frame) => handler(frame.payload ?? {}));

export function useController(): { controller: BlackboardController; state: BlackboardState } {
  const controller = useMemo(() => new BlackboardController(rpc, subscribe), []);
  const state = useSyncExternalStore(controller.subscribe, controller.getState);
  useEffect(() => {
    void controller.start();
    return () => controller.stop();
  }, [controller]);
  return { controller, state };
}
