#!/usr/bin/env python3
"""Validate agent-profile JSON without networking, coercion or wallet operations."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from typing import Any
from jsonschema import Draft202012Validator

SCHEMA = json.loads(Path(__file__).with_name('agent-profile.schema.json').read_text(encoding='utf-8'))
Draft202012Validator.check_schema(SCHEMA)
VALIDATOR = Draft202012Validator(SCHEMA)
MAX_INPUT_BYTES = 65536

def pointer(parts: Any) -> str:
    """RFC 6901 JSON Pointer; root is the empty string."""
    return ''.join('/'+str(part).replace('~','~0').replace('/','~1') for part in parts)

def validate_profile(profile: Any) -> dict[str, Any]:
    """Return all structural errors without altering the submitted data.

    The caller supplies JSON-compatible values. A valid wallet string is not a
    checksum, control/ownership check, or proof of support by a receiving service.
    """
    errors = [
        {'path': pointer(error.absolute_path), 'rule': error.validator,
         'schema_path': pointer(error.absolute_schema_path),
         'message': error.message}
        for error in VALIDATOR.iter_errors(profile)
    ]
    errors.sort(key=lambda error: (error['path'], error['schema_path'], error['message']))
    return {'valid': not errors, 'errors': errors}

def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON member')
        result[key] = value
    return result

def _reject_constant(value: str) -> None:
    raise ValueError('nonstandard JSON numeric constant')

def parse_json(raw: bytes) -> Any:
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError('input exceeds 65536 bytes')
    return json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_keys,
                      parse_constant=_reject_constant)

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', help='UTF-8 profile JSON file, or - for stdin')
    args = parser.parse_args(argv)
    try:
        if args.file == '-':
            raw = sys.stdin.buffer.read(MAX_INPUT_BYTES+1)
        else:
            with open(args.file, 'rb') as stream:
                raw = stream.read(MAX_INPUT_BYTES+1)
        result = validate_profile(parse_json(raw))
    except (OSError, ValueError, UnicodeError, RecursionError):
        # Avoid echoing arbitrary malformed input or local filesystem paths.
        print(json.dumps({'valid': False, 'errors': [{'path':'', 'rule':'input',
              'message':'Unreadable, oversized, malformed or nonstandard UTF-8 JSON.'}]}))
        return 2
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result['valid'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
