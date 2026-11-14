/** The keys that move an entry of a list one place: Alt+↑/↓ (WCAG 2.5.7, no dragging needed). */
export function moveTarget(
  event: { readonly altKey: boolean; readonly key: string },
  index: number,
  count: number,
): number | null {
  if (!event.altKey || (event.key !== "ArrowUp" && event.key !== "ArrowDown")) return null;
  const to = event.key === "ArrowUp" ? index - 1 : index + 1;
  return to >= 0 && to < count ? to : null;
}

/** The ids in a new order: the one at ``from`` moved to ``to``. */
export function moved(ids: readonly string[], from: number, to: number): string[] {
  const order = [...ids];
  const [id] = order.splice(from, 1);
  if (id !== undefined) order.splice(to, 0, id);
  return order;
}
