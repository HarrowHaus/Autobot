import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verifier import HTTP,Verifier,parse_claim_text

class Resp:
    def __init__(self,status=200,obj=None,text=None):
        self.status=status
        self.headers={}
        self.data=text.encode() if text is not None else json.dumps(obj if obj is not None else {}).encode()
    def __enter__(self): return self
    def __exit__(self,*a): pass
    def read(self): return self.data

class Fake:
    def __init__(self): self.calls=[]
    def __call__(self,req,timeout=15):
        self.calls.append(req.full_url)
        u=req.full_url
        if "/following/Scottcjn" in u: return Resp(204,obj={})
        if "/starred?" in u:
            return Resp(200,obj=[
                {"repo":{"owner":{"login":"Scottcjn"},"name":"Rustchain"}},
                {"repo":{"owner":{"login":"Other"},"name":"x"}}
            ])
        if "/wallet/balance?" in u: return Resp(200,obj={"balance_rtc":10.5})
        if "/issues/77/comments" in u:
            return Resp(200,obj=[{"user":{"login":"alice"},"body":"Claiming X","html_url":"u1"}])
        if "dev.to" in u:
            vocab=[f"term{i}" for i in range(80)]
            text=" ".join(vocab[i%80] for i in range(600))
            return Resp(200,text="<html><body><p>"+text+"</p><p>second paragraph</p><p>third paragraph</p></body></html>")
        raise AssertionError(u)

class Tests(unittest.TestCase):
    def setUp(self):
        self.fake=Fake()
        self.v=Verifier(HTTP(opener=self.fake),owner="Scottcjn",node="https://node.test")
    def test_follow(self): self.assertTrue(self.v.follows_owner("alice").ok)
    def test_stars(self):
        c=self.v.starred_owner_repos("alice")
        self.assertTrue(c.ok); self.assertEqual(c.detail,"1")
    def test_wallet(self): self.assertTrue(self.v.wallet_exists("alice-wallet").ok)
    def test_article_word_count(self):
        c=self.v.article("https://dev.to/alice/post",500)
        self.assertTrue(c.ok); self.assertIn("words=",c.detail); self.assertIn("unique_ratio=",c.detail)

    def test_article_placeholder_fails_quality(self):
        class PlaceholderFake(Fake):
            def __call__(self,req,timeout=15):
                if "dev.to" in req.full_url:
                    return Resp(200,text="<html><body><p>TODO "+("useful content "*500)+"</p></body></html>")
                return super().__call__(req,timeout)
        v=Verifier(HTTP(opener=PlaceholderFake()),owner="Scottcjn",node="https://node.test")
        self.assertFalse(v.article("https://dev.to/alice/post",500).ok)
    def test_duplicate_single_is_ok(self):
        self.assertTrue(self.v.duplicate_claims("Scottcjn/rustchain-bounties",77,"alice","Claiming").ok)
    def test_full_verify(self):
        out=self.v.verify({"github":"alice","wallet":"alice-wallet","article_url":"https://dev.to/alice/post","min_words":500,"repo":"Scottcjn/rustchain-bounties","issue":77,"duplicate_marker":"Claiming"})
        self.assertTrue(out["all_checks_ok"]); self.assertEqual(len(out["checks"]),5)
    def test_parse_claim(self):
        p=parse_claim_text("GitHub: @alice\nWallet: alice-wallet\nLive-URL: https://dev.to/alice/post")
        self.assertEqual(p["github"],"alice"); self.assertEqual(p["wallet"],"alice-wallet")

if __name__=="__main__":
    unittest.main()
