/** One free conversion per IP+email, tracked in KV. Not perfect anti-abuse, but
 * enough friction for a low-stakes free trial without adding auth to try it. */
export async function consumeFreeTrial(kv: KVNamespace, ip: string, email: string): Promise<boolean> {
  const key = `trial:${ip}:${email || "anon"}`;
  const used = await kv.get(key);
  if (used) return false;
  await kv.put(key, "1", { expirationTtl: 60 * 60 * 24 * 365 });
  return true;
}
