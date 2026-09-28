// Settings from the environment the host's manager sets (host/docservice_manager.py).
export interface Config {
  port: number
  bind: string
  apiPort: number
  dbPath: string
  docSecret: string
  apiSecret: string
  parentPid: number | null
  version: string
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
  }
}
