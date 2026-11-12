/** Several named print layouts, one the default (#48): which one a document prints with. */

export interface Choosable {
  readonly id: string;
  readonly is_default: boolean;
}

/**
 * The layout a document prints with: its own, else its customer's, else the default, as the
 * server decides. A choice whose layout was deleted falls through to the next one.
 */
export function layoutFor<L extends Choosable>(
  layouts: readonly L[],
  chosen: string | null,
  customers: string | null,
): L | undefined {
  for (const wanted of [chosen, customers]) {
    const found = layouts.find((layout) => layout.id === wanted);
    if (found !== undefined) return found;
  }
  return layouts.find((layout) => layout.is_default);
}
