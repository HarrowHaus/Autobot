# Sources

Pinned RustChain source commit: `91d0d2487743161e3dac7a8bd8116dd8f5f30678`

## Miner lifecycle
- `attest()`: https://github.com/Scottcjn/Rustchain/blob/91d0d2487743161e3dac7a8bd8116dd8f5f30678/miners/windows/rustchain_windows_miner.py#L494-L630
- challenge request: lines 503–518
- local entropy + commitment: lines 523–553
- fingerprint integration: lines 555–589
- canonical Ed25519 signing: lines 596–617
- attestation submit: lines 619–629

## Enrollment
- `enroll()`: https://github.com/Scottcjn/Rustchain/blob/91d0d2487743161e3dac7a8bd8116dd8f5f30678/miners/windows/rustchain_windows_miner.py#L652-L705
- current epoch lookup: lines 659–665
- enrollment payload / fingerprint: lines 667–679
- signed enrollment message: lines 681–693
- `/epoch/enroll`: lines 695–702

## Participation
- eligibility lookup: https://github.com/Scottcjn/Rustchain/blob/91d0d2487743161e3dac7a8bd8116dd8f5f30678/miners/windows/rustchain_windows_miner.py#L707-L724
- signed header builder starts: https://github.com/Scottcjn/Rustchain/blob/91d0d2487743161e3dac7a8bd8116dd8f5f30678/miners/windows/rustchain_windows_miner.py#L726-L740

## Dynamic network sources
Capture at publication time:
- https://rustchain.org/epoch
- https://rustchain.org/api/miners

Accuracy boundaries:
- Do not fabricate terminal output.
- Do not hardcode a live miner count or epoch pot into the finished video.
- Do not describe antiquity weighting as CPU speed, benchmark performance, guaranteed profit, or market value.
