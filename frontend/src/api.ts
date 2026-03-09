const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';
if (!BACKEND_URL && typeof window !== 'undefined') {
  console.error('[API] EXPO_PUBLIC_BACKEND_URL is not set. Check your .env file.');
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

  /**
   * Chunked PDF upload system for large files (up to 1GB).
   * 1. Init upload session
   * 2. Upload file in 5MB chunks with progress
   * 3. Signal completion to start background processing
   * 4. Poll for processing status
   */
  importPdfChunked: async (
    batchId: string,
    file: File,
    onProgress: (phase: 'validating' | 'uploading' | 'processing' | 'done' | 'error', detail: string, progress?: number) => void
  ): Promise<any> => {
    const MAX_SIZE = 1000 * 1024 * 1024; // 1000MB
    const CHUNK_SIZE = 5 * 1024 * 1024; // 5MB

    // --- Phase: Validation ---
    onProgress('validating', 'Validating file...');
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      throw new Error('Only PDF files are accepted. For images (JPG, PNG), use "Upload Images" instead.');
    }
    if (file.size > MAX_SIZE) {
      throw new Error(`PDF file is too large (${(file.size / (1024 * 1024)).toFixed(0)}MB). Maximum allowed size is 1000MB.`);
    }
    if (file.size < 100) {
      throw new Error('File is too small to be a valid PDF.');
    }

    const totalChunks = Math.ceil(file.size / CHUNK_SIZE);
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (authToken) headers['Authorization'] = `Bearer ${authToken}`;

    // --- Phase 1: Init upload session ---
    onProgress('uploading', `Initializing upload for ${(file.size / (1024 * 1024)).toFixed(1)}MB PDF (${totalChunks} chunks)...`, 0);
    const initRes = await fetch(`${API_BASE}/pdf-upload/init`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        batch_id: batchId,
        filename: file.name,
        file_size: file.size,
        total_chunks: totalChunks,
      }),
    });
    if (!initRes.ok) {
      const err = await initRes.json().catch(() => ({ detail: `Server error ${initRes.status}` }));
      throw new Error(err.detail || `Failed to initialize upload (${initRes.status})`);
    }
    const { upload_id } = await initRes.json();

    // --- Phase 2: Upload chunks ---
    for (let i = 0; i < totalChunks; i++) {
      const start = i * CHUNK_SIZE;
      const end = Math.min(start + CHUNK_SIZE, file.size);
      const blob = file.slice(start, end);
      const pct = Math.round(((i + 1) / totalChunks) * 100);

      onProgress('uploading', `Uploading chunk ${i + 1}/${totalChunks} (${pct}%)...`, pct);

      const chunkForm = new FormData();
      chunkForm.append('file', blob, `chunk_${i}`);
      const chunkHeaders: Record<string, string> = {};
      if (authToken) chunkHeaders['Authorization'] = `Bearer ${authToken}`;

      let retries = 0;
      const maxRetries = 3;
      let chunkSuccess = false;

      while (retries < maxRetries && !chunkSuccess) {
        try {
          const chunkRes = await fetch(`${API_BASE}/pdf-upload/${upload_id}/chunk?chunk_index=${i}`, {
            method: 'POST',
            headers: chunkHeaders,
            body: chunkForm,
          });
          if (!chunkRes.ok) {
            const err = await chunkRes.json().catch(() => ({ detail: `Chunk upload failed` }));
            throw new Error(err.detail || `Chunk ${i} upload failed (${chunkRes.status})`);
          }
          chunkSuccess = true;
        } catch (e: any) {
          retries++;
          if (retries >= maxRetries) {
            if (e.message?.includes('Failed to fetch') || e.message?.includes('NetworkError')) {
              throw new Error(
                `Network error uploading chunk ${i + 1}/${totalChunks}.\n` +
                `Uploaded: ${(start / (1024 * 1024)).toFixed(0)}MB of ${(file.size / (1024 * 1024)).toFixed(0)}MB\n` +
                `Check your internet connection and try again.`
              );
            }
            throw new Error(`Failed to upload chunk ${i + 1}/${totalChunks} after ${maxRetries} attempts: ${e.message}`);
          }
          onProgress('uploading', `Chunk ${i + 1} failed, retrying (${retries}/${maxRetries})...`, pct);
          await new Promise(r => setTimeout(r, 2000 * retries)); // exponential backoff
        }
      }
    }

    // --- Phase 3: Signal complete, start processing ---
    onProgress('processing', 'Upload complete. Assembling PDF and starting page extraction...', 100);
    const completeHeaders: Record<string, string> = {};
    if (authToken) completeHeaders['Authorization'] = `Bearer ${authToken}`;
    const completeRes = await fetch(`${API_BASE}/pdf-upload/${upload_id}/complete`, {
      method: 'POST',
      headers: completeHeaders,
    });
    if (!completeRes.ok) {
      const err = await completeRes.json().catch(() => ({ detail: `Server error ${completeRes.status}` }));
      throw new Error(err.detail || `Failed to start processing (${completeRes.status})`);
    }

    // --- Phase 4: Poll for processing status ---
    const pollHeaders: Record<string, string> = {};
    if (authToken) pollHeaders['Authorization'] = `Bearer ${authToken}`;

    let pollCount = 0;
    const maxPolls = 1800; // 30 minutes at 1s intervals
    while (pollCount < maxPolls) {
      await new Promise(r => setTimeout(r, 1500));
      pollCount++;

      try {
        const statusRes = await fetch(`${API_BASE}/pdf-upload/${upload_id}/status`, { headers: pollHeaders });
        if (!statusRes.ok) continue;

        const status = await statusRes.json();

        if (status.upload_status === 'processing') {
          const pagesProgress = status.total_pages > 0
            ? Math.round((status.pages_processed / status.total_pages) * 100)
            : 0;
          onProgress(
            'processing',
            `Processing page ${status.pages_processed}/${status.total_pages} (${status.imported} imported, ${status.failed} failed)`,
            pagesProgress
          );
        } else if (status.upload_status === 'done') {
          onProgress('done', `Complete! ${status.imported} pages imported.`, 100);
          return status;
        } else if (status.upload_status === 'error') {
          throw new Error(status.error || 'PDF processing failed on the server.');
        }
      } catch (e: any) {
        if (e.message?.includes('PDF processing failed') || e.message?.includes('processing failed')) {
          throw e;
        }
        // Network hiccup during polling — keep trying
      }
    }

    throw new Error('PDF processing timed out after 30 minutes. The server may still be processing. Check back later.');
  },

  // Legacy single-shot import (kept for backward compat with small PDFs)
  importPdf: async (path: string, file: File, onProgress?: (phase: string, detail: string) => void) => {
    const maxSize = 1000 * 1024 * 1024;
    if (file.size > maxSize) {
      throw new Error(`PDF file is too large (${(file.size / (1024 * 1024)).toFixed(0)}MB). Maximum allowed size is 1000MB.`);
    }
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      throw new Error('Please select a PDF file (.pdf).');
    }
    onProgress?.('uploading', `Uploading ${(file.size / (1024 * 1024)).toFixed(1)}MB PDF...`);
    const formData = new FormData();
    formData.append('file', file);
    const headers: Record<string, string> = {};
    if (authToken) headers['Authorization'] = `Bearer ${authToken}`;
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 1800000);
      const res = await fetch(`${API_BASE}${path}`, { method: 'POST', headers, body: formData, signal: controller.signal });
      clearTimeout(timeoutId);
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: `Server error ${res.status}` }));
        throw new Error(err.detail || `Server returned error ${res.status}`);
      }
      onProgress?.('processing', 'PDF uploaded. Extracting pages...');
      return await res.json();
    } catch (e: any) {
      if (e.name === 'AbortError') throw new Error('Upload timed out.');
      if (e.message?.includes('Failed to fetch') || e.message?.includes('NetworkError')) {
        throw new Error(`Network error during PDF upload. File: ${(file.size / (1024 * 1024)).toFixed(1)}MB. Check connection and retry.`);
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
