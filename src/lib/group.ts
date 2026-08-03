import type { NormalizedTransaction } from "../types.js";

export interface PayoutGroup {
  payoutId: string;
  /** Latest transaction date in the group — used as the deposit date proxy. */
  date: string;
  currency: string;
  transactions: NormalizedTransaction[];
  totalGrossCents: number;
  totalFeeCents: number;
  totalNetCents: number;
}

export function groupByPayout(transactions: NormalizedTransaction[]): PayoutGroup[] {
  const groups = new Map<string, NormalizedTransaction[]>();
  for (const txn of transactions) {
    const list = groups.get(txn.payoutId);
    if (list) {
      list.push(txn);
    } else {
      groups.set(txn.payoutId, [txn]);
    }
  }

  const result: PayoutGroup[] = [];
  for (const [payoutId, txns] of groups) {
    const totalGrossCents = txns.reduce((sum, t) => sum + t.grossCents, 0);
    const totalFeeCents = txns.reduce((sum, t) => sum + t.feeCents, 0);
    const totalNetCents = txns.reduce((sum, t) => sum + t.netCents, 0);
    const date = txns.reduce((latest, t) => (t.date > latest ? t.date : latest), txns[0]!.date);

    result.push({
      payoutId,
      date,
      currency: txns[0]!.currency,
      transactions: txns,
      totalGrossCents,
      totalFeeCents,
      totalNetCents,
    });
  }

  // Stable, deterministic ordering for reproducible output.
  result.sort((a, b) => (a.date === b.date ? a.payoutId.localeCompare(b.payoutId) : a.date.localeCompare(b.date)));
  return result;
}
