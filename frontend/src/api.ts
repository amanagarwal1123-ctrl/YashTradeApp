const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';
if (!BACKEND_URL && typeof window !== 'undefined') {
  console.error('[API] EXPO_PUBLIC_BACKEND_URL is not set. Check your .env file. See .env.example for reference.');
}
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
  uploadFiles: async (path: string, files: File[], onProgress?: (done: number, total: number) => void) => {
    const CHUNK = 3;
    const allResults: any[] = [];
    for (let i = 0; i < files.length; i += CHUNK) {
      const chunk = files.slice(i, i + CHUNK);
      const formData = new FormData();
      chunk.forEach(f => formData.append('files', f));
      const headers: Record<string, string> = {};
      if (authToken) headers['Authorization'] = `Bearer ${authToken}`;
      const res = await fetch(`${API_BASE}${path}`, { method: 'POST', headers, body: formData });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Upload failed' }));
        throw new Error(err.detail || `Error ${res.status}`);
      }
      const data = await res.json();
      allResults.push(data);
      onProgress?.(Math.min(i + CHUNK, files.length), files.length);
    }
    return allResults;
  },
  importPdf: async (path: string, file: File, onProgress?: (phase: string, detail: string) => void) => {
    // Validate file size client-side
    const maxSize = 300 * 1024 * 1024; // 300MB
    if (file.size > maxSize) {
      throw new Error(`PDF file is too large (${(file.size / (1024 * 1024)).toFixed(0)}MB). Maximum allowed size is 300MB.`);
    }
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      throw new Error('Please select a PDF file (.pdf). For images, use the "Upload Images" option instead.');
    }

    onProgress?.('uploading', `Uploading ${(file.size / (1024 * 1024)).toFixed(1)}MB PDF...`);

    const formData = new FormData();
    formData.append('file', file);
    const headers: Record<string, string> = {};
    if (authToken) headers['Authorization'] = `Bearer ${authToken}`;

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 600000); // 10 min timeout

      const res = await fetch(`${API_BASE}${path}`, {
        method: 'POST',
        headers,
        body: formData,
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: `Server error ${res.status}` }));
        throw new Error(err.detail || `Server returned error ${res.status}`);
      }

      onProgress?.('processing', 'PDF uploaded. Extracting pages...');
      return await res.json();
    } catch (e: any) {
      if (e.name === 'AbortError') {
        throw new Error('Upload timed out. The PDF may be too large or the connection is slow. Please try again or use a smaller file.');
      }
      if (e.message?.includes('Failed to fetch') || e.message?.includes('NetworkError')) {
        throw new Error(
          `Network error during PDF upload. Possible reasons:\n` +
          `• PDF file may be too large for your connection\n` +
          `• Internet connection was interrupted\n` +
          `• Server took too long to respond\n\n` +
          `File size: ${(file.size / (1024 * 1024)).toFixed(1)}MB\n` +
          `Try again or use a smaller PDF.`
        );
      }
      throw e;
    }
  },
};

export const getImageUrl = (product: any, thumbnail = true): string => {
  if (thumbnail && product?.thumbnail_path) {
    return `${API_BASE}/files/${product.thumbnail_path}`;
  }
  if (product?.storage_path) {
    return `${API_BASE}/files/${product.storage_path}`;
  }
  return product?.images?.[0] || '';
};
