import { createIconFontLoader, withTimeout } from '../iconFontLoader';

const ANDROID_EMPTY = 'Font file for ionicons is empty. Make sure the local file path is correctly populated.';

function deps(overrides: Partial<Parameters<typeof createIconFontLoader>[0]> = {}) {
  return {
    family: 'ionicons',
    isLoaded: jest.fn(() => false),
    loadBundled: jest.fn(async () => undefined),
    loadFromUri: jest.fn(async () => undefined),
    fetchFallback: jest.fn(async () => ({ uri: 'file:///cache/icon-fonts/Ionicons.ttf' })),
    timeoutMs: 500,
    autoRetries: 1,
    retryDelayMs: 0,
    sleep: jest.fn(async () => undefined),
    ...overrides,
  };
}

describe('icon font loader state machine', () => {
  it('loads the bundled font map on the happy path', async () => {
    const d = deps();
    const outcome = await createIconFontLoader(d).load();
    expect(outcome).toEqual({ ok: true, source: 'bundled', attempts: 1 });
    expect(d.loadBundled).toHaveBeenCalledTimes(1);
    expect(d.fetchFallback).not.toHaveBeenCalled();
  });

  it('does not reload a family that the native loader already registered', async () => {
    const d = deps({ isLoaded: jest.fn(() => true) });
    const outcome = await createIconFontLoader(d).load();
    expect(outcome).toEqual({ ok: true, source: 'already-loaded', attempts: 1 });
    expect(d.loadBundled).not.toHaveBeenCalled();
  });

  it('recovers from the reproduced Android "font file is empty" rejection through the validated fallback', async () => {
    const d = deps({ loadBundled: jest.fn(async () => { throw new Error(ANDROID_EMPTY); }) });
    const outcome = await createIconFontLoader(d).load();
    expect(outcome).toEqual({ ok: true, source: 'fallback', attempts: 1 });
    expect(d.loadFromUri).toHaveBeenCalledWith('ionicons', 'file:///cache/icon-fonts/Ionicons.ttf');
  });

  it('reports a bounded, caught failure when both sources fail (offline) instead of looping', async () => {
    const d = deps({
      loadBundled: jest.fn(async () => { throw new Error(ANDROID_EMPTY); }),
      fetchFallback: jest.fn(async () => { throw new Error('FALLBACK_HTTP_0: Network request failed'); }),
    });
    const outcome = await createIconFontLoader(d).load();
    expect(outcome.ok).toBe(false);
    if (!outcome.ok) {
      expect(outcome.stage).toBe('fallback');
      expect(outcome.fallbackTried).toBe(true);
      expect(outcome.attempts).toBe(2); // initial + exactly one automatic retry
      expect(outcome.message).toContain('Font file for ionicons is empty');
      expect(outcome.message).toContain('Network request failed');
    }
    expect(d.loadBundled).toHaveBeenCalledTimes(2);
    expect(d.fetchFallback).toHaveBeenCalledTimes(2);
    expect(d.sleep).toHaveBeenCalledTimes(1);
  });

  it('rejects an invalid fallback (HTML / truncated / hash mismatch) and never registers it', async () => {
    const d = deps({
      loadBundled: jest.fn(async () => { throw new Error(ANDROID_EMPTY); }),
      fetchFallback: jest.fn(async () => { throw new Error('FALLBACK_HTML: server returned an HTML page instead of the font'); }),
      autoRetries: 0,
    });
    const outcome = await createIconFontLoader(d).load();
    expect(outcome.ok).toBe(false);
    expect(d.loadFromUri).not.toHaveBeenCalled();
  });

  it('classifies a hanging native loader as a timeout instead of an infinite splash', async () => {
    const d = deps({ loadBundled: jest.fn(() => new Promise<void>(() => undefined)), fetchFallback: undefined, timeoutMs: 20, autoRetries: 0 });
    const outcome = await createIconFontLoader(d).load();
    expect(outcome.ok).toBe(false);
    if (!outcome.ok) expect(outcome.stage).toBe('timeout');
  });

  it('is single-flight: concurrent callers share one attempt', async () => {
    let release: () => void = () => undefined;
    const d = deps({ loadBundled: jest.fn(() => new Promise<void>((resolve) => { release = resolve; })) });
    const loader = createIconFontLoader(d);
    const a = loader.load();
    const b = loader.load();
    const c = loader.retry();
    expect(loader.isInFlight()).toBe(true);
    release();
    const results = await Promise.all([a, b, c]);
    expect(results.every((r) => r.ok)).toBe(true);
    expect(d.loadBundled).toHaveBeenCalledTimes(1);
    expect(loader.stats()).toEqual({ cycles: 1, manualRetries: 0 });
  });

  it('a deliberate retry genuinely re-runs the loaders and can succeed after a failure', async () => {
    let calls = 0;
    const d = deps({
      loadBundled: jest.fn(async () => { calls += 1; if (calls <= 2) throw new Error(ANDROID_EMPTY); }),
      fetchFallback: jest.fn(async () => { throw new Error('FALLBACK_HTTP_503'); }),
    });
    const loader = createIconFontLoader(d);
    const first = await loader.load();
    expect(first.ok).toBe(false);
    const second = await loader.retry();
    expect(second).toEqual({ ok: true, source: 'bundled', attempts: 3 });
    expect(d.loadBundled).toHaveBeenCalledTimes(3);
    expect(loader.stats()).toEqual({ cycles: 3, manualRetries: 1 });
  });
});

describe('withTimeout', () => {
  it('resolves before the deadline and rejects after it', async () => {
    await expect(withTimeout(Promise.resolve(1), 50, 'x')).resolves.toBe(1);
    await expect(withTimeout(new Promise(() => undefined), 10, 'slow')).rejects.toThrow('TIMEOUT: slow exceeded 10ms');
  });
});
