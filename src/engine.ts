import { validateStripePayoutItemized, type StripeValidationOutcome } from "./validators/stripe-payout-itemized.js";
import { buildQboJournalCsv, type AccountMappings, type JournalBuildResult } from "./lib/qbo-journal-builder.js";

/**
 * Only Stripe is supported. PayPal and Xero are disabled at this layer as
 * well as in the UI — an API caller who explicitly requests either gets a
 * clear rejection here, not a silently-wrong result.
 */
export type SupportedProcessor = "stripe";

export function isSupportedProcessor(value: string): value is SupportedProcessor {
  return value === "stripe";
}

export interface ConvertOptions {
  /** Only honored when the caller has already confirmed ALLOW_QBO_EXPORT is true. */
  qboExport?: { mappings: AccountMappings };
}

export interface ConvertResult {
  validation: StripeValidationOutcome;
  qboJournal: JournalBuildResult | null;
}

export async function convert(csvText: string, processor: string, options: ConvertOptions = {}): Promise<ConvertResult> {
  if (!isSupportedProcessor(processor)) {
    return {
      validation: {
        ok: false,
        report: null,
        errorsTruncated: false,
        blockingErrors: [
          {
            code: "unsupported_processor",
            field: "processor",
            message: `Processor "${processor}" is not supported in this alpha. Only "stripe" is currently enabled.`,
          },
        ],
      },
      qboJournal: null,
    };
  }

  const validation = await validateStripePayoutItemized(csvText);

  let qboJournal: JournalBuildResult | null = null;
  if (validation.ok && validation.report && options.qboExport) {
    qboJournal = buildQboJournalCsv(validation.report, options.qboExport.mappings);
  }

  return { validation, qboJournal };
}
