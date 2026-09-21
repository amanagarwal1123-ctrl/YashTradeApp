/**
 * First-open notification prompt bookkeeping (owner decision 21 Sep 2026): the OS dialog is preceded by an in-app card
 * exactly once per install, only while the OS has not decided yet; every later launch is silent. `requestPermission`
 * asks the OS only while it still allows asking and never registers a token by itself.
 */
const mockGetPermissions = jest.fn();
const mockRequestPermissions = jest.fn();
jest.mock('expo-notifications', () => ({
  getPermissionsAsync: (...args: any[]) => mockGetPermissions(...args),
  requestPermissionsAsync: (...args: any[]) => mockRequestPermissions(...args),
  setNotificationHandler: jest.fn(),
  setNotificationChannelAsync: jest.fn(async () => {}),
  getExpoPushTokenAsync: jest.fn(async () => ({ data: 'ExponentPushToken[test]' })),
  AndroidImportance: { HIGH: 4, DEFAULT: 3 },
}));
jest.mock('expo-device', () => ({ isDevice: true, modelName: 'Unit Phone' }));
jest.mock('expo-constants', () => ({ __esModule: true, default: { expoConfig: { version: '1.0.0', extra: {} } } }));
jest.mock('expo-secure-store', () => ({ getItemAsync: jest.fn(async () => null), setItemAsync: jest.fn(async () => {}), deleteItemAsync: jest.fn(async () => {}) }));
jest.mock('@react-native-async-storage/async-storage', () => require('@react-native-async-storage/async-storage/jest/async-storage-mock'));
jest.mock('../api', () => ({ api: { post: jest.fn(async () => ({})) } }));

// eslint-disable-next-line import/first
import AsyncStorage from '@react-native-async-storage/async-storage';
// eslint-disable-next-line import/first
import { firstOpenPromptDue, markFirstOpenPromptSeen, requestPermission } from '../push';

const undetermined = { granted: false, status: 'undetermined', canAskAgain: true };
const denied = (canAskAgain: boolean) => ({ granted: false, status: 'denied', canAskAgain });
const granted = { granted: true, status: 'granted', canAskAgain: true };

beforeEach(async () => {
  await AsyncStorage.clear();
  mockGetPermissions.mockReset();
  mockRequestPermissions.mockReset();
});

describe('first-open prompt is due exactly once, before the OS has decided', () => {
  it('is due on a fresh install while the OS permission is undetermined', async () => {
    mockGetPermissions.mockResolvedValue(undetermined);
    expect(await firstOpenPromptDue()).toBe(true);
    expect(await AsyncStorage.getItem('notif_prompt_seen')).toBeNull(); // only the user's answer marks it seen
  });

  it('is never due again once the card was answered (Continue or Not now)', async () => {
    mockGetPermissions.mockResolvedValue(undetermined);
    await markFirstOpenPromptSeen();
    expect(await firstOpenPromptDue()).toBe(false);
    expect(mockGetPermissions).not.toHaveBeenCalled();
  });

  it('is not due when the OS already decided (granted / denied / blocked) and records that silently', async () => {
    for (const current of [granted, denied(true), denied(false)]) {
      await AsyncStorage.clear();
      mockGetPermissions.mockResolvedValue(current);
      expect(await firstOpenPromptDue()).toBe(false);
      expect(await AsyncStorage.getItem('notif_prompt_seen')).not.toBeNull();
    }
  });
});

describe('requestPermission asks the OS only while it still allows asking', () => {
  it('undetermined → OS dialog → granted', async () => {
    mockGetPermissions.mockResolvedValue(undetermined);
    mockRequestPermissions.mockResolvedValue(granted);
    expect(await requestPermission()).toBe('granted');
    expect(mockRequestPermissions).toHaveBeenCalledTimes(1);
  });

  it('a denial that may be asked again is "denied"; a final denial is "blocked"', async () => {
    mockGetPermissions.mockResolvedValue(undetermined);
    mockRequestPermissions.mockResolvedValueOnce(denied(true));
    expect(await requestPermission()).toBe('denied');
    mockRequestPermissions.mockResolvedValueOnce(denied(false));
    expect(await requestPermission()).toBe('blocked');
  });

  it('never calls the OS dialog when it would not be shown (already granted, or blocked → Settings)', async () => {
    mockGetPermissions.mockResolvedValueOnce(granted);
    expect(await requestPermission()).toBe('granted');
    mockGetPermissions.mockResolvedValueOnce(denied(false));
    expect(await requestPermission()).toBe('blocked');
    expect(mockRequestPermissions).not.toHaveBeenCalled();
  });
});
