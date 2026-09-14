import { type ComponentProps } from 'react';
import { LiveVoiceIntegratedRoutePanel as VoicePanel } from '../../src/components/ChatPanel/LiveVoiceIntegratedRoutePanel';
import { FormalTaskSessionProvider } from '../../src/features/tasks/FormalTaskSessionProvider';
import { FEATURE_LIVE_VOICE_PRODUCT_P3_MUTATION } from '../../src/featureFlags';

export * from '../../src/components/ChatPanel/LiveVoiceIntegratedRoutePanel';

// Mounted Voice tests explicitly supply the same Host task lifecycle as ChatPanel.
export function LiveVoiceIntegratedRoutePanel(props: ComponentProps<typeof VoicePanel>) {
  return (
    <FormalTaskSessionProvider
      sessionId={props.activeSessionId}
      connected={props.isConnected}
      enabled={FEATURE_LIVE_VOICE_PRODUCT_P3_MUTATION}
      request={props.request}
    >
      <VoicePanel {...props} />
    </FormalTaskSessionProvider>
  );
}
