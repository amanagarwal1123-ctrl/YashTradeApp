import * as fs from 'fs';
import * as path from 'path';
import { createFallbackFetcher, IONICONS_MANIFEST, validateFontBytes } from '../fallbackFont';

const REAL_FONT = path.resolve(__dirname, '../../../node_modules/@expo/vector-icons/build/vendor/react-native-vector-icons/Fonts/Ionicons.ttf');
const realBytes = () => new Uint8Array(fs.readFileSync(REAL_FONT));

describe('fallback font validation (before anything reaches the font loader)', () => {
  it('accepts only the exact version-matched Ionicons.ttf', () => {
    const bytes = realBytes();
    expect(bytes.byteLength).toBe(IONICONS_MANIFEST.bytes);
    expect(() => validateFontBytes(bytes, 'font/ttf')).not.toThrow();
  });

  it('rejects an empty file (the reproduced device symptom)', () => {
    expect(() => validateFontBytes(new Uint8Array(0), 'font/ttf')).toThrow('FALLBACK_EMPTY');
  });

  it('rejects an HTML error page by content type or body', () => {
    const html = new TextEncoder().encode('<!DOCTYPE html><title>Unauthorized asset request</title>');
    expect(() => validateFontBytes(html, 'text/html; charset=utf-8')).toThrow('FALLBACK_HTML');
    expect(() => validateFontBytes(html, 'font/ttf')).toThrow('FALLBACK_HTML');
  });

  it('rejects truncated and tampered bytes', () => {
    expect(() => validateFontBytes(realBytes().slice(0, 1724), 'font/ttf')).toThrow('FALLBACK_SIZE');
    const tampered = realBytes();
    tampered[1000] ^= 0xff;
    expect(() => validateFontBytes(tampered, 'font/ttf')).toThrow('FALLBACK_HASH');
  });
});

describe('fallback fetcher', () => {
  const originalFetch = global.fetch;
  afterEach(() => { global.fetch = originalFetch; });

  it('is disabled when no backend URL is configured, so startup never depends on it', () => {
    expect(createFallbackFetcher(undefined)).toBeUndefined();
    expect(createFallbackFetcher('')).toBeUndefined();
  });

  it('refuses a 403 HTML CDN-style response', async () => {
    global.fetch = jest.fn(async () => new Response('<html>Unauthorized asset request</html>', { status: 403, headers: { 'content-type': 'text/html' } })) as any;
    await expect(createFallbackFetcher('https://backend.test/', 'web')!()).rejects.toThrow('FALLBACK_HTTP_403');
    expect((global.fetch as jest.Mock).mock.calls[0][0]).toBe('https://backend.test/api/fonts/ionicons.ttf');
  });

  it('refuses a 200 response whose body is not the font', async () => {
    global.fetch = jest.fn(async () => new Response('<!doctype html>', { status: 200, headers: { 'content-type': 'text/html' } })) as any;
    await expect(createFallbackFetcher('https://backend.test', 'web')!()).rejects.toThrow('FALLBACK_HTML');
  });

  it('returns a loadable URI only for validated bytes (web path)', async () => {
    global.fetch = jest.fn(async () => new Response(realBytes(), { status: 200, headers: { 'content-type': 'font/ttf' } })) as any;
    const created: string[] = [];
    (global as any).URL.createObjectURL = jest.fn(() => { created.push('blob:validated'); return 'blob:validated'; });
    await expect(createFallbackFetcher('https://backend.test', 'web')!()).resolves.toEqual({ uri: 'blob:validated' });
    expect(created).toHaveLength(1);
  });

  it('native path: replaces ONLY the corrupt app-owned cache file and validates the staged download before use', async () => {
    const store = mockFileSystem({ 'Ionicons-fa2ab7d2557819b2.ttf': new Uint8Array(0) }); // reproduced empty-file state
    global.fetch = jest.fn(async () => new Response(realBytes(), { status: 200, headers: { 'content-type': 'font/ttf' } })) as any;
    const result = await createFallbackFetcher('https://backend.test', 'android')!();
    expect(result.uri).toBe('file:///cache/icon-fonts/Ionicons-fa2ab7d2557819b2.ttf');
    expect(store.deleted).toEqual(['file:///cache/icon-fonts/Ionicons-fa2ab7d2557819b2.ttf']);
    expect(store.files['file:///cache/icon-fonts/Ionicons-fa2ab7d2557819b2.ttf']!.byteLength).toBe(IONICONS_MANIFEST.bytes);
    expect(store.files['file:///cache/icon-fonts/Ionicons-fa2ab7d2557819b2.download']).toBeUndefined();
    // Second run reuses the validated copy without any network (offline-capable after one recovery).
    (global.fetch as jest.Mock).mockClear();
    await expect(createFallbackFetcher('https://backend.test', 'android')!()).resolves.toEqual(result);
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it('native path: a truncated download is never promoted to the font file', async () => {
    const store = mockFileSystem({});
    global.fetch = jest.fn(async () => new Response(realBytes().slice(0, 1000), { status: 200, headers: { 'content-type': 'font/ttf' } })) as any;
    await expect(createFallbackFetcher('https://backend.test', 'android')!()).rejects.toThrow('FALLBACK_SIZE');
    expect(store.files['file:///cache/icon-fonts/Ionicons-fa2ab7d2557819b2.ttf']).toBeUndefined();
  });
});

/** In-memory stand-in for the expo-file-system File/Directory API surface used by the fallback. */
function mockFileSystem(initial: Record<string, Uint8Array>) {
  const fsMock = jest.requireMock('expo-file-system') as any;
  const files: Record<string, Uint8Array | undefined> = {};
  for (const [name, bytes] of Object.entries(initial)) files[`file:///cache/icon-fonts/${name}`] = bytes;
  const deleted: string[] = [];
  fsMock.__store = { files, deleted };
  return fsMock.__store as { files: Record<string, Uint8Array | undefined>; deleted: string[] };
}

jest.mock('expo-file-system', () => {
  const mod: any = { __store: { files: {}, deleted: [] } };
  class Directory {
    uri: string;
    constructor(...parts: any[]) { this.uri = parts.map((p) => (typeof p === 'string' ? p : p.uri)).join('/'); }
    create() { /* idempotent */ }
  }
  class File {
    uri: string;
    constructor(...parts: any[]) { this.uri = parts.map((p) => (typeof p === 'string' ? p : p.uri)).join('/'); }
    get exists() { return mod.__store.files[this.uri] !== undefined; }
    async bytes() { return mod.__store.files[this.uri]; }
    delete() { mod.__store.deleted.push(this.uri); delete mod.__store.files[this.uri]; }
    create() { mod.__store.files[this.uri] = new Uint8Array(0); }
    write(content: Uint8Array) { mod.__store.files[this.uri] = content; }
    move(destination: File) { mod.__store.files[destination.uri] = mod.__store.files[this.uri]; delete mod.__store.files[this.uri]; this.uri = destination.uri; }
  }
  mod.Directory = Directory; mod.File = File; mod.Paths = { cache: 'file:///cache' };
  return mod;
});
