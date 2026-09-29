import type { ReactNode } from 'react';
import type { FileDownloadItem, ToolCall, ToolResult } from '../types';

export type ApplicationPluginNavKey = `app:${string}`;

export interface ApplicationPluginContribution {
  plugin_id: string;
  plugin_version: string;
  description?: string;
  permissions?: string[];
  enabled?: boolean;
  id: string;
  nav_key: string;
  title: string;
  title_i18n_key?: string;
  render_mode: 'bundled' | 'iframe' | 'none';
  component?: string;
  entry_url?: string;
  position: number;
  // Built-in navigation item this page follows, for example 'chat'.
  nav_after?: string;
}

export interface ApplicationPluginManifest {
  api_version: number;
  plugins: ApplicationPluginContribution[];
}

export interface ApplicationPluginSettingsProps {
  contribution: ApplicationPluginContribution;
  onManifestChanged: () => void;
}

export interface ApplicationPluginTaskInputActionProps {
  fallback: ReactNode;
  eligible: boolean;
  sessionId: string | null;
  ensureSession: (initialTitle?: string) => Promise<string | null>;
  labels: {
    start: string;
    starting: string;
    stop: string;
  };
}

// An item a plugin adds to the chat input's + menu. It may open its own panel next to the menu;
// the menu shows one such panel at a time. sessionId is null until the conversation has a session;
// ensureSession creates it.
export interface ApplicationPluginTaskMenuItemProps {
  sessionId: string | null;
  ensureSession: (initialTitle?: string) => Promise<string | null>;
  direction: 'up' | 'down';
  teamMode: boolean;
  panelOpen: boolean;
  onPanelOpenChange: (open: boolean) => void;
  closeMenu: () => void;
}

// A tag a plugin shows in the chat input's toolbar for the current session.
export interface ApplicationPluginTaskInputTagProps {
  sessionId: string | null;
}

export interface ApplicationPluginTaskRuntimeProps {
  sessionId: string | null;
  onConversationItem: (
    sessionId: string,
    role: 'user' | 'assistant',
    text: string,
    presentation?: 'tool_result',
  ) => void;
  onAssistantStream: (sessionId: string, update: { streamId: string; content: string; final: boolean }) => void;
  onReasoning: (sessionId: string, content: string, atMs?: number) => void;
  onReasoningClose: (sessionId: string, atMs?: number) => void;
  onToolCall: (sessionId: string, toolCall: ToolCall, startedAt?: string) => void;
  onToolResult: (sessionId: string, toolResult: ToolResult, updatedAt?: string) => void;
  onFileItems: (sessionId: string, files: FileDownloadItem[], timestampIso?: string) => void;
}
