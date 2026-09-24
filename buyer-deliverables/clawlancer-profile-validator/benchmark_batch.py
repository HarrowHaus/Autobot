#!/usr/bin/env python3
"""Reproducible synthetic demonstration, not a service-level or profit promise."""
import io
import json
from pathlib import Path
import platform
import time
from batch_profiles import audit, sha


def fixture(count):
    rows = [{'name': f'Synthetic profile {n}', 'bio': 'Generated validation fixture.',
             'skills': ['python', 'json'], 'wallet_address': '0x'+'a1'*20}
            for n in range(count)]
    return b''.join(json.dumps(row, sort_keys=True).encode()+b'\n' for row in rows)


def run():
    raw = fixture(10000)
    runs, reports = [], []
    for attempt in range(2):
        start = time.perf_counter()
        report = audit(io.BytesIO(raw))
        runs.append({'attempt': attempt+1, 'seconds': time.perf_counter()-start})
        reports.append(report)
    if reports[0] != reports[1] or reports[0]['valid_records'] != 10000:
        raise AssertionError('valid-control or determinism check failed')
    mixed = fixture(250) + b'{}\nnot-json\n[]\n' + b'\n'
    bad = audit(io.BytesIO(mixed))
    if (bad['valid_records'], bad['invalid_records'], bad['parse_error_records'], bad['blank_lines']) != (250,3,1,1):
        raise AssertionError('mixed-fixture counts failed')
    rss = None
    if platform.system() in ('Linux', 'Darwin'):
        import resource
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if platform.system() == 'Linux':
            rss *= 1024
    out = Path('demo-output')
    out.mkdir(exist_ok=True)
    (out/'mixed-report.json').write_text(json.dumps(bad, sort_keys=True, indent=2)+'\n')
    result = {'status': 'passed', 'source_sha256': reports[0]['source_sha256'],
              'environment': reports[0]['environment'], 'os': platform.system(),
              'synthetic_records': 10000, 'input_bytes': len(raw), 'input_sha256': sha(raw),
              'runs': runs, 'identical_reports': True, 'peak_process_rss_bytes': rss,
              'memory_scope': 'process peak including imports, fixture generation and both audit runs',
              'mixed_control': {'valid': 250, 'invalid': 3, 'parse_errors': 1, 'blank_lines': 1},
              'unmeasured_commercial_costs': ['customer acquisition', 'intake/review effort',
                  'payment processing', 'support/corrections', 'hosting allocation'],
              'revenue_collected': None,
              'limitations': 'Synthetic fixture performance only; not arbitrary input performance or an accepted paid order.'}
    (out/'measurements.json').write_text(json.dumps(result, sort_keys=True, indent=2)+'\n')
    print(json.dumps(result, sort_keys=True, indent=2))

if __name__ == '__main__':
    run()
