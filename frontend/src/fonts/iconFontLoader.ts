/**
 * Icon-font loading state machine. Pure logic with injected side effects so the exact production
 * failure ("Font file for ionicons is empty…", timeouts, offline) can be reproduced in tests.
 *
 * Order of every load cycle: bundled asset -> (on failure) validated last-resort fallback.
 * Retries are bounded and single-flight; a retry ALWAYS re-runs the real loaders (changing a
 * useFonts map alone would not reload anything).
 */
export type LoadOutcome =
  | { ok: true; source: 'already-loaded' | 'bundled' | 'fallback'; attempts: number }
  | { ok: false; stage: 'bundled' | 'fallback' | 'timeout'; message: string; fallbackTried: boolean; attempts: number };

export interface IconFontLoaderDeps {
  family: string;
  isLoaded: (family: string) => boolean;
  loadBundled: () => Promise<void>;
  /** Downloads + validates the fallback and returns a local/blob URI; must throw on any doubt. */
  fetchFallback?: () => Promise<{ uri: string }>;
  loadFromUri: (family: string, uri: string) => Promise<void>;
  timeoutMs: number;
  autoRetries: number;
  retryDelayMs: number;
  sleep?: (ms: number) => Promise<void>;
  onEvent?: (event: string, detail?: string) => void;
}

const describe = (error: unknown) => (error instanceof Error ? error.message : String(error)).slice(0, 300);

export function withTimeout<T>(promise: Promise<T>, ms: number, label: string): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`TIMEOUT: ${label} exceeded ${ms}ms`)), ms);
    promise.then(
      (value) => { clearTimeout(timer); resolve(value); },
      (error) => { clearTimeout(timer); reject(error); },
    );
  });
}

export function createIconFontLoader(deps: IconFontLoaderDeps) {
  const sleep = deps.sleep ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)));
  let inflight: Promise<LoadOutcome> | null = null;
  let cycles = 0;
  let manualRetries = 0;

  async function attempt(attemptNumber: number): Promise<LoadOutcome> {
    if (deps.isLoaded(deps.family)) return { ok: true, source: 'already-loaded', attempts: attemptNumber };
    let bundledMessage = '';
    try {
      await withTimeout(deps.loadBundled(), deps.timeoutMs, 'bundled icon font');
      return { ok: true, source: 'bundled', attempts: attemptNumber };
    } catch (error) {
      bundledMessage = describe(error);
      deps.onEvent?.('bundled-failed', bundledMessage);
    }
    if (!deps.fetchFallback) {
      return { ok: false, stage: bundledMessage.startsWith('TIMEOUT') ? 'timeout' : 'bundled', message: bundledMessage, fallbackTried: false, attempts: attemptNumber };
    }
    try {
      const { uri } = await withTimeout(deps.fetchFallback(), deps.timeoutMs, 'fallback icon font download');
      await withTimeout(deps.loadFromUri(deps.family, uri), deps.timeoutMs, 'fallback icon font load');
      deps.onEvent?.('fallback-loaded');
      return { ok: true, source: 'fallback', attempts: attemptNumber };
    } catch (error) {
      const message = describe(error);
      deps.onEvent?.('fallback-failed', message);
      return { ok: false, stage: message.startsWith('TIMEOUT') ? 'timeout' : 'fallback', message: `${bundledMessage} | fallback: ${message}`, fallbackTried: true, attempts: attemptNumber };
    }
  }

  async function cycle(): Promise<LoadOutcome> {
    let outcome: LoadOutcome = { ok: false, stage: 'bundled', message: 'not started', fallbackTried: false, attempts: 0 };
    for (let n = 0; n <= deps.autoRetries; n += 1) {
      cycles += 1;
      outcome = await attempt(cycles);
      if (outcome.ok) return outcome;
      if (n < deps.autoRetries) await sleep(deps.retryDelayMs);
    }
    return outcome;
  }

  function run(): Promise<LoadOutcome> {
    if (!inflight) {
      inflight = cycle().finally(() => { inflight = null; });
    }
    return inflight;
  }

  return {
    /** Initial load; concurrent callers share one in-flight promise. */
    load: run,
    /** Deliberate user retry; also single-flight and counted. */
    retry: () => { if (!inflight) manualRetries += 1; return run(); },
    isInFlight: () => inflight !== null,
    stats: () => ({ cycles, manualRetries }),
  };
}
