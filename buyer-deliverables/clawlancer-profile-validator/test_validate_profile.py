import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
from validate_profile import validate_profile, parse_json, pointer, SCHEMA
from jsonschema import Draft202012Validator

BASE={'name':'Aven test','bio':'Checks records.','skills':['python','json'], 'wallet_address':'0x'+'ab'*20}

class ProfileTests(unittest.TestCase):
    def valid(self, value): self.assertTrue(validate_profile(value)['valid'])
    def invalid(self, value): self.assertFalse(validate_profile(value)['valid'])
    def test_schema_itself_valid(self): Draft202012Validator.check_schema(SCHEMA)
    def test_valid(self): self.valid(BASE)
    def test_unicode_profile(self): self.valid({**BASE,'name':'検証係','bio':'Vérification de données.'})
    def test_every_required_field(self):
        for key in BASE:
            p=copy.deepcopy(BASE); del p[key]
            with self.subTest(key=key): self.invalid(p)
    def test_every_field_wrong_type(self):
        for key in BASE:
            with self.subTest(key=key): self.invalid({**BASE,key:None})
    def test_no_coercion(self):
        for value in (0,False,[],{},1.5): self.invalid({**BASE,'name':value})
    def test_wrong_root(self):
        for value in (None,[],1,True,'profile'): self.invalid(value)
    def test_unknown_field(self): self.invalid({**BASE,'private_key':'not-a-real-key'})
    def test_empty_text(self):
        for key in ('name','bio'):
            for value in ('',' ','\t\n'): self.invalid({**BASE,key:value})
    def test_name_limits(self):
        self.valid({**BASE,'name':'x'*80}); self.invalid({**BASE,'name':'x'*81})
    def test_bio_limits(self):
        self.valid({**BASE,'bio':'x'*2000}); self.invalid({**BASE,'bio':'x'*2001})
    def test_empty_skills(self): self.invalid({**BASE,'skills':[]})
    def test_nonarray_skills(self): self.invalid({**BASE,'skills':'python'})
    def test_duplicate_skills(self): self.invalid({**BASE,'skills':['python','python']})
    def test_case_sensitive_skills_documented(self): self.valid({**BASE,'skills':['Python','python']})
    def test_invalid_skill(self):
        for value in ('','  ',None,12,{},'x'*65): self.invalid({**BASE,'skills':[value]})
    def test_skill_limits(self):
        self.valid({**BASE,'skills':[str(n) for n in range(50)]})
        self.invalid({**BASE,'skills':[str(n) for n in range(51)]})
    def test_wallet_case(self): self.valid({**BASE,'wallet_address':'0x'+'AB'*20})
    def test_wallet_not_coerced_or_trimmed(self):
        for value in ('0X'+'ab'*20,'0x'+'ab'*19,'0x'+'ab'*21,'0x'+'zz'*20,BASE['wallet_address']+'\n',' '+BASE['wallet_address']):
            self.invalid({**BASE,'wallet_address':value})
    def test_wallet_format_does_not_verify_ownership(self): self.valid({**BASE,'wallet_address':'0x'+'0'*40})
    def test_error_paths(self):
        result=validate_profile({**BASE,'skills':['ok',5]})
        self.assertEqual(result['errors'][0]['path'],'/skills/1')
    def test_pointer_escaping(self): self.assertEqual(pointer(['a/b','~',0]),'/a~1b/~0/0')
    def test_no_input_mutation(self):
        before=copy.deepcopy(BASE); validate_profile(BASE); self.assertEqual(BASE,before)
    def test_deterministic(self):
        p={**BASE,'name':0,'bio':None}
        self.assertEqual(validate_profile(p),validate_profile(p))
    def test_no_network(self):
        with patch('socket.socket',side_effect=AssertionError('network attempted')): self.valid(BASE)
    def test_json_duplicate_rejected(self):
        with self.assertRaises(ValueError): parse_json(b'{"name":"a","name":"b"}')
    def test_nonstandard_json_rejected(self):
        for raw in (b'NaN',b'Infinity',b'-Infinity',b'{',b'\xff'):
            with self.assertRaises((ValueError,UnicodeError)): parse_json(raw)
    def test_input_size(self):
        with self.assertRaises(ValueError): parse_json(b' '*65537)
    def test_cli_valid(self):
        p=subprocess.run([sys.executable,'validate_profile.py','-'],input=json.dumps(BASE),text=True,capture_output=True)
        self.assertEqual(p.returncode,0); self.assertTrue(json.loads(p.stdout)['valid'])
    def test_cli_invalid(self):
        p=subprocess.run([sys.executable,'validate_profile.py','-'],input='{}',text=True,capture_output=True)
        self.assertEqual(p.returncode,1); self.assertFalse(json.loads(p.stdout)['valid'])
    def test_cli_malformed(self):
        p=subprocess.run([sys.executable,'validate_profile.py','-'],input='{',text=True,capture_output=True)
        self.assertEqual(p.returncode,2)
    def test_cli_file_and_missing(self):
        good=subprocess.run([sys.executable,'validate_profile.py','example.json'],capture_output=True)
        bad=subprocess.run([sys.executable,'validate_profile.py','file-that-does-not-exist.json'],capture_output=True)
        self.assertEqual(good.returncode,0); self.assertEqual(bad.returncode,2)

if __name__=='__main__': unittest.main()
