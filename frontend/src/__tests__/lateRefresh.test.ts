import { Platform } from 'react-native';

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
import { api, endSession, getToken, onSessionLost, setRefreshToken, setToken, SessionChangedError } from '../api';

type Pending = { resolve: (r: Response) => void };
const json = (status: number, body: any): Response => ({ status, ok: status >= 200 && status < 300, json: async () => body } as any);
let fetchQueue: Array<(url: string, init: any) => Promise<Response>> = [];
const heldRefresh = (): Pending => {
  const p: Pending = { resolve: () => {} };
  fetchQueue.push(() => new Promise<Response>(resolve => { p.resolve = resolve; }));
  return p;
};

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
    endSession(); await setRefreshToken(null); setToken(null); delete mockSecure.auth_token;
    held.resolve(json(200, { token: 'jwt-A2', refresh_token: 'rA2' }));
    await expect(call).rejects.toBeInstanceOf(SessionChangedError);
    expect(getToken()).toBeNull();
    expect(mockSecure.refresh_token).toBeUndefined();
    expect(mockSecure.auth_token).toBeUndefined();
  });

  it('another account signs in while the refresh is pending: account B credentials are kept, A is discarded', async () => {
    setToken('jwt-A'); mockSecure.refresh_token = 'rA'; mockSecure.auth_token = 'jwt-A';
    const { call, held } = await startExpiredRequest();
    endSession(); setToken('jwt-B'); await setRefreshToken('rB'); mockSecure.auth_token = 'jwt-B';
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
    endSession(); setToken('jwt-B'); await setRefreshToken('rB');
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
