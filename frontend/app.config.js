const config = require('./app.json').expo;
// Metro's supported explicit origin allowlist, only for the embedded development preview.
// Never change the native production asset/fetch origin or relax the website BFF's CSRF rules.
const previewOrigin = process.env.NODE_ENV === 'development' ? process.env.EXPO_DEVTOOLS_ORIGIN : undefined;

module.exports = {
  ...config,
  extra: {
    ...config.extra,
    router: { ...config.extra?.router, ...(previewOrigin ? { origin: previewOrigin } : {}) },
    backendUrl: process.env.EXPO_PUBLIC_BACKEND_URL,
    enrollmentUrl: process.env.EXPO_PUBLIC_ENROLLMENT_URL || process.env.EXPO_PUBLIC_REGISTRATION_URL,
  },
};