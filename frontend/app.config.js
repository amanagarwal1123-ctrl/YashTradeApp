const config = require('./app.json').expo;
// Metro's supported explicit origin allowlist, only for the embedded development preview.
// Never change the native production asset/fetch origin or relax the website BFF's CSRF rules.
const previewOrigin = process.env.NODE_ENV === 'development' ? process.env.EXPO_DEVTOOLS_ORIGIN : undefined;

// Backend origin for RELEASE builds (Emergent Publish web export and iOS/Android store builds evaluate this file with
// NODE_ENV=production). Resolved ONLY from EXPO_PUBLIC_* environment supplied at build time: the deployment pipeline
// rewrites EXPO_PUBLIC_BACKEND_URL to the production host; EXPO_PUBLIC_PRODUCTION_BACKEND_URL (frontend/.env) is the
// release fallback so a preview-container origin (*.preview.emergentagent.com) is never shipped in a release.
// Development (Metro preview) keeps EXPO_PUBLIC_BACKEND_URL untouched. No backend host is hardcoded in source.
const isPreviewOrigin = (url) => /^https?:\/\/[^/]+\.preview\.emergentagent\.com\/?$/i.test(url || '');

function resolveBackendUrl(env) {
  const configured = (env.EXPO_PUBLIC_BACKEND_URL || '').trim().replace(/\/+$/, '');
  if (env.NODE_ENV !== 'production') return configured;
  const production = (env.EXPO_PUBLIC_PRODUCTION_BACKEND_URL || '').trim().replace(/\/+$/, '');
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
