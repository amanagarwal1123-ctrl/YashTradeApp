import Constants from 'expo-constants';
import { PixelRatio, Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';

export const BACKEND_URL = Constants.expoConfig?.extra?.backendUrl || process.env.EXPO_PUBLIC_BACKEND_URL || '';
export const API_BASE = `${BACKEND_URL}/api`;
let authToken: string | null = null;
let webRefresh: string | null = null;
let refreshing: Promise<void> | null = null;
// Session epoch: bumped whenever the signed-in identity changes (login, logout, deletion, revoked session). A response
// that started under an older epoch is discarded, so a slow request can never restore the previous account's data.
let sessionEpoch = 0;
export const currentSession = () => sessionEpoch;
export const endSession = () => { sessionEpoch += 1; };
export class SessionChangedError extends Error {
  constructor() { super('Session changed before the response arrived'); this.name = 'SessionChangedError'; }
}
export const setToken = (token: string | null) => { authToken = token; };
export const getToken = () => authToken;
export const setRefreshToken = async (token: string | null) => {
  if (Platform.OS === 'web') { webRefresh = token; return; }
  if (token) await SecureStore.setItemAsync('refresh_token', token);
  else await SecureStore.deleteItemAsync('refresh_token');
};

let sessionLost: (() => void) | null = null;
/** Registered by the auth provider: runs ONLY when the server confirms the session is gone (401/403 on refresh, no
 * refresh credential). Network failures and 5xx never end the session. */
export const onSessionLost = (handler: (() => void) | null) => { sessionLost = handler; };
export class TransientError extends Error {
  constructor(message: string) { super(message); this.name = 'TransientError'; }
}
const isTransientStatus = (status: number) => status >= 500 || status === 408 || status === 429;

async function refreshSession() {
  // The refresh is bound to the session generation and the credential it started with (F01): if the session changes
  // while the HTTP request is pending (logout, another account signed in, revocation), its result - success OR failure -
  // is obsolete and must neither persist credentials nor sign the CURRENT session out.
  const epoch = sessionEpoch;
  const refresh = Platform.OS === 'web' ? webRefresh : await SecureStore.getItemAsync('refresh_token');
  if (!refresh) { if (epoch === sessionEpoch) sessionLost?.(); throw new Error('Please sign in again'); }
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/auth/refresh`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh_token: refresh }) });
  } catch {
    throw new TransientError('You are offline; your session is kept and will reconnect');
  }
  const stillCurrent = async () => {
    if (epoch !== sessionEpoch) return false;
    const now = Platform.OS === 'web' ? webRefresh : await SecureStore.getItemAsync('refresh_token');
    return now === refresh; // the credential this refresh rotated is still the device's credential
  };
  if (response.status === 409) return; // concurrent refresh already rotated the credentials on this device: keep going
  if (isTransientStatus(response.status)) throw new TransientError('Server unavailable; your session is kept');
  if (!response.ok) {
    if (!(await stillCurrent())) throw new SessionChangedError();
    await setRefreshToken(null); setToken(null); sessionLost?.(); throw new Error('Session expired; please sign in again');
  }
  const data = await response.json();
  if (!(await stillCurrent())) throw new SessionChangedError();
  setToken(data.token); await setRefreshToken(data.refresh_token);
  if (Platform.OS !== 'web') await SecureStore.setItemAsync('auth_token', data.token);
}

export const REFRESH_EXEMPT = ['/auth/send-otp', '/auth/verify-otp', '/auth/refresh', '/auth/review/login'];

export async function authenticatedFetch(path: string, options: RequestInit = {}, retry = true): Promise<Response> {
  const headers: Record<string, string> = { ...(options.headers as Record<string, string> || {}) };
  if (authToken) headers.Authorization = `Bearer ${authToken}`;
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  } catch {
    throw new TransientError('Network unavailable');
  }
  if (response.status === 401 && authToken && retry && !REFRESH_EXEMPT.includes(path)) {
    if (!refreshing) refreshing = refreshSession().finally(() => { refreshing = null; });
    await refreshing;
    return authenticatedFetch(path, options, false);
  }
  return response;
}

export async function responseJson(res: Response) {
  const data = await res.json().catch(() => ({ detail: 'Unable to read server response' }));
  if (!res.ok) {
    const error: any = new Error(typeof data.detail === 'string' ? data.detail : data.detail?.detail || `Request failed (${res.status})`);
    error.status = res.status; error.code = data.code; error.body = data; error.transient = isTransientStatus(res.status); throw error;
  }
  return data;
}

async function request(path: string, method = 'GET', body?: any) {
  const epoch = sessionEpoch;
  const response = await authenticatedFetch(path, { method, headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
  if (epoch !== sessionEpoch) throw new SessionChangedError();
  return responseJson(response);
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
    const body = new FormData(); body.append('file', file);
    return responseJson(await authenticatedFetch(path, { method: 'POST', body }));
  },
  uploadFiles: async (path: string, files: File[], progress?: (done: number, total: number) => void) => {
    uploadController = new AbortController(); const results = [];
    try {
      for (let i = 0; i < files.length; i += 3) {
        const body = new FormData(); files.slice(i, i+3).forEach(f => body.append('files', f));
        results.push(await responseJson(await authenticatedFetch(path, { method: 'POST', body, signal: uploadController.signal })));
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