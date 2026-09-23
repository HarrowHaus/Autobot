#!/usr/bin/env python3
"""Operator-directed Synapse worker. Python 3.11+; standard library only.

Durable task exchange, independently reviewed routing feedback and a read-only
Project Room inbox adapter. No LLM, social registrations, paid calls or arbitrary
code execution. `python worker.py --help` lists local controls.
"""
from __future__ import annotations
import argparse
import hashlib
import http.client
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import sqlite3
import ssl
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote, urlsplit

VERSION = '0.2.0'
MAX_BODY = 262144
MAX_RESPONSE = 4 * 1024 * 1024
ID = re.compile(r'^[A-Za-z0-9_-]{1,100}$')

def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)

def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()

def text(value, label='text', limit=16000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise Fault(422, 'invalid_' + label)
    return value

def identifier(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise Fault(422, 'invalid_id')
    return value

class Fault(Exception):
    def __init__(self, status, code):
        self.status, self.code = status, code
        super().__init__(code)

class NetworkFault(Fault):
    pass

def origin_url(value):
    text(value, 'origin', 500)
    u = urlsplit(value)
    try: port = u.port
    except ValueError: raise Fault(422, 'invalid_port') from None
    if (u.scheme != 'https' or not u.hostname or u.username or u.password or
            u.path not in ('', '/') or u.query or u.fragment or port not in (None, 443)):
        raise Fault(422, 'https_origin_required')
    return 'https://' + u.hostname

class Network:
    """HTTPS, public IPs only, pinned DNS answers, verified TLS, no redirects/cookies.

    A request timeout never proves whether a remote write happened. Callers must
    journal their intent before sending and reconcile an uncertain write.
    """
    def request(self, url, method='GET', body=None, headers=None):
        u = urlsplit(text(url, 'url', 3000))
        try:
            port = u.port
        except ValueError:
            raise Fault(422, 'invalid_port') from None
        if (u.scheme != 'https' or not u.hostname or u.username or u.password or
                u.fragment or port not in (None, 443) or '\\' in url or
                any(ord(c) < 32 for c in url)):
            raise Fault(422, 'public_https_required')
        if method not in ('GET', 'POST'):
            raise Fault(422, 'method_not_allowed')
        try:
            answers = socket.getaddrinfo(u.hostname, 443, type=socket.SOCK_STREAM)
            if not answers:
                raise NetworkFault(503, 'dns_empty')
            for family, _, _, _, addr in answers:
                ip = ipaddress.ip_address(addr[0])
                if not ip.is_global or getattr(ip, 'ipv4_mapped', None) is not None:
                    raise Fault(422, 'private_address_blocked')
            family, _, proto, _, addr = answers[0]
            raw = socket.socket(family, socket.SOCK_STREAM, proto)
            raw.settimeout(15)
            conn = http.client.HTTPSConnection(u.hostname, timeout=15)
            try:
                raw.connect(addr)
                conn.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=u.hostname)
                payload = encode(body).encode() if body is not None else None
                outgoing = {'User-Agent': 'SynapseWorker/' + VERSION, 'Accept': 'application/json'}
                if payload is not None:
                    outgoing['Content-Type'] = 'application/json'
                outgoing.update(headers or {})
                conn.request(method, (u.path or '/') + ('?' + u.query if u.query else ''), payload, outgoing)
                response = conn.getresponse()
                deadline = time.monotonic() + 15
                chunks, count = [], 0
                while count <= MAX_RESPONSE:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0: raise TimeoutError()
                    if conn.sock is not None: conn.sock.settimeout(remaining)
                    chunk = response.read1(min(65536, MAX_RESPONSE + 1 - count))
                    if not chunk: break
                    chunks.append(chunk); count += len(chunk)
                content = b''.join(chunks)
                if len(content) > MAX_RESPONSE:
                    raise NetworkFault(502, 'response_too_large')
                if not 200 <= response.status < 300:
                    # Never log a URL, body, bearer, redirect location or server error text.
                    raise NetworkFault(response.status, 'remote_http_' + str(response.status))
                try:
                    value = json.loads(content)
                except (ValueError, UnicodeDecodeError):
                    value = None
                return {'status': response.status, 'bytes': len(content),
                        'sha256': hashlib.sha256(content).hexdigest(), 'json': value,
                        'observed_at': time.time()}
            finally:
                conn.close()
                raw.close()
        except socket.gaierror:
            raise NetworkFault(503, 'dns_resolution_failed') from None
        except (TimeoutError, OSError, http.client.HTTPException):
            raise NetworkFault(503, 'transport_failed') from None

@contextmanager
def process_lock(directory):
    """One serving process per local database; never silently replace a worker."""
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    f = (path / 'worker.lock').open('a+b')
    try:
        if os.name == 'nt':
            import msvcrt
            f.seek(0); f.write(b'0'); f.flush(); f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        raise Fault(409, 'worker_already_running') from None
    try:
        yield
    finally:
        f.close()

class Store:
    def __init__(self, directory, clock=time.time):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.directory, 0o700)
        self.clock, self.lock = clock, threading.RLock()
        self.private_path = self.directory / 'private.json'
        configured_admin = os.environ.get('SYNAPSE_ADMIN_TOKEN')
        if configured_admin is not None and (not 32 <= len(configured_admin) <= 512 or not configured_admin.isascii()):
            raise Fault(422, 'admin_token_must_be_32_to_512_ascii_characters')
        if not self.private_path.exists():
            fd = os.open(self.private_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(encode({'node_id': 'synapse-' + uuid.uuid4().hex,
                                'admin_token': configured_admin or secrets.token_urlsafe(40), 'room': {}}))
                f.flush(); os.fsync(f.fileno())
        self.private = json.loads(self.private_path.read_text(encoding='utf-8'))
        text(self.private.get('admin_token'), 'admin_token', 512)
        if configured_admin and not secrets.compare_digest(configured_admin, self.private['admin_token']):
            raise Fault(409, 'admin_token_differs_from_saved_identity')
        self.db = sqlite3.connect(self.directory / 'worker.sqlite3', check_same_thread=False, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=FULL;
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS peers(id TEXT PRIMARY KEY, token_hash TEXT UNIQUE,
          scope TEXT NOT NULL, evidence TEXT NOT NULL, active INTEGER NOT NULL, weights TEXT NOT NULL, examples INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, kind TEXT NOT NULL, peer TEXT,
          payload TEXT NOT NULL, fingerprint TEXT NOT NULL, state TEXT NOT NULL, attempts INTEGER NOT NULL,
          created REAL NOT NULL, updated REAL NOT NULL, next_at REAL NOT NULL, lease_until REAL NOT NULL,
          result TEXT, error TEXT, review TEXT);
        CREATE TABLE IF NOT EXISTS inbox(source TEXT NOT NULL, event_id TEXT NOT NULL,
          fingerprint TEXT NOT NULL, body TEXT NOT NULL, seen REAL NOT NULL, PRIMARY KEY(source,event_id,fingerprint));
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS audit(seq INTEGER PRIMARY KEY, event TEXT NOT NULL, details TEXT NOT NULL, at REAL NOT NULL);
        ''')
        self.db.commit()
        os.chmod(self.private_path, 0o600)
        os.chmod(self.directory / 'worker.sqlite3', 0o600)

    @contextmanager
    def tx(self):
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                yield self.db
                self.db.commit()
            except BaseException:
                self.db.rollback()
                raise

    def close(self):
        self.db.close()

    def save_private(self):
        temp = self.directory / ('private-' + uuid.uuid4().hex + '.tmp')
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(encode(self.private)); f.flush(); os.fsync(f.fileno())
        os.replace(temp, self.private_path)
        if os.name != 'nt':
            d = os.open(self.directory, os.O_RDONLY)
            try: os.fsync(d)
            finally: os.close(d)

    def audit(self, db, event, details):
        db.execute('INSERT INTO audit(event,details,at) VALUES(?,?,?)', (event, encode(details), self.clock()))

    def meta(self, key, value=None):
        if value is not None:
            with self.tx() as db:
                db.execute('INSERT OR REPLACE INTO meta VALUES(?,?)', (key, encode(value)))
        with self.lock:
            row = self.db.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def peer_add(self, peer, scope, evidence):
        identifier(peer); text(scope, 'scope', 3000); text(evidence, 'evidence', 3000)
        token = secrets.token_urlsafe(40)
        with self.tx() as db:
            if db.execute('SELECT 1 FROM peers WHERE id=?', (peer,)).fetchone():
                raise Fault(409, 'peer_exists_reuse_identity')
            db.execute('INSERT INTO peers VALUES(?,?,?,?,1,?,0)',
                       (peer, hashlib.sha256(token.encode()).hexdigest(), scope, evidence, encode([0.0]*256)))
            self.audit(db, 'peer_authorized', {'peer': peer})
        return {'peer_id': peer, 'token': token, 'scope': scope, 'endpoint_verified': False}

    def peer_revoke(self, peer):
        with self.tx() as db:
            if not db.execute('UPDATE peers SET active=0 WHERE id=?', (peer,)).rowcount:
                raise Fault(404, 'peer_not_found')
            self.audit(db, 'peer_revoked', {'peer': peer})
        return {'peer_id': peer, 'active': False}

    def authenticate(self, token):
        if secrets.compare_digest(token, self.private['admin_token']):
            return 'admin', None
        with self.lock:
            row = self.db.execute('SELECT id FROM peers WHERE token_hash=? AND active=1',
                                  (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        if row: return 'peer', row[0]
        raise Fault(401, 'unauthorized')

    def enqueue(self, job_id, kind, payload, peer=None):
        identifier(job_id)
        if kind not in ('public_read', 'room_read', 'peer_task') or not isinstance(payload, dict):
            raise Fault(422, 'invalid_job')
        if len(encode(payload).encode()) > MAX_BODY // 2:
            raise Fault(413, 'payload_too_large')
        if kind == 'public_read':
            u = urlsplit(text(payload.get('url'), 'url', 3000))
            if u.scheme != 'https' or not u.hostname or u.username or u.password or u.fragment:
                raise Fault(422, 'public_https_required')
        if kind == 'room_read' and payload:
            raise Fault(422, 'room_read_uses_saved_identity_only')
        if kind == 'peer_task':
            identifier(peer); text(payload.get('task'), 'task')
        elif peer is not None:
            raise Fault(422, 'unexpected_peer')
        fingerprint = digest([kind, payload, peer]); now = self.clock()
        with self.tx() as db:
            old = db.execute('SELECT fingerprint FROM jobs WHERE id=?', (job_id,)).fetchone()
            if old:
                if old[0] != fingerprint: raise Fault(409, 'idempotency_conflict')
                return {'id': job_id, 'duplicate': True}
            if kind == 'peer_task' and not db.execute('SELECT 1 FROM peers WHERE id=? AND active=1', (peer,)).fetchone():
                raise Fault(403, 'peer_not_authorized')
            if db.execute('SELECT count(*) FROM jobs').fetchone()[0] >= 20000:
                raise Fault(409, 'retention_limit_export_required')
            db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,0,?,?,?,0,NULL,NULL,NULL)',
                       (job_id, kind, peer, encode(payload), fingerprint,
                        'awaiting_peer' if kind == 'peer_task' else 'queued', now, now, now))
            self.audit(db, 'job_created', {'id': job_id, 'kind': kind})
        return {'id': job_id, 'duplicate': False}

    def jobs(self, peer=None, limit=100):
        with self.lock:
            if peer:
                rows = self.db.execute('SELECT * FROM jobs WHERE peer=? ORDER BY created DESC LIMIT ?', (peer, limit)).fetchall()
            else:
                rows = self.db.execute('SELECT * FROM jobs ORDER BY created DESC LIMIT ?', (limit,)).fetchall()
        return [self.decode_job(r) for r in rows]

    @staticmethod
    def decode_job(row):
        result = dict(row)
        for key in ('payload', 'result', 'review'):
            result[key] = json.loads(result[key]) if result[key] else None
        return result

    def job(self, job_id):
        with self.lock:
            row = self.db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
        if not row: raise Fault(404, 'job_not_found')
        return self.decode_job(row)

    def receive_result(self, peer, job_id, result):
        identifier(job_id)
        if not isinstance(result, dict) or len(encode(result).encode()) > MAX_BODY // 2:
            raise Fault(422, 'invalid_result')
        with self.tx() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
            if not row or row['peer'] != peer: raise Fault(404, 'job_not_found')
            if not db.execute('SELECT 1 FROM peers WHERE id=? AND active=1', (peer,)).fetchone():
                raise Fault(403, 'peer_revoked')
            if row['result'] is not None:
                if row['result'] == encode(result): return {'id': job_id, 'duplicate': True}
                raise Fault(409, 'result_conflict')
            if row['state'] != 'awaiting_peer': raise Fault(409, 'not_awaiting_peer')
            db.execute("UPDATE jobs SET state='submitted',result=?,updated=? WHERE id=?", (encode(result), self.clock(), job_id))
            self.audit(db, 'result_received', {'id': job_id, 'peer': peer, 'sha256': digest(result)})
        return {'id': job_id, 'duplicate': False, 'state': 'submitted', 'verified': False}

    def review(self, job_id, passed, evidence):
        if type(passed) is not bool: raise Fault(422, 'boolean_verdict_required')
        text(evidence, 'evidence', 5000)
        verdict = {'passed': passed, 'evidence': evidence, 'reviewer': 'operator'}
        with self.tx() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
            if not row: raise Fault(404, 'job_not_found')
            if row['review']:
                if row['review'] == encode(verdict): return {'id': job_id, 'duplicate': True}
                raise Fault(409, 'review_already_recorded')
            if row['state'] != 'submitted': raise Fault(409, 'no_result_to_review')
            if row['peer']:
                p = db.execute('SELECT weights FROM peers WHERE id=?', (row['peer'],)).fetchone()
                weights = json.loads(p[0]); x = features(json.loads(row['payload'])['task'])
                prediction = score(weights, x)
                for i, v in enumerate(x): weights[i] += .1 * (float(passed) - prediction) * v
                db.execute('UPDATE peers SET weights=?,examples=examples+1 WHERE id=?', (encode(weights), row['peer']))
            db.execute('UPDATE jobs SET state=?,review=?,updated=? WHERE id=?',
                       ('verified' if passed else 'rejected', encode(verdict), self.clock(), job_id))
            self.audit(db, 'result_reviewed', {'id': job_id, 'passed': passed})
        return {'id': job_id, 'duplicate': False, 'state': 'verified' if passed else 'rejected'}

    def claim(self):
        now = self.clock()
        with self.tx() as db:
            day = now - now % 86400
            if db.execute("SELECT count(*) FROM audit WHERE event='job_claimed' AND at>=?", (day,)).fetchone()[0] >= 100:
                return None
            # Only GET/read work is automatically retried. No uncertain remote write is replayed.
            db.execute("UPDATE jobs SET state=CASE WHEN attempts>=3 THEN 'failed' ELSE 'queued' END,error='interrupted_read' WHERE state='running' AND lease_until<?", (now,))
            row = db.execute("SELECT * FROM jobs WHERE state='queued' AND next_at<=? AND attempts<3 ORDER BY created,id LIMIT 1", (now,)).fetchone()
            if not row: return None
            db.execute("UPDATE jobs SET state='running',lease_until=?,attempts=attempts+1,updated=? WHERE id=?", (now+120, now, row['id']))
            self.audit(db, 'job_claimed', {'id': row['id']})
            result = self.decode_job(row); result['attempts'] += 1
            return result

    def finish(self, job_id, result=None, error=None):
        with self.tx() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
            if not row or row['state'] != 'running': raise Fault(409, 'job_not_running')
            state = 'submitted' if error is None else 'failed'
            next_at = self.clock()
            if error and row['attempts'] < 3 and error in ('dns_resolution_failed', 'transport_failed', 'remote_http_429', 'remote_http_503'):
                state, next_at = 'queued', next_at + 60 * (2 ** row['attempts'])
            db.execute('UPDATE jobs SET state=?,result=?,error=?,next_at=?,lease_until=0,updated=? WHERE id=?',
                       (state, encode(result) if result is not None else None, error, next_at, self.clock(), job_id))
            self.audit(db, 'job_finished', {'id': job_id, 'state': state, 'error': error})

    def ingest(self, source, event_id, body):
        text(source, 'source', 1000); text(event_id, 'event', 200)
        if len(encode(body).encode()) > MAX_BODY: raise Fault(413, 'event_too_large')
        with self.tx() as db:
            # An edit is a new version, not a duplicate or a new task.
            n = db.execute('INSERT OR IGNORE INTO inbox VALUES(?,?,?,?,?)',
                           (source, event_id, digest(body), encode(body), self.clock())).rowcount
        return bool(n)

    def inbox(self):
        with self.lock:
            rows = self.db.execute('SELECT * FROM inbox ORDER BY seen DESC LIMIT 100').fetchall()
        return [dict(r, body=json.loads(r['body'])) for r in rows]

    def ranking(self, query):
        x = features(text(query, 'query', 2000))
        with self.lock: rows = self.db.execute('SELECT * FROM peers WHERE active=1').fetchall()
        return sorted([{'peer': r['id'], 'score': score(json.loads(r['weights']), x),
                        'reviewed_examples': r['examples'], 'scope': r['scope'],
                        'availability': 'not_proven_by_this_score'} for r in rows], key=lambda r: -r['score'])

    def status(self):
        with self.lock:
            states = dict(self.db.execute('SELECT state,count(*) FROM jobs GROUP BY state'))
            examples = self.db.execute('SELECT coalesce(sum(examples),0) FROM peers').fetchone()[0]
            peers = self.db.execute('SELECT count(*) FROM peers WHERE active=1').fetchone()[0]
            incoming = self.db.execute('SELECT count(*) FROM inbox').fetchone()[0]
        room = self.private.get('room', {})
        return {'version': VERSION, 'node_id': self.private['node_id'], 'jobs': states,
                'authorized_peer_records': peers, 'reviewed_training_examples': examples,
                'inbox_versions': incoming, 'room_identity_saved': bool(room.get('secret')),
                'room_membership_receipt': self.meta('room_membership'),
                'live_external_nodes_proven': False, 'general_purpose_llm': False}

def features(query):
    x = [0.0] * 256
    for word in re.findall(r'\w+', query.lower()):
        raw = hashlib.sha256(word.encode()).digest()
        x[raw[0]] += 1 if raw[1] & 1 else -1
    norm = math.sqrt(sum(v*v for v in x)) or 1
    return [v/norm for v in x]

def score(w, x):
    z = max(-30, min(30, sum(a*b for a, b in zip(w, x))))
    return 1 / (1 + math.exp(-z))

class Room:
    def __init__(self, store, network=None):
        self.store, self.net = store, network or Network()

    def request(self, origin, path, method='GET', body=None, secret=None):
        origin = origin_url(origin)
        headers = {'Origin': origin}
        if secret: headers['Authorization'] = 'Bearer ' + secret
        result = self.net.request(origin + path, method, body, headers)
        if not isinstance(result['json'], dict): raise NetworkFault(502, 'invalid_room_response')
        return result['json']

    def initialize(self, origin, name='Synapse / HarrowHaus'):
        origin = origin_url(origin); text(name, 'name', 80)
        existing = self.store.private.get('room', {})
        if existing.get('secret'):
            if existing['origin'] != origin: raise Fault(409, 'identity_origin_mismatch')
            return {'identity_id': existing['identity_id'], 'reused': True}
        if self.store.meta('identity_creation'):
            raise Fault(409, 'identity_creation_uncertain_import_or_reconcile_do_not_remint')
        # Persist intent before a non-idempotent third-party POST.
        self.store.meta('identity_creation', {'state': 'attempt_started', 'at': self.store.clock()})
        try:
            value = self.request(origin, '/api/agent-identities', 'POST', {'displayName': name})
            identity = identifier(value.get('identityId')); secret = text(value.get('secret'), 'secret', 500)
            if not secret.startswith('pri_'): raise Fault(502, 'invalid_identity_response')
            self.store.private['room'] = {'origin': origin, 'identity_id': identity,
                                          'secret': secret, 'display_name': name}
            self.store.save_private()
            self.store.meta('identity_creation', {'state': 'saved', 'identity_id': identity})
            return {'identity_id': identity, 'reused': False}
        except Fault as e:
            self.store.meta('identity_creation', {'state': 'uncertain', 'error': e.code})
            raise

    def join(self, invite, expected_room):
        c = self.store.private.get('room', {})
        if not c.get('secret'): raise Fault(409, 'create_or_import_identity_first')
        identifier(expected_room); text(invite, 'invite', 2000)
        if invite.startswith('https://'):
            u = urlsplit(invite)
            if origin_url(u.scheme+'://'+u.netloc) != c['origin'] or not u.fragment.startswith('join/'):
                raise Fault(422, 'invitation_origin_or_fragment_mismatch')
            invite = u.fragment[5:]
        preview = self.request(c['origin'], '/api/share-links/preview', 'POST', {'linkToken': invite})
        if preview.get('room', {}).get('id') != expected_room:
            raise Fault(409, 'wrong_room_preview')
        link = preview.get('link', {})
        if link.get('status') != 'active' or link.get('permissions') != []:
            raise Fault(409, 'unexpected_invitation_scope')
        c['pending_room_id'] = expected_room
        self.store.save_private()
        value = self.request(c['origin'], '/api/share-links/join-agent', 'POST',
                             {'linkToken': invite, 'displayName': c['display_name']}, c['secret'])
        if value.get('roomId') != expected_room or value.get('identityId') != c['identity_id'] or value.get('memberId') != c['identity_id']:
            raise Fault(502, 'join_identity_mismatch')
        return self.read()

    def read(self):
        c = self.store.private.get('room', {})
        room_id = c.get('pending_room_id') or c.get('room_id')
        if not room_id or not all(c.get(k) for k in ('origin', 'secret', 'identity_id')):
            raise Fault(409, 'room_not_configured')
        s = self.request(c['origin'], '/api/rooms/' + quote(room_id, safe=''), secret=c['secret'])
        state = s.get('state', {})
        if not isinstance(state, dict): raise Fault(502, 'invalid_room_state')
        members = state.get('members', {})
        member = members.get(c['identity_id']) if isinstance(members, dict) else None
        if (s.get('roomId') != room_id or s.get('viewerId') != c['identity_id'] or
                not isinstance(member, dict) or member.get('id') != c['identity_id'] or
                member.get('kind') != 'agent' or member.get('active') is not True or
                any(s.get(k) is not None for k in ('viewerAccountId', 'viewerAuthEpoch', 'viewerSessionBinding', 'viewerSessionRevision'))):
            raise Fault(403, 'membership_not_verified')
        receipt = {'room_id': room_id, 'identity_id': c['identity_id'],
                   'checked_at': self.store.clock(), 'access': 'verified', 'write': 'not_tested',
                   'execution': 'not_tested', 'origin': c['origin']}
        messages = state.get('messages', [])
        if not isinstance(messages, list): raise Fault(502, 'invalid_message_list')
        added = 0
        for m in messages:
            if isinstance(m, dict) and isinstance(m.get('id'), str):
                added += self.store.ingest(c['origin']+'/'+room_id, m['id'], m)
        c['room_id'] = room_id
        c.pop('pending_room_id', None)
        self.store.save_private()
        self.store.meta('room_membership', receipt)
        # Room content stays in the private database, not public logs or status.
        return dict(receipt, new_message_versions=added, snapshot_only=True)

class Worker:
    def __init__(self, store, network=None):
        self.store, self.net = store, network or Network()
        self.room = Room(store, self.net)
        self.stop = threading.Event()

    def once(self):
        job = self.store.claim()
        if not job: return False
        try:
            if job['kind'] == 'public_read':
                r = self.net.request(job['payload']['url'])
                result = {k:v for k,v in r.items() if k != 'json'}
            elif job['kind'] == 'room_read':
                with self.store.lock: result = self.room.read()
            else: raise Fault(422, 'unknown_local_job')
            self.store.finish(job['id'], result=result)
        except Fault as e:
            self.store.finish(job['id'], error=e.code)
        return True

    def run(self):
        while not self.stop.is_set():
            try:
                # Once a room has been joined, schedule at most one read per UTC hour.
                # This does not send replies or interpret messages as instructions.
                if self.store.private.get('room', {}).get('room_id'):
                    hour = int(self.store.clock() // 3600)
                    self.store.enqueue('room-poll-' + str(hour), 'room_read', {})
                self.once()
            except Exception as e:
                self.store.meta('worker_fatal', {'type': type(e).__name__})
                self.stop.set()
                if hasattr(self, 'on_fatal'): self.on_fatal()
                return
            self.stop.wait(2)

class Server(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, addr, handler):
        self.slots = threading.BoundedSemaphore(16)
        super().__init__(addr, handler)
    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request); return
        try: super().process_request(request, client_address)
        except BaseException:
            self.slots.release(); raise
    def process_request_thread(self, request, client_address):
        try: super().process_request_thread(request, client_address)
        finally: self.slots.release()


def handler(store):
    class API(BaseHTTPRequestHandler):
        server_version = 'SynapseWorker/' + VERSION
        def setup(self):
            super().setup(); self.connection.settimeout(10)
        def log_message(self, *_): pass
        def send(self, status, value):
            raw = encode(value).encode()
            self.send_response(status)
            for k,v in {'Content-Type':'application/json; charset=utf-8', 'Content-Length':str(len(raw)),
                        'Cache-Control':'no-store', 'X-Content-Type-Options':'nosniff'}.items(): self.send_header(k,v)
            self.end_headers()
            try: self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError): pass
        def handle_api(self, method):
            try:
                path = urlsplit(self.path).path
                if method == 'GET' and path == '/health':
                    return self.send(503 if store.meta('worker_fatal') else 200, {'ok': not bool(store.meta('worker_fatal')), 'version': VERSION})
                if method == 'GET' and path == '/.well-known/synapse.json':
                    return self.send(200, {'name':'Synapse', 'node_id':store.private['node_id'],
                        'protocol':'synapse-task-exchange/1', 'a2a_compatible':False,
                        'auth':'per-peer bearer; operator enrollment required',
                        'peer_tasks':'/v1/peer/tasks', 'peer_results':'/v1/peer/result'})
                auth = self.headers.get('Authorization', '')
                if not auth.startswith('Bearer '): raise Fault(401, 'unauthorized')
                role, peer = store.authenticate(auth[7:])
                if role != 'admin' and path not in ('/v1/peer/tasks', '/v1/peer/result'):
                    raise Fault(403, 'admin_required')
                b = {}
                if method == 'POST':
                    if self.headers.get('Transfer-Encoding'): raise Fault(400, 'transfer_encoding_not_supported')
                    if len(self.headers.get_all('Content-Length', [])) != 1: raise Fault(411, 'content_length_required')
                    if self.headers.get_content_type() != 'application/json': raise Fault(415, 'json_required')
                    n = int(self.headers.get('Content-Length', '-1'))
                    if n < 0 or n > MAX_BODY: raise Fault(413, 'body_too_large')
                    b = json.loads(self.rfile.read(n))
                    if not isinstance(b, dict): raise Fault(422, 'json_object_required')
                if method == 'GET':
                    routes = {'/v1/status':store.status, '/v1/jobs':store.jobs, '/v1/inbox':store.inbox}
                    if path in routes: return self.send(200, routes[path]())
                    if path == '/v1/peer/tasks' and role == 'peer': return self.send(200, store.jobs(peer=peer))
                if method == 'POST':
                    if path in ('/v1/room/init', '/v1/room/join', '/v1/room/check'):
                        with store.lock:
                            room = Room(store)
                            if path == '/v1/room/init': result = room.initialize(b.get('origin', 'https://room.trydemigod.com'))
                            elif path == '/v1/room/join': result = room.join(b.get('invite'), b.get('room'))
                            else: result = room.read()
                        return self.send(200, result)
                    if path == '/v1/peers': return self.send(201, store.peer_add(b.get('id'), b.get('scope'), b.get('evidence')))
                    if path == '/v1/peers/revoke': return self.send(200, store.peer_revoke(identifier(b.get('id'))))
                    if path == '/v1/jobs': return self.send(200, store.enqueue(b.get('id'), b.get('kind'), b.get('payload'), b.get('peer')))
                    if path == '/v1/peer/result' and role == 'peer': return self.send(200, store.receive_result(peer, b.get('id'), b.get('result')))
                    if path == '/v1/review': return self.send(200, store.review(identifier(b.get('id')), b.get('passed'), b.get('evidence')))
                    if path == '/v1/rank': return self.send(200, store.ranking(b.get('query')))
                    if path == '/v1/inbox/import':
                        return self.send(200, {'new_version': store.ingest(b.get('source'), b.get('event_id'), b.get('body'))})
                raise Fault(404, 'not_found')
            except Fault as e: self.send(e.status, {'error': e.code})
            except (ValueError, TypeError, OverflowError): self.send(422, {'error':'invalid_input'})
            except Exception: self.send(500, {'error':'internal_error'})
        def do_GET(self): self.handle_api('GET')
        def do_POST(self): self.handle_api('POST')
    return API


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', default=os.environ.get('SYNAPSE_DATA_DIR', str(Path.home()/'.synapse-worker')))
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('init', 'status', 'once', 'room-check'): sub.add_parser(name)
    serve = sub.add_parser('serve'); serve.add_argument('--host', default='127.0.0.1'); serve.add_argument('--port', type=int, default=int(os.environ.get('PORT', '8080')))
    peer = sub.add_parser('peer-add'); peer.add_argument('id'); peer.add_argument('--scope', required=True); peer.add_argument('--evidence', required=True)
    queue = sub.add_parser('enqueue'); queue.add_argument('file', help='JSON {id,kind,payload,peer?}')
    ingest = sub.add_parser('import-receipt'); ingest.add_argument('file', help='JSON {source,event_id,body}')
    identity = sub.add_parser('room-init'); identity.add_argument('--origin', default='https://room.trydemigod.com')
    join = sub.add_parser('room-join'); join.add_argument('--room', required=True, help='Expected room ID; invitation is read from SYNAPSE_ROOM_INVITE, never a CLI argument')
    args = parser.parse_args(argv)
    try:
        # A Railway service must not accidentally store its state on ephemeral disk.
        if args.command == 'serve' and os.environ.get('RAILWAY_ENVIRONMENT_ID'):
            volume = os.environ.get('RAILWAY_VOLUME_MOUNT_PATH')
            if not volume or not Path(args.data).resolve().is_relative_to(Path(volume).resolve()):
                raise Fault(409, 'persistent_volume_required')
        with process_lock(args.data):
            store = Store(args.data)
            try:
                if args.command == 'init': out = {'node_id':store.private['node_id'], 'private_credentials_file':str(store.private_path), 'network_requests':0}
                elif args.command == 'status': out = store.status()
                elif args.command == 'peer-add': out = store.peer_add(args.id, args.scope, args.evidence)
                elif args.command == 'enqueue':
                    b = json.loads(Path(args.file).read_text()); out = store.enqueue(b['id'], b['kind'], b['payload'], b.get('peer'))
                elif args.command == 'import-receipt':
                    b = json.loads(Path(args.file).read_text()); out = {'new_version': store.ingest(b['source'], b['event_id'], b['body'])}
                elif args.command == 'room-init': out = Room(store).initialize(args.origin)
                elif args.command == 'room-join': out = Room(store).join(os.environ.get('SYNAPSE_ROOM_INVITE', ''), args.room)
                elif args.command == 'room-check': out = Room(store).read()
                elif args.command == 'once': out = {'ran_job': Worker(store).once()}
                elif args.command == 'serve':
                    server = Server((args.host, args.port), handler(store)); worker = Worker(store)
                    store.meta('worker_fatal', False)
                    worker.on_fatal = lambda: threading.Thread(target=server.shutdown, daemon=True).start()
                    thread = threading.Thread(target=worker.run, daemon=True); thread.start()
                    def stop(*_):
                        worker.stop.set()
                        threading.Thread(target=server.shutdown, daemon=True).start()
                    signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop)
                    print(encode({'listening':args.host, 'port':server.server_port, 'node_id':store.private['node_id']}), flush=True)
                    try: server.serve_forever()
                    finally:
                        worker.stop.set(); thread.join(timeout=20); server.server_close()
                    return 1 if store.meta('worker_fatal') else 0
                print(encode(out)); return 0
            finally: store.close()
    except (Fault, OSError, ValueError, KeyError) as e:
        print(encode({'error': e.code if isinstance(e, Fault) else type(e).__name__}), file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
