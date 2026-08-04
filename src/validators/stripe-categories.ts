/**
 * Stripe `reporting_category` model.
 *
 * THREE separate questions are answered here. Conflating them is how
 * accounting bugs get shipped:
 *
 *   1. RECOGNITION — "is this a real Stripe reporting category?"
 *      An unrecognized value may mean a report format we don't understand,
 *      so it blocks the file.
 *
 *   2. DIRECTION — "does this increase or decrease the balance?"
 *      Recorded only where Stripe's own prose or a worked example says so.
 *
 *   3. CLASSIFICATION — "how should this be booked in double-entry terms?"
 *      Assigned only where Stripe documents it. A category can be perfectly
 *      RECOGNIZED and still be UNCLASSIFIED. That is an honest state: the
 *      report shows it by name with its own totals, and the QuickBooks
 *      journal builder refuses to invent an account for it.
 *
 * ── Sources (verified against docs, not recalled) ──────────────────────────
 * - docs.stripe.com/reports/reporting-categories (48 entries; the .md mirror
 *   truncates before the reference table — the HTML is authoritative)
 * - stripe/openapi spec3.json → /v1/reporting/report_runs → parameters →
 *   reporting_category.enum (37 entries). This is the ONLY machine-readable
 *   list Stripe publishes. Note: BalanceTransaction.reporting_category is
 *   typed as a bare `string` with NO enum.
 * - docs.stripe.com/connect/network-cost-passthrough-platforms
 *   (platform_fee_transfer)
 *
 * ── Why this list can never be treated as closed ───────────────────────────
 * The OpenAPI enum carries `"x-stripeBypassValidation": true` — Stripe
 * explicitly accepts values outside its own published enum. The docs page
 * and the enum also disagree in BOTH directions (16 docs-only values, 5
 * enum-only values), so neither is a superset. The union below is 54 values
 * and is still, by construction, incomplete. Unknown categories must fail
 * loudly rather than be absorbed.
 */

export type CategoryProvenance = "openapi_enum" | "docs_page" | "connect_doc";

/** Direction of balance impact, with the confidence we have in it. */
export type Direction = "increase" | "decrease" | "bidirectional" | "unknown";
export type DirectionConfidence = "confirmed" | "likely" | "unknown";

/**
 * - `revenue`       gross sales activity
 * - `refund`        return of previously recognized revenue
 * - `dispute`       chargeback activity (either direction)
 * - `fee`           a Stripe processing/software fee
 * - `payout_event`  movement of funds to the bank, not activity within it
 * - `unclassified`  recognized, but Stripe does not document how to book it
 */
export type CategoryClassification = "revenue" | "refund" | "dispute" | "fee" | "payout_event" | "unclassified";

export interface CategorySpec {
  provenance: CategoryProvenance;
  direction: Direction;
  directionConfidence: DirectionConfidence;
  classification: CategoryClassification;
  /**
   * True for the four categories Stripe's published fee-total formula reads
   * from the GROSS column rather than the fee column.
   *
   * CONFIRMED verbatim, docs.stripe.com/revenue-recognition/data-reconciliation:
   *   "Calculate the total fee on the Balance summary report by summing:
   *    - Gross column: fee + network_cost + contribution + financing_paydown rows
   *    - Fee column: total row"
   *
   * A tool that totals only the `fee` COLUMN systematically understates
   * fees, because standalone fee rows carry 0 there and put the amount in
   * gross/net instead. This flag is what stops that.
   *
   * CAVEAT, and it matters: `contribution` (a Climate donation) and
   * `financing_paydown` (a loan repayment) are NOT economically fees.
   * Stripe groups them here because they are gross-negative non-activity
   * rows to exclude from revenue, not because they are expenses. They are
   * therefore counted in the "amounts carried in gross" subtotal but are
   * NOT classified as `fee`, and must not be booked to a fee account.
   */
  feeInGross?: true;
  note?: string;
}

const spec = (
  provenance: CategoryProvenance,
  direction: Direction,
  directionConfidence: DirectionConfidence,
  classification: CategoryClassification,
  extra: Partial<CategorySpec> = {}
): CategorySpec => ({ provenance, direction, directionConfidence, classification, ...extra });

export const CATEGORY_SPECS: Record<string, CategorySpec> = {
  // ── Payments ────────────────────────────────────────────────────────────
  charge: spec("openapi_enum", "increase", "confirmed", "revenue"),
  charge_failure: spec("openapi_enum", "decrease", "likely", "unclassified", {
    note: "Reverses a previously credited pending charge (ACH/direct debit failure).",
  }),
  refund: spec("openapi_enum", "decrease", "confirmed", "refund"),
  refund_failure: spec("openapi_enum", "increase", "confirmed", "unclassified", {
    note: "Refund failed and Stripe returned the funds. Reverses a refund; booking is not documented.",
  }),
  partial_capture_reversal: spec("openapi_enum", "decrease", "confirmed", "unclassified", {
    note: "Uncaptured portion of an authorization. Must be netted against the matching `charge`, not booked alone.",
  }),
  dispute: spec("openapi_enum", "decrease", "confirmed", "dispute"),
  dispute_reversal: spec("openapi_enum", "increase", "confirmed", "dispute"),

  // ── Fees and fee-like gross rows (Stripe's published fee formula) ───────
  fee: spec("openapi_enum", "decrease", "confirmed", "fee", {
    feeInGross: true,
    note: "Stripe software/service fees (Radar, Connect, Billing, Identity). Amount is in gross/net; the fee column is 0.",
  }),
  network_cost: spec("openapi_enum", "decrease", "confirmed", "fee", {
    feeInGross: true,
    note: "Interchange/scheme costs. In Stripe's fee-total formula. Not described on the reporting-categories page; enum-only.",
  }),
  contribution: spec("openapi_enum", "decrease", "confirmed", "unclassified", {
    feeInGross: true,
    note: "Climate contribution. Included in Stripe's fee-total formula but NOT economically a fee — do not book as expense without a decision.",
  }),
  financing_paydown: spec("openapi_enum", "decrease", "confirmed", "unclassified", {
    feeInGross: true,
    note: "Capital loan repayment. Included in Stripe's fee-total formula but is debt repayment, not a fee.",
  }),
  tax: spec("openapi_enum", "decrease", "likely", "unclassified", {
    note: "Tax on Stripe fees. A real cost, but Stripe deliberately EXCLUDES it from its own fee-total formula.",
  }),

  // ── Payouts ─────────────────────────────────────────────────────────────
  payout: spec("openapi_enum", "decrease", "likely", "payout_event", {
    note: "The payout itself. Whether Stripe emits this row inside an itemized payout export is UNDOCUMENTED — verify against a real export.",
  }),
  payout_reversal: spec("openapi_enum", "increase", "confirmed", "payout_event", {
    note: "Failed/cancelled payout returned to balance. Same undocumented-presence caveat as `payout`.",
  }),
  payout_minimum_balance_hold: spec("docs_page", "decrease", "likely", "unclassified"),
  payout_minimum_balance_release: spec("docs_page", "increase", "likely", "unclassified"),

  // ── Balance movements ───────────────────────────────────────────────────
  topup: spec("openapi_enum", "increase", "confirmed", "unclassified"),
  topup_reversal: spec("openapi_enum", "decrease", "confirmed", "unclassified"),
  other_adjustment: spec("openapi_enum", "unknown", "unknown", "unclassified", {
    note: "Explicit catch-all; absorbs both inbound and outbound obligations. Direction genuinely varies.",
  }),
  currency_conversion: spec("docs_page", "unknown", "unknown", "unclassified"),
  unreconciled_customer_funds: spec("openapi_enum", "increase", "confirmed", "unclassified"),
  stripe_balance_payment_debit: spec("docs_page", "decrease", "confirmed", "unclassified"),
  stripe_balance_payment_debit_reversal: spec("docs_page", "increase", "confirmed", "unclassified"),
  payment_network_reserve_hold: spec("docs_page", "decrease", "likely", "unclassified"),
  payment_network_reserve_release: spec("docs_page", "increase", "likely", "unclassified"),
  risk_reserved_funds: spec("openapi_enum", "bidirectional", "confirmed", "unclassified", {
    note: "Emits a debit and a matching credit under one category — never assume a sign.",
  }),
  anticipation_repayment: spec("openapi_enum", "decrease", "likely", "unclassified"),
  climate_order_purchase: spec("openapi_enum", "decrease", "likely", "unclassified"),
  climate_order_refund: spec("openapi_enum", "increase", "confirmed", "unclassified"),
  revenue_share: spec("docs_page", "increase", "likely", "unclassified", {
    note: "Revenue share paid by Stripe to partners.",
  }),
  reward: spec("docs_page", "increase", "confirmed", "unclassified"),
  tax_fund: spec("docs_page", "unknown", "unknown", "unclassified", {
    note: "Funds moved BETWEEN balances — explicitly bidirectional.",
  }),
  tax_withholding: spec("docs_page", "decrease", "confirmed", "unclassified"),
  fee_credit_funding: spec("docs_page", "increase", "confirmed", "unclassified"),

  // ── Connect ─────────────────────────────────────────────────────────────
  transfer: spec("openapi_enum", "decrease", "confirmed", "unclassified"),
  transfer_reversal: spec("openapi_enum", "increase", "likely", "unclassified"),
  platform_earning: spec("openapi_enum", "increase", "likely", "unclassified"),
  platform_earning_refund: spec("openapi_enum", "decrease", "confirmed", "unclassified"),
  connect_collection_transfer: spec("openapi_enum", "decrease", "likely", "unclassified", {
    note: "Perspective-dependent: the connected account sees the opposite sign.",
  }),
  connect_reserved_funds: spec("openapi_enum", "bidirectional", "confirmed", "unclassified"),
  platform_fee_transfer: spec("connect_doc", "unknown", "unknown", "unclassified", {
    note: "Network-cost passthrough. Transfers before March 2026 carry `charge` or `transfer` instead — the SAME economic event changes category by date.",
  }),
  advance: spec("openapi_enum", "increase", "confirmed", "unclassified"),
  advance_funding: spec("openapi_enum", "decrease", "confirmed", "unclassified"),
  financing_payout: spec("openapi_enum", "increase", "likely", "unclassified"),
  financing_payout_reversal: spec("openapi_enum", "decrease", "likely", "unclassified"),
  financing_paydown_reversal: spec("openapi_enum", "increase", "likely", "unclassified"),

  // ── Issuing ─────────────────────────────────────────────────────────────
  issuing_authorization_hold: spec("openapi_enum", "decrease", "confirmed", "unclassified"),
  issuing_authorization_release: spec("openapi_enum", "increase", "confirmed", "unclassified"),
  issuing_transaction: spec("openapi_enum", "decrease", "confirmed", "unclassified"),
  issuing_dispute: spec("openapi_enum", "increase", "confirmed", "unclassified"),
  issuing_disbursement: spec("docs_page", "increase", "confirmed", "unclassified"),
  issuing_dispute_fraud_liability_debit: spec("docs_page", "decrease", "confirmed", "unclassified"),
  issuing_dispute_provisional_credit: spec("docs_page", "increase", "confirmed", "unclassified"),
  issuing_dispute_provisional_credit_reversal: spec("docs_page", "decrease", "confirmed", "unclassified"),
};

/** The 54-value union above is deliberately NOT treated as closed — see file header. */
export const KNOWN_CATEGORY_COUNT = Object.keys(CATEGORY_SPECS).length;

export function isKnownCategory(category: string): boolean {
  return Object.prototype.hasOwnProperty.call(CATEGORY_SPECS, category);
}

export function specFor(category: string): CategorySpec | undefined {
  return CATEGORY_SPECS[category];
}

/** Categories that ARE the payout, not activity within it. */
export function isPayoutEvent(category: string): boolean {
  return specFor(category)?.classification === "payout_event";
}

/** Categories whose amount is carried in gross/net rather than the fee column. */
export function isFeeInGross(category: string): boolean {
  return specFor(category)?.feeInGross === true;
}

/** True when we cannot say how to book this category — including unknown ones. */
export function isUnclassified(category: string): boolean {
  const s = specFor(category);
  return s === undefined || s.classification === "unclassified";
}
