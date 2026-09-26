# Storyboard

Format: 16:9, approximately 4 minutes.

## Shot 1 — 0:00–0:30
Show the pinned Windows miner source:
https://github.com/Scottcjn/Rustchain/blob/91d0d2487743161e3dac7a8bd8116dd8f5f30678/miners/windows/rustchain_windows_miner.py#L494-L505

Highlight:
- `def attest(self)`
- POST to `/attest/challenge`

On-screen flow:
`challenge → measure → attest → enroll`

## Shot 2 — 0:30–1:05
Source lines 512–553.

Highlight:
- nonce extraction
- `_collect_entropy()`
- commitment construction
- attestation device/signals fields

Do not display invented entropy values.

## Shot 3 — 1:05–1:45
Source lines 555–589.

Highlight:
- `validate_all_checks(include_rom_check=False)`
- `all_passed`
- `checks`
- warnings explaining missing fingerprint consequences

Optional real terminal capture:
Run the actual repository fingerprint script. If shown, record its output verbatim rather than reformatting it.

## Shot 4 — 1:45–2:20
Source lines 596–626.

Highlight:
- canonical JSON signature
- public_key
- signature_type
- POST `/attest/submit`

## Shot 5 — 2:20–3:00
Source lines 652–702.

Highlight:
- GET `/epoch`
- enrollment payload
- resubmitted fingerprint
- exact enrollment string at lines 681–691
- POST `/epoch/enroll`

## Shot 6 — 3:00–3:35
Source lines 707–740.

Highlight:
- GET `/lottery/eligibility`
- `generate_header`
- Ed25519 requirement

Then terminal capture, at recording time:
```bash
curl -fsS https://rustchain.org/epoch
curl -fsS https://rustchain.org/api/miners
```

Use whatever values are actually returned that day.

## Shot 7 — 3:35–4:00
Animated text flow:
`challenge → measure → fingerprint → sign → attest → enroll → participate`

End card:
https://github.com/Scottcjn/Rustchain
