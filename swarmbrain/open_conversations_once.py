#!/usr/bin/env python3
"""Three reviewed public replies; one ephemeral encrypted credential handoff.
No account creation, private inbox reads, votes, paid actions or delegated jobs.
"""
import base64, hashlib, json, os, re, subprocess, tempfile, time
from datetime import datetime, timezone
from pathlib import Path
from urllib import request, error, parse

REPO='HarrowHaus/Autobot'
BRANCH='swarmbrain/open-conversations-20260923'
RUN=os.environ.get('GITHUB_RUN_ID','local-test')
PREFIX='reports/open-conversations/'
NAME='SwarmBrain'
COLONY_ID='21ec91e5-83ce-4b5d-b69f-0b0be365a343'
ALLOW={'api.github.com','tantive.space','thecolony.ai'}
class HttpFailure(Exception):
    def __init__(self,status): self.status=status; super().__init__('HTTP '+str(status))
class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): raise ValueError('redirect declined')
def http(url, data=None, token=None, method=None):
    u=parse.urlsplit(url)
    if u.scheme!='https' or u.hostname not in ALLOW or u.username or u.password: raise ValueError('unapproved origin')
    headers={'User-Agent':'SwarmBrain/1.0 public-conversation','Accept':'application/json'}
    if token: headers['Authorization']='Bearer '+token
    if data is not None: headers['Content-Type']='application/json'
    rq=request.Request(url, data=None if data is None else json.dumps(data).encode(),headers=headers,method=method)
    try:
        with request.build_opener(NoRedirect()).open(rq,timeout=25) as r:
            raw=r.read(1000001)
            if len(raw)>1000000: raise ValueError('oversize response')
            return r.status,json.loads(raw)
    except error.HTTPError as e:
        raise HttpFailure(e.code) from None

def put(path,obj):
    # Fixed owner repository. Only public receipts/ciphertext; never raw keys.
    _,r=http('https://api.github.com/repos/'+REPO+'/contents/'+path,
             {'message':'Record open conversation '+RUN,'branch':BRANCH,
              'content':base64.b64encode((json.dumps(obj,ensure_ascii=False,indent=2)+'\n').encode()).decode()},
             os.environ['GH_TOKEN'], 'PUT')
    return r['content']['html_url']

def get_file(path):
    _,r=http('https://api.github.com/repos/'+REPO+'/contents/'+path+'?ref='+parse.quote(BRANCH,safe=''),token=os.environ['GH_TOKEN'])
    return json.loads(base64.b64decode(r['content']))

def obj_message(r):
    if isinstance(r,dict):
        if 'body' in r:return r
        for k in ('message','data','comment'):
            if isinstance(r.get(k),dict):
                v=obj_message(r[k])
                if v is not None:return v
    return None

def solve(challenge):
    # Exactly the text challenge shape documented by the forum. No eval/code execution.
    m=re.fullmatch(r'Add (\d{1,6}) and (\d{1,6})\. Append a hyphen and the word ([A-Za-z]{1,40})\.',challenge.strip())
    if not m: raise ValueError('unsupported challenge shape')
    return str(int(m[1])+int(m[2]))+'-'+m[3]

def tantive(m):
    _,ctx=http('https://tantive.space/api/thread/'+str(m['root_id'])+'?last=50')
    if not any(x.get('id')==m['reply_to'] for x in ctx.get('data',[])):raise ValueError('reviewed parent missing')
    prior=[x for x in ctx['data'] if x.get('author')==NAME]
    for x in prior:
        if x.get('body')==m['body'] and x.get('reply_to')==m['reply_to']:
            return {'status':'already_present','message_id':x['id'],'root_id':m['root_id'],'body':x['body']}
    if prior:return {'status':'skipped_existing_conversation','root_id':m['root_id']}
    payload={'name':NAME,'body':m['body'],'reply_to':m['reply_to'],'request_id':m['request_id'],'vote':0}
    _,pre=http('https://tantive.space/write/preview',payload)
    if pre.get('status') in ('already_published','published'):
        receipt=pre
    else:
        pm=pre.get('public_message',{})
        if pm.get('author',pm.get('name'))!=NAME or pm.get('body')!=m['body'] or pm.get('reply_to')!=m['reply_to']:
            raise ValueError('preview does not match intended public reply')
        pub=pre['publish']
        if pub.get('url')!='https://tantive.space/write/publish' or pub.get('method')!='POST':raise ValueError('unexpected publish route')
        template=pub['json_template']
        if template.get('answer')!='YOUR_ANSWER' or template.get('confirm')!='publish-publicly':raise ValueError('unexpected confirmation schema')
        template['answer']=solve(pre['challenge'])
        # Preview ticket remains solely in runner memory; never printed or persisted.
        try: _,receipt=http(pub['url'],template)
        except Exception:
            # Ambiguous delivery: lookup original UUID instead of resending blindly.
            _,receipt=http('https://tantive.space/api/requests/'+m['request_id'])
    mid=(obj_message(receipt) or receipt.get('message',{})).get('id')
    if not isinstance(mid,int):raise ValueError('missing message receipt')
    status,read=http('https://tantive.space/api/messages/'+str(mid)+'?full=1&preview=0')
    actual=obj_message(read)
    if not actual or actual.get('author')!=NAME or actual.get('body')!=m['body'] or actual.get('reply_to')!=m['reply_to'] or actual.get('request_id')!=m['request_id']:
        return {'status':'published_readback_mismatch','message_id':mid,'root_id':m['root_id']}
    return {'status':'published_and_verified','http_status':status,'message_id':mid,'root_id':m['root_id'],'url':'https://tantive.space/t/'+str(m['root_id'])+'?message='+str(mid)+'#m'+str(mid),'body':actual['body'],'created_at':actual.get('created_at')}

def colony(m,key):
    _,r=http('https://thecolony.ai/api/v1/auth/token',{'api_key':key})
    token=r['access_token']
    # Defence in depth against accidental later runner output.
    print('::add-mask::'+token,flush=True)
    _,me=http('https://thecolony.ai/api/v1/users/me',token=token)
    if me.get('id')!=COLONY_ID or me.get('username')!='swarmbrain-harrow':raise ValueError('existing account mismatch')
    base='https://thecolony.ai/api/v1/posts/'+m['post_id']
    _,ctx=http(base+'/context',token=token)
    if ctx.get('author',{}).get('username')!='huiyou-pfa':raise ValueError('unexpected thread author')
    comments=ctx.get('comments',[])
    if not any(x.get('id')==m['parent_id'] and x.get('author_username')=='excelsior' for x in comments):raise ValueError('reviewed parent missing')
    own=[x for x in comments if x.get('author_username')=='swarmbrain-harrow']
    for x in own:
        if x.get('body')==m['body'] and x.get('parent_id')==m['parent_id']:
            return {'status':'already_present','message_id':x['id'],'account_verified':True}
    if own or ctx.get('your_comment_count',0):return {'status':'skipped_existing_conversation','account_verified':True}
    posted_id=None;write_status=None
    try:
        write_status,r=http(base+'/comments',{'body':m['body'],'parent_id':m['parent_id']},token=token)
        posted_id=(obj_message(r) or {}).get('id')
    except Exception:
        # Never repeat an ambiguous publication. A context read can recover it.
        pass
    read_status,ctx=http(base+'/context',token=token)
    matches=[x for x in ctx.get('comments',[]) if x.get('author_username')=='swarmbrain-harrow' and x.get('body')==m['body'] and x.get('parent_id')==m['parent_id']]
    if len(matches)!=1:return {'status':'delivery_unconfirmed','message_id':posted_id,'write_http_status':write_status,'account_verified':True}
    x=matches[0]
    return {'status':'published_and_verified','account_verified':True,'write_http_status':write_status,'read_http_status':read_status,'message_id':x['id'],'post_id':m['post_id'],'parent_id':m['parent_id'],'url':'https://thecolony.ai/post/'+m['post_id']+'#comments','body':x['body'],'created_at':x.get('created_at')}

def main():
    messages=json.loads(Path('requests/open-conversations/messages.json').read_text())
    assert len(messages)==3
    for m in messages:assert hashlib.sha256(m['body'].encode()).hexdigest()==m['body_sha256']
    report={'run_id':RUN,'started_at':datetime.now(timezone.utc).isoformat(),'scope':'three public conversations; no registrations, recruitment, private inboxes, votes, sales pitches or delegated tasks','events':[]}
    with tempfile.TemporaryDirectory() as tmp:
        priv=Path(tmp)/'ephemeral.pem';pub=Path(tmp)/'public.pem'
        subprocess.run(['openssl','genpkey','-algorithm','RSA','-pkeyopt','rsa_keygen_bits:3072','-out',str(priv)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        priv.chmod(0o600)
        subprocess.run(['openssl','pkey','-in',str(priv),'-pubout','-out',str(pub)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        pem=pub.read_text();fp=hashlib.sha256(pem.encode()).hexdigest()
        handshake={'run_id':RUN,'public_key_pem':pem,'public_key_sha256':fp,'credential_destination':'existing owner-controlled runner only; auth requests only to thecolony.ai','ciphertext_path':'requests/open-conversations/key-'+RUN+'.json'}
        put(PREFIX+'handshake-'+RUN+'.json',handshake)
        for m in messages[:2]:
            entry={k:m[k] for k in ('platform','recipient','request_id','body_sha256')}
            try:entry.update(tantive(m))
            except Exception as exc:entry.update(status='not_verified',error=type(exc).__name__+': '+str(exc))
            report['events'].append(entry)
            print(json.dumps({'public_event':entry},ensure_ascii=True),flush=True)
            time.sleep(3)
        # Explicitly finite rendezvous with this coordinating session, not an ongoing bot.
        envelope=None
        for _ in range(48):
            try:envelope=get_file(handshake['ciphertext_path']);break
            except HttpFailure as e:
                if e.status!=404:raise
            time.sleep(10)
        m=messages[2];entry={k:m[k] for k in ('platform','recipient','request_id','body_sha256')}
        try:
            if envelope is None:raise ValueError('private credential handoff not received')
            if envelope.get('run_id')!=RUN or envelope.get('recipient_key_sha256')!=fp:raise ValueError('ciphertext wrong recipient')
            sealed=base64.b64decode(envelope['ciphertext_b64'],validate=True)
            key=subprocess.run(['openssl','pkeyutl','-decrypt','-inkey',str(priv),'-pkeyopt','rsa_padding_mode:oaep','-pkeyopt','rsa_oaep_md:sha256','-pkeyopt','rsa_mgf1_md:sha256'],input=sealed,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=True).stdout.decode()
            if not key.startswith('col_') or not 35<len(key)<100:raise ValueError('invalid recovered key shape')
            print('::add-mask::'+key,flush=True)
            entry.update(colony(m,key));del key
        except Exception as exc:entry.update(status='not_verified',error=type(exc).__name__+': '+str(exc))
        report['events'].append(entry)
    report['finished_at']=datetime.now(timezone.utc).isoformat()
    report['verified_publications']=sum(e['status']=='published_and_verified' for e in report['events'])
    url=put(PREFIX+'session-'+RUN+'.json',report)
    print(json.dumps({'report_url':url,'verified_publications':report['verified_publications']},ensure_ascii=True),flush=True)

if __name__=='__main__':main()
