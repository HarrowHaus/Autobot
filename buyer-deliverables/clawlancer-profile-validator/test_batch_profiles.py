import io
import json
import subprocess
import sys
import unittest
from unittest.mock import patch
from batch_profiles import audit, IntakeError, MAX_BYTES, MAX_RECORDS

PROFILE = {'name':'Synthetic auditor','bio':'Public fixture.', 'skills':['python'],
           'wallet_address':'0x'+'ab'*20}
LINE = (json.dumps(PROFILE)+'\n').encode()

class BatchTests(unittest.TestCase):
    def run_audit(self, data): return audit(io.BytesIO(data))
    def test_valid_batch(self):
        r=self.run_audit(LINE*3)
        self.assertEqual((r['valid_records'],r['invalid_records']),(3,0))
    def test_mixed_and_line_numbers(self):
        r=self.run_audit(LINE+b'\n{}\n')
        self.assertEqual((r['records'],r['valid_records'],r['blank_lines']),(2,1,1))
        self.assertEqual({e['line'] for e in r['findings']},{3})
    def test_parse_failures_are_records(self):
        r=self.run_audit(b'{\n{"name":"x","name":"y"}\nNaN\n\xff\n')
        self.assertEqual(r['parse_error_records'],4)
        self.assertEqual(r['invalid_records'],4)
    def test_nonobject_record(self):
        r=self.run_audit(b'[]\n1\nnull\ntrue\n')
        self.assertEqual(r['invalid_records'],4)
        self.assertTrue(all(e['rule']=='type' for e in r['findings']))
    def test_blank_lines_and_crlf(self):
        r=self.run_audit(b' \t\r\n'+LINE.rstrip(b'\n')+b'\r\n\n')
        self.assertEqual((r['physical_lines'],r['blank_lines']),(3,2))
        self.assertTrue(r['valid'])
    def test_exact_record_limit(self):
        self.assertEqual(self.run_audit(LINE*MAX_RECORDS)['records'],MAX_RECORDS)
    def test_record_limit_precedes_validation(self):
        with patch('batch_profiles.parse_json',side_effect=AssertionError('validation too soon')):
            with self.assertRaisesRegex(IntakeError,'record_limit_exceeded'):
                self.run_audit(LINE*(MAX_RECORDS+1))
    def test_exact_byte_limit(self):
        data=LINE+b' '*(MAX_BYTES-len(LINE))
        r=self.run_audit(data)
        self.assertTrue(r['valid']); self.assertEqual(r['input_bytes'],MAX_BYTES)
    def test_byte_limit_precedes_validation(self):
        with patch('batch_profiles.parse_json',side_effect=AssertionError('validation too soon')):
            with self.assertRaisesRegex(IntakeError,'byte_limit_exceeded'):
                self.run_audit(LINE+b' '*MAX_BYTES)
    def test_record_size_limit(self):
        r=self.run_audit(b'{"bio":"'+b'x'*65536+b'"}\n')
        self.assertEqual(r['parse_error_records'],1)
    def test_findings_are_bounded_not_counts(self):
        r=self.run_audit(b'{}\n'*10000)
        self.assertEqual((r['invalid_records'],r['findings_total'],r['findings_retained']),(10000,40000,1000))
        self.assertTrue(r['findings_truncated'])
    def test_deterministic(self):
        raw=LINE+b'{}\n'
        self.assertEqual(self.run_audit(raw),self.run_audit(raw))
    def test_no_record_contents_echoed(self):
        r=self.run_audit(json.dumps({**PROFILE,'hidden':'DO-NOT-ECHO-123','name':12345}).encode())
        text=json.dumps(r)
        self.assertNotIn('DO-NOT-ECHO-123',text); self.assertNotIn('12345',text)
    def test_no_network(self):
        with patch('socket.socket',side_effect=AssertionError('network')):
            self.assertTrue(self.run_audit(LINE)['valid'])
    def test_empty_or_whitespace_rejected(self):
        for raw in (b'',b'\n \t\r\n'):
            with self.assertRaisesRegex(IntakeError,'no_records'):self.run_audit(raw)
    def test_manifest_hashes(self):
        r=self.run_audit(LINE)
        self.assertEqual(len(r['source_sha256']),3)
        self.assertTrue(all(len(v)==64 for v in r['source_sha256'].values()))
    def test_cli_exit_codes(self):
        for raw, code in [(LINE,0),(b'{}\n',1),(b'',2)]:
            r=subprocess.run([sys.executable,'batch_profiles.py','-'],input=raw,capture_output=True)
            self.assertEqual(r.returncode,code,r.stderr)
            json.loads(r.stdout)
    def test_missing_path_not_echoed(self):
        r=subprocess.run([sys.executable,'batch_profiles.py','/private/not-a-real-file'],capture_output=True)
        self.assertEqual(r.returncode,2)
        self.assertNotIn(b'/private/',r.stdout)

if __name__ == '__main__': unittest.main()
