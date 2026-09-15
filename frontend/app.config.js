const config = require('./app.json').expo;
// Metro's supported explicit origin allowlist, only for the embedded development preview.
// Never change the native production asset/fetch origin or relax the website BFF's CSRF rules.
const previewOrigin = process.env.NODE_ENV === 'development' ? process.env.EXPO_DEVTOOLS_ORIGIN : undefined;

// Backend origin for RELEASE builds (Emergent Publish web export and iOS/Android store builds evaluate this file with
// NODE_ENV=production). Order: EXPO_PUBLIC_BACKEND_URL when it is not a preview-container origin (the Android pipeline
// rewrites it to the production host) -> EXPO_PUBLIC_PRODUCTION_BACKEND_URL (frontend/.env) -> app.json
// extra.productionBackendUrl (config; the EAS upload excludes .env* via .easignore, so this is what a store build sees).
// A *.preview.emergentagent.com origin is never shipped in a release. Development keeps EXPO_PUBLIC_BACKEND_URL as is.
const isPreviewOrigin = (url) => /^https?:\/\/[^/]+\.preview\.emergentagent\.com\/?$/i.test(url || '');
const clean = (url) => (url || '').trim().replace(/\/+$/, '');

function resolveBackendUrl(env, fallback = config.extra?.productionBackendUrl) {
  const configured = clean(env.EXPO_PUBLIC_BACKEND_URL);
  if (env.NODE_ENV !== 'production') return configured;
  const production = clean(env.EXPO_PUBLIC_PRODUCTION_BACKEND_URL) || clean(fallback);
  return !configured || isPreviewOrigin(configured) ? production : configured;
}

module.exports = {
  ...config,
  extra: {
    ...config.extra,
    router: { ...config.extra?.router, ...(previewOrigin ? { origin: previewOrigin } : {}) },
    backendUrl: resolveBackendUrl(process.env),
    enrollmentUrl: process.env.EXPO_PUBLIC_ENROLLMENT_URL || process.env.EXPO_PUBLIC_REGISTRATION_URL,
    // Sign-in consent line ("By continuing you agree…"): Terms falls back to the Privacy Policy URL until a Terms page exists.
    privacyUrl: process.env.EXPO_PUBLIC_PRIVACY_URL || '',
    termsUrl: process.env.EXPO_PUBLIC_TERMS_URL || process.env.EXPO_PUBLIC_PRIVACY_URL || '',
  },
};
