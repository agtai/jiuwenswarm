export interface PlacedNavItem<T> {
  item: T;
  after?: string;
}

/**
 * Put application plugin items into the built-in navigation: right after the
 * built-in item named by `after`, else after all built-in items. Plugin items
 * keep their given order within each place.
 */
export function placeNavItems<T extends { key: string }>(builtIn: T[], plugins: PlacedNavItem<T>[]): T[] {
  const builtInKeys = new Set(builtIn.map((item) => item.key));
  const anchored = new Map<string, T[]>();
  const trailing: T[] = [];
  for (const { item, after } of plugins) {
    if (after && builtInKeys.has(after)) {
      anchored.set(after, [...(anchored.get(after) ?? []), item]);
    } else {
      trailing.push(item);
    }
  }
  return [...builtIn.flatMap((item) => [item, ...(anchored.get(item.key) ?? [])]), ...trailing];
}
