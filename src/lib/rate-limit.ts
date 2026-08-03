/**
 * Free-trial gate: one free conversion per IP+email, tracked in KV. The
 * caller is responsible for checking/marking this at the right point in
 * the flow — hasUsedFreeTrial() is a read-only peek, markFreeTrialUsed() is
 * the mutation, and the mutation must only happen after a conversion has
 * been fully validated (see /convert in index.ts). Not perfect anti-abuse,
 * but enough friction for a free trial without adding auth to try it.
 */
function trialKey(ip: string, email: string): string {
  return `trial:${ip}:${email || "anon"}`;
}

export async function hasUsedFreeTrial(kv: KVNamespace, ip: string, email: string): Promise<boolean> {
  return (await kv.get(trialKey(ip, email))) !== null;
}

export async function markFreeTrialUsed(kv: KVNamespace, ip: string, email: string): Promise<void> {
  await kv.put(trialKey(ip, email), "1", { expirationTtl: 60 * 60 * 24 * 365 });
}

export interface RateLimitResult {
  allowed: boolean;
  limit: number;
  remaining: number;
}

/**
 * Fixed-window rate limit per (route, IP). Uses a plain KV get/increment/put
 * rather than a strongly-consistent counter — under concurrent requests a
 * client could squeak slightly over the limit, which is an acceptable
 * trade-off for an abuse-prevention control (not a financial calculation).
 */
export async function checkRateLimit(
  kv: KVNamespace,
  routeKey: string,
  ip: string,
  limit: number,
  windowSeconds: number
): Promise<RateLimitResult> {
  const bucket = Math.floor(Date.now() / (windowSeconds * 1000));
  const key = `ratelimit:${routeKey}:${ip}:${bucket}`;
  const current = Number((await kv.get(key)) ?? "0");

  if (current >= limit) {
    return { allowed: false, limit, remaining: 0 };
  }

  await kv.put(key, String(current + 1), { expirationTtl: windowSeconds + 5 });
  return { allowed: true, limit, remaining: limit - current - 1 };
}
