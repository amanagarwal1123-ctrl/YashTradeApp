/**
 * Bounded catalogue cache: de-duplication, TTL, force bypass, identity separation, wipe on logout, and the session
 * epoch guard that stops a slow request from restoring the previous account's data.
 */
jest.mock('@react-native-async-storage/async-storage', () => require('@react-native-async-storage/async-storage/jest/async-storage-mock'));
jest.mock('expo-constants', () => ({ __esModule: true, default: { expoConfig: { extra: { backendUrl: 'https://unit.test' } } } }));
jest.mock('expo-secure-store', () => ({ getItemAsync: jest.fn(async () => null), setItemAsync: jest.fn(async () => {}), deleteItemAsync: jest.fn(async () => {}) }));

import AsyncStorage from '@react-native-async-storage/async-storage';
import { api, endSession, SessionChangedError } from '../api';
import { cachedGet, cacheable, clearCaches, persistable, sanitize, setCacheIdentity, swrGet, cacheStats } from '../dataCache';

type Deferred = { resolve: (v: any) => void; reject: (e: any) => void };
let pending: Deferred[] = [];
const fetchMock = jest.fn();

function jsonResponse(body: any, status = 200) {
  return { ok: status < 400, status, json: async () => body } as any;
}

beforeEach(async () => {
  pending = [];
  fetchMock.mockReset();
  fetchMock.mockImplementation(() => new Promise((resolve, reject) => { pending.push({ resolve: (v) => resolve(jsonResponse(v)), reject }); }));
  (global as any).fetch = fetchMock;
  await clearCaches();
  setCacheIdentity({ id: 'u1', role: 'customer' });
});

const flush = () => new Promise(r => setTimeout(r, 0));

describe('dataCache', () => {
  it('only stable catalogue paths are cacheable; carts, wishlists and sessions never are', () => {
    expect(cacheable('/products?metal_type=silver&page=1&limit=20')).toBe(true);
    expect(cacheable('/products/abc')).toBe(true);
    expect(cacheable('/banners')).toBe(true);
    expect(cacheable('/stories')).toBe(true);
    for (const p of ['/cart/count', '/wishlist', '/auth/me', '/requests', '/rates/latest', '/customers', '/products/abc/photos']) expect(cacheable(p)).toBe(false);
    expect(persistable('/products?metal_type=gold&page=1&limit=20')).toBe(true);
    expect(persistable('/products?metal_type=gold&page=3&limit=20')).toBe(false);
  });

  it('persists only approved public fields', () => {
    const safe = sanitize('/products?page=1', { total: 1, page: 1, pages: 1, products: [{ id: 'p', title: 'Ring', thumbnail_path: 't', views: 99, original_filename: 'secret.jpg', batch_id: 'b', source_upload_id: 'j' }] });
    expect(safe).not.toBeNull();
    expect(safe!.products[0]).toEqual({ id: 'p', title: 'Ring', thumbnail_path: 't' });
    expect(sanitize('/banners', { banners: [{ id: 'b', title: 'x', image_url: '/api/files/a', created_by: 'admin' }] })).toEqual({ banners: [{ id: 'b', title: 'x', image_url: '/api/files/a' }] });
    expect(sanitize('/cart/count', { count: 3 })).toBeNull();
  });

  it('identical concurrent GETs share one network request and a fresh entry is served from memory', async () => {
    const a = cachedGet('/products?page=1&limit=20');
    const b = cachedGet('/products?page=1&limit=20');
    await flush();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(cacheStats().inflight).toBe(1);
    pending[0].resolve({ products: [{ id: 'p1', title: 'Ring' }], total: 1, page: 1, pages: 1 });
    expect((await a).products[0].id).toBe('p1');
    expect((await b).products[0].id).toBe('p1');
    expect(await cachedGet('/products?page=1&limit=20')).toEqual(await a);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    // pull-to-refresh bypasses memory and disk
    const forced = cachedGet('/products?page=1&limit=20', { force: true });
    await flush();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    pending[1].resolve({ products: [{ id: 'p2', title: 'Chain' }], total: 1, page: 1, pages: 1 });
    expect((await forced).products[0].id).toBe('p2');
  });

  it('stale-while-revalidate paints the persisted copy first, then the network copy', async () => {
    const first = cachedGet('/banners');
    await flush();
    pending[0].resolve({ banners: [{ id: 'b1', title: 'Old' }] });
    await first;
    await flush();
    const keys = await AsyncStorage.getAllKeys();
    expect(keys.some(k => k.startsWith('yash:cache:v1:https://unit.test:customer:u1:/banners'))).toBe(true);
    // new process: memory is empty (simulate by switching identity away and back)
    setCacheIdentity(null); setCacheIdentity({ id: 'u1', role: 'customer' });
    const seen: [string, boolean][] = [];
    const done = swrGet('/banners', (data, stale) => seen.push([data.banners[0].title, stale]));
    await flush(); await flush();
    expect(seen).toEqual([['Old', true]]);
    pending[1].resolve({ banners: [{ id: 'b1', title: 'New' }] });
    await done;
    expect(seen).toEqual([['Old', true], ['New', false]]);
  });

  it('accounts and roles never share entries; logout wipes memory and disk', async () => {
    const a = cachedGet('/products/p1');
    await flush();
    pending[0].resolve({ id: 'p1', title: 'Ring' });
    await a; await flush();
    setCacheIdentity({ id: 'u2', role: 'admin' });
    const b = cachedGet('/products/p1');
    await flush();
    expect(fetchMock).toHaveBeenCalledTimes(2); // u2 does not see u1's copy
    pending[1].resolve({ id: 'p1', title: 'Ring (admin view)' });
    await b;
    expect((await AsyncStorage.getAllKeys()).filter(k => k.startsWith('yash:cache:')).length).toBeGreaterThanOrEqual(2);
    await clearCaches();
    expect((await AsyncStorage.getAllKeys()).filter(k => k.startsWith('yash:cache:'))).toEqual([]);
    expect(cacheStats()).toEqual({ memory: 0, inflight: 0 });
  });

  it('a response that started before logout / account switch is discarded and never cached', async () => {
    const slow = cachedGet('/products?page=1&limit=20');
    await flush();
    endSession(); // logout or a different account signing in
    await clearCaches();
    setCacheIdentity({ id: 'u2', role: 'customer' });
    pending[0].resolve({ products: [{ id: 'from-old-account' }], total: 1, page: 1, pages: 1 });
    await expect(slow).rejects.toBeInstanceOf(SessionChangedError);
    await flush();
    expect(cacheStats().memory).toBe(0);
    expect((await AsyncStorage.getAllKeys()).filter(k => k.startsWith('yash:cache:'))).toEqual([]);
    // the new account fetches its own copy
    const fresh = api.get('/products?page=1&limit=20');
    await flush();
    pending[1].resolve({ products: [{ id: 'from-new-account' }] });
    expect((await fresh).products[0].id).toBe('from-new-account');
  });
});
