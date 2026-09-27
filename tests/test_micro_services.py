import hashlib
import json
import unittest
from swarmbrain.micro_services import execute, MAX_BYTES

class MicroServiceTests(unittest.TestCase):
    def csv(self, data): return execute('csv-audit', data, 'text/csv')['result']
    def srt(self, text): return execute('subtitle-audit', text.encode(), 'application/x-subrip')['result']
    def svg(self, text): return execute('svg-structure-audit', text.encode(), 'image/svg+xml')['result']

    def test_csv_preserves_leading_zeroes(self):
        self.assertEqual(self.csv(b'id,value\n001,2.00\n')['records'], [{'id':'001','value':'2.00'}])
    def test_csv_counts_but_does_not_remove_duplicates(self):
        r=self.csv(b'a,b\nx,y\nx,y\n');self.assertEqual((r['row_count'],r['duplicate_row_count']),(2,1))
    def test_csv_ragged_is_not_silent_repair(self):
        with self.assertRaisesRegex(ValueError,'ragged'):self.csv(b'a,b\nx\n')
    def test_csv_duplicate_header(self):
        with self.assertRaisesRegex(ValueError,'duplicate'):self.csv(b'a,a\nx,y\n')
    def test_csv_empty_header(self):
        with self.assertRaisesRegex(ValueError,'header'):self.csv(b'a, \nx,y\n')
    def test_csv_formula_is_flagged_not_evaluated(self):
        r=self.csv(b'a\n=1+1\n');self.assertEqual(r['records'][0]['a'],'=1+1');self.assertEqual(r['formula_like_cell_count'],1)
    def test_csv_quoted_multiline(self):
        self.assertEqual(self.csv(b'a,b\n"hello\nworld",2\n')['records'][0]['a'],'hello\nworld')
    def test_csv_utf8_bom(self):
        self.assertEqual(self.csv(b'\xef\xbb\xbfa\nx')['columns'],['a'])
    def test_csv_row_limit(self):
        with self.assertRaisesRegex(ValueError,'limit'):self.csv(('a\n'+'b\n'*2001).encode())
    def test_csv_report_truncation_visible(self):
        r=self.csv(('a\n'+'=1\n'*51).encode());self.assertEqual(r['formula_like_cell_count'],51);self.assertTrue(r['formula_findings_truncated'])
    def test_csv_column_limit(self):
        with self.assertRaisesRegex(ValueError,'header'):self.csv(','.join(str(i) for i in range(65)).encode())
    def test_srt_correct_milliseconds(self):
        r=self.srt('1\n01:02:03,004 --> 01:02:04,005\nText\n');self.assertEqual(r['cues'][0]['start_ms'],3723004)
    def test_srt_overlap_report(self):
        r=self.srt('1\n00:00:01,000 --> 00:00:03,000\nA\n\n2\n00:00:02,000 --> 00:00:04,000\nB');self.assertEqual(r['overlapping_cues'],[2])
    def test_srt_index_must_match(self):
        with self.assertRaisesRegex(ValueError,'index'):self.srt('2\n00:00:01,000 --> 00:00:03,000\nA')
    def test_srt_timestamp_range(self):
        with self.assertRaisesRegex(ValueError,'timestamp'):self.srt('1\n00:70:01,000 --> 00:71:03,000\nA')
    def test_srt_negative_duration_rejected(self):
        with self.assertRaisesRegex(ValueError,'duration'):self.srt('1\n00:00:03,000 --> 00:00:01,000\nA')
    def test_svg_simple(self):
        r=self.svg('<svg xmlns="http://www.w3.org/2000/svg"><rect width="2" height="2"/></svg>');self.assertEqual((r['element_count'],r['finding_count']),(2,0))
    def test_svg_script_and_event_flagged(self):
        r=self.svg('<svg onload="run()"><script>run()</script></svg>');self.assertEqual(r['finding_count'],2)
    def test_svg_external_reference(self):
        r=self.svg('<svg><image href="https://untrusted.example/private"/></svg>');self.assertEqual(r['findings'][0]['kind'],'external_or_embedded_reference')
    def test_svg_doctype_rejected(self):
        with self.assertRaisesRegex(ValueError,'doctype'):self.svg('<!DOCTYPE svg [<!ENTITY x "secret">]><svg>&x;</svg>')
    def test_svg_never_claims_sanitization(self):
        self.assertIn('not a sanitizer',self.svg('<svg/>')['scope'])
    def test_svg_node_limit(self):
        with self.assertRaisesRegex(ValueError,'limit'):self.svg('<svg>'+'<g/>'*5001+'</svg>')
    def test_svg_wrong_root(self):
        with self.assertRaisesRegex(ValueError,'not_svg'):self.svg('<html/>')
    def test_svg_bad_xml(self):
        with self.assertRaisesRegex(ValueError,'invalid_xml'):self.svg('<svg>')
    def test_deterministic_receipt(self):
        a=execute('csv-audit',b'a\nx','text/csv');b=execute('csv-audit',b'a\nx','text/csv');self.assertEqual(a,b)
        h=a.pop('result_sha256');expected=hashlib.sha256(json.dumps(a,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest();self.assertEqual(h,expected)
    def test_input_hash_binds_raw_bytes(self):
        a=execute('csv-audit',b'a\nx','text/csv');b=execute('csv-audit',b'a\nx\n','text/csv');self.assertNotEqual(a['input_sha256'],b['input_sha256'])
    def test_no_execution_receipt_is_money(self):
        self.assertEqual(execute('csv-audit',b'a\nx','text/csv')['payment_state'],'not_observed')
    def test_mime_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError,'mime'):execute('csv-audit',b'a\nx','image/svg+xml')
    def test_unknown_service_rejected(self):
        with self.assertRaisesRegex(ValueError,'not_implemented'):execute('transcribe',b'speech','audio/wav')
    def test_bounds_and_encoding(self):
        for data in (b'',b'a'*(MAX_BYTES+1),'not-bytes'):
            with self.subTest(data=str(type(data))):
                with self.assertRaises(ValueError):execute('csv-audit',data,'text/csv')
        with self.assertRaises(UnicodeDecodeError):execute('csv-audit',b'\xff','text/csv')
        with self.assertRaisesRegex(ValueError,'null'):execute('csv-audit',b'a\n\x00','text/csv')

if __name__=='__main__':unittest.main()
