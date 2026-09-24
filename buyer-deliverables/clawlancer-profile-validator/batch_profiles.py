#!/usr/bin/env python3
"""Bounded, offline JSONL agent-profile audit. No data repair or payment actions."""
from __future__ import annotations
import argparse
import hashlib
from importlib.metadata import version
import io
import json
from pathlib import Path
import platform
import sys
from typing import BinaryIO
from validate_profile import VALIDATOR, parse_json, pointer

MAX_BYTES = 5_000_000
MAX_RECORDS = 10_000
MAX_FINDINGS = 1_000
HERE = Path(__file__).resolve().parent

class IntakeError(ValueError):
    """Input cannot be accepted under the fixed batch contract."""


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def snapshot(stream: BinaryIO) -> bytes:
    """Read once into a bounded snapshot; do not reopen a changing source."""
    chunks, size = [], 0
    while size <= MAX_BYTES:
        block = stream.read(min(65536, MAX_BYTES + 1 - size))
        if not isinstance(block, bytes):
            raise IntakeError('binary_input_required')
        if not block:
            break
        size += len(block)
        if size > MAX_BYTES:
            raise IntakeError('byte_limit_exceeded')
        chunks.append(block)
    return b''.join(chunks)


def audit(stream: BinaryIO) -> dict:
    """Preflight byte and record caps before schema validation; do not echo values."""
    raw = snapshot(stream)
    lines, records = 0, 0
    for line in io.BytesIO(raw):
        lines += 1
        if line.strip(b' \t\r\n'):
            records += 1
            if records > MAX_RECORDS:
                raise IntakeError('record_limit_exceeded')
    if not records:
        raise IntakeError('no_records')
    findings = []
    total_findings = valid = invalid = parse_errors = 0
    for line_number, line in enumerate(io.BytesIO(raw), 1):
        if not line.strip(b' \t\r\n'):
            continue
        errors = []
        try:
            profile = parse_json(line)
            for err in VALIDATOR.iter_errors(profile):
                # The fixed schema has only four top-level properties and skill indexes.
                # Do not serialize error.message or the record: they can expose contents.
                errors.append({'line': line_number, 'path': pointer(err.absolute_path),
                               'rule': str(err.validator),
                               'schema_path': pointer(err.absolute_schema_path)})
        except (ValueError, UnicodeError, RecursionError):
            parse_errors += 1
            errors = [{'line': line_number, 'path': '', 'rule': 'input',
                       'schema_path': '', 'code': 'malformed_duplicate_or_oversized_record'}]
        errors.sort(key=lambda item: (item['path'], item['schema_path'], item['rule']))
        if errors:
            invalid += 1
        else:
            valid += 1
        total_findings += len(errors)
        available = MAX_FINDINGS - len(findings)
        if available > 0:
            findings.extend(errors[:available])
    source_hashes = {name: sha((HERE/name).read_bytes()) for name in
                     ('batch_profiles.py', 'validate_profile.py', 'agent-profile.schema.json')}
    return {
        'report_version': 1, 'service': 'agent_profile_schema_batch_only',
        'valid': invalid == 0, 'input_sha256': sha(raw), 'input_bytes': len(raw),
        'physical_lines': lines, 'blank_lines': lines-records, 'records': records,
        'valid_records': valid, 'invalid_records': invalid, 'parse_error_records': parse_errors,
        'findings_total': total_findings, 'findings_retained': len(findings),
        'findings_truncated': total_findings > len(findings), 'findings': findings,
        'source_sha256': source_hashes,
        'environment': {'python': platform.python_version(), 'jsonschema': version('jsonschema')},
        'limits': {'bytes': MAX_BYTES, 'records': MAX_RECORDS,
                   'record_bytes': 65536, 'retained_findings': MAX_FINDINGS},
        'limitations': 'Schema conformance only. No correction, domain truth, identity, wallet control, or compliance certification.'
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', help='Local public/synthetic JSONL file, or - for stdin')
    args = parser.parse_args(argv)
    try:
        if args.file == '-':
            result = audit(sys.stdin.buffer)
        else:
            with open(args.file, 'rb') as stream:
                result = audit(stream)
    except (OSError, IntakeError) as error:
        code = str(error) if isinstance(error, IntakeError) else 'unreadable_input'
        print(json.dumps({'valid': False, 'intake_accepted': False, 'code': code}))
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=True, indent=2))
    return 0 if result['valid'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
