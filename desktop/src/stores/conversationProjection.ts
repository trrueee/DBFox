export function mergeProjectionById<T extends { id: string }>(
  current: readonly T[],
  incoming: readonly T[],
  version: (item: T) => number,
): T[] {
  const values = new Map(current.map((item) => [item.id, item]));
  for (const item of incoming) {
    const previous = values.get(item.id);
    if (!previous || version(item) >= version(previous)) values.set(item.id, item);
  }
  return [...values.values()];
}
