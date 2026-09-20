import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';
import { api, setToken, setRefreshToken, getToken, endSession, onSessionLost } from '../api';
import { clearCaches, setCacheIdentity, cacheIdentity } from '../dataCache';

// Secure token storage: SecureStore on devices. On web the session is memory-only (never persisted): the
// module-level token survives a navigator reset that remounts this provider, but not a page reload.
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
  set: (v: string) => Platform.OS === 'web' ? Promise.resolve() : SecureStore.setItemAsync('auth_token', v),
  remove: async () => {
    if (Platform.OS === 'web') { await AsyncStorage.removeItem('auth_token'); return; }
    await SecureStore.deleteItemAsync('auth_token');
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
  login: (token: string, user: User, refreshToken?: string) => Promise<User>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  user: null, loading: true,
  login: async () => { throw new Error('Authentication provider unavailable'); }, logout: async () => {}, refreshUser: async () => {},
});

export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Expired or revoked session (e.g. an administrator changed this staff member's number): drop state and caches.
    onSessionLost(() => { endSession(); setCacheIdentity(null); clearCaches(); tokenStore.remove(); setUser(null); });
    (async () => {
      try {
        const token = await tokenStore.get();
        if (token) {
          setToken(token);
          const me = await api.get('/auth/me');
          setCacheIdentity(me);
          setUser(me);
        }
      } catch {
        await tokenStore.remove();
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
    setCacheIdentity(null);
    await clearCaches();
    await tokenStore.set(token);
    setToken(token);
    await setRefreshToken(refreshToken || null);
    const me = await api.get('/auth/me');
    if (!['customer', 'admin', 'telecaller', 'billing_executive'].includes(me.role)) throw new Error('Unknown account role');
    setCacheIdentity(me);
    setUser(me);
    return me;
  };

  const logout = async () => {
    try { await api.post('/auth/logout'); } catch { /* Local tokens are still removed if offline. */ }
    endSession();
    await setRefreshToken(null);
    await tokenStore.remove();
    setToken(null);
    setCacheIdentity(null);
    await clearCaches();
    setUser(null);
  };

  const refreshUser = async () => {
    try {
      const me = await api.get('/auth/me');
      const before = cacheIdentity();
      setCacheIdentity(me);
      if (before !== 'anon' && cacheIdentity() !== before) await clearCaches(); // role / permission change
      setUser(me);
    } catch {}
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}
