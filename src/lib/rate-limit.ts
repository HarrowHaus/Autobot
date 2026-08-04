/**
 * Rate limiting is the only access control in this alpha. There is no
 * free-trial counter and no credit balance, because there are no accounts —
 * that whole system was removed rather than left dormant.
 */

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
