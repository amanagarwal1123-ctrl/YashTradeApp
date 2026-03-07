const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';
const API_BASE = `${BACKEND_URL}/api`;

let authToken: string | null = null;

export const setToken = (token: string | null) => { authToken = token; };
export const getToken = () => authToken;

async function request(path: string, options: RequestInit = {}) {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> || {}),
  };
  if (authToken) headers['Authorization'] = `Bearer ${authToken}`;

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(err.detail || `Error ${res.status}`);
  }
  return res.json();
}

export const api = {
  get: (path: string) => request(path),
  post: (path: string, body?: any) => request(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),
  put: (path: string, body?: any) => request(path, { method: 'PUT', body: JSON.stringify(body) }),
  patch: (path: string, body?: any) => request(path, { method: 'PATCH', body: JSON.stringify(body) }),
  delete: (path: string) => request(path, { method: 'DELETE' }),
};
