// `node --import <this file> --test ...`: the tests run the TypeScript sources directly, and their
// package imports resolve from the web app, which holds the service's dependencies.
import { register } from 'node:module'

register('./resolve.mjs', import.meta.url)
