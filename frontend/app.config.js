const config = require('./app.json').expo;

module.exports = {
  ...config,
  extra: {
    ...config.extra,
    backendUrl: process.env.EXPO_PUBLIC_BACKEND_URL,
    enrollmentUrl: process.env.EXPO_PUBLIC_ENROLLMENT_URL || process.env.EXPO_PUBLIC_REGISTRATION_URL,
  },
};