// utils/cache.ts

export interface CacheEntry<T> {
  value: T;
  expiresAt: number;
}

export class TTLCache<K, V> {
  private ttl: number;
  private store: Map<K, CacheEntry<V>> = new Map();

  constructor(ttlMs: number) {
    this.ttl = ttlMs;
  }

  get(key: K): V | undefined {
    const entry = this.store.get(key);
    if (!entry) return undefined;
    if (Date.now() > entry.expiresAt) {
      this.store.delete(key);
      return undefined;
    }
    return entry.value;
  }

  set(key: K, value: V): void {
    this.store.set(key, { value, expiresAt: Date.now() + this.ttl });
  }

  has(key: K): boolean {
    const entry = this.store.get(key);
    return !!entry && Date.now() <= entry.expiresAt;
  }

  clear(): void {
    this.store.clear();
  }

  delete(key: K): void {
    this.store.delete(key);
  }

  size(): number {
    return this.store.size;
  }
}
