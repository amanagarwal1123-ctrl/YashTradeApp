import AsyncStorage from '@react-native-async-storage/async-storage';
import { api, BACKEND_URL } from './api';

/**
 * Bounded read cache for STABLE catalogue data only (products, banners, stories). Never caches carts, wishlists,
 * enquiries, rates, sessions or any customer record. Entries are keyed by backend origin + signed-in identity (role +
 * account id) so nothing crosses accounts or environments; everything is wiped on logout / identity change.
 *
 *  - in-flight de-duplication: identical concurrent GETs share one network request
 *  - memory: 5 minutes, bounded number of entries
 *  - persisted (AsyncStorage): first pages / details only, allow-listed public fields only, 24 h, used purely as an
 *    instant first paint that is revalidated immediately (stale-while-revalidate); pull-to-refresh bypasses everything
 */
const PREFIX = 'yash:cache:v1:';
const MEMORY_TTL_MS = 5 * 60 * 1000;
const PERSIST_MAX_AGE_MS = 24 * 60 * 60 * 1000;
const MEMORY_LIMIT = 60;
const PERSIST_LIMIT = 40;

type Entry = { at: number; data: any };
const memory = new Map<string, Entry>();
const inflight = new Map<string, Promise<any>>();
let identity = 'anon';

const PRODUCT_FIELDS = ['id', 'product_code', 'title', 'description', 'images', 'metal_type', 'base_metal', 'category', 'subcategory',
  'approx_weight', 'purity', 'selling_touch', 'selling_label', 'stone_weight_ct', 'stock_status', 'tags', 'video_url', 'is_new_arrival',
  'is_trending', 'is_pinned', 'storage_path', 'thumbnail_path', 'original_source_storage_path', 'post_type', 'version', 'created_at', 'updated_at'];
const BANNER_FIELDS = ['id', 'title', 'subtitle', 'image_url', 'cta_label', 'cta_type', 'cta_target'];
const STORY_FIELDS = ['id', 'title', 'image_url', 'category', 'link_type', 'link_id'];

const pick = (row: any, fields: string[]) => Object.fromEntries(fields.filter(f => row && row[f] !== undefined).map(f => [f, row[f]]));

/** Which GET paths may be cached at all. */
export const cacheable = (path: string) => /^\/(products(\?.*)?$|products\/[^/?]+$|banners$|stories$)/.test(path);
/** Persisted only for first pages and details (bounded storage); deeper pages live in memory only. */
export const persistable = (path: string) => cacheable(path) && !(path.startsWith('/products?') && /(\?|&)page=(?!1(&|$))\d+/.test(path));

/** Approved public fields only: internal, admin or customer data never reaches disk. */
export function sanitize(path: string, data: any) {
  if (path.startsWith('/products?')) return { total: data.total, page: data.page, pages: data.pages, limit: data.limit, products: (data.products || []).map((p: any) => pick(p, PRODUCT_FIELDS)) };
  if (path.startsWith('/products/')) return pick(data, PRODUCT_FIELDS);
  if (path === '/banners') return { banners: (data.banners || []).map((b: any) => pick(b, BANNER_FIELDS)) };
  if (path === '/stories') return { stories: (data.stories || []).map((s: any) => pick(s, STORY_FIELDS)) };
  return null;
}

export function setCacheIdentity(user: { id: string; role: string } | null) {
  const next = user ? `${user.role}:${user.id}` : 'anon';
  if (next !== identity) { identity = next; memory.clear(); }
}
export const cacheIdentity = () => identity;
const keyOf = (path: string) => `${PREFIX}${BACKEND_URL}:${identity}:${path}`;

function remember(key: string, data: any) {
  memory.set(key, { at: Date.now(), data });
  while (memory.size > MEMORY_LIMIT) memory.delete(memory.keys().next().value as string);
}

async function persist(key: string, path: string, data: any) {
  const safe = sanitize(path, data);
  if (!safe) return;
  try {
    await AsyncStorage.setItem(key, JSON.stringify({ at: Date.now(), data: safe }));
    const index = JSON.parse((await AsyncStorage.getItem(`${PREFIX}index`)) || '[]') as string[];
    const next = [key, ...index.filter(k => k !== key)];
    if (next.length > PERSIST_LIMIT) await AsyncStorage.multiRemove(next.splice(PERSIST_LIMIT));
    await AsyncStorage.setItem(`${PREFIX}index`, JSON.stringify(next));
  } catch { /* persistence is best-effort */ }
}

async function readPersisted(key: string) {
  try {
    const raw = await AsyncStorage.getItem(key);
    if (!raw) return null;
    const entry = JSON.parse(raw) as Entry;
    if (Date.now() - entry.at > PERSIST_MAX_AGE_MS) { await AsyncStorage.removeItem(key); return null; }
    return entry.data;
  } catch { return null; }
}

/** Fresh-enough memory hit, otherwise ONE shared network request. `force` (pull-to-refresh) bypasses every cache. */
export function cachedGet(path: string, { force = false } = {}): Promise<any> {
  if (!cacheable(path)) return api.get(path);
  const key = keyOf(path);
  if (!force) {
    const hit = memory.get(key);
    if (hit && Date.now() - hit.at < MEMORY_TTL_MS) return Promise.resolve(hit.data);
    const pending = inflight.get(key);
    if (pending) return pending;
  }
  const promise = api.get(path).then(data => {
    remember(key, data);
    if (persistable(path)) persist(key, path, data);
    return data;
  }).finally(() => { if (inflight.get(key) === promise) inflight.delete(key); });
  inflight.set(key, promise);
  return promise;
}

/**
 * Stale-while-revalidate: `onData(stale=true)` is called at once with a persisted copy when there is one, then the
 * network result arrives with `stale=false`. Returns the network promise so callers can await completion/errors.
 */
export async function swrGet(path: string, onData: (data: any, stale: boolean) => void, { force = false } = {}): Promise<any> {
  const key = keyOf(path);
  const hit = memory.get(key);
  if (!force && hit && Date.now() - hit.at < MEMORY_TTL_MS) { onData(hit.data, false); return hit.data; }
  const started = identity;
  if (!force && persistable(path)) {
    const persisted = await readPersisted(key);
    if (persisted && identity === started) onData(persisted, true);
  }
  const data = await cachedGet(path, { force });
  if (identity === started) onData(data, false);
  return data;
}

/** Called on logout, account deletion, identity or permission change: memory, in-flight handles and disk copies go. */
export async function clearCaches() {
  memory.clear();
  inflight.clear();
  try {
    const keys = await AsyncStorage.getAllKeys();
    const ours = keys.filter(k => k.startsWith(PREFIX));
    if (ours.length) await AsyncStorage.multiRemove(ours);
  } catch { /* best-effort */ }
}

export const cacheStats = () => ({ memory: memory.size, inflight: inflight.size });
