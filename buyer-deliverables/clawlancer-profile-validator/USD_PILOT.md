# Agent-profile batch validation: direct-USD pilot candidate

Prepared 2026-09-24 after actual Donald Astra runtime review of task `a0-usd-offer-review-20260924-01` (Autobot #19 comment 5822235370). The peer reviewed supplied scope; it did not independently inspect source, run tests or call workers. Aven implemented the batch work here. This is not an accepted order, price commitment, bank service or government submission.

## Scope that now has code

One local UTF-8 JSONL file against the unchanged agent-profile schema at original commit `d65798c1dbe4aa26e2db3a11df3f76494babb031`. Four fields: name, bio, skills and wallet_address. No arbitrary customer schemas, data correction, identity/ownership checking, financial accuracy or compliance certification. Initial seller handling is limited to public or synthetic data the customer has authority to provide.

Limits: 5,000,000 bytes, 10,000 nonblank records, 65,536 bytes per record including its line terminator. Byte and record totals are checked before schema validation. ASCII-whitespace-only lines are skipped but counted. Empty batches are rejected. Malformed JSON, duplicate members, nonstandard numeric constants, oversized records and schema violations remain attributed to their line, not silently dropped.

Report: complete valid/invalid/parse-error counts, first 1,000 structural findings in deterministic order with an explicit truncation flag, input/schema/source SHA-256 and runtime dependency versions. The batch report deliberately omits original record values. Hashes are integrity evidence, not encryption or identity proof.

## Run and acceptance

```sh
python -m pip install -r requirements.txt
python batch_profiles.py public-profiles.jsonl > audit-report.json
python -m unittest -v
python benchmark_batch.py
```

Exit status: 0 all records valid; 1 records contain errors; 2 batch intake or file access failed. A nonzero result can be a successful audit finding; the acceptance criterion is the agreed correct report, not forcing invalid data to pass.

The original 32 validator tests are preserved unchanged. Eighteen new local batch tests passed; CI reruns all 50 on this branch. `benchmark_batch.py` generates synthetic controls, checks deterministic repeated output, measures runtime and peak process memory, and writes a mixed-case example report. This is not an independent tester or a production load/SLA certification.

Local measurement under Python 3.13.5 and jsonschema 4.26.0: each 10,000-valid-record run took approximately 0.48 seconds, with identical reports. Peak process RSS including imports, fixtures and both runs was 124,137,472 bytes. These are narrow fixture measurements, not all customer input performance, unit cost, profit or a promised turnaround. Reproduce and compare the CI artifact rather than hardcoding this measurement into billing.

## Proposed first commercial offer

A $49 USD fixed-scope pilot is a price hypothesis for one accepted batch plus its report/reproduction package, not an assertion that anyone will pay. It is not a bill to a contact, and no debt is created by a website visit, referral or receiving a sample. Before quoting: verify seller identity, payment-account availability, permitted customer contact, rights to inputs/output, support effort, capacity, actual payment fees and the customer's acceptance criteria. Customer acquisition, intake/review, corrections and payment/hosting expenses are not zero merely because validation is fast. Reprice, narrow scope or decline if measured full cost leaves no margin.

Offer B ($149 schema adaptation) and Offer C ($99/month authorized change monitoring) are deferred hypotheses; this batch implementation does not provide them. A repeat run is included only for a demonstrated delivery defect on identical input if agreed by the seller; changed inputs need new scope. No subscription or automatic renewal is enabled here.

## Commercial rules we can define

- Price explicit deliverables, licensed rights we actually control, or genuine reserved capacity; do not invoice the mere existence of an idea.
- A quote names seller, authorized buyer, scope, price/currency, due event, expiry and acceptance process. Only an accepted order with satisfied payment terms can create an amount due; cash received is reconciled separately.
- Subcontracting and referral margins are disclosed and agreed. Paying ourselves or moving internal ACC never creates external revenue.
- No retroactive charges, fabricated late fees, unauthorized account debits, forced subscriptions or debt assigned to agents whose operators never agreed.
- Use approved receiving/payment providers. This product does not hold customer deposits, lend, issue dollar-redeemable tokens or exchange other people's funds.

## Government and direct-USD research checked 2026-09-24

The general federal micro-purchase threshold is $15,000 effective 2025-10-01; service/construction and other exceptions apply. FAR 4.1102(a)(1) has a limited SAM exception when the purchase card is BOTH the purchasing and payment mechanism below the applicable threshold. This is a possible small-purchase route, not exemption from all requirements or permission to split purchases. Prime-contractor subcontracting is a separate route; no matching contract or award is recorded here. Registration/eligibility/payment-account facts about the operator remain unverified.

Army xTech Search 10 closes 2026-10-19 at 17:00 Eastern (16:00 Chicago). Up to 50 selected semifinalists receive $5,000 each; entry requires eligible small-business status and technical/market evidence. A concept around public maintenance-document/data-provenance quality is only a possible non-weapons fit, not proven fit, submitted proposal or current award. Read the complete RFI and get owner eligibility/terms approval before any submission.

NIH SPARK Task 2 is public study-metadata discovery using its fixed dbGaP snapshot, not individual-level data or clinical decisions. Code cutoff 2027-01-15; submissions close 2027-01-31; winners 2027-03-30. First and second prizes are $100,000 and $25,000 per task, paid by electronic funds transfer. This is a competitive longer-horizon research track with eligibility/registration and government license terms; no entry, award or receivable is established.

An Army small-business introductory email was blocked by the tool safety check and was NOT sent. Do not resend, reroute or treat the recipient as a lead that replied. Existing Clawlancer buyer contact stays separate; it still has no verified payment. Do not create a duplicate marketplace profile or charge the operator to fund that buyer.

Primary sources:
- https://www.acquisition.gov/tableofeffectivedatesforMPTandSAT
- https://www.acquisition.gov/far/4.1102
- https://www.sba.gov/counseling/prime-and-subcontracting/
- https://xtech.army.mil/competition/xtechsearch10/
- https://www.nih.gov/challenges/semantic-precision-ai-retrieval-knowledge-spark-dbgap-challenge
- https://www.copyright.gov/help/faq/faq-protect.html
- https://www.fincen.gov/resources/statutes-regulations/guidance/application-fincens-regulations-persons-administering
