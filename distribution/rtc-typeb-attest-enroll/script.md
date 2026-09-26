# Narration Script — ~4 minutes

## 0:00–0:30 — The lifecycle

A RustChain miner does more than send a CPU name to a server. The current Windows miner has a concrete sequence: get a challenge, collect local hardware evidence, attach the hardware fingerprint, sign the attestation when the Ed25519 module is available, submit it, then enroll into the current epoch.

This walkthrough follows that code directly.

## 0:30–1:05 — Challenge first

In `RustChainMiner.attest()`, the client starts by POSTing to `/attest/challenge`. It requires a returned nonce before it continues.

The miner then collects entropy locally and builds a commitment from the challenge nonce, wallet identity, and sorted entropy payload.

That means the attestation starts with a server-issued challenge and a response derived from the current local measurement cycle.

## 1:05–1:45 — Hardware fingerprint

Next, the miner runs the Proof-of-Antiquity hardware fingerprint checks when `fingerprint_checks.py` is available.

The code calls `validate_all_checks(include_rom_check=False)` for this modern-x86 path and places both the overall result and the individual check results inside the attestation.

The source is explicit about why this matters: if the miner submits no fingerprint, the server can enroll it at the VM-tier weight instead of silently treating it as verified physical hardware.

## 1:45–2:20 — Bind the payload

Before submission, the miner can sign the canonical JSON attestation with its Ed25519 keypair.

The signature, public key, and signature type are then attached to the request. The actual attestation is POSTed to `/attest/submit`.

If the server returns HTTP 200 with `ok`, the miner marks the attestation valid for its local refresh window.

## 2:20–3:00 — Enroll into the epoch

Attestation and epoch enrollment are separate steps.

The miner fetches the current `/epoch` response, builds an enrollment payload containing its wallet identity, miner ID, device family and architecture, and resubmits the fingerprint data.

When signing is available, the enrollment message is the exact string:

`miner_pubkey|miner_id|epoch`

The miner sends that payload to `/epoch/enroll`. A successful response marks it enrolled.

## 3:00–3:35 — Participation status

After enrollment, the miner can query its eligibility and construct signed header submissions.

The code checks `/lottery/eligibility` using the wallet identity, and the header builder requires an Ed25519 keypair before signing a slot/miner/timestamp message.

For the network-level picture, `/epoch` exposes the live epoch state and `/api/miners` exposes recently visible miners.

## 3:35–4:00 — The useful mental model

So the clean mental model is:

**challenge → measure → fingerprint → sign → attest → enroll → participate.**

The physical machine is measured first. The measurement travels with the identity. Enrollment then places that attested identity into the current epoch.

For current network values, capture the live endpoints at publication time instead of hardcoding this video’s numbers.
