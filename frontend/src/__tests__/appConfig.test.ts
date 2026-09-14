/**
 * Release builds (Emergent Publish web export, iOS/Android store builds) evaluate app.config.js with
 * NODE_ENV=production and must resolve the canonical production backend, never the preview container.
 * The Metro development preview keeps EXPO_PUBLIC_BACKEND_URL untouched.
 */
const PREVIEW = 'https://yash-review-deploy.preview.emergentagent.com';
const PRODUCTION = 'https://yash-tryon-test.emergent.host';

function loadConfig(env: Record<string, string | undefined>) {
  const saved = { ...process.env };
  for (const key of ['NODE_ENV', 'EXPO_PUBLIC_BACKEND_URL', 'EXPO_PUBLIC_PRODUCTION_BACKEND_URL', 'EXPO_DEVTOOLS_ORIGIN']) delete process.env[key];
  Object.assign(process.env, env);
  let extra: { backendUrl: string; router?: { origin?: string } } = { backendUrl: '' };
  jest.isolateModules(() => { extra = require('../../app.config.js').extra; });
  process.env = saved;
  return extra;
}

describe('app.config.js backend origin resolution', () => {
  it('development preview uses EXPO_PUBLIC_BACKEND_URL as configured (preview container)', () => {
    expect(loadConfig({ NODE_ENV: 'development', EXPO_PUBLIC_BACKEND_URL: PREVIEW }).backendUrl).toBe(PREVIEW);
  });

  it('release build never ships a preview-container origin: it resolves to the canonical production backend', () => {
    expect(loadConfig({ NODE_ENV: 'production', EXPO_PUBLIC_BACKEND_URL: PREVIEW }).backendUrl).toBe(PRODUCTION);
    expect(loadConfig({ NODE_ENV: 'production', EXPO_PUBLIC_BACKEND_URL: 'https://yash-review-deploy.preview.emergentagent.com/' }).backendUrl).toBe(PRODUCTION);
    expect(loadConfig({ NODE_ENV: 'production' }).backendUrl).toBe(PRODUCTION);
  });

  it('release build honours an explicit non-preview EXPO_PUBLIC_BACKEND_URL (deployment Secrets) and strips trailing slashes', () => {
    expect(loadConfig({ NODE_ENV: 'production', EXPO_PUBLIC_BACKEND_URL: `${PRODUCTION}/` }).backendUrl).toBe(PRODUCTION);
    expect(loadConfig({ NODE_ENV: 'production', EXPO_PUBLIC_BACKEND_URL: 'https://api.example.com' }).backendUrl).toBe('https://api.example.com');
  });

  it('EXPO_PUBLIC_PRODUCTION_BACKEND_URL overrides the built-in production origin only for release builds', () => {
    expect(loadConfig({ NODE_ENV: 'production', EXPO_PUBLIC_BACKEND_URL: PREVIEW, EXPO_PUBLIC_PRODUCTION_BACKEND_URL: 'https://next.example.com/' }).backendUrl).toBe('https://next.example.com');
    expect(loadConfig({ NODE_ENV: 'development', EXPO_PUBLIC_BACKEND_URL: PREVIEW, EXPO_PUBLIC_PRODUCTION_BACKEND_URL: 'https://next.example.com' }).backendUrl).toBe(PREVIEW);
  });

  it('embedded preview origin allowlist applies to development only', () => {
    expect(loadConfig({ NODE_ENV: 'development', EXPO_PUBLIC_BACKEND_URL: PREVIEW, EXPO_DEVTOOLS_ORIGIN: 'https://devtools.example' }).router?.origin).toBe('https://devtools.example');
    expect(loadConfig({ NODE_ENV: 'production', EXPO_PUBLIC_BACKEND_URL: PRODUCTION, EXPO_DEVTOOLS_ORIGIN: 'https://devtools.example' }).router?.origin).toBeUndefined();
  });
});
