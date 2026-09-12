const config = require('./app.json').expo;
// Metro's supported explicit origin allowlist, only for the embedded development preview.
// Never change the native production asset/fetch origin or relax the website BFF's CSRF rules.
const previewOrigin = process.env.NODE_ENV === 'development' ? process.env.EXPO_DEVTOOLS_ORIGIN : undefined;

// Canonical production backend origin for RELEASE builds (Emergent Publish web export and iOS/Android store
// builds evaluate this file with NODE_ENV=production). Development (Metro preview) keeps EXPO_PUBLIC_BACKEND_URL.
// A preview-container origin (*.preview.emergentagent.com) or an empty value is never shipped in a release.
const PRODUCTION_BACKEND_URL = 'https://yash-tryon-test.emergent.host';
const isPreviewOrigin = (url) => /^https?:\/\/[^/]+\.preview\.emergentagent\.com\/?$/i.test(url || '');

function resolveBackendUrl(env) {
  const configured = (env.EXPO_PUBLIC_BACKEND_URL || '').trim().replace(/\/+$/, '');
  if (env.NODE_ENV !== 'production') return configured;
  const production = (env.EXPO_PUBLIC_PRODUCTION_BACKEND_URL || PRODUCTION_BACKEND_URL).trim().replace(/\/+$/, '');
  return !configured || isPreviewOrigin(configured) ? production : configured;
}

module.exports = {
  ...config,
  extra: {
    ...config.extra,
    router: { ...config.extra?.router, ...(previewOrigin ? { origin: previewOrigin } : {}) },
    backendUrl: resolveBackendUrl(process.env),
    enrollmentUrl: process.env.EXPO_PUBLIC_ENROLLMENT_URL || process.env.EXPO_PUBLIC_REGISTRATION_URL,
  },
};
