"""Bounded, deterministic services: no LLM, network, filesystem writes, or payment.

This is NOT image perception, transcription, or a deployed merchant. The adapter
must bind content hashes and result acceptance to its own durable paid order.
"""
from __future__ import annotations
import csv
import hashlib
import io
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter

VERSION = 'a0-micro-services/1'
MAX_BYTES = 262144


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                   separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _csv(text):
    reader = csv.reader(io.StringIO(text, newline=''), strict=True)
    try:
        header = next(reader)
    except StopIteration:
        raise ValueError('csv_empty')
    if not 1 <= len(header) <= 64 or any(not key.strip() for key in header):
        raise ValueError('csv_invalid_header')
    if len(set(header)) != len(header):
        raise ValueError('csv_duplicate_header')
    rows, counts, risky, risky_count = [], Counter(), [], 0
    for n, row in enumerate(reader, 2):
        if len(rows) >= 2000 or any(len(cell) > 10000 for cell in row):
            raise ValueError('csv_limit')
        if len(row) != len(header):
            raise ValueError('csv_ragged_row')
        counts[tuple(row)] += 1
        for c, cell in enumerate(row, 1):
            if cell.lstrip().startswith(('=', '+', '-', '@')):
                risky_count += 1
                if len(risky) < 50:
                    risky.append({'record': n, 'column': c})
        rows.append(dict(zip(header, row)))
    return {'columns': header, 'records': rows, 'row_count': len(rows),
            'duplicate_row_count': sum(count - 1 for count in counts.values()),
            'spreadsheet_formula_like_cells': risky, 'formula_like_cell_count': risky_count,
            'formula_findings_truncated': risky_count > len(risky),
            'policy': 'strings_preserved; no imputation, formula execution, or deletion'}


_STAMP = r'(\d{2}):([0-5]\d):([0-5]\d),(\d{3})'
_TIMING = re.compile(r'^' + _STAMP + r' --> ' + _STAMP + r'$')


def _srt(text):
    blocks = re.split(r'\n[ \t]*\n', text.replace('\r\n', '\n').replace('\r', '\n').strip())
    if not text.strip() or len(blocks) > 1000:
        raise ValueError('srt_empty_or_limit')
    cues, overlaps, prior_end = [], [], 0
    for expected, block in enumerate(blocks, 1):
        lines = block.split('\n')
        if len(lines) < 3 or lines[0].strip() != str(expected):
            raise ValueError('srt_index_or_text')
        match = _TIMING.fullmatch(lines[1].strip())
        if not match:
            raise ValueError('srt_timestamp')
        numbers = list(map(int, match.groups()))
        times = [((numbers[i]*60+numbers[i+1])*60+numbers[i+2])*1000+numbers[i+3] for i in (0, 4)]
        if times[1] <= times[0] or not '\n'.join(lines[2:]).strip():
            raise ValueError('srt_nonpositive_duration_or_empty_text')
        if expected > 1 and times[0] < prior_end:
            overlaps.append(expected)
        prior_end = max(prior_end, times[1])
        cues.append({'index': expected, 'start_ms': times[0], 'end_ms': times[1],
                     'text': '\n'.join(lines[2:])})
    return {'cues': cues, 'cue_count': len(cues), 'overlapping_cues': overlaps,
            'scope': 'subtitle syntax/timing only; not speech accuracy or transcription'}


def _svg(text):
    if re.search(r'<!\s*(DOCTYPE|ENTITY)', text, re.I):
        raise ValueError('svg_doctype_or_entity_disallowed')
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError('svg_invalid_xml') from exc
    local = lambda name: str(name).split('}')[-1].lower()
    if local(root.tag) != 'svg':
        raise ValueError('not_svg')
    flags, count, total = [], 0, 0
    for element in root.iter():
        count += 1
        if count > 5000:
            raise ValueError('svg_node_limit')
        risks = []
        if local(element.tag) in {'script', 'foreignobject', 'style', 'iframe', 'object', 'embed', 'animate', 'set'}:
            risks.append('active_or_styled_element')
        for key, value in element.attrib.items():
            name = local(key)
            if name.startswith('on') or name in {'style', 'base'}:
                risks.append('active_or_style_attribute')
            if name in {'href', 'src'} and not value.strip().startswith('#'):
                risks.append('external_or_embedded_reference')
            if 'url(' in value.lower() or 'javascript:' in value.lower():
                risks.append('url_or_script_value')
        for risk in sorted(set(risks)):
            total += 1
            if len(flags) < 50:
                flags.append({'node': count, 'kind': risk})
    return {'element_count': count, 'findings': flags, 'finding_count': total,
            'findings_truncated': total > len(flags),
            'scope': 'structural lint only; not a sanitizer, visual review, or proof of safety'}


SERVICES = {
    'csv-audit': ('text/csv', _csv),
    'subtitle-audit': ('application/x-subrip', _srt),
    'svg-structure-audit': ('image/svg+xml', _svg),
}


def execute(service_id: str, content: bytes, mime_type: str):
    if service_id not in SERVICES:
        raise ValueError('service_not_implemented')
    if not isinstance(content, bytes) or not 0 < len(content) <= MAX_BYTES:
        raise ValueError('input_size_or_type')
    expected, run = SERVICES[service_id]
    if mime_type != expected:
        raise ValueError('mime_mismatch')
    text = content.decode('utf-8-sig', errors='strict')
    if '\x00' in text:
        raise ValueError('null_byte')
    result = {'protocol': VERSION, 'service_id': service_id,
              'input_sha256': hashlib.sha256(content).hexdigest(), 'result': run(text),
              'payment_state': 'not_observed'}
    result['result_sha256'] = _hash(result)
    return result
