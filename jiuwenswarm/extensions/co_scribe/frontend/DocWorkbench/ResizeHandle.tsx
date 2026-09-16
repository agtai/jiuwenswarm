/**
 * A drag handle on one edge of a pane. Dragging reports the pane's new size,
 * double-click reports null so the owner can fall back to its default. The body
 * class it sets while dragging is the app's own: it turns pointer events off on
 * every iframe, without which the framed editor swallows the drag.
 */
import { useCallback, useRef } from 'react';
import type { PointerEvent as ReactPointerEvent } from 'react';
import { useTranslation } from 'react-i18next';

const BODY_CLASS = 'workspace-resize-active';

export function ResizeHandle({ axis, size, onResize, testId }: {
  /** 'x' resizes a pane to the handle's right (drag left = wider); 'y' a pane below it (drag up = taller). */
  axis: 'x' | 'y';
  /** The pane's current size in px, measured by the owner when null. */
  size: () => number;
  onResize: (px: number | null) => void;
  testId?: string;
}) {
  const { t } = useTranslation();
  const drag = useRef<{ pointerId: number; start: number; startSize: number } | null>(null);

  const onPointerDown = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    if (e.button !== 0 || drag.current) return;
    e.preventDefault();
    document.body.classList.add(BODY_CLASS);
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { pointerId: e.pointerId, start: axis === 'x' ? e.clientX : e.clientY, startSize: size() };
  }, [axis, size]);

  const onPointerMove = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    if (!d || d.pointerId !== e.pointerId) return;
    const delta = (axis === 'x' ? e.clientX : e.clientY) - d.start;
    onResize(d.startSize - delta);
  }, [axis, onResize]);

  const onPointerEnd = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    if (!d || d.pointerId !== e.pointerId) return;
    drag.current = null;
    document.body.classList.remove(BODY_CLASS);
    if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId);
  }, []);

  return (
    <div
      role="separator"
      aria-orientation={axis === 'x' ? 'vertical' : 'horizontal'}
      title={t('docs.workbench.resizeHint')}
      className={`doc-workbench__resize doc-workbench__resize--${axis}`}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerEnd}
      onPointerCancel={onPointerEnd}
      onDoubleClick={() => onResize(null)}
      data-testid={testId}
    />
  );
}
