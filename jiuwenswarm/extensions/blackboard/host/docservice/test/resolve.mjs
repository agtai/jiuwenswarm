// Resolve hook (see register.mjs): bare package names resolve as if imported from the web app.
import { isBuiltin } from 'node:module'

const WEB_APP = new URL('../../../../../channels/web/frontend/package.json', import.meta.url).href

export async function resolve(specifier, context, next) {
  if (/^[./]|^[a-z]+:/i.test(specifier) || isBuiltin(specifier)) return next(specifier, context)
  return next(specifier, { ...context, parentURL: WEB_APP })
}
