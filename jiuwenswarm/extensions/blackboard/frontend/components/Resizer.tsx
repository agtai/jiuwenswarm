// A handle between two areas: drag it, or focus it and use the arrow keys (Shift for bigger steps).
import { useRef, type KeyboardEvent, type PointerEvent } from 'react';

export function Resizer({
  orientation,
  label,
  onStart,
  onResize,
  onDone,
  testId,
}: {
  // "vertical" separates areas side by side (drag left and right); "horizontal" stacked ones.
  orientation: 'vertical' | 'horizontal';
  label: string;
  // A drag or a key step begins: the parent notes the size it measures from.
  onStart: () => void;
  // Called with how far the pointer moved since the drag began.
  onResize: (delta: number) => void;
  onDone?: () => void;
  testId?: string;
}) {
  const start = useRef<number | null>(null);
  const axis = (event: { clientX: number; clientY: number }) => (orientation === 'vertical' ? event.clientX : event.clientY);

  const down = (event: PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    start.current = axis(event);
    onStart();
    document.body.classList.add('bb-resizing');
  };
  const move = (event: PointerEvent<HTMLDivElement>) => {
    if (start.current !== null) onResize(axis(event) - start.current);
  };
  const up = (event: PointerEvent<HTMLDivElement>) => {
    if (start.current === null) return;
    start.current = null;
    event.currentTarget.releasePointerCapture(event.pointerId);
    document.body.classList.remove('bb-resizing');
    onDone?.();
  };
  const key = (event: KeyboardEvent<HTMLDivElement>) => {
    const step = event.shiftKey ? 64 : 16;
    const keys: Record<string, number> = orientation === 'vertical' ? { ArrowLeft: -step, ArrowRight: step } : { ArrowUp: -step, ArrowDown: step };
    const delta = keys[event.key];
    if (delta === undefined) return;
    event.preventDefault();
    onStart();
    onResize(delta);
    onDone?.();
  };

  return (
    <div
      role="separator"
      aria-orientation={orientation}
      aria-label={label}
      tabIndex={0}
      className={`bb-resizer bb-resizer--${orientation}`}
      data-testid={testId}
      onPointerDown={down}
      onPointerMove={move}
      onPointerUp={up}
      onPointerCancel={up}
      onKeyDown={key}
    />
  );
}
