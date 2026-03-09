const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';
if (!BACKEND_URL && typeof window !== 'undefined') {
  console.error('[API] EXPO_PUBLIC_BACKEND_URL is not set. Check your .env file.');
}
const API_BASE = `${BACKEND_URL}/api`;

let authToken: string | null = null;

export const setToken = (token: string | null) => { authToken = token; };
export const getToken = () => authToken;

// Global abort controller for cancellable uploads
let _uploadAbortController: AbortController | null = null;

export const cancelUpload = () => {
  if (_uploadAbortController) {
    _uploadAbortController.abort();
    _uploadAbortController = null;
  }
};

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
  patch: (path: string, body?: any) => request(path, { method: 'PATCH', body: body ? JSON.stringify(body) : undefined }),
  delete: (path: string) => request(path, { method: 'DELETE' }),

  uploadFiles: async (path: string, files: File[], onProgress?: (done: number, total: number) => void) => {
    _uploadAbortController = new AbortController();
    const signal = _uploadAbortController.signal;
    const CHUNK = 3;
    const allResults: any[] = [];
    try {
      for (let i = 0; i < files.length; i += CHUNK) {
        if (signal.aborted) throw new Error('Upload cancelled by user.');
        const chunk = files.slice(i, i + CHUNK);
        const formData = new FormData();
        chunk.forEach(f => formData.append('files', f));
        const headers: Record<string, string> = {};
        if (authToken) headers['Authorization'] = `Bearer ${authToken}`;
        const res = await fetch(`${API_BASE}${path}`, { method: 'POST', headers, body: formData, signal });
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: 'Upload failed' }));
          throw new Error(err.detail || `Error ${res.status}`);
        }
        const data = await res.json();
        allResults.push(data);
        onProgress?.(Math.min(i + CHUNK, files.length), files.length);
      }
    } finally {
      _uploadAbortController = null;
    }
    return allResults;
  },

  /**
   * Chunked PDF upload with resume support (up to 1GB).
   * - 5MB chunks with 5 retries each (exponential backoff up to 15s)
   * - Per-chunk 90s timeout
   * - Queries server for already-received chunks to skip on resume
   * - AbortController for user cancellation
   */
  importPdfChunked: async (
    batchId: string,
    file: File,
    onProgress: (phase: 'validating' | 'uploading' | 'processing' | 'done' | 'error', detail: string, progress?: number) => void,
    existingUploadId?: string | null,
  ): Promise<any> => {
    const MAX_SIZE = 1000 * 1024 * 1024; // 1GB
    const CHUNK_SIZE = 25 * 1024 * 1024; // 25MB — fewer roundtrips, more reliable on mobile
    const MAX_RETRIES = 5;
    const CHUNK_TIMEOUT_MS = 180000; // 180s per 25MB chunk on mobile

    _uploadAbortController = new AbortController();
    const signal = _uploadAbortController.signal;

    try {
      // --- Validation ---
      onProgress('validating', 'Validating file...');
      if (!file.name.toLowerCase().endsWith('.pdf')) {
        throw new Error('Only PDF files are accepted. For images (JPG, PNG), use "Upload Images" instead.');
      }
      if (file.size > MAX_SIZE) {
        throw new Error(`PDF file is too large (${(file.size / (1024 * 1024)).toFixed(0)}MB). Maximum allowed is 1000MB.`);
      }
      if (file.size < 100) {
        throw new Error('File is too small to be a valid PDF.');
      }

      const totalChunks = Math.ceil(file.size / CHUNK_SIZE);
      const jsonHeaders: Record<string, string> = { 'Content-Type': 'application/json' };
      if (authToken) jsonHeaders['Authorization'] = `Bearer ${authToken}`;

      let upload_id = existingUploadId || '';
      let chunksAlreadyReceived = new Set<number>();

      if (upload_id) {
        // Resume mode: query which chunks are already received
        onProgress('uploading', 'Resuming upload — checking server state...', 0);
        try {
          const authH: Record<string, string> = {};
          if (authToken) authH['Authorization'] = `Bearer ${authToken}`;
          const statusRes = await fetch(`${API_BASE}/pdf-upload/${upload_id}/status`, { headers: authH, signal });
          if (statusRes.ok) {
            const st = await statusRes.json();
            if (st.upload_status === 'done') return st;
            if (st.upload_status === 'processing') {
              // Already processing, just poll
              return await _pollProcessing(upload_id, onProgress, signal);
            }
            if (st.upload_status === 'error') {
              throw new Error(st.error || 'Previous upload session failed.');
            }
            // Mark received chunks precisely
            if (st.received_chunk_indices) {
              for (const c of st.received_chunk_indices) chunksAlreadyReceived.add(c);
            } else {
              for (let c = 0; c < st.chunks_received; c++) chunksAlreadyReceived.add(c);
            }
          }
        } catch (e: any) {
          if (e.name === 'AbortError') throw new Error('Upload cancelled by user.');
          // Can't resume, start fresh
          upload_id = '';
          chunksAlreadyReceived.clear();
        }
      }

      if (!upload_id) {
        // Init new session
        onProgress('uploading', `Initializing upload for ${(file.size / (1024 * 1024)).toFixed(1)}MB PDF (${totalChunks} chunks)...`, 0);
        const initRes = await fetch(`${API_BASE}/pdf-upload/init`, {
          method: 'POST', headers: jsonHeaders, signal,
          body: JSON.stringify({ batch_id: batchId, filename: file.name, file_size: file.size, total_chunks: totalChunks }),
        });
        if (!initRes.ok) {
          const err = await initRes.json().catch(() => ({ detail: `Server error ${initRes.status}` }));
          throw new Error(err.detail || `Failed to initialize upload (${initRes.status})`);
        }
        const initData = await initRes.json();
        upload_id = initData.upload_id;
      }

      // Store upload_id so it can be used for resume
      _lastUploadId = upload_id;

      // --- Upload chunks ---
      for (let i = 0; i < totalChunks; i++) {
        if (signal.aborted) throw new Error('Upload cancelled by user.');

        // Skip already-received chunks (resume)
        if (chunksAlreadyReceived.has(i)) {
          const pct = Math.round(((i + 1) / totalChunks) * 100);
          onProgress('uploading', `Chunk ${i + 1}/${totalChunks} already uploaded (skipping)`, pct);
          continue;
        }

        const start = i * CHUNK_SIZE;
        const end = Math.min(start + CHUNK_SIZE, file.size);
        const pct = Math.round(((i + 1) / totalChunks) * 100);
        const sizeMB = ((end - start) / (1024 * 1024)).toFixed(1);

        onProgress('uploading', `Uploading chunk ${i + 1}/${totalChunks} (${pct}%) — ${sizeMB}MB`, pct);

        let retries = 0;
        let chunkSuccess = false;

        while (retries < MAX_RETRIES && !chunkSuccess) {
          if (signal.aborted) throw new Error('Upload cancelled by user.');
          try {
            // CRITICAL: Re-slice for each attempt — blob is consumed by FormData/fetch
            const chunkBlob = file.slice(start, end);
            if (chunkBlob.size === 0) {
              throw new Error(`Chunk ${i} sliced to 0 bytes (file may be stale). Re-select the file.`);
            }

            const chunkForm = new FormData();
            chunkForm.append('file', chunkBlob, `chunk_${i}`);
            const chunkHeaders: Record<string, string> = {};
            if (authToken) chunkHeaders['Authorization'] = `Bearer ${authToken}`;

            // Per-chunk timeout
            const chunkAbort = new AbortController();
            const chunkTimer = setTimeout(() => chunkAbort.abort(), CHUNK_TIMEOUT_MS);
            const onMainAbort = () => chunkAbort.abort();
            signal.addEventListener('abort', onMainAbort, { once: true });

            try {
              const chunkRes = await fetch(`${API_BASE}/pdf-upload/${upload_id}/chunk?chunk_index=${i}`, {
                method: 'POST', headers: chunkHeaders, body: chunkForm, signal: chunkAbort.signal,
              });
              clearTimeout(chunkTimer);
              signal.removeEventListener('abort', onMainAbort);

              if (!chunkRes.ok) {
                const err = await chunkRes.json().catch(() => ({ detail: 'Chunk upload failed' }));
                throw new Error(err.detail || `Chunk ${i} failed (${chunkRes.status})`);
              }
              chunkSuccess = true;
            } catch (innerE: any) {
              clearTimeout(chunkTimer);
              signal.removeEventListener('abort', onMainAbort);
              throw innerE;
            }
          } catch (e: any) {
            if (signal.aborted) throw new Error('Upload cancelled by user.');
            retries++;
            if (retries >= MAX_RETRIES) {
              const uploadedMB = (start / (1024 * 1024)).toFixed(0);
              const totalMB = (file.size / (1024 * 1024)).toFixed(0);
              if (e.name === 'AbortError') {
                throw new Error(
                  `Chunk ${i + 1}/${totalChunks} timed out after ${CHUNK_TIMEOUT_MS / 1000}s.\n` +
                  `Uploaded: ${uploadedMB}MB of ${totalMB}MB.\n` +
                  `Your connection may be too slow. Try again — upload will resume from chunk ${i + 1}.`
                );
              }
              throw new Error(
                `Failed to upload chunk ${i + 1}/${totalChunks} after ${MAX_RETRIES} attempts.\n` +
                `Uploaded: ${uploadedMB}MB of ${totalMB}MB.\n` +
                `Error: ${e.message}\n` +
                `Try again — upload will resume from where it stopped.`
              );
            }
            // Exponential backoff: 2s, 4s, 8s, 12s, 15s
            const delay = Math.min(2000 * Math.pow(2, retries - 1), 15000);
            onProgress('uploading', `Chunk ${i + 1} failed (attempt ${retries}/${MAX_RETRIES}), retrying in ${(delay / 1000).toFixed(0)}s...`, pct);
            await new Promise(r => setTimeout(r, delay));
          }
        }
      }

      // --- Signal complete ---
      if (signal.aborted) throw new Error('Upload cancelled by user.');
      onProgress('processing', 'Upload complete. Assembling PDF and starting page extraction...', 100);
      const completeHeaders: Record<string, string> = {};
      if (authToken) completeHeaders['Authorization'] = `Bearer ${authToken}`;
      const completeRes = await fetch(`${API_BASE}/pdf-upload/${upload_id}/complete`, {
        method: 'POST', headers: completeHeaders, signal,
      });
      if (!completeRes.ok) {
        const err = await completeRes.json().catch(() => ({ detail: `Server error ${completeRes.status}` }));
        throw new Error(err.detail || `Failed to start processing (${completeRes.status})`);
      }

      // --- Poll for processing ---
      return await _pollProcessing(upload_id, onProgress, signal);

    } finally {
      _uploadAbortController = null;
    }
  },

  // Legacy single-shot import
  importPdf: async (path: string, file: File, onProgress?: (phase: string, detail: string) => void) => {
    const maxSize = 1000 * 1024 * 1024;
    if (file.size > maxSize) throw new Error(`PDF too large (${(file.size / (1024 * 1024)).toFixed(0)}MB). Max 1000MB.`);
    if (!file.name.toLowerCase().endsWith('.pdf')) throw new Error('Please select a PDF file (.pdf).');
    onProgress?.('uploading', `Uploading ${(file.size / (1024 * 1024)).toFixed(1)}MB PDF...`);
    const formData = new FormData();
    formData.append('file', file);
    const headers: Record<string, string> = {};
    if (authToken) headers['Authorization'] = `Bearer ${authToken}`;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 1800000);
    try {
      const res = await fetch(`${API_BASE}${path}`, { method: 'POST', headers, body: formData, signal: controller.signal });
      clearTimeout(timeoutId);
      if (!res.ok) { const err = await res.json().catch(() => ({ detail: `Server error ${res.status}` })); throw new Error(err.detail || `Error ${res.status}`); }
      onProgress?.('processing', 'Extracting pages...');
      return await res.json();
    } catch (e: any) {
      clearTimeout(timeoutId);
      if (e.name === 'AbortError') throw new Error('Upload timed out.');
      if (e.message?.includes('Failed to fetch')) throw new Error(`Network error. File: ${(file.size / (1024 * 1024)).toFixed(1)}MB.`);
      throw e;
    }
  },
};

// Track last upload_id for resume
let _lastUploadId: string | null = null;
export const getLastUploadId = () => _lastUploadId;
export const clearLastUploadId = () => { _lastUploadId = null; };

async function _pollProcessing(
  upload_id: string,
  onProgress: (phase: 'validating' | 'uploading' | 'processing' | 'done' | 'error', detail: string, progress?: number) => void,
  signal: AbortSignal,
): Promise<any> {
  const pollHeaders: Record<string, string> = {};
  if (authToken) pollHeaders['Authorization'] = `Bearer ${authToken}`;

  let pollCount = 0;
  const maxPolls = 1800;
  while (pollCount < maxPolls) {
    if (signal.aborted) throw new Error('Cancelled by user during processing.');
    await new Promise(r => setTimeout(r, 1500));
    pollCount++;
    try {
      const statusRes = await fetch(`${API_BASE}/pdf-upload/${upload_id}/status`, { headers: pollHeaders });
      if (!statusRes.ok) continue;
      const status = await statusRes.json();
      if (status.upload_status === 'processing') {
        const pagesProgress = status.total_pages > 0 ? Math.round((status.pages_processed / status.total_pages) * 100) : 0;
        onProgress('processing', `Processing page ${status.pages_processed}/${status.total_pages} (${status.imported} imported, ${status.failed} failed)`, pagesProgress);
      } else if (status.upload_status === 'done') {
        onProgress('done', `Complete! ${status.imported} pages imported.`, 100);
        return status;
      } else if (status.upload_status === 'error') {
        throw new Error(status.error || 'PDF processing failed on the server.');
      }
    } catch (e: any) {
      if (e.message?.includes('processing failed') || e.message?.includes('Cancelled')) throw e;
    }
  }
  throw new Error('PDF processing timed out after 30 minutes.');
}

export const getImageUrl = (product: any, thumbnail = true): string => {
  if (thumbnail && product?.thumbnail_path) return `${API_BASE}/files/${product.thumbnail_path}`;
  if (product?.storage_path) return `${API_BASE}/files/${product.storage_path}`;
  return product?.images?.[0] || '';
};
