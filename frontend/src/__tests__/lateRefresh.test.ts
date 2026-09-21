import { Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';

/** F01 regression (R01-B / R00-C): a refresh that was started under an older session must never persist credentials
 *  or sign the CURRENT session out when its response arrives late - after logout, after another account signed in, or
 *  as a late failure. Isolated fetch + SecureStore doubles; the real api.ts logic runs. */
const mockSecure: Record<string, string> = {};
jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(async (k: string) => mockSecure[k] ?? null),
  setItemAsync: jest.fn(async (k: string, v: string) => { mockSecure[k] = v; }),
  deleteItemAsync: jest.fn(async (k: string) => { delete mockSecure[k]; }),
}));
jest.mock('expo-constants', () => ({ __esModule: true, default: { expoConfig: { extra: { backendUrl: 'https://backend.test' } } } }));

// eslint-disable-next-line import/first
import { api, currentSession, endSession, getToken, onSessionLost, storeCredentials, setToken, SessionChangedError } from '../api';

type Pending = { resolve: (r: Response) => void };
const json = (status: number, body: any): Response => ({ status, ok: status >= 200 && status < 300, json: async () => body } as any);
let fetchQueue: Array<(url: string, init: any) => Promise<Response>> = [];
const heldRefresh = (): Pending => {
  const p: Pending = { resolve: () => {} };
  fetchQueue.push(() => new Promise<Response>(resolve => { p.resolve = resolve; }));
  return p;
};
const flush = () => new Promise(r => setTimeout(r, 0));
/** Account switch exactly as AuthContext.login does it: new generation, then generation-bound persistence. */
const signIn = (token: string, refresh: string) => { endSession(); return storeCredentials(currentSession(), token, refresh); };
const signOut = () => { endSession(); return storeCredentials(currentSession(), null, null); };

beforeEach(() => {
  (Platform as any).OS = 'android';
  for (const k of Object.keys(mockSecure)) delete mockSecure[k];
  fetchQueue = [];
  (global as any).fetch = jest.fn((url: string, init: any) => { const next = fetchQueue.shift(); if (!next) throw new Error(`unexpected fetch ${url}`); return next(url, init); });
  setToken(null);
});

async function startExpiredRequest() {
  // 1) the API call answers 401 -> api.ts starts a refresh; 2) the refresh request is held open
  fetchQueue.push(async () => json(401, { detail: 'expired' }));
  const held = heldRefresh();
  const call = api.get('/auth/me');
  await new Promise(r => setTimeout(r, 0));
  return { call, held };
}

describe('late refresh responses (F01)', () => {
  it('a normal refresh rotates and persists the credentials, then retries the call', async () => {
    setToken('jwt-A'); mockSecure.refresh_token = 'rA'; mockSecure.auth_token = 'jwt-A';
    const { call, held } = await startExpiredRequest();
    fetchQueue.push(async () => json(200, { id: 'A' }));                 // retried /auth/me
    held.resolve(json(200, { token: 'jwt-A2', refresh_token: 'rA2' }));
    await expect(call).resolves.toEqual({ id: 'A' });
    expect(getToken()).toBe('jwt-A2');
    expect(mockSecure.refresh_token).toBe('rA2');
    expect(mockSecure.auth_token).toBe('jwt-A2');
  });

  it('logout while the refresh is pending: the late success never restores account A credentials', async () => {
    setToken('jwt-A'); mockSecure.refresh_token = 'rA'; mockSecure.auth_token = 'jwt-A';
    const { call, held } = await startExpiredRequest();
    // logout finishes first (same order as AuthContext.logout)
    await signOut();
    held.resolve(json(200, { token: 'jwt-A2', refresh_token: 'rA2' }));
    await expect(call).rejects.toBeInstanceOf(SessionChangedError);
    expect(getToken()).toBeNull();
    expect(mockSecure.refresh_token).toBeUndefined();
    expect(mockSecure.auth_token).toBeUndefined();
  });

  it('another account signs in while the refresh is pending: account B credentials are kept, A is discarded', async () => {
    setToken('jwt-A'); mockSecure.refresh_token = 'rA'; mockSecure.auth_token = 'jwt-A';
    const { call, held } = await startExpiredRequest();
    await signIn('jwt-B', 'rB');
    held.resolve(json(200, { token: 'jwt-A2', refresh_token: 'rA2' }));
    await expect(call).rejects.toBeInstanceOf(SessionChangedError);
    expect(getToken()).toBe('jwt-B');
    expect(mockSecure.refresh_token).toBe('rB');
    expect(mockSecure.auth_token).toBe('jwt-B');
  });

  it('a late refresh FAILURE for the old session does not sign the new session out', async () => {
    const lost = jest.fn(); onSessionLost(lost);
    setToken('jwt-A'); mockSecure.refresh_token = 'rA';
    const { call, held } = await startExpiredRequest();
    await signIn('jwt-B', 'rB');
    held.resolve(json(401, { detail: 'revoked' }));
    await expect(call).rejects.toBeInstanceOf(SessionChangedError);
    expect(lost).not.toHaveBeenCalled();
    expect(getToken()).toBe('jwt-B');
    expect(mockSecure.refresh_token).toBe('rB');
    onSessionLost(null);
  });

  it('a genuine refresh rejection for the CURRENT session still ends it exactly once', async () => {
    const lost = jest.fn(); onSessionLost(lost);
    setToken('jwt-A'); mockSecure.refresh_token = 'rA';
    const { call, held } = await startExpiredRequest();
    held.resolve(json(401, { detail: 'revoked' }));
    await expect(call).rejects.toThrow('Session expired; please sign in again');
    expect(lost).toHaveBeenCalledTimes(1);
    expect(getToken()).toBeNull();
    expect(mockSecure.refresh_token).toBeUndefined();
    onSessionLost(null);
  });

  it('parallel calls within ONE session share a single refresh (no double rotation)', async () => {
    setToken('jwt-A'); mockSecure.refresh_token = 'rA';
    fetchQueue.push(async () => json(401, {}), async () => json(401, {}));
    const held = heldRefresh();
    const a = api.get('/one'), b = api.get('/two');
    await new Promise(r => setTimeout(r, 0));
    fetchQueue.push(async () => json(200, { r: 1 }), async () => json(200, { r: 2 }));
    held.resolve(json(200, { token: 'jwt-A2', refresh_token: 'rA2' }));
    await expect(Promise.all([a, b])).resolves.toEqual([{ r: 1 }, { r: 2 }]);
    expect((global as any).fetch).toHaveBeenCalledTimes(5);                // 2 calls + 1 refresh + 2 retries
  });
});

/** G01 (follow-up review of e34d76a): isolation must hold at EVERY asynchronous boundary - a delayed HTTP response, a
 *  delayed native storage read and a delayed native storage write - not only while the refresh request is pending. */
describe('session isolation at asynchronous boundaries (G01)', () => {
  const fetchMock = () => (global as any).fetch as jest.Mock;

  it('A: a delayed 401 of account A is discarded BEFORE any refresh or retry - the POST is never repeated with B credentials', async () => {
    setToken('jwt-A'); mockSecure.refresh_token = 'rA'; mockSecure.auth_token = 'jwt-A';
    let release!: (r: Response) => void;
    fetchQueue.push(() => new Promise<Response>(resolve => { release = resolve; }));     // A's POST /cart/add, response held
    const call = api.post('/cart/add', { product_id: 'p1', quantity: 1 });
    await flush();
    await signIn('jwt-B', 'rB');                                                        // A signs out, B signs in
    release(json(401, { detail: 'expired' }));                                          // A's delayed response arrives
    await expect(call).rejects.toBeInstanceOf(SessionChangedError);
    expect(fetchMock()).toHaveBeenCalledTimes(1);                                        // no /auth/refresh, no retried POST
    expect(fetchMock().mock.calls[0][1].headers.Authorization).toBe('Bearer jwt-A');
    expect(fetchMock().mock.calls.some((c: any[]) => c[1]?.headers?.Authorization === 'Bearer jwt-B')).toBe(false);
    expect(getToken()).toBe('jwt-B'); expect(mockSecure.refresh_token).toBe('rB'); expect(mockSecure.auth_token).toBe('jwt-B');
  });

  it('B: a delayed native storage READ that captured A\'s credential cannot start a refresh for A once B signed in', async () => {
    setToken('jwt-A'); mockSecure.refresh_token = 'rA'; mockSecure.auth_token = 'jwt-A';
    let releaseRead!: () => void;
    (SecureStore.getItemAsync as jest.Mock).mockImplementationOnce(() => new Promise(resolve => { releaseRead = () => resolve('rA'); }));
    fetchQueue.push(async () => json(401, { detail: 'expired' }));                     // A's call -> refresh -> storage read held
    const call = api.get('/auth/me');
    await flush();
    await signIn('jwt-B', 'rB');
    releaseRead();                                                                       // the read completes with A's stale credential
    await expect(call).rejects.toBeInstanceOf(SessionChangedError);
    expect(fetchMock()).toHaveBeenCalledTimes(1);                                        // rA was never sent to /auth/refresh
    expect(getToken()).toBe('jwt-B'); expect(mockSecure.refresh_token).toBe('rB'); expect(mockSecure.auth_token).toBe('jwt-B');
  });

  it('C: a delayed native storage WRITE of A\'s refreshed credentials cannot overwrite B who signed in meanwhile', async () => {
    setToken('jwt-A'); mockSecure.refresh_token = 'rA'; mockSecure.auth_token = 'jwt-A';
    let releaseWrite!: () => void;
    (SecureStore.setItemAsync as jest.Mock).mockImplementationOnce((k: string, v: string) => new Promise<void>(resolve => { releaseWrite = () => { mockSecure[k] = v; resolve(); }; }));
    const { call, held } = await startExpiredRequest();
    held.resolve(json(200, { token: 'jwt-A2', refresh_token: 'rA2' }));                // A's refresh succeeds; its first storage write is held
    await flush(); await flush();
    const b = signIn('jwt-B', 'rB');                                                     // B signs in while A's write is in flight
    releaseWrite();
    await b;
    await expect(call).rejects.toBeInstanceOf(SessionChangedError);
    expect(getToken()).toBe('jwt-B'); expect(mockSecure.auth_token).toBe('jwt-B'); expect(mockSecure.refresh_token).toBe('rB');
  });

  it('D: a rejected OLD refresh whose clearing write is in flight cannot clear B or sign B out', async () => {
    const lost = jest.fn(); onSessionLost(lost);
    setToken('jwt-A'); mockSecure.refresh_token = 'rA'; mockSecure.auth_token = 'jwt-A';
    let releaseDelete!: () => void;
    (SecureStore.deleteItemAsync as jest.Mock).mockImplementationOnce((k: string) => new Promise<void>(resolve => { releaseDelete = () => { delete mockSecure[k]; resolve(); }; }));
    const { call, held } = await startExpiredRequest();
    held.resolve(json(401, { detail: 'revoked' }));                                     // server rejects A's credential; the clear is held
    await flush(); await flush();
    const b = signIn('jwt-B', 'rB');
    releaseDelete();
    await b;
    await expect(call).rejects.toBeInstanceOf(SessionChangedError);
    expect(lost).not.toHaveBeenCalled();
    expect(getToken()).toBe('jwt-B'); expect(mockSecure.auth_token).toBe('jwt-B'); expect(mockSecure.refresh_token).toBe('rB');
    onSessionLost(null);
  });

  it('E: B\'s expired call gets its OWN refresh instead of waiting on (and failing with) A\'s stale one', async () => {
    setToken('jwt-A'); mockSecure.refresh_token = 'rA'; mockSecure.auth_token = 'jwt-A';
    const a = await startExpiredRequest();                                              // A's call -> A's refresh held
    await signIn('jwt-B', 'rB');
    fetchQueue.push(async () => json(401, { detail: 'expired' }));                     // B's call answers 401
    const heldB = heldRefresh();                                                         // B's refresh (a second /auth/refresh)
    const bCall = api.get('/auth/me');
    await flush();
    fetchQueue.push(async () => json(200, { id: 'B' }));                                // B's retry
    heldB.resolve(json(200, { token: 'jwt-B2', refresh_token: 'rB2' }));
    await expect(bCall).resolves.toEqual({ id: 'B' });
    a.held.resolve(json(200, { token: 'jwt-A2', refresh_token: 'rA2' }));               // A's refresh finally answers
    await expect(a.call).rejects.toBeInstanceOf(SessionChangedError);
    expect(getToken()).toBe('jwt-B2'); expect(mockSecure.refresh_token).toBe('rB2'); expect(mockSecure.auth_token).toBe('jwt-B2');
    expect(fetchMock().mock.calls.filter((c: any[]) => String(c[0]).endsWith('/auth/refresh'))).toHaveLength(2);
    expect(fetchMock().mock.calls.filter((c: any[]) => String(c[0]).endsWith('/auth/me')).map((c: any[]) => c[1].headers.Authorization)).toEqual(['Bearer jwt-A', 'Bearer jwt-B', 'Bearer jwt-B2']);
  });

  it('control: a same-session refresh with slow storage still persists and retries normally', async () => {
    setToken('jwt-A'); mockSecure.refresh_token = 'rA'; mockSecure.auth_token = 'jwt-A';
    (SecureStore.setItemAsync as jest.Mock).mockImplementationOnce((k: string, v: string) => new Promise<void>(resolve => setTimeout(() => { mockSecure[k] = v; resolve(); }, 5)));
    const { call, held } = await startExpiredRequest();
    fetchQueue.push(async () => json(200, { id: 'A' }));
    held.resolve(json(200, { token: 'jwt-A2', refresh_token: 'rA2' }));
    await expect(call).resolves.toEqual({ id: 'A' });
    expect(getToken()).toBe('jwt-A2'); expect(mockSecure.auth_token).toBe('jwt-A2'); expect(mockSecure.refresh_token).toBe('rA2');
  });
});
