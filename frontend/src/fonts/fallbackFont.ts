/**
 * Last-resort Ionicons source: the exact version-matched file served by our own backend at a
 * fixed path. Only used after the bundled asset failed. Every response is validated (HTTP status,
 * content type, byte length, SHA-256) BEFORE the font loader ever sees it, so an HTML error page,
 * a truncated download or a foreign file can never be registered as the icon font.
 *
 * Native: the validated bytes live in an app-owned cache file (Paths.cache/icon-fonts). Only that
 * file is ever replaced; Expo Go's own update cache and other app data are never touched.
 */
import { Platform } from 'react-native';
import { Directory, File, Paths } from 'expo-file-system';
import { sha256 } from '@noble/hashes/sha2';
import { bytesToHex } from '@noble/hashes/utils';
import manifest from './ionicons.manifest.json';

export const IONICONS_MANIFEST = manifest as { family: string; file: string; bytes: number; sha256: string; md5: string; source_version: string };
export const FALLBACK_PATH = '/api/fonts/ionicons.ttf';

export function validateFontBytes(bytes: Uint8Array, contentType: string | null | undefined): void {
  if (bytes.byteLength === 0) throw new Error('FALLBACK_EMPTY: zero-byte response');
  if ((contentType || '').toLowerCase().includes('text/html')) throw new Error('FALLBACK_HTML: server returned an HTML page instead of the font');
  const head = String.fromCharCode(...bytes.slice(0, 5));
  if (head.startsWith('<') || head.toLowerCase().startsWith('<!doc')) throw new Error('FALLBACK_HTML: body looks like markup');
  if (bytes.byteLength !== IONICONS_MANIFEST.bytes) throw new Error(`FALLBACK_SIZE: expected ${IONICONS_MANIFEST.bytes} bytes, received ${bytes.byteLength}`);
  const digest = bytesToHex(sha256(bytes));
  if (digest !== IONICONS_MANIFEST.sha256) throw new Error('FALLBACK_HASH: SHA-256 mismatch');
}

async function fetchValidated(url: string): Promise<Uint8Array> {
  const response = await fetch(url, { headers: { Accept: 'font/ttf, application/octet-stream' } });
  if (!response.ok) throw new Error(`FALLBACK_HTTP_${response.status}`);
  const bytes = new Uint8Array(await response.arrayBuffer());
  validateFontBytes(bytes, response.headers.get('content-type'));
  return bytes;
}

async function nativeFallback(url: string): Promise<{ uri: string }> {
  const directory = new Directory(Paths.cache, 'icon-fonts');
  directory.create({ intermediates: true, idempotent: true });
  const file = new File(directory, `Ionicons-${IONICONS_MANIFEST.sha256.slice(0, 16)}.ttf`);
  if (file.exists) {
    try {
      validateFontBytes(await file.bytes(), 'font/ttf');
      return { uri: file.uri };
    } catch {
      file.delete(); // corrupt app-owned copy: replace it, nothing else
    }
  }
  const bytes = await fetchValidated(url);
  const staging = new File(directory, `Ionicons-${IONICONS_MANIFEST.sha256.slice(0, 16)}.download`);
  if (staging.exists) staging.delete();
  staging.create();
  staging.write(bytes);
  validateFontBytes(await staging.bytes(), 'font/ttf');
  if (file.exists) file.delete();
  staging.move(file);
  return { uri: file.uri };
}

async function webFallback(url: string): Promise<{ uri: string }> {
  const bytes = await fetchValidated(url);
  const copy = new Uint8Array(new ArrayBuffer(bytes.byteLength));
  copy.set(bytes);
  return { uri: URL.createObjectURL(new Blob([copy], { type: 'font/ttf' })) };
}

/** Returns undefined when no backend URL is configured: startup never depends on this route. */
export function createFallbackFetcher(backendUrl: string | undefined, platform: string = Platform.OS): (() => Promise<{ uri: string }>) | undefined {
  if (!backendUrl) return undefined;
  const url = `${backendUrl.replace(/\/$/, '')}${FALLBACK_PATH}`;
  return () => (platform === 'web' ? webFallback(url) : nativeFallback(url));
}
