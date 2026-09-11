import Constants from 'expo-constants';
import { Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';

export const BACKEND_URL = Constants.expoConfig?.extra?.backendUrl || process.env.EXPO_PUBLIC_BACKEND_URL || '';
export const API_BASE = `${BACKEND_URL}/api`;
let authToken: string | null = null;
let webRefresh: string | null = null;
let refreshing: Promise<void> | null = null;
export const setToken = (token: string | null) => { authToken = token; };
export const getToken = () => authToken;
export const setRefreshToken = async (token: string | null) => {
  if (Platform.OS === 'web') { webRefresh = token; return; }
  if (token) await SecureStore.setItemAsync('refresh_token', token);
  else await SecureStore.deleteItemAsync('refresh_token');
};

async function refreshSession() {
  const refresh = Platform.OS === 'web' ? webRefresh : await SecureStore.getItemAsync('refresh_token');
  if (!refresh) throw new Error('Please sign in again');
  const response = await fetch(`${API_BASE}/auth/refresh`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh_token: refresh }) });
  if (!response.ok) { await setRefreshToken(null); setToken(null); throw new Error('Session expired; please sign in again'); }
  const data = await response.json();
  setToken(data.token); await setRefreshToken(data.refresh_token);
  if (Platform.OS !== 'web') await SecureStore.setItemAsync('auth_token', data.token);
}

export async function authenticatedFetch(path: string, options: RequestInit = {}, retry = true): Promise<Response> {
  const headers: Record<string, string> = { ...(options.headers as Record<string, string> || {}) };
  if (authToken) headers.Authorization = `Bearer ${authToken}`;
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (response.status === 401 && authToken && retry && !['/auth/send-otp', '/auth/verify-otp', '/auth/refresh'].includes(path)) {
    if (!refreshing) refreshing = refreshSession().finally(() => { refreshing = null; });
    await refreshing;
    return authenticatedFetch(path, options, false);
  }
  if (response.status === 401 && path === '/auth/me' && retry) {
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
    error.status = res.status; error.code = data.code; throw error;
  }
  return data;
}

async function request(path: string, method = 'GET', body?: any) {
  return responseJson(await authenticatedFetch(path, { method, headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) }));
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
export const getImageUrl = (product: any, thumbnail = true): string => {
  if (thumbnail && product?.thumbnail_path) return `${API_BASE}/files/${product.thumbnail_path}`;
  if (product?.storage_path) return `${API_BASE}/files/${product.storage_path}`;
  return resolveFileUrl(product?.images?.[0] || '');
};
export const getProductGallery = (product: any): string[] => [...new Set<string>([
  ...(product?.original_source_storage_path ? [`${API_BASE}/files/${product.original_source_storage_path}`] : []),
  ...(product?.storage_path ? [getImageUrl(product, false)] : []),
  ...(product?.images || []).map(resolveFileUrl),
].filter(Boolean))];