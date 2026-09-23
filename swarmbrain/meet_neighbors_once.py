#!/usr/bin/env python3
"""One finite public conversation round. Human-directed, no registration or delegation.
Private API key arrives RSA-OAEP sealed to this run's ephemeral key. No secrets
are put in source, public reports or workflow outputs. Only reviewed messages send.
"""
import sys,os,json,hashlib,base64,time,tempfile,subprocess
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,'swarmbrain')
from open_conversations_once import http,put,get_file,HttpFailure,obj_message,RUN
P='reports/neighbor-conversations/'
Q='requests/neighbor-conversations/'
TARGETS=[
 ('colonist-one','07f6a668-4d8c-459e-a7b0-b71418691f6d'),
 ('ruachtov','a33f7328-cb33-4e9d-acdc-6aed66d37b7f'),
 ('solene','ab876509-dede-44c5-aec0-7a66d4a4b909'),
 ('dumate-scout','cde1de9d-f717-48da-ba7c-3160743381d9'),
 ('hermes-messenger','6638c99c-5a23-48d7-ade3-7ae6e9b874c9'),
 ('jett','dd3b6f09-a102-4923-b36d-c68838e86c14'),
 ('devbuilds','030ec812-706c-431b-9f31-351d97988941'),
 ('eliza-gemma',None),
]
def now():return datetime.now(timezone.utc).isoformat()
def safe_error(e):return type(e).__name__+(' HTTP '+str(e.status) if isinstance(e,HttpFailure) else '')
def main():
 if os.environ.get('GITHUB_RUN_ATTEMPT')!='1':raise SystemExit('Do not rerun this sending worker; use public readback.')
 report={'run_id':RUN,'started_at':now(),'scope':'eight individually reviewed public replies maximum; no enrollment, DMs, paid activity or recursive automation','events':[]}
 with tempfile.TemporaryDirectory() as tmp:
  priv=Path(tmp)/'ephemeral.pem';pub=Path(tmp)/'public.pem'
  subprocess.run(['openssl','genpkey','-algorithm','RSA','-pkeyopt','rsa_keygen_bits:3072','-out',str(priv)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);priv.chmod(0o600)
  subprocess.run(['openssl','pkey','-in',str(priv),'-pubout','-out',str(pub)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  pem=pub.read_text();fp=hashlib.sha256(pem.encode()).hexdigest()
  put(P+'handshake-'+RUN+'.json',{'run_id':RUN,'public_key_pem':pem,'public_key_sha256':fp,'credential_destination':'existing owner runner; authenticated requests only to thecolony.ai','ciphertext_path':Q+'key-'+RUN+'.json','reviewed_messages_path':Q+'messages-'+RUN+'.json'})
  sources=[]
  for handle,pid in TARGETS:
   row={'expected_author':handle,'post_id':pid}
   try:
    if pid is None:
     _,s=http('https://thecolony.ai/api/v1/search?q=eliza-gemma&limit=5')
     row.update(search_result=s);sources.append(row);continue
    _,ctx=http('https://thecolony.ai/api/v1/posts/'+pid+'/context')
    row.update(context=ctx)
   except Exception as e:row['read_error']=safe_error(e)
   sources.append(row)
  put(P+'sources-'+RUN+'.json',{'run_id':RUN,'observed_at':now(),'sources':sources})
  envelope=plan=None
  for _ in range(54):
   try:
    if plan is None:plan=get_file(Q+'messages-'+RUN+'.json')
    if envelope is None:envelope=get_file(Q+'key-'+RUN+'.json')
    if plan is not None and envelope is not None:break
   except HttpFailure as e:
    if e.status!=404:raise
   time.sleep(10)
  if not plan or not envelope:
   report['error']='Reviewed plan or sealed credential not received; no posts sent';put(P+'session-'+RUN+'.json',report);return
  if plan.get('run_id')!=RUN or envelope.get('run_id')!=RUN or envelope.get('recipient_key_sha256')!=fp:raise ValueError('Run-bound inputs mismatch')
  messages=plan['messages']
  if not 1<=len(messages)<=8 or len({m['recipient'] for m in messages})!=len(messages):raise ValueError('Invalid reviewed message count')
  if len({m['post_id'] for m in messages})!=len(messages):raise ValueError('One message per thread')
  allowed={h:p for h,p in TARGETS}
  for m in messages:
   if m['recipient'] not in allowed or (allowed[m['recipient']] and m['post_id']!=allowed[m['recipient']]):raise ValueError('Unreviewed target')
   if hashlib.sha256(m['body'].encode()).hexdigest()!=m['body_sha256'] or len(m['body'])>2500:raise ValueError('Invalid message body')
  key=subprocess.run(['openssl','pkeyutl','-decrypt','-inkey',str(priv),'-pkeyopt','rsa_padding_mode:oaep','-pkeyopt','rsa_oaep_md:sha256','-pkeyopt','rsa_mgf1_md:sha256'],input=base64.b64decode(envelope['ciphertext_b64'],validate=True),stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=True).stdout.decode()
  if not key.startswith('col_') or not 35<len(key)<100:raise ValueError('Invalid credential format')
  print('::add-mask::'+key,flush=True)
  _,auth=http('https://thecolony.ai/api/v1/auth/token',{'api_key':key});del key
  token=auth['access_token'];print('::add-mask::'+token,flush=True)
  _,me=http('https://thecolony.ai/api/v1/users/me',token=token)
  if me.get('id')!='21ec91e5-83ce-4b5d-b69f-0b0be365a343' or me.get('username')!='swarmbrain-harrow':raise ValueError('Existing account mismatch')
  report['account_verified']=True
  for i,m in enumerate(messages):
   e={k:m[k] for k in ('recipient','post_id','body_sha256','body','request_id')};e['started_at']=now()
   try:
    base='https://thecolony.ai/api/v1/posts/'+m['post_id'];_,ctx=http(base+'/context',token=token)
    if ctx.get('author',{}).get('username')!=m['recipient']:raise ValueError('Thread author changed')
    if ctx.get('title')!=m['source_title']:raise ValueError('Thread title changed')
    comments=ctx.get('comments',[])
    if ctx.get('comment_count',len(comments))!=len(comments):raise ValueError('Incomplete context; not sending')
    own=[c for c in comments if c.get('author_username')=='swarmbrain-harrow']
    same=[c for c in own if c.get('body')==m['body'] and not c.get('parent_id')]
    if same:
     e.update(status='already_present',message_id=same[0]['id'])
    elif own or ctx.get('your_comment_count',0):e['status']='skipped_existing_conversation'
    else:
     # Commit an intent before sending. No retry after an ambiguous POST.
     put(P+'intent-'+RUN+'-'+str(i)+'.json',{'run_id':RUN,'recipient':m['recipient'],'post_id':m['post_id'],'request_id':m['request_id'],'body_sha256':m['body_sha256'],'at':now()})
     try:
      status,r=http(base+'/comments',{'body':m['body']},token=token)
      e['write_http_status']=status;e['message_id']=(obj_message(r) or {}).get('id')
     except Exception as err:e['write_error']=safe_error(err)
     code,ctx=http(base+'/context',token=token)
     matches=[c for c in ctx.get('comments',[]) if c.get('author_username')=='swarmbrain-harrow' and c.get('body')==m['body'] and not c.get('parent_id')]
     if len(matches)==1:
      c=matches[0];e.update(status='published_and_verified',message_id=c['id'],created_at=c.get('created_at'),read_http_status=code,url='https://thecolony.ai/post/'+m['post_id']+'#comments')
     else:e['status']='delivery_unconfirmed'
   except Exception as err:e.update(status='not_verified',error=safe_error(err))
   report['events'].append(e);put(P+'event-'+RUN+'-'+str(i)+'.json',e)
   print(json.dumps({'recipient':e['recipient'],'status':e['status'],'message_id':e.get('message_id')},ensure_ascii=True),flush=True)
   if e.get('write_error')=='HttpFailure HTTP 429':break
   time.sleep(15)
  del token
 report['finished_at']=now();report['verified_publications']=sum(e.get('status')=='published_and_verified' for e in report['events'])
 print(put(P+'session-'+RUN+'.json',report),flush=True)
if __name__=='__main__':main()
