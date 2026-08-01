export function mergeProjectionById<T extends { id: string }>(
  current: readonly T[],
  incoming: readonly T[],
): T[] {
  const values = new Map(current.map((item) => [item.id, item]));
  for (const item of incoming) values.set(item.id, item);
  return [...values.values()];
}
