/**
 * Minimal in-memory stand-in for KVNamespace, covering the get/put shape
 * used by src/lib/rate-limit.ts. expirationTtl is accepted but not enforced
 * (tests that care about expiry manipulate keys directly via `store`).
 */
export class FakeKV {
  store = new Map<string, string>();

  async get(key: string): Promise<string | null> {
    return this.store.get(key) ?? null;
  }

  async put(key: string, value: string, _opts?: { expirationTtl?: number }): Promise<void> {
    this.store.set(key, value);
  }
}
