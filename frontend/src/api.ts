import Constants from 'expo-constants';
import { PixelRatio, Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';

export const BACKEND_URL = Constants.expoConfig?.extra?.backendUrl || process.env.EXPO_PUBLIC_BACKEND_URL || '';
export const API_BASE = `${BACKEND_URL}/api`;
let authToken: string | null = null;
let webRefresh: string | null = null;
// Session generation: bumped whenever the signed-in identity changes (login, logout, deletion, revoked session). Every
// request, refresh attempt and credential write is bound to the generation it started under and re-checked after EVERY
// asynchronous step (F01 / G01): a slow response of the previous account is discarded before any refresh or retry, so
// it can never be re-sent with the new account's credentials, and its late success or failure can neither restore the
// previous account's credentials nor sign the current account out.
let sessionEpoch = 0;
export const currentSession = () => sessionEpoch;
export const endSession = () => { sessionEpoch += 1; };
export class SessionChangedError extends Error {
  constructor() { super('Session changed before the response arrived'); this.name = 'SessionChangedError'; }
}
export const setToken = (token: string | null) => { authToken = token; };
export const getToken = () => authToken;

// Credential persistence is SERIALIZED and generation-bound. An operation runs only when its turn comes AND its
// generation is still the current one: two generations' storage reads/writes never interleave, and a stale write that
// was queued before the account changed is dropped instead of overwriting the account that signed in meanwhile.
// Resolves false when the operation was dropped.
let credentialQueue: Promise<unknown> = Promise.resolve();
export function storeCredentials(epoch: number, token: string | null, refresh: string | null): Promise<boolean> {
  const run = credentialQueue.then(async () => {
    if (epoch !== sessionEpoch) return false;
    authToken = token;
    if (Platform.OS === 'web') { webRefresh = refresh; return true; }   // web sessions are memory-only
    await (token ? SecureStore.setItemAsync('auth_token', token) : SecureStore.deleteItemAsync('auth_token'));
    await (refresh ? SecureStore.setItemAsync('refresh_token', refresh) : SecureStore.deleteItemAsync('refresh_token'));
    return true;
  });
  credentialQueue = run.catch(() => undefined);
  return run;
}

let sessionLost: (() => void) | null = null;
/** Registered by the auth provider: runs ONLY when the server confirms the session is gone (401/403 on refresh, no
 * refresh credential). Network failures and 5xx never end the session. */
export const onSessionLost = (handler: (() => void) | null) => { sessionLost = handler; };
export class TransientError extends Error {
  constructor(message: string) { super(message); this.name = 'TransientError'; }
}
const isTransientStatus = (status: number) => status >= 500 || status === 408 || status === 429;

async function refreshSession(epoch: number) {
  // Bound to the generation of the request that needed it: after every await the generation is re-checked, so a
  // refresh that outlives its session (logout, another account signed in, revocation) is abandoned - it never persists
  // credentials, never signs the CURRENT session out, and its callers never retry under the new account.
  const changed = () => epoch !== sessionEpoch;
  if (changed()) throw new SessionChangedError();
  const refresh = Platform.OS === 'web' ? webRefresh : await SecureStore.getItemAsync('refresh_token');
  if (changed()) throw new SessionChangedError();   // the read may have captured the previous account's credential
  if (!refresh) { sessionLost?.(); throw new Error('Please sign in again'); }
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/auth/refresh`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh_token: refresh }) });
  } catch {
    if (changed()) throw new SessionChangedError();
    throw new TransientError('You are offline; your session is kept and will reconnect');
  }
  if (changed()) throw new SessionChangedError();
  if (response.status === 409) return; // concurrent refresh already rotated the credentials on this device: keep going
  if (isTransientStatus(response.status)) throw new TransientError('Server unavailable; your session is kept');
  if (!response.ok) {
    // The server confirmed THIS generation's credential is gone: clear it (dropped if the account changed meanwhile)
    // and end this generation only.
    if (!(await storeCredentials(epoch, null, null)) || changed()) throw new SessionChangedError();
    sessionLost?.();
    throw new Error('Session expired; please sign in again');
  }
  const data = await response.json();
  if (!(await storeCredentials(epoch, data.token, data.refresh_token))) throw new SessionChangedError();
}

// One refresh in flight per session generation: a request of the CURRENT generation never waits on (or fails with) a
// refresh that an earlier generation started.
let refreshing: { epoch: number; promise: Promise<void> } | null = null;
function sharedRefresh(epoch: number) {
  if (!refreshing || refreshing.epoch !== epoch) {
    const promise = refreshSession(epoch).finally(() => { if (refreshing?.promise === promise) refreshing = null; });
    refreshing = { epoch, promise };
  }
  return refreshing.promise;
}

export const REFRESH_EXEMPT = ['/auth/send-otp', '/auth/verify-otp', '/auth/refresh', '/auth/review/login'];

export async function authenticatedFetch(path: string, options: RequestInit = {}, retry = true, epoch = sessionEpoch): Promise<Response> {
  const headers: Record<string, string> = { ...(options.headers as Record<string, string> || {}) };
  if (authToken) headers.Authorization = `Bearer ${authToken}`;
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  } catch {
    if (epoch !== sessionEpoch) throw new SessionChangedError();
    throw new TransientError('Network unavailable');
  }
  // A response that arrives after the account changed is discarded HERE - before any refresh or retry - so the
  // previous account's request (and its body) is never repeated with the new account's authorization.
  if (epoch !== sessionEpoch) throw new SessionChangedError();
  if (response.status === 401 && authToken && retry && !REFRESH_EXEMPT.includes(path)) {
    await sharedRefresh(epoch);
    if (epoch !== sessionEpoch) throw new SessionChangedError();
    return authenticatedFetch(path, options, false, epoch);
  }
  return response;
}

/** Parses a response body under the generation the request started in (defaults to the generation current when the
 * headers were handled). Headers can arrive before the body is complete (G01c): a body that finishes after the account
 * changed - a profile, an error detail, an upload result - is rejected here, before any consumer can apply it. */
export async function responseJson(res: Response, epoch = sessionEpoch) {
  const data = await res.json().catch(() => ({ detail: 'Unable to read server response' }));
  if (epoch !== sessionEpoch) throw new SessionChangedError();
  if (!res.ok) {
    const error: any = new Error(typeof data.detail === 'string' ? data.detail : data.detail?.detail || `Request failed (${res.status})`);
    error.status = res.status; error.code = data.code; error.body = data; error.transient = isTransientStatus(res.status); throw error;
  }
  return data;
}

async function request(path: string, method = 'GET', body?: any) {
  const epoch = sessionEpoch;
  const response = await authenticatedFetch(path, { method, headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) }, true, epoch);
  return responseJson(response, epoch);
}
let uploadController: AbortController | null = null;
export const cancelUpload = () => uploadController?.abort();
export const getLastUploadId = () => null;
export const clearLastUploadId = () => {};
export const api = {
  get: (path: string) => request(path), post: (path: string, body?: any) => request(path, 'POST', body),
  put: (path: string, body?: any) => request(path, 'PUT', body), patch: (path: string, body?: any) => request(path, 'PATCH', body),
  delete: (path: string) => request(path, 'DELETE'),
  uploadSingle: async (path: string, file: File) => {
    const epoch = sessionEpoch;
    const body = new FormData(); body.append('file', file);
    return responseJson(await authenticatedFetch(path, { method: 'POST', body }, true, epoch), epoch);
  },
  uploadFiles: async (path: string, files: File[], progress?: (done: number, total: number) => void) => {
    const epoch = sessionEpoch;
    uploadController = new AbortController(); const results = [];
    try {
      for (let i = 0; i < files.length; i += 3) {
        const body = new FormData(); files.slice(i, i+3).forEach(f => body.append('files', f));
        results.push(await responseJson(await authenticatedFetch(path, { method: 'POST', body, signal: uploadController.signal }, true, epoch), epoch));
        progress?.(Math.min(i+3, files.length), files.length);
      }
      return results;
    } finally { uploadController = null; }
  },
  // Old UI adapters are retired; all visible entry points open the reviewed importer.
  importPdfChunked: async (..._args: any[]): Promise<any> => { throw new Error('Open the reviewed PDF importer from Products'); },
};

export const resolveFileUrl = (url: string): string => !url ? '' : /^https?:\/\//.test(url) ? url : `${BACKEND_URL}${url}`;

// Display variants served by GET /api/files/{path}?w= (400 | 800, JPEG, derived from the write-once master). The
// device-pixel need is capped at 2x: a 3x phone gets the same bytes as a 2x one, which is visually sufficient for
// catalogue cards and keeps mobile data bounded. Full-resolution originals are fetched only where zoom matters.
export const VARIANT_WIDTHS = [400, 800] as const;
export type Variant = (typeof VARIANT_WIDTHS)[number];
export const variantFor = (displayWidthDp: number, pixelRatio = PixelRatio.get()): Variant => {
  const needed = displayWidthDp * Math.min(2, Math.max(1, pixelRatio));
  return needed <= 400 ? 400 : 800;
};
const fileUrl = (path: string, width?: Variant) => `${API_BASE}/files/${path}${width ? `?w=${width}` : ''}`;

/**
 * Card / list image for a product at the given display width (dp). Prefers the stored thumbnail when it already
 * covers the need (no server work), otherwise a sized variant of the master; legacy external URLs pass through.
 */
export const productImage = (product: any, displayWidthDp: number): string => {
  const width = variantFor(displayWidthDp);
  if (product?.thumbnail_path && width <= 400) return fileUrl(product.thumbnail_path);
  if (product?.storage_path) return fileUrl(product.storage_path, width);
  if (product?.thumbnail_path) return fileUrl(product.thumbnail_path);
  return resolveFileUrl(product?.images?.[0] || '');
};
/** Smallest available image: shown instantly as the placeholder while a larger one loads. */
export const productThumb = (product: any): string => product?.thumbnail_path ? fileUrl(product.thumbnail_path)
  : product?.storage_path ? fileUrl(product.storage_path, 400) : resolveFileUrl(product?.images?.[0] || '');
/** Full-resolution master for detail zoom. */
export const productFull = (product: any): string => product?.storage_path ? fileUrl(product.storage_path) : resolveFileUrl(product?.images?.[0] || '');
/** Sized variant of any stored gallery URL (`…/api/files/<path>`); external URLs are returned as they are. */
export const sizedUrl = (url: string, displayWidthDp: number): string => {
  const prefix = `${API_BASE}/files/`;
  return url.startsWith(prefix) && !url.includes('?') ? `${url}?w=${variantFor(displayWidthDp)}` : url;
};

export const getImageUrl = (product: any, thumbnail = true): string => {
  if (thumbnail && product?.thumbnail_path) return fileUrl(product.thumbnail_path);
  if (product?.storage_path) return fileUrl(product.storage_path);
  return resolveFileUrl(product?.images?.[0] || '');
};
export const getProductGallery = (product: any): string[] => [...new Set<string>([
  ...(product?.original_source_storage_path ? [fileUrl(product.original_source_storage_path)] : []),
  ...(product?.storage_path ? [getImageUrl(product, false)] : []),
  ...(product?.images || []).map(resolveFileUrl),
].filter(Boolean))];