// The author guard's ledger counts only the blocks an update touches; it must accept and refuse
// exactly what the whole-document check does, and stay in step with updates it does not check.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import * as Y from 'yjs'
import { CreditLedger, authorProblems } from '../src/hooks/authorGuard.ts'
import { addParagraph } from './helpers.ts'

const ALICE = { id: 'u_alice', kind: 'person' }
const BOB = { id: 'u_bob', kind: 'person' }

function setup() {
  const live = new Y.Doc()
  addParagraph(live, 'Alice wrote this.', ALICE)
  addParagraph(live, 'Bob wrote this.', BOB)
  addParagraph(live, 'Shared words.', ALICE)
  const ledger = new CreditLedger(live)
  // Alice's editor, in step with the document.
  const alice = new Y.Doc()
  Y.applyUpdate(alice, Y.encodeStateAsUpdate(live))
  return { live, ledger, alice }
}

// Alice changes her copy; the update is checked both ways and, when accepted, applied as the
// service would.
function send(env: ReturnType<typeof setup>, change: (fragment: Y.XmlFragment) => void): boolean {
  const before = Y.encodeStateVector(env.alice)
  env.alice.transact(() => change(env.alice.getXmlFragment('default')))
  const update = Y.encodeStateAsUpdate(env.alice, before)
  const reference = authorProblems(env.live, update, 'u_alice')
  const fast = env.ledger.check(update, 'u_alice')
  assert.equal(fast.length > 0, reference.length > 0, `ledger ${JSON.stringify(fast)}, reference ${JSON.stringify(reference)}`)
  if (fast.length === 0) Y.applyUpdate(env.live, update)
  else {
    // A refused update never reaches the document; Alice's editor starts again from it.
    env.alice = new Y.Doc()
    Y.applyUpdate(env.alice, Y.encodeStateAsUpdate(env.live))
  }
  return fast.length === 0
}

const textOf = (fragment: Y.XmlFragment, index: number) => (fragment.get(index) as Y.XmlElement).get(0) as Y.XmlText

test('the ledger agrees with the whole-document check', () => {
  const env = setup()
  assert.ok(send(env, (f) => textOf(f, 0).insert(5, ' really', { author: ALICE })), 'typing as herself')
  assert.ok(!send(env, (f) => textOf(f, 2).insert(0, 'Forged ', { author: BOB })), 'text credited to Bob')
  assert.ok(send(env, (f) => textOf(f, 2).insert(0, 'Now ', { author: ALICE })), 'fine again after a refusal')
  // Splitting Bob's paragraph moves his words into a new block, still credited to him.
  assert.ok(
    send(env, (f) => {
      textOf(f, 1).delete(4, 11)
      const paragraph = new Y.XmlElement('paragraph')
      const text = new Y.XmlText()
      text.insert(0, 'wrote this.', { author: BOB })
      paragraph.insert(0, [text])
      f.insert(2, [paragraph])
    }),
    'moving Bob text',
  )
  assert.ok(!send(env, (f) => textOf(f, 2).insert(0, 'More ', { author: BOB })), 'adding to Bob in the new block')
  assert.ok(send(env, (f) => f.delete(1, 1)), 'deleting a block')
  assert.ok(!send(env, (f) => (f.get(0) as Y.XmlElement).setAttribute('_mark_deletion', { author: BOB } as any)), 'a block mark for Bob')
  assert.ok(send(env, (f) => (f.get(0) as Y.XmlElement).setAttribute('_mark_deletion', { author: ALICE } as any)), 'a block mark for herself')
})

test('updates the ledger does not check keep it in step', () => {
  const env = setup()
  // Bob types in his own editor; the service applies his update without asking this ledger.
  const bob = new Y.Doc()
  Y.applyUpdate(bob, Y.encodeStateAsUpdate(env.live))
  const before = Y.encodeStateVector(bob)
  textOf(bob.getXmlFragment('default'), 1).insert(0, 'Truly, ', { author: BOB })
  Y.applyUpdate(env.live, Y.encodeStateAsUpdate(bob, before))
  Y.applyUpdate(env.alice, Y.encodeStateAsUpdate(env.live))
  // Alice deletes Bob's new words: credits drop, nothing is added to Bob.
  assert.ok(send(env, (f) => textOf(f, 1).delete(0, 7)))
  assert.ok(!send(env, (f) => textOf(f, 1).insert(0, 'x', { author: BOB })))
})
