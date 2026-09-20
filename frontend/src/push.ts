/**
 * Remote push (Expo Push Service via expo-notifications). Permission is requested only after an explicit, contextual
 * moment (never at install), the token is registered against the signed-in account, unlinked on logout, and every
 * notification tap is routed through a role-authorised destination. Nothing here works in Expo Go for remote pushes
 * on Android (SDK 54): a development/production build is required; the web preview has no push at all.
 */
import { Platform } from 'react-native';
import Constants from 'expo-constants';
import * as SecureStore from 'expo-secure-store';
import { api } from './api';

let Notifications: typeof import('expo-notifications') | null = null;
let Device: typeof import('expo-device') | null = null;
try {
  if (Platform.OS !== 'web') {
    Notifications = require('expo-notifications');
    Device = require('expo-device');
  }
} catch { Notifications = null; }

const TOKEN_KEY = 'push_token';
export type PermissionState = 'granted' | 'denied' | 'undetermined' | 'unsupported' | 'blocked';

export const pushSupported = () => Platform.OS !== 'web' && !!Notifications && !!Device?.isDevice;

export async function permissionState(): Promise<{ state: PermissionState; canAskAgain: boolean }> {
  if (!pushSupported()) return { state: 'unsupported', canAskAgain: false };
  const current = await Notifications!.getPermissionsAsync();
  if (current.granted) return { state: 'granted', canAskAgain: current.canAskAgain };
  if (current.status === 'undetermined') return { state: 'undetermined', canAskAgain: true };
  return { state: current.canAskAgain ? 'denied' : 'blocked', canAskAgain: current.canAskAgain };
}

export function configureForeground() {
  if (!Notifications) return;
  Notifications.setNotificationHandler({
    handleNotification: async () => ({ shouldShowBanner: true, shouldShowList: true, shouldPlaySound: true, shouldSetBadge: false } as any),
  });
  if (Platform.OS === 'android') {
    Notifications.setNotificationChannelAsync('operational', { name: 'Customer queries & account', importance: Notifications.AndroidImportance.HIGH, sound: 'default' }).catch(() => {});
    Notifications.setNotificationChannelAsync('marketing', { name: 'Offers & collections', importance: Notifications.AndroidImportance.DEFAULT }).catch(() => {});
  }
}

/** Asks the OS (only when allowed) and registers the Expo token for the signed-in account. Returns the final state. */
export async function enablePush(): Promise<PermissionState> {
  if (!pushSupported()) return 'unsupported';
  const before = await permissionState();
  let granted = before.state === 'granted';
  if (!granted && before.canAskAgain) {
    const asked = await Notifications!.requestPermissionsAsync();
    granted = asked.granted;
    if (!granted) return asked.canAskAgain ? 'denied' : 'blocked';
  } else if (!granted) {
    return 'blocked';
  }
  const projectId = Constants.expoConfig?.extra?.eas?.projectId || (Constants as any).easConfig?.projectId;
  try {
    const token = (await Notifications!.getExpoPushTokenAsync(projectId ? { projectId } : undefined)).data;
    await api.post('/notifications/devices', { token, platform: Platform.OS, app_version: Constants.expoConfig?.version || '', device_name: Device?.modelName || '' });
    await SecureStore.setItemAsync(TOKEN_KEY, token);
  } catch {
    // Token retrieval fails in Expo Go / without push credentials; the account keeps its in-app inbox.
  }
  return 'granted';
}

/** Re-registers silently when permission was already granted (token rotation, app update, account switch). */
export async function syncPushIfGranted() {
  if (!pushSupported()) return;
  const { state } = await permissionState();
  if (state === 'granted') await enablePush();
}

export async function storedPushToken(): Promise<string | null> {
  if (Platform.OS === 'web') return null;
  try { return await SecureStore.getItemAsync(TOKEN_KEY); } catch { return null; }
}

/** Detaches this device from the account (called before logout so the next user never receives the prior alerts). */
export async function unlinkPush() {
  const token = await storedPushToken();
  if (!token) return null;
  try { await api.post('/notifications/devices/unlink', { token }); } catch { /* server-side revoke on logout covers offline */ }
  try { await SecureStore.deleteItemAsync(TOKEN_KEY); } catch {}
  return token;
}

export const notificationsModule = () => Notifications;
