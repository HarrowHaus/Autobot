# Agent profile JSON Schema and validator

Prepared for Clawlancer listing `cbc3b557-8fae-4b4c-8eb1-0bc3ac0090b1`: create a JSON schema validating name, bio, skills and wallet_address, with a validation function and test cases.

## Run

Python 3.10 or newer:

```sh
python -m pip install -r requirements.txt
python validate_profile.py example.json
cat example.json | python validate_profile.py -
python -m unittest -v
```

Python API: `from validate_profile import validate_profile`; call `validate_profile(profile)` to receive `{"valid": bool, "errors": [...]}`. Each error has a JSON Pointer path, failing rule and schema path. Input is not modified or coerced.

The standalone Draft 2020-12 schema is used directly by the Python function. The task did not prescribe length limits, so the following explicit design choices are editable in the schema:

- Four required fields only; unknown fields rejected.
- Name: non-whitespace string, 1–80 characters.
- Bio: non-whitespace string, 1–2,000 characters.
- Skills: 1–50 unique, case-sensitive strings, each 1–64 characters and not whitespace-only.
- Wallet: lowercase `0x` prefix plus exactly 40 hexadecimal digits. Hexadecimal letters may use either case.

Wallet validation is format only, not checksum, ownership, balance, network compatibility or proof of skill. Even the all-zero address is structurally valid; usable payment destinations need a separate policy. Never submit keys or secrets as profile data.

The CLI limits input to 64 KiB of UTF-8 JSON; duplicate members, NaN/Infinity, malformed input and unreadable files fail. Exit codes: 0 valid, 1 schema-invalid, 2 input/IO error. Errors for parsed JSON can contain submitted values; do not log private inputs publicly.

32 local unittest methods passed on 2026-09-24 with jsonschema 4.26.0. Coverage includes valid controls, missing/wrong fields, Unicode, wallet length/characters, duplicates, bounds, no mutation/networking, CLI exit codes and malformed JSON. CI runs these tests again on the published files; see the linked workflow result for committed-source verification.

AI-assisted implementation by Aven for Vince / KungFury87. All sample identities are fixtures. This is prepared work, not a statement of marketplace acceptance or payment.

Library reference: https://python-jsonschema.readthedocs.io/en/stable/validate/
