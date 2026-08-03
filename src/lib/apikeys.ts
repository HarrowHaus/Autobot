import type { Env } from "../types.js";
import { newId } from "./ids.js";

async function sha256Hex(input: string): Promise<string> {
  const data = new TextEncoder().encode(input);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function randomToken(bytes = 24): string {
  const arr = new Uint8Array(bytes);
  crypto.getRandomValues(arr);
  return Array.from(arr)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export interface IssuedApiKey {
  id: string;
  key: string; // shown to the user exactly once
  prefix: string;
}

export async function issueApiKey(db: D1Database, accountId: string): Promise<IssuedApiKey> {
  const secret = randomToken();
  const key = `ps_live_${secret}`;
  const prefix = key.slice(0, 12);
  const keyHash = await sha256Hex(key);
  const id = newId("key");

  await db
    .prepare(
      `INSERT INTO api_keys (id, account_id, key_hash, key_prefix) VALUES (?, ?, ?, ?)`
    )
    .bind(id, accountId, keyHash, prefix)
    .run();

  return { id, key, prefix };
}

export async function findAccountIdByApiKey(env: Env, key: string): Promise<string | null> {
  if (!key.startsWith("ps_live_")) return null;
  const keyHash = await sha256Hex(key);

  const row = await env.DB.prepare(
    `SELECT account_id, id FROM api_keys WHERE key_hash = ? AND revoked_at IS NULL`
  )
    .bind(keyHash)
    .first<{ account_id: string; id: string }>();

  if (!row) return null;

  // Best-effort last-used tracking; not on the critical path for correctness.
  await env.DB.prepare(`UPDATE api_keys SET last_used_at = datetime('now') WHERE id = ?`)
    .bind(row.id)
    .run();

  return row.account_id;
}
