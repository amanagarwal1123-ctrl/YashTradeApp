const { withXcodeProject } = require('@expo/config-plugins');

const NSE_TARGET_NAME = 'NotificationServiceExtension';
const DEVELOPMENT_TEAM = '9SJ8BYBLVW';

// expo-rich-notifications' config plugin creates this target with
// CODE_SIGN_STYLE=Automatic and never sets DEVELOPMENT_TEAM, which EAS's
// headless build machines can't resolve interactively -> archive fails with
// "Signing for NotificationServiceExtension requires a development team."
// This plugin must run after expo-rich-notifications in app.json's plugins
// array so the target already exists when it patches the build settings.
const withNSEDevelopmentTeam = (config) => {
  return withXcodeProject(config, (config) => {
    const xcodeProject = config.modResults;
    const configurations = xcodeProject.pbxXCBuildConfigurationSection();

    for (const key in configurations) {
      const entry = configurations[key];
      if (
        typeof entry === 'object' &&
        entry.buildSettings &&
        entry.buildSettings.PRODUCT_NAME === `"${NSE_TARGET_NAME}"`
      ) {
        entry.buildSettings.DEVELOPMENT_TEAM = DEVELOPMENT_TEAM;
        entry.buildSettings.CODE_SIGN_STYLE = '"Automatic"';
      }
    }

    return config;
  });
};

module.exports = withNSEDevelopmentTeam;
