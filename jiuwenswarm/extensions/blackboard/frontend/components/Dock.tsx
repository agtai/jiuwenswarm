// The right side of the page, as in an IDE: a bar of icons on the edge, and the panels they open
// beside it. An icon shows its panel alone; dragging an icon onto a panel splits the side, so
// several panels stack. Each can be folded to its header, closed, dragged to another place in the
// stack, and given more or less of the height.
import { useEffect, useRef, useState, type DragEvent, type KeyboardEvent, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronDown, ChevronRight, GripVertical, Keyboard, PanelRightClose, PanelRightOpen, X, type LucideIcon } from 'lucide-react';

import type { RailTab } from '../controller';
import { LIMITS, clamp, updateLayout, useLayout } from '../layout';
import { Resizer } from './Resizer';

export interface DockPanel {
  id: RailTab;
  label: string;
  icon: LucideIcon;
  badge?: number;
  // A shortcut shown in the icon's tooltip, such as "Alt+1".
  shortcut?: string;
  // Panels that scroll inside themselves (the chat) get a body that does not scroll.
  fill?: boolean;
  render: () => ReactNode;
}

const MIN_PANEL_PX = 96;
const DRAG_TYPE = 'application/x-blackboard-panel';

export function ActivityBar({
  panels,
  open,
  onShow,
  onHelp,
}: {
  panels: DockPanel[];
  open: RailTab[];
  onShow: (id: RailTab) => void;
  onHelp: () => void;
}) {
  const { t } = useTranslation();
  const layout = useLayout();
  const shown = !layout.dockHidden;
  return (
    <nav className="bb-activity" aria-label={t('blackboard.layout.panels')} data-testid="blackboard-activity-bar">
      {panels.map((panel) => {
        const Icon = panel.icon;
        const isOpen = shown && open.includes(panel.id);
        const tip = `${panel.shortcut ? `${panel.label} (${panel.shortcut})` : panel.label}\n${t('blackboard.layout.splitHint')}`;
        return (
          <button
            key={panel.id}
            type="button"
            className={`bb-activity__btn${isOpen ? ' is-active' : ''}`}
            aria-pressed={isOpen}
            aria-label={panel.label}
            title={tip}
            data-testid={`blackboard-rail-tab-${panel.id}`}
            draggable={shown}
            onDragStart={(event) => {
              event.dataTransfer.setData(DRAG_TYPE, panel.id);
              event.dataTransfer.effectAllowed = 'move';
            }}
            onClick={() => {
              // With the panels hidden, an icon shows them again, with its panel.
              if (!shown) {
                updateLayout({ dockHidden: false });
                if (!open.includes(panel.id)) onShow(panel.id);
                return;
              }
              onShow(panel.id);
            }}
          >
            <Icon size={18} aria-hidden />
            {panel.badge ? (
              <span className="bb-rail__badge" data-testid="blackboard-rail-badge">
                {panel.badge}
              </span>
            ) : null}
          </button>
        );
      })}
      <span className="bb-activity__spacer" />
      <button
        type="button"
        className="bb-activity__btn"
        aria-label={t('blackboard.shortcuts.title')}
        title={`${t('blackboard.shortcuts.title')} (?)`}
        data-testid="blackboard-shortcuts-btn"
        onClick={onHelp}
      >
        <Keyboard size={18} aria-hidden />
      </button>
      <button
        type="button"
        className="bb-activity__btn"
        aria-label={shown ? t('blackboard.layout.hidePanels') : t('blackboard.layout.showPanels')}
        title={`${shown ? t('blackboard.layout.hidePanels') : t('blackboard.layout.showPanels')} (Ctrl+Alt+B)`}
        data-testid="blackboard-dock-toggle-btn"
        onClick={() => updateLayout({ dockHidden: shown })}
      >
        {shown ? <PanelRightClose size={18} aria-hidden /> : <PanelRightOpen size={18} aria-hidden />}
      </button>
    </nav>
  );
}

export function Dock({
  panels,
  open,
  active,
  onClose,
  onMove,
}: {
  panels: DockPanel[];
  open: RailTab[];
  // The panel last asked for: it comes into view, unfolded.
  active: RailTab;
  onClose: (id: RailTab) => void;
  // Moves an open panel, or adds a closed one (its icon dropped here) to the split.
  onMove: (id: RailTab, index: number) => void;
}) {
  const { t } = useTranslation();
  const layout = useLayout();
  const byId = new Map(panels.map((p) => [p.id, p]));
  const shownPanels = open.map((id) => byId.get(id)).filter((p): p is DockPanel => Boolean(p));
  const sections = useRef(new Map<RailTab, HTMLElement>());
  const widthAtStart = useRef(layout.dockWidth);
  const pairAtStart = useRef<{ above: number; below: number; weights: [number, number] } | null>(null);
  const [dropAt, setDropAt] = useState<number | null>(null);

  // A panel asked for after the page opened (made active, or opened) unfolds and comes into view;
  // a reload or a move keeps folded panels folded.
  const before = useRef<{ active: RailTab; open: RailTab[] } | null>(null);
  useEffect(() => {
    const previous = before.current;
    before.current = { active, open };
    if (!previous || !open.includes(active)) return;
    if (previous.active === active && previous.open.includes(active)) return;
    if (layout.collapsed.includes(active)) updateLayout((l) => ({ collapsed: l.collapsed.filter((id) => id !== active) }));
    sections.current.get(active)?.scrollIntoView({ block: 'nearest' });
  }, [active, open.join(',')]);

  if (layout.dockHidden || shownPanels.length === 0) return null;

  const weight = (id: RailTab) => layout.weights[id] ?? 1;
  const collapsed = (id: RailTab) => layout.collapsed.includes(id);
  const setCollapsed = (id: RailTab, fold: boolean) =>
    updateLayout((l) => ({ collapsed: fold ? [...new Set([...l.collapsed, id])] : l.collapsed.filter((c) => c !== id) }));

  // The handle below `upper` moves the border between it and the next unfolded panel.
  const nextOpen = (index: number) => shownPanels.slice(index + 1).find((p) => !collapsed(p.id));
  const startPair = (upper: RailTab, lower: RailTab) => {
    const a = sections.current.get(upper)?.getBoundingClientRect().height ?? 0;
    const b = sections.current.get(lower)?.getBoundingClientRect().height ?? 0;
    pairAtStart.current = { above: a, below: b, weights: [weight(upper), weight(lower)] };
  };
  const resizePair = (upper: RailTab, lower: RailTab, delta: number) => {
    const start = pairAtStart.current;
    if (!start || start.above + start.below === 0) return;
    const total = start.above + start.below;
    const above = Math.max(MIN_PANEL_PX, Math.min(total - MIN_PANEL_PX, start.above + delta));
    const sum = start.weights[0] + start.weights[1];
    updateLayout((l) => ({ weights: { ...l.weights, [upper]: (sum * above) / total, [lower]: (sum * (total - above)) / total } }));
  };

  const dropIndex = (event: DragEvent<HTMLElement>, index: number) => {
    const box = event.currentTarget.getBoundingClientRect();
    return event.clientY < box.top + box.height / 2 ? index : index + 1;
  };
  const drop = (event: DragEvent<HTMLElement>, index: number) => {
    const id = event.dataTransfer.getData(DRAG_TYPE) as RailTab;
    setDropAt(null);
    if (!id) return;
    event.preventDefault();
    const at = dropIndex(event, index);
    const from = open.indexOf(id);
    onMove(id, from >= 0 && from < at ? at - 1 : at);
  };
  const headerKeys = (event: KeyboardEvent<HTMLElement>, id: RailTab, index: number) => {
    if (!event.altKey || (event.key !== 'ArrowUp' && event.key !== 'ArrowDown')) return;
    event.preventDefault();
    onMove(id, index + (event.key === 'ArrowUp' ? -1 : 1));
  };

  return (
    <aside className="bb-dock" style={{ width: layout.dockWidth }} data-testid="blackboard-rail">
      <Resizer
        orientation="vertical"
        label={t('blackboard.layout.resizePanels')}
        testId="blackboard-dock-resizer"
        onStart={() => (widthAtStart.current = layout.dockWidth)}
        onResize={(delta) => updateLayout({ dockWidth: clamp(widthAtStart.current - delta, LIMITS.dock) })}
      />
      <div className="bb-dock__stack">
        {shownPanels.map((panel, index) => {
          const Icon = panel.icon;
          const folded = collapsed(panel.id);
          const lower = nextOpen(index);
          return (
            // A panel or an icon dropped on the upper half of a panel goes above it, on the lower half below.
            <section
              key={panel.id}
              ref={(el) => {
                if (el) sections.current.set(panel.id, el);
                else sections.current.delete(panel.id);
              }}
              className={`bb-dock__panel is-${panel.id}${folded ? ' is-folded' : ''}${active === panel.id ? ' is-current' : ''}${dropAt === index ? ' is-drop-before' : ''}${dropAt === index + 1 ? ' is-drop-after' : ''}`}
              style={{ flex: folded ? '0 0 auto' : `${weight(panel.id)} 1 0` }}
              data-testid="blackboard-dock-panel"
              data-variant={panel.id}
              onDragOver={(event) => {
                if (!event.dataTransfer.types.includes(DRAG_TYPE)) return;
                event.preventDefault();
                setDropAt(dropIndex(event, index));
              }}
              onDragLeave={(event) => {
                if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDropAt(null);
              }}
              onDrop={(event) => drop(event, index)}
            >
              <header
                className="bb-dock__head"
                draggable
                tabIndex={0}
                title={t('blackboard.layout.moveHint')}
                onDragStart={(event) => {
                  event.dataTransfer.setData(DRAG_TYPE, panel.id);
                  event.dataTransfer.effectAllowed = 'move';
                }}
                onDragEnd={() => setDropAt(null)}
                onKeyDown={(event) => headerKeys(event, panel.id, index)}
                onDoubleClick={() => setCollapsed(panel.id, !folded)}
              >
                <GripVertical size={14} className="bb-dock__grip" aria-hidden />
                <button
                  type="button"
                  className="bb-icon-button"
                  aria-expanded={!folded}
                  aria-label={folded ? t('blackboard.layout.unfold') : t('blackboard.layout.fold')}
                  data-testid="blackboard-dock-fold-btn"
                  onClick={() => setCollapsed(panel.id, !folded)}
                >
                  {folded ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
                </button>
                <Icon size={14} aria-hidden />
                <h3 className="bb-dock__title" data-testid="blackboard-rail-title">
                  {panel.label}
                </h3>
                {panel.badge ? <span className="bb-rail__badge bb-rail__badge--inline">{panel.badge}</span> : null}
                <button
                  type="button"
                  className="bb-icon-button bb-dock__close"
                  aria-label={t('blackboard.layout.close', { name: panel.label })}
                  title={t('blackboard.layout.close', { name: panel.label })}
                  data-testid="blackboard-dock-close-btn"
                  onClick={() => onClose(panel.id)}
                >
                  <X size={14} />
                </button>
              </header>
              {folded ? null : <div className={`bb-dock__body${panel.fill ? ' is-fill' : ''}`}>{panel.render()}</div>}
              {!folded && lower ? (
                <Resizer
                  orientation="horizontal"
                  label={t('blackboard.layout.resizeBetween', { above: panel.label, below: lower.label })}
                  onStart={() => startPair(panel.id, lower.id)}
                  onResize={(delta) => resizePair(panel.id, lower.id, delta)}
                />
              ) : null}
            </section>
          );
        })}
      </div>
    </aside>
  );
}
