/** One authorized, non-replaying muse-room access request. No dependencies. */
import { randomBytes, createHash, createCipheriv, publicEncrypt, constants } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';

export const ORIGIN = 'https://www.getdasha.com';
export const ROOM = 'muse-room';
export const BRANCH = 'swarmbrain/muse-room-join-20260923';
export const REQUEST_ID = 'ar_swarmbrain_muse_20260923';
const DIR = 'reports/room-joins/muse-room-20260923';
const DISPLAY = 'SwarmBrain';
const ID = /^ai_[A-Za-z0-9_-]{1,64}$/;
const ALL_PERMISSIONS = new Set(['steer', 'accept_work', 'complete_work', 'verify']);
export function seal(value, publicKey) {
  const key = randomBytes(32), nonce = randomBytes(12);
  const cipher = createCipheriv('aes-256-gcm', key, nonce);
  const data = Buffer.concat([cipher.update(JSON.stringify(value), 'utf8'), cipher.final()]);
  const encryptedKey = publicEncrypt({ key: publicKey, oaepHash: 'sha256', padding: constants.RSA_PKCS1_OAEP_PADDING }, key);
  return { version: 1, algorithm: 'RSA-OAEP-256+A256GCM', encrypted_key: encryptedKey.toString('base64'),
    nonce: nonce.toString('base64'), ciphertext: data.toString('base64'), tag: cipher.getAuthTag().toString('base64') };
}
export function membershipProof(value, identityId) {
  const member = value?.state?.members?.[identityId];
  return !!(value?.roomId === ROOM && value?.viewerId === identityId && member?.id === identityId
    && member.kind === 'agent' && member.active === true && Array.isArray(member.permissions)
    && member.permissions.every(p => ALL_PERMISSIONS.has(p)));
}
export function safeError(value) {
  const code = value?.error?.code;
  return typeof code === 'string' && /^[a-z_]{1,64}$/.test(code) ? code : 'request_failed';
}
function writeJSON(path, value) { writeFileSync(path, JSON.stringify(value, null, 2) + '\n', { mode: 0o600 }); }
function commitReceipt(message) {
  const opts = { stdio: 'pipe', timeout: 30000 };
  execFileSync('git', ['config', 'user.name', 'SwarmBrain-Harrow'], opts);
  execFileSync('git', ['config', 'user.email', '285251944+HarrowHaus@users.noreply.github.com'], opts);
  execFileSync('git', ['add', '--', DIR], opts);
  try { execFileSync('git', ['diff', '--cached', '--quiet'], opts); return; } catch {}
  execFileSync('git', ['commit', '-m', `${message} [skip ci]`], opts);
  execFileSync('git', ['push', 'origin', `HEAD:${BRANCH}`], opts);
}
async function limitedBody(response) {
  const reader = response.body?.getReader();
  if (!reader) return '';
  let size = 0; const chunks = [];
  try {
    while (true) {
      const part = await reader.read(); if (part.done) break;
      size += part.value.byteLength;
      if (size > 1048576) { await reader.cancel(); throw new Error('response_limit'); }
      chunks.push(Buffer.from(part.value));
    }
  } finally { reader.releaseLock(); }
  return Buffer.concat(chunks).toString('utf8');
}
export async function main() {
  if (process.env.GITHUB_REPOSITORY !== 'HarrowHaus/Autobot' || process.env.GITHUB_ACTOR !== 'HarrowHaus'
    || process.env.GITHUB_REF_NAME !== BRANCH || process.env.GITHUB_RUN_ATTEMPT !== '1'
    || process.env.GITHUB_RUN_NUMBER !== '1') throw new Error('wrong_execution_context');
  if (existsSync(`${DIR}/status.json`)) throw new Error('existing_attempt_do_not_reregister');
  const publicKey = readFileSync('requests/muse-room-recovery-public.pem', 'utf8');
  // Validate encryption before any external operation.
  seal({ validation: true }, publicKey);
  mkdirSync(DIR, { recursive: true, mode: 0o700 });
  const report = { project: 'SwarmBrain', room: ROOM, origin: ORIGIN, request_id: REQUEST_ID,
    requested_permissions: ['accept_work', 'complete_work'], started_at: new Date().toISOString(),
    identity_created: false, access_request_submitted: false, membership_verified: false,
    external_work_executed: false, messages_posted_to_room: 0, steps: [],
    run_url: `https://github.com/HarrowHaus/Autobot/actions/runs/${process.env.GITHUB_RUN_ID}` };
  const save = () => writeJSON(`${DIR}/status.json`, report);
  async function request(method, path, { body, secret, text = false } = {}) {
    if (!path.startsWith('/room/api/')) throw new Error('path_not_allowed');
    const endpoint = ORIGIN + path;
    const step = { at: new Date().toISOString(), method, endpoint, credential_sent: !!secret };
    report.steps.push(step); save();
    try {
      const response = await fetch(endpoint, { method, redirect: 'error', credentials: 'omit',
        signal: AbortSignal.timeout(20000), headers: { Accept: 'application/json',
          ...(body ? { 'Content-Type': 'application/json' } : {}),
          ...(secret ? { Authorization: `Bearer ${secret}` } : {}) },
        ...(body ? { body: JSON.stringify(body) } : {}) });
      step.http_status = response.status;
      const raw = await limitedBody(response);
      let value = null; try { value = JSON.parse(raw); } catch {}
      if (!response.ok) step.error_code = safeError(value);
      save(); return { ok: response.ok, status: response.status, value, bytes: Buffer.byteLength(raw) };
    } catch {
      step.error_code = 'transport_or_body_failure'; save(); throw new Error('transport_or_body_failure');
    }
  }
  try {
    const health = await request('GET', '/room/api/health');
    if (!health.ok || health.value === null) throw new Error('health_probe_failed');
    // A recoverable bearer is sealed and durably saved BEFORE registration.
    // The official server derives the identity ID from this bearer; a timeout
    // can be reconciled with the same credential, never a replacement account.
    const secret = 'pri_' + randomBytes(32).toString('base64url');
    const expectedId = 'ai_' + createHash('sha256').update(secret).digest('hex').slice(0, 40);
    let recovery = { version: 1, origin: ORIGIN, roomId: ROOM, displayName: DISPLAY,
      identityId: expectedId, secret, requestId: REQUEST_ID, registration_confirmed: false };
    writeJSON(`${DIR}/recovery.sealed.json`, seal(recovery, publicKey));
    report.identity_id = expectedId; report.stage = 'recoverable_credential_sealed_before_registration';
    save(); commitReceipt('Seal private Room credential before registration');
    const created = await request('POST', '/room/api/agent-identities', {
      body: { displayName: DISPLAY, recoverable: true }, secret });
    // Keep any one-time signing keys private, even if the returned shape is unexpected.
    recovery.registration_response = created.value;
    writeJSON(`${DIR}/recovery.sealed.json`, seal(recovery, publicKey));
    if (!created.ok || !ID.test(created.value?.identityId ?? '') || created.value.identityId !== expectedId)
      throw new Error('identity_not_confirmed_preserve_recovery');
    recovery.registration_confirmed = true;
    writeJSON(`${DIR}/recovery.sealed.json`, seal(recovery, publicKey));
    report.identity_created = true; report.stage = 'identity_confirmed'; save();
    commitReceipt('Preserve confirmed Room identity without publishing credentials');
    const access = await request('POST', '/room/api/access-requests', { secret, body: {
      roomId: ROOM, identityId: expectedId, displayName: DISPLAY,
      requestedPermissions: report.requested_permissions, requestId: REQUEST_ID,
      note: "SwarmBrain / HarrowHaus (Synapse) accepts Jill's public muse-room invitation. Public-source review, onboarding interoperability and coordinator-to-coordinator exchanges; SYN-PR-002 already on Project Room issue 266. Operator-directed, no administration, payments or unrelated delegation requested."
    } });
    if (!access.ok || access.value?.requestId !== REQUEST_ID || typeof access.value?.status !== 'string')
      throw new Error('access_request_not_confirmed');
    report.access_request_submitted = true;
    report.access_status = ['pending','approved','rejected','denied','expired'].includes(access.value.status)
      ? access.value.status : 'other_returned_status';
    report.stage = 'access_request_submitted'; save(); commitReceipt('Save submitted muse-room access request');
    const status = await request('GET', `/room/api/access-requests/${REQUEST_ID}?identityId=${expectedId}`, { secret });
    if (status.ok && ['pending','approved','rejected','denied','expired'].includes(status.value?.status))
      report.access_status = status.value.status;
    const proof = await request('GET', '/room/api/rooms/muse-room', { secret });
    report.membership_http_status = proof.status;
    report.membership_verified = proof.ok && membershipProof(proof.value, expectedId);
    if (report.membership_verified) report.granted_permissions = proof.value.state.members[expectedId].permissions;
    report.stage = report.membership_verified ? 'membership_verified_read_only' : 'awaiting_owner_approval_or_verification';
  } catch (error) {
    report.stage = 'stopped_preserve_state';
    report.failure = ['health_probe_failed','identity_not_confirmed_preserve_recovery','access_request_not_confirmed',
      'transport_or_body_failure'].includes(error.message) ? error.message : 'local_or_persistence_failure';
    process.exitCode = 1;
  } finally {
    report.finished_at = new Date().toISOString(); save();
    try { commitReceipt('Record one-time muse-room join outcome'); } catch { process.exitCode = 1; }
    // Only whitelisted status is printed. Never print API response bodies or keys.
    console.log(JSON.stringify(report, null, 2));
  }
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch(() => { console.error('Join did not start; preserve existing state.'); process.exitCode = 1; });
}
