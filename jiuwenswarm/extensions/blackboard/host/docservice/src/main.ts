// Process entry: start the service, report readiness on stdout, and exit when the host that
// started it is gone (on Windows the host cannot always stop it before it dies).
import { loadConfig } from './config.ts'
import { startService } from './service.ts'

const PARENT_CHECK_MS = 5000

function alive(pid: number): boolean {
  try {
    process.kill(pid, 0)
    return true
  } catch (error: any) {
    return error?.code === 'EPERM'
  }
}

async function main(): Promise<void> {
  const config = loadConfig()
  const service = await startService(config, { onShutdown: () => process.exit(0) })
  const exit = async (code: number) => {
    await service.stop().catch((error) => console.error('docservice: stop failed', error))
    process.exit(code)
  }

  process.on('SIGINT', () => void exit(0))
  process.on('SIGTERM', () => void exit(0))
  if (config.parentPid) {
    const parent = config.parentPid
    setInterval(() => {
      if (!alive(parent)) void exit(0)
    }, PARENT_CHECK_MS).unref()
  }
  console.log(JSON.stringify({ event: 'ready', port: config.port, apiPort: config.apiPort, version: config.version }))
}

main().catch((error) => {
  console.error('docservice: failed to start', error)
  process.exit(1)
})
