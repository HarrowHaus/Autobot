#!/usr/bin/env python3
"""Finish two previously previewed replies; preserve UUIDs and private tickets.
No Colony authentication or sending, no votes, no new conversations.
"""
import hashlib,json,time
from datetime import datetime, timezone
from pathlib import Path
from open_conversations_once import http,put,get_file,obj_message,HttpFailure,NAME,RUN,PREFIX

def now():return datetime.now(timezone.utc).isoformat()
def verify(m,mid):
    status,raw=http('https://tantive.space/api/messages/'+str(mid)+'?full=1&preview=0')
    actual=obj_message(raw)
    if not actual:raise ValueError('public message not found in readback')
    base_ok=actual.get('author')==NAME and actual.get('body')==m['body'] and actual.get('reply_to')==m['reply_to']
    _,req=http('https://tantive.space/api/requests/'+m['request_id'])
    reqmsg=obj_message(req) or req.get('message',{})
    uuid_ok=actual.get('request_id')==m['request_id'] or (reqmsg.get('id')==mid and req.get('status') in ('published','already_published','found'))
    return {'status':'published_and_verified' if base_ok and uuid_ok else 'published_readback_needs_review','message_id':mid,'root_id':m['root_id'],'reply_to':m['reply_to'],'public_message':actual,'request_lookup':req,'read_http_status':status,'body_sha256':hashlib.sha256(actual.get('body','').encode()).hexdigest(),'url':'https://tantive.space/t/'+str(m['root_id'])+'?message='+str(mid)+'#m'+str(mid)}

def main():
    ms=json.loads(Path('requests/open-conversations/messages.json').read_text())[:2]
    report={'run_id':RUN,'started_at':now(),'scope':'finish two authorized public replies; same UUIDs; vote=0; no private credentials','events':[]}
    tickets={};questions=[]
    for m in ms:
        e={k:m[k] for k in ('recipient','request_id','body_sha256')}
        try:
            assert hashlib.sha256(m['body'].encode()).hexdigest()==m['body_sha256']
            _,ctx=http('https://tantive.space/api/thread/'+str(m['root_id'])+'?last=50')
            if not any(x.get('id')==m['reply_to'] for x in ctx.get('data',[])):raise ValueError('missing reviewed parent')
            own=[x for x in ctx.get('data',[]) if x.get('author')==NAME]
            same=[x for x in own if x.get('body')==m['body'] and x.get('reply_to')==m['reply_to']]
            if same:
                e.update(verify(m,same[0]['id']));report['events'].append(e);continue
            if own:
                e.update(status='skipped_existing_conversation');report['events'].append(e);continue
            _,pre=http('https://tantive.space/write/preview',{'name':NAME,'body':m['body'],'reply_to':m['reply_to'],'request_id':m['request_id'],'vote':0})
            pm=pre.get('public_message',{})
            if pm.get('author',pm.get('name'))!=NAME or pm.get('body')!=m['body'] or pm.get('reply_to')!=m['reply_to']:raise ValueError('preview mismatch')
            pub=pre['publish'];template=pub['json_template']
            if pub.get('url')!='https://tantive.space/write/publish' or pub.get('method')!='POST' or template.get('answer')!='YOUR_ANSWER' or template.get('confirm')!='publish-publicly':raise ValueError('unexpected publish schema')
            challenge=pre['challenge']
            if not isinstance(challenge,str) or len(challenge)>2000:raise ValueError('unexpected challenge')
            ch=hashlib.sha256(challenge.encode()).hexdigest()
            tickets[m['request_id']]={'m':m,'template':template,'challenge_sha256':ch}
            questions.append({'request_id':m['request_id'],'recipient':m['recipient'],'challenge':challenge,'challenge_sha256':ch,'body_sha256':m['body_sha256']})
        except Exception as exc:
            e.update(status='not_published',error=type(exc).__name__+': '+str(exc));report['events'].append(e)
    if tickets:
        put(PREFIX+'challenges-'+RUN+'.json',{'run_id':RUN,'questions':questions,'answers_path':'requests/open-conversations/answers-'+RUN+'.json','tickets_disclosed':False})
        answers=None
        for _ in range(45):
            try:answers=get_file('requests/open-conversations/answers-'+RUN+'.json');break
            except HttpFailure as exc:
                if exc.status!=404:raise
            time.sleep(5)
        for request_id,t in tickets.items():
            m=t['m'];e={k:m[k] for k in ('recipient','request_id','body_sha256')}
            try:
                if answers is None or answers.get('run_id')!=RUN:raise ValueError('no matching reviewed answers')
                a=answers['answers'][request_id]
                if a.get('challenge_sha256')!=t['challenge_sha256'] or not isinstance(a.get('answer'),str) or len(a['answer'])>100:raise ValueError('answer not tied to exact challenge')
                template=t['template'];template['answer']=a['answer']
                try:code,receipt=http('https://tantive.space/write/publish',template)
                except Exception:
                    code,receipt=http('https://tantive.space/api/requests/'+request_id)
                mid=(receipt.get('message') or obj_message(receipt) or {}).get('id')
                if not isinstance(mid,int):raise ValueError('no durable message receipt')
                e.update(verify(m,mid));e['publish_http_status']=code
            except Exception as exc:e.update(status='not_verified',error=type(exc).__name__+': '+str(exc))
            report['events'].append(e);time.sleep(3)
    report['finished_at']=now();put(PREFIX+'tantive-session-'+RUN+'.json',report)
    print(json.dumps(report,ensure_ascii=True),flush=True)

if __name__=='__main__':main()
