// The comment margin beside the document: one card per open thread, level with its passage, as in
// other editors' margin comments. Positions come from the threads' anchors in the live document and
// are worked out again after edits, remote changes, reflow and card resizes.
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import type { Editor } from '@tiptap/core';

import { placeCards } from '../conversation';
import { locate, type ThreadAnchor } from './comments';

function sameTops(a: ReadonlyMap<string, number>, b: ReadonlyMap<string, number>): boolean {
  if (a.size !== b.size) return false;
  for (const [id, top] of a) if (Math.abs((b.get(id) ?? NaN) - top) > 0.5) return false;
  return true;
}

export function CommentMargin({
  editor,
  anchors,
  active,
  render,
  onActivate,
}: {
  editor: Editor;
  anchors: ThreadAnchor[];
  active: string | null;
  render: (id: string, active: boolean) => ReactNode;
  onActivate: (id: string) => void;
}) {
  const margin = useRef<HTMLDivElement | null>(null);
  const cards = useRef(new Map<string, HTMLDivElement>());
  const [tops, setTops] = useState<ReadonlyMap<string, number>>(new Map());
  const [tick, setTick] = useState(0);
  const frame = useRef(0);
  const bump = useRef(() => {
    if (frame.current) return;
    frame.current = requestAnimationFrame(() => {
      frame.current = 0;
      setTick((n) => n + 1);
    });
  });
  const [observer] = useState(() => new ResizeObserver(() => bump.current()));

  useEffect(() => {
    const onChange = () => bump.current();
    editor.on('transaction', onChange);
    observer.observe(editor.view.dom);
    for (const el of cards.current.values()) observer.observe(el);
    window.addEventListener('resize', onChange);
    return () => {
      editor.off('transaction', onChange);
      window.removeEventListener('resize', onChange);
      observer.disconnect();
      cancelAnimationFrame(frame.current);
      frame.current = 0;
    };
  }, [editor, observer]);

  useLayoutEffect(() => {
    const box = margin.current?.getBoundingClientRect();
    if (!box) return;
    const wanted = locate(editor.state, anchors)
      .map(({ id, from }) => {
        try {
          return { id, from, top: editor.view.coordsAtPos(from).top - box.top };
        } catch {
          return null;
        }
      })
      .filter((w): w is { id: string; from: number; top: number } => w !== null)
      .sort((a, b) => a.from - b.from);
    const heights = new Map([...cards.current].map(([id, el]) => [id, el.offsetHeight]));
    const next = placeCards(wanted, heights, active);
    setTops((previous) => (sameTops(previous, next) ? previous : next));
  }, [editor, anchors, active, tick]);

  // One ref callback per card for its lifetime, so a render does not detach and observe it again.
  const refs = useRef(new Map<string, (el: HTMLDivElement | null) => void>());
  const card = (id: string) => {
    let ref = refs.current.get(id);
    if (!ref) {
      ref = (el) => {
        const previous = cards.current.get(id);
        if (previous) observer.unobserve(previous);
        if (el) {
          cards.current.set(id, el);
          observer.observe(el);
        } else {
          cards.current.delete(id);
          refs.current.delete(id);
        }
      };
      refs.current.set(id, ref);
    }
    return ref;
  };

  let bottom = 0;
  for (const [id, top] of tops) bottom = Math.max(bottom, top + (cards.current.get(id)?.offsetHeight ?? 0));
  return (
    <div className="bb-editor__margin" ref={margin} style={{ minHeight: bottom }} data-testid="blackboard-comment-margin">
      {anchors.map((anchor) => {
        const top = tops.get(anchor.id);
        const isActive = anchor.id === active;
        return (
          <div
            key={anchor.id}
            ref={card(anchor.id)}
            className={`bb-margin-card${isActive ? ' is-active' : ''}`}
            // Not yet placed: drawn transparent rather than hidden, so a composer inside can take focus.
            style={top === undefined ? { top: 0, opacity: 0, pointerEvents: 'none' } : { top }}
            data-testid="blackboard-margin-card"
            data-variant={anchor.id}
            onClick={() => {
              if (!isActive) onActivate(anchor.id);
            }}
          >
            {render(anchor.id, isActive)}
          </div>
        );
      })}
    </div>
  );
}
