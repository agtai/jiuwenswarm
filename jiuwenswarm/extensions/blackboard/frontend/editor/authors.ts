// Who wrote what: the legend behind the Authors toggle. Colors come from the schema's
// data-author-color, which the stylesheet maps to the app's avatar palette.
import { authorColorIndex } from '../../host/docservice/src/schema/extensions.ts';

export interface AuthorEntry {
  id: string;
  kind: 'person' | 'agent';
  name: string;
  // Characters written, for ordering the legend.
  chars: number;
  color: number;
}

interface JsonNode {
  type?: string;
  text?: string;
  marks?: Array<{ type: string; attrs?: Record<string, unknown> }>;
  content?: JsonNode[];
}

export function authorColor(id: string, part: 'surface' | 'border' | 'text' = 'border'): string {
  return `var(--color-agent-group-avatar-variant-${authorColorIndex(id)}-${part})`;
}

// Authors of the text in a document (ProseMirror JSON), most characters first.
export function authorsOf(doc: JsonNode, names: ReadonlyMap<string, string>): AuthorEntry[] {
  const found = new Map<string, AuthorEntry>();
  const walk = (node: JsonNode) => {
    if (node.type === 'text' && node.text) {
      const mark = node.marks?.find((m) => m.type === 'author');
      const id = typeof mark?.attrs?.id === 'string' ? mark.attrs.id : null;
      if (id) {
        const entry = found.get(id);
        if (entry) entry.chars += node.text.length;
        else {
          const kind = mark?.attrs?.kind === 'agent' ? 'agent' : 'person';
          found.set(id, { id, kind, name: names.get(id) ?? id, chars: node.text.length, color: authorColorIndex(id) });
        }
      }
    }
    node.content?.forEach(walk);
  };
  walk(doc);
  return [...found.values()].sort((a, b) => b.chars - a.chars || a.name.localeCompare(b.name));
}
