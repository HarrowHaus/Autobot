#!/usr/bin/env python3
"""Persistent outbound peer network. Public peer registration is not worker enrollment.
Python standard library only. No execution of remote code, payments, or background loop.
"""
from __future__ import annotations
import argparse, hashlib, ipaddress, json, math, os, re, socket, time, uuid
from pathlib import Path
from urllib import request, error, parse

ROOT = Path(__file__).resolve().parents[1]
NS = uuid.UUID('5afddba9-2778-4a10-89b5-1f2a0a4cff30')
STOP_CODES = {401, 402, 403, 429}

def now(): return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
def digest(v): return hashlib.sha256(json.dumps(v, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    os.replace(temp, path)

def valid_url(url):
    p = parse.urlsplit(url)
    if p.scheme != 'https' or not p.hostname or p.username or p.password or p.fragment or p.port not in (None,443):
        raise ValueError('A public HTTPS URL without credentials, fragment, or custom port is required')
    for address in socket.getaddrinfo(p.hostname,443,type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(address[4][0]).is_global:
            raise ValueError('Non-public address rejected')
    return p

class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): raise ValueError('Redirect stopped; inspect the published address')

class Network:
    def __init__(self, max_calls=24, seconds=300):
        self.left=max_calls; self.deadline=time.monotonic()+seconds; self.blocked=set()
    def call(self,url,body=None,headers=None):
        p=valid_url(url)
        if p.hostname in self.blocked: raise RuntimeError('Peer paused after access, payment, or rate-limit response')
        if self.left<=0 or time.monotonic()>=self.deadline: raise RuntimeError('Run budget exhausted')
        self.left-=1
        h={'User-Agent':'SwarmBrain-Harrow/0.6 peer-client','Accept':'application/json'}
        h.update(headers or {})
        data=None if body is None else json.dumps(body).encode()
        if data is not None: h['Content-Type']='application/json'
        started=time.monotonic(); r={'url':url,'method':'GET' if body is None else 'POST','at':now()}
        if body is not None:r['request']=body
        try:
            rq=request.Request(url,data=data,headers=h)
            with request.build_opener(NoRedirect()).open(rq,timeout=min(45,max(1,self.deadline-time.monotonic()))) as response:
                raw=response.read(1048577); r['http_status']=response.status
                if len(raw)>1048576:raise ValueError('Response exceeds 1 MiB')
        except error.HTTPError as exc:
            r['http_status']=exc.code; raw=exc.read(32768)
            r['retry_after']=exc.headers.get('Retry-After')
            if exc.code in STOP_CODES:self.blocked.add(p.hostname)
        except Exception as exc:
            r.update(http_status=0,error=type(exc).__name__+': '+str(exc));raw=b''
        r['latency_ms']=round((time.monotonic()-started)*1000)
        r['response_sha256']=hashlib.sha256(raw).hexdigest()
        try:r['response']=json.loads(raw)
        except (ValueError,UnicodeError):r['response']={'unparsed_text':raw.decode('utf-8','replace')[:4000]}
        return r

def card_interface(card,preferred=None):
    if preferred=='0.3' and isinstance(card.get('url'),str):return card['url'],'0.3'
    for interface in card.get('supportedInterfaces',[]):
        if interface.get('protocolBinding')=='JSONRPC':
            return interface['url'],str(interface.get('protocolVersion','1.0'))
    if isinstance(card.get('url'),str):return card['url'],str(card.get('protocolVersion','0.3'))
    raise ValueError('No supported JSON-RPC interface in Agent Card')

def envelope(version, rpc_id, message_id, payload, context=None, agent_id='swarmbrain-harrow'):
    old=version.startswith('0.')
    part={'text':payload} if isinstance(payload,str) else {'data':payload}
    if old:part['kind']='text' if isinstance(payload,str) else 'data'
    message={'messageId':message_id,'role':'user' if old else 'ROLE_USER','parts':[part]}
    if old:message['kind']='message'
    if context:message['contextId']=context
    message['metadata']={'agent_id':agent_id}
    return {'jsonrpc':'2.0','id':rpc_id,'method':'message/send' if old else 'SendMessage',
            'params':{'message':message,'metadata':{'agent_id':agent_id}}}

def normalize(receipt, expected_id):
    if receipt.get('http_status') not in (200,201,202):return {'state':'unreachable','result':None}
    value=receipt.get('response')
    if not isinstance(value,dict) or value.get('jsonrpc')!='2.0' or value.get('id')!=expected_id:
        return {'state':'invalid_protocol_response','result':None}
    if value.get('error'):return {'state':'protocol_error','error':value['error'],'result':None}
    result=value.get('result')
    if not isinstance(result,dict):return {'state':'invalid_protocol_response','result':None}
    obj=result.get('message') or result.get('task') or result
    status=obj.get('status',{})
    state=str(status.get('state','')).upper().removeprefix('TASK_STATE_') if isinstance(status,dict) else ''
    task_id=obj.get('id') if state or obj.get('kind')=='task' else None
    if state in {'FAILED','CANCELED','CANCELLED','REJECTED'}: label='remote_'+state.lower()
    elif state in {'INPUT_REQUIRED','INPUT-REQUIRED','AUTH_REQUIRED','AUTH-REQUIRED'}: label='input_required'
    elif task_id and state!='COMPLETED': label='pending'
    elif isinstance(obj.get('parts'),list) or state=='COMPLETED':label='response_received'
    else:label='invalid_protocol_response'
    return {'state':label,'remote_state':state or 'MESSAGE','remote_task_id':task_id,
            'context_id':obj.get('contextId'),'result':result}

def parts_of(result):
    found=[]
    def walk(v):
        if isinstance(v,dict):
            if isinstance(v.get('parts'),list): found.extend(v['parts'])
            for k,x in v.items():
                if k!='parts':walk(x)
        elif isinstance(v,list):
            for x in v:walk(x)
    walk(result)
    return found

class Mesh:
    def __init__(self,root=ROOT,network=None):
        self.root=Path(root); self.path=self.root/'data/mesh-state.json'
        self.net=network or Network()
        self.state=json.loads(self.path.read_text()) if self.path.exists() else {
            'schema_version':1,'coordinator':'swarmbrain-harrow','peers':{},'tasks':{},'edges':[], 'runs':{}}
    def save(self):
        self.state['updated_at']=now();write_json(self.path,self.state)
    def register(self,alias,card_url,kind='public_service',region='discovery',source='operator'):
        if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}',alias):raise ValueError('Invalid peer alias')
        p=parse.urlsplit(card_url)
        if p.scheme!='https' or not p.hostname or p.username or p.password:raise ValueError('Invalid card URL')
        for peer in self.state['peers'].values():
            if peer['card_url']==card_url:return peer
        if alias in self.state['peers']:raise ValueError('Alias already belongs to a different card')
        peer={'id':alias,'node_id':str(uuid.uuid5(NS,card_url)),'slot':len(self.state['peers'])+1,
              'card_url':card_url,'kind':kind,'region':region,'first_seen':now(),'status':'discovered',
              'source':source,'capabilities':[],'calls':0,'responses':0,'verified_results':0,
              'contact_basis':'published_public_interface','membership_required':False}
        self.state['peers'][alias]=peer
        self.state['edges'].append({'from':'swarmbrain-harrow','to':alias,'relation':'knows_peer','source':source})
        self.save();return peer
    def connect(self,alias,preferred=None):
        peer=self.state['peers'][alias]
        receipt=self.net.call(peer['card_url'])
        write_json(self.root/'reports/peer-cards'/f'{alias}.json',receipt)
        card=receipt.get('response',{})
        if receipt['http_status']!=200 or not isinstance(card.get('name'),str) or not isinstance(card.get('skills'),list):
            peer.update(status='card_unavailable',last_error=receipt.get('error') or str(receipt['http_status']))
            self.save();return False
        try:
            endpoint,version=card_interface(card,preferred)
            if parse.urlsplit(endpoint).hostname!=parse.urlsplit(peer['card_url']).hostname:
                raise ValueError('Cross-host endpoint requires an explicit reviewed adapter')
            valid_url(endpoint)
        except (ValueError,OSError) as exc:
            peer.update(status='card_only',last_error=str(exc));self.save();return False
        peer.update(name=card['name'],endpoint=endpoint,protocol_version=version,status='card_verified',
                    last_seen=now(),card_sha256=receipt['response_sha256'],
                    capabilities=[{'id':s.get('id'),'name':s.get('name'),'tags':s.get('tags',[])} for s in card['skills'] if isinstance(s,dict)])
        if card.get('security') or card.get('securityRequirements'):peer['advertised_auth_required']=True
        self.save();return True
    def send(self,alias,payload,request_id,depends_on=None):
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}',request_id):raise ValueError('Invalid request ID')
        spec_hash=digest({'peer':alias,'payload':payload,'depends_on':depends_on})
        prior=self.state['tasks'].get(request_id)
        if prior:
            if prior['spec_hash']!=spec_hash:raise ValueError('Request ID reused with different content')
            return prior
        peer=self.state['peers'][alias]
        if peer.get('status') not in ('card_verified','connected'):raise ValueError('Peer needs a successful card handshake')
        if peer.get('advertised_auth_required'):raise ValueError('Published authorization requirements need configured credentials')
        if depends_on and depends_on not in self.state['tasks']:raise ValueError('Unknown parent task')
        message_id=str(uuid.uuid5(NS,request_id))
        body=envelope(peer['protocol_version'],request_id,message_id,payload,peer.get('context_id'))
        task={'id':request_id,'peer':alias,'spec_hash':spec_hash,'created_at':now(),
              'state':'dispatching','depends_on':depends_on,'semantic_validation':'not_reviewed'}
        self.state['tasks'][request_id]=task;self.save()
        headers={'A2A-Version':peer['protocol_version'],'X-Agent-ID':'swarmbrain-harrow'}
        receipt=self.net.call(peer['endpoint'],body,headers)
        receipt_path='reports/task-receipts/'+request_id+'.json'
        write_json(self.root/receipt_path,receipt)
        outcome=normalize(receipt,request_id)
        task.update({k:v for k,v in outcome.items() if k!='result'})
        task.update(finished_at=now(),receipt=receipt_path,latency_ms=receipt['latency_ms'],http_status=receipt['http_status'])
        text='\n'.join(p.get('text','') for p in parts_of(outcome.get('result')) if isinstance(p,dict))
        task['response_excerpt']=text[:1200]
        peer['calls']+=1
        if outcome['state'] in ('response_received','pending','input_required'):
            peer['responses']+=1;peer.update(status='connected',last_seen=now())
        if outcome.get('context_id'):peer['context_id']=outcome['context_id']
        if receipt['http_status'] in STOP_CODES:peer['status']='paused'
        peer['response_reliability']=(peer['responses']+1)/(peer['calls']+2)
        self.state['edges'].append({'from':'swarmbrain-harrow','to':alias,'relation':'requested',
                                   'task_id':request_id,'state':task['state'],'weight':peer['response_reliability']})
        if depends_on:
            parent=self.state['tasks'][depends_on]
            self.state['edges'].append({'from':parent['peer'],'to':alias,'relation':'task_handoff','task_id':request_id,'depends_on':depends_on})
        self.save();return task
    def route(self,query,limit=3):
        words=set(re.findall(r'[a-z0-9]+',query.lower()));choices=[]
        for peer in self.state['peers'].values():
            if peer.get('status') not in ('card_verified','connected'):continue
            features=set(re.findall(r'[a-z0-9]+',json.dumps(peer.get('capabilities',[])).lower()))
            overlap=len(words&features)/max(1,len(words))
            if not overlap:continue
            reliability=(peer['verified_results']+1)/(peer['calls']+2)
            choices.append({'peer':peer['id'],'activation':round(overlap*(0.5+reliability),5),
                            'matched_terms':sorted(words&features),'verified_results':peer['verified_results']})
        return sorted(choices,key=lambda x:(-x['activation'],x['peer']))[:max(1,min(limit,10))]
    def review(self,task_id,accepted,evidence):
        if not evidence.strip():raise ValueError('Review evidence is required')
        task=self.state['tasks'][task_id]
        if task.get('semantic_validation')!='not_reviewed':raise ValueError('Task already reviewed')
        if task['state']!='response_received':raise ValueError('Only a returned result can be reviewed')
        task.update(semantic_validation='accepted' if accepted else 'rejected',review_evidence=evidence,reviewed_at=now())
        peer=self.state['peers'][task['peer']]
        if accepted:peer['verified_results']+=1
        peer['task_weight']=(peer['verified_results']+1)/(peer['calls']+2)
        self.save()
    def export(self):
        graph={'generated_at':now(),'nodes':[{'id':'swarmbrain-harrow','kind':'coordinator','slot':0}]+list(self.state['peers'].values()),
               'edges':self.state['edges'],'note':'Topology and empirical routing scores, not trained neural model weights.'}
        write_json(self.root/'data/graph.json',graph)
        return {'registered_peers':len(self.state['peers']),
                'connected_peers':sum(p.get('status')=='connected' for p in self.state['peers'].values()),
                'tasks':len(self.state['tasks']),
                'results_received':sum(t.get('state')=='response_received' for t in self.state['tasks'].values()),
                'verified_task_results':sum(t.get('semantic_validation')=='accepted' for t in self.state['tasks'].values())}

def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('status')
    cmd=sub.add_parser('connect');cmd.add_argument('peer');cmd.add_argument('card');cmd.add_argument('--version')
    cmd=sub.add_parser('route');cmd.add_argument('query')
    cmd=sub.add_parser('request');cmd.add_argument('peer');cmd.add_argument('request_id');cmd.add_argument('payload',help='JSON object or a plain text request')
    args=parser.parse_args();mesh=Mesh()
    if args.command=='connect':mesh.register(args.peer,args.card);result=mesh.connect(args.peer,args.version)
    elif args.command=='route':result=mesh.route(args.query)
    elif args.command=='request':
        try:payload=json.loads(args.payload)
        except ValueError:payload=args.payload
        result=mesh.send(args.peer,payload,args.request_id)
    else:result=mesh.export()
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
