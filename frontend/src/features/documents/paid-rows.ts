interface PayableRow {
  readonly id: string;
  readonly status: string;
  readonly display_status: string;
  readonly open_amount: string;
}

/** The rows of a list as they look once the given invoices are paid in full. */
export function markItemsPaid<T extends PayableRow>(
  items: readonly T[],
  ids: readonly string[],
): T[] {
  return items.map((item) =>
    ids.includes(item.id)
      ? { ...item, status: "paid", display_status: "paid", open_amount: "0.00" }
      : item,
  );
}
