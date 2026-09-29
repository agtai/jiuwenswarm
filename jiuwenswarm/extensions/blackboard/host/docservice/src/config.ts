// Settings from the environment the host's manager sets (host/docservice_manager.py).
import { normalizeOrigin } from './origins.ts'

export interface Config {
  port: number
  bind: string
  apiPort: number
  dbPath: string
  docSecret: string
  apiSecret: string
  parentPid: number | null
  version: string
  // Where new versions are announced (the host's API), or null to announce nothing.
  hostUrl: string | null
  // How long a document stays quiet after people's edits before they become a version.
  idleMs: number
  // A Chrome, Edge or Chromium binary for PDF export, when not found in the usual places.
  chromium: string | null
  // Web pages besides loopback ones that may open live documents (see origins.ts).
  allowedOrigins: string[]
  allowAnyOrigin: boolean
  // Versions older than this many days are removed, except named ones and each document's
  // latest; 0 keeps every version.
  versionRetentionDays: number
}

function required(env: NodeJS.ProcessEnv, name: string): string {
  const value = env[name]
  if (!value) throw new Error(`${name} is not set`)
  return value
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): Config {
  return {
    port: Number(env.BB_DOC_PORT || 19010),
    bind: env.BB_DOC_BIND || '127.0.0.1',
    apiPort: Number(env.BB_DOC_API_PORT || 19012),
    dbPath: required(env, 'BB_DOC_DB'),
    docSecret: required(env, 'BB_DOC_SECRET'),
    apiSecret: required(env, 'BB_API_SECRET'),
    parentPid: env.BB_PARENT_PID ? Number(env.BB_PARENT_PID) : null,
    version: env.BB_VERSION || '0.1.0',
    hostUrl: env.BB_HOST_URL || null,
    idleMs: Number(env.BB_VERSION_IDLE_MS || 30000),
    chromium: env.BB_CHROMIUM_PATH || null,
    allowedOrigins: (env.BB_ALLOWED_ORIGINS || '')
      .split(',')
      .map((o) => normalizeOrigin(o))
      .filter(Boolean),
    allowAnyOrigin: env.BB_ALLOW_ANY_ORIGIN === '1',
    versionRetentionDays: Math.max(0, Number(env.BB_VERSION_RETENTION_DAYS || 0) || 0),
  }
}
