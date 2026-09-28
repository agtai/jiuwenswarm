import assert from 'node:assert/strict'
import test from 'node:test'
import { TokenError, mintDocToken, verifyDocToken } from '../src/auth.ts'

// Minted by the host's Python code (common/tokens.py mint_doc_token) with secret 'python-secret'
// and a 100-year lifetime, so a change to either side's format shows up here.
const PYTHON_TOKEN =
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkJCRE9DIn0.eyJ1aWQiOiJ1X3B5Iiwid3MiOiJ3c19weSIsImRvYyI6ImRfcHkiLCJyb2xlIjoiY29tbWVudGVyIiwiZXhwIjo0OTQ0MTk5MTEwfQ.ud0YY_WaOagEWBMDzd5iEJFr-3X9AWGj36aC2xAPAWM'

const reason = (fn: () => unknown): string => {
  try {
    fn()
  } catch (error) {
    if (error instanceof TokenError) return error.reason
    throw error
  }
  return 'accepted'
}

test('a token minted by the Python host verifies here', () => {
  const claims = verifyDocToken(PYTHON_TOKEN, 'python-secret')
  assert.deepEqual({ uid: claims.uid, ws: claims.ws, doc: claims.doc, role: claims.role }, { uid: 'u_py', ws: 'ws_py', doc: 'd_py', role: 'commenter' })
  assert.equal(reason(() => verifyDocToken(PYTHON_TOKEN, 'another-secret')), 'token_bad_signature')
})

test('expired, tampered and malformed tokens are refused', () => {
  const good = mintDocToken({ uid: 'u', ws: 'w', doc: 'd', role: 'editor' }, 's')
  assert.equal(reason(() => verifyDocToken(good, 's')), 'accepted')
  assert.equal(reason(() => verifyDocToken(mintDocToken({ uid: 'u', ws: 'w', doc: 'd', role: 'editor' }, 's', -5), 's')), 'token_expired')
  const [header, , sig] = good.split('.')
  const forged = Buffer.from(JSON.stringify({ uid: 'u', ws: 'w', doc: 'd', role: 'owner', exp: 9999999999 })).toString('base64url')
  assert.equal(reason(() => verifyDocToken(`${header}.${forged}.${sig}`, 's')), 'token_bad_signature')
  for (const bad of ['', 'a.b', null, 'x.y.z']) assert.notEqual(reason(() => verifyDocToken(bad, 's')), 'accepted')
})
