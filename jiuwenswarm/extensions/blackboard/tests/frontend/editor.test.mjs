// The author stamp and the authors legend, on the shared document schema.
import assert from 'node:assert/strict';
import test from 'node:test';
import {
  EditorState,
  authorsOf,
  blackboardSchema,
  insertedRanges,
  stampAuthor,
} from '../../../../channels/web/frontend/node_modules/.cache/blackboard/editorKit.js';

const ME = { id: 'u_me', kind: 'person' };

function run(state, tr) {
  const next = state.apply(tr);
  const extra = stampAuthor(next, insertedRanges([tr]), ME);
  return extra ? next.apply(extra) : next;
}

function marksAt(state, text) {
  let found = null;
  state.doc.descendants((node) => {
    if (node.isText && node.text.includes(text)) found = node.marks.map((m) => [m.type.name, m.attrs.id]);
  });
  return found;
}

test('typed and pasted text carries my author mark; other authors and their suggestions are dropped', () => {
  const schema = blackboardSchema();
  const bob = schema.marks.author.create({ id: 'u_bob', kind: 'person' });
  const agentInsert = schema.marks.insertion.create({ id: 's1', author: { id: 'a_bot', kind: 'agent' } });
  const doc = schema.node('doc', null, [schema.node('paragraph', { id: 'b1' }, [schema.text('Hello', [bob])])]);
  let state = EditorState.create({ schema, doc });

  state = run(state, state.tr.insertText(' world', 6));
  assert.deepEqual(marksAt(state, ' world'), [['author', 'u_me']]);
  assert.deepEqual(marksAt(state, 'Hello'), [['author', 'u_bob']]);

  state = run(state, state.tr.insert(1, schema.text('pasted', [bob, agentInsert])));
  assert.deepEqual(marksAt(state, 'pasted'), [['author', 'u_me']]);
});

test('changes from other people are left alone', () => {
  const schema = blackboardSchema();
  const doc = schema.node('doc', null, [schema.node('paragraph', { id: 'b1' }, [schema.text('Hi')])]);
  const state = EditorState.create({ schema, doc });
  const remote = state.tr.insertText(' there', 3).setMeta('y-sync$', { isChangeOrigin: true });
  assert.deepEqual(insertedRanges([remote]), []);
});

test('the legend lists authors by how much they wrote, with member names', () => {
  const doc = {
    type: 'doc',
    content: [
      {
        type: 'paragraph',
        content: [
          { type: 'text', text: 'ab', marks: [{ type: 'author', attrs: { id: 'u1', kind: 'person' } }] },
          { type: 'text', text: 'cdefg', marks: [{ type: 'author', attrs: { id: 'a1', kind: 'agent' } }] },
          { type: 'text', text: 'h', marks: [{ type: 'bold' }] },
        ],
      },
    ],
  };
  const legend = authorsOf(doc, new Map([['u1', 'Ann']]));
  assert.deepEqual(
    legend.map((a) => [a.id, a.name, a.kind, a.chars]),
    [
      ['a1', 'a1', 'agent', 5],
      ['u1', 'Ann', 'person', 2],
    ],
  );
  assert.ok(legend.every((a) => a.color >= 1 && a.color <= 6));
});

test("a person and their agent are two authors with two colors", () => {
  const doc = {
    type: 'doc',
    content: [
      {
        type: 'paragraph',
        content: [
          { type: 'text', text: 'mine', marks: [{ type: 'author', attrs: { id: 'u1', kind: 'agent' } }] },
          { type: 'text', text: 'me', marks: [{ type: 'author', attrs: { id: 'u1', kind: 'person' } }] },
        ],
      },
    ],
  };
  const legend = authorsOf(doc, new Map([['u1', 'Ann']]));
  assert.deepEqual(
    legend.map((a) => [a.key, a.name, a.kind, a.chars]),
    [
      ['agent:u1', 'Ann', 'agent', 4],
      ['u1', 'Ann', 'person', 2],
    ],
  );
  assert.notEqual(legend[0].color, legend[1].color);
});
