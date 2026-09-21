import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';
import { api, setToken, storeCredentials, getToken, endSession, currentSession, onSessionLost } from '../api';
import { clearCaches, setCacheIdentity, cacheIdentity } from '../dataCache';
import { syncPushIfGranted, unlinkPush } from '../push';

// Secure token storage: SecureStore on devices. On web the session is memory-only (never persisted): the
// module-level token survives a navigator reset that remounts this provider, but not a page reload.
// Writes go through `storeCredentials` (api.ts): serialized and bound to the session generation, so a late refresh of
// a previous account can never overwrite or clear the credentials of the account that signed in meanwhile (G01).
const tokenStore = {
  get: async (): Promise<string | null> => {
    if (Platform.OS === 'web') { await AsyncStorage.removeItem('auth_token'); return getToken(); }
    const secure = await SecureStore.getItemAsync('auth_token');
    if (secure) return secure;
    // One-time migration from the old AsyncStorage location
    const legacy = await AsyncStorage.getItem('auth_token');
    if (legacy) {
      await SecureStore.setItemAsync('auth_token', legacy);
      await AsyncStorage.removeItem('auth_token');
    }
    return legacy;
  },
  /** Clears memory + secure storage for the CURRENT generation (a stale clear is dropped) and the legacy location. */
  remove: async () => {
    await storeCredentials(currentSession(), null, null);
    await AsyncStorage.removeItem('auth_token');
  },
};

interface User {
  id: string;
  phone: string;
  name: string;
  role: string;
  shop_name?: string;
  location?: string;
  city?: string;
  customer_code?: string;
  customer_type?: string;
  reward_points?: number;
  phone_verified?: boolean;
  onboarding_status?: string;
  has_logged_in?: boolean;
  account_status?: string;
  registration_source?: string;
  registered_at?: string;
  first_login_at?: string;
  last_login_at?: string;
  [key: string]: any;
}

interface AuthContextType {
  user: User | null;
  loading: boolean;
  /** True when the stored session could not be re-validated because the server/network was unavailable (not a logout). */
  offline: boolean;
  login: (token: string, user: User, refreshToken?: string) => Promise<User>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  user: null, loading: true, offline: false,
  login: async () => { throw new Error('Authentication provider unavailable'); }, logout: async () => {}, refreshUser: async () => {},
});

export const useAuth = () => useContext(AuthContext);
export const KNOWN_ROLES = ['customer', 'admin', 'telecaller', 'billing_executive', 'upload_executive'];

// Minimal profile snapshot (no tokens) so a cold start without network restores the signed-in role immediately; the
// server re-validates the session as soon as it is reachable and privileged actions always hit the server.
const snapshotStore = {
  get: async (): Promise<User | null> => {
    if (Platform.OS === 'web') return null;
    try { const raw = await SecureStore.getItemAsync('auth_user'); return raw ? JSON.parse(raw) : null; } catch { return null; }
  },
  set: (u: User) => Platform.OS === 'web' ? Promise.resolve() : SecureStore.setItemAsync('auth_user', JSON.stringify({ id: u.id, role: u.role, name: u.name, phone: u.phone, shop_name: u.shop_name, location: u.location })).catch(() => {}),
  remove: () => Platform.OS === 'web' ? Promise.resolve() : SecureStore.deleteItemAsync('auth_user').catch(() => {}),
};

const sessionEnded = (e: any) => e?.status === 401 || e?.status === 403 || /sign in again/i.test(e?.message || '');

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    // Only a CONFIRMED security/account event ends the session (revoked refresh credential, disabled/deleted account,
    // administrator revocation): drop state, caches and the device's notification association.
    onSessionLost(() => { endSession(); setCacheIdentity(null); clearCaches(); tokenStore.remove(); snapshotStore.remove(); unlinkPush(); setUser(null); setOffline(false); });
    (async () => {
      try {
        const token = await tokenStore.get();
        if (token) {
          setToken(token);
          try {
            const me = await api.get('/auth/me');
            setCacheIdentity(me);
            setUser(me);
            await snapshotStore.set(me);
            setOffline(false);
            syncPushIfGranted();
          } catch (e: any) {
            if (sessionEnded(e)) throw e;
            // Network timeout / 5xx: not proof the session is invalid. Keep the credentials, restore the snapshot.
            const snap = await snapshotStore.get();
            if (snap) { setCacheIdentity(snap); setUser(snap); }
            setOffline(true);
          }
        }
      } catch {
        await tokenStore.remove();
        await snapshotStore.remove();
        setToken(null);
        await clearCaches();
      } finally {
        setLoading(false);
      }
    })();
    return () => onSessionLost(null);
  }, []);

  const login = async (token: string, userData: User, refreshToken?: string) => {
    // A new identity starts: nothing from a previous account (memory, disk or an in-flight response) may carry over.
    endSession();
    const epoch = currentSession();
    setCacheIdentity(null);
    await clearCaches();
    await storeCredentials(epoch, token, refreshToken || null);
    const me = await api.get('/auth/me');
    if (!KNOWN_ROLES.includes(me.role)) throw new Error('Unknown account role');
    setCacheIdentity(me);
    setUser(me);
    await snapshotStore.set(me);
    setOffline(false);
    syncPushIfGranted();
    return me;
  };

  const logout = async () => {
    const pushToken = await unlinkPush();
    try { await api.post('/auth/logout', pushToken ? { push_token: pushToken } : undefined); } catch { /* Local tokens are still removed if offline. */ }
    endSession();
    await tokenStore.remove();
    await snapshotStore.remove();
    setCacheIdentity(null);
    await clearCaches();
    setUser(null);
    setOffline(false);
  };

  const refreshUser = async () => {
    try {
      const me = await api.get('/auth/me');
      const before = cacheIdentity();
      setCacheIdentity(me);
      if (before !== 'anon' && cacheIdentity() !== before) await clearCaches(); // role / permission change
      setUser(me);
      await snapshotStore.set(me);
      setOffline(false);
    } catch (e: any) {
      if (!sessionEnded(e)) setOffline(true);
    }
  };

  return (
    <AuthContext.Provider value={{ user, loading, offline, login, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}
