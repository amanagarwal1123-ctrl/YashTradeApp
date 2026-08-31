import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';
import { api, setToken } from '../api';

// Secure token storage: SecureStore on devices, AsyncStorage on web
const tokenStore = {
  get: async (): Promise<string | null> => {
    if (Platform.OS === 'web') return AsyncStorage.getItem('auth_token');
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
  set: (v: string) => Platform.OS === 'web' ? AsyncStorage.setItem('auth_token', v) : SecureStore.setItemAsync('auth_token', v),
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
  login: (token: string, user: User) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  user: null, loading: true,
  login: async () => {}, logout: async () => {}, refreshUser: async () => {},
});

export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const token = await tokenStore.get();
        if (token) {
          setToken(token);
          const me = await api.get('/auth/me');
          setUser(me);
        }
      } catch (e) {
        await tokenStore.remove();
        setToken(null);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const login = async (token: string, userData: User) => {
    await tokenStore.set(token);
    setToken(token);
    setUser(userData);
  };

  const logout = async () => {
    await tokenStore.remove();
    setToken(null);
    setUser(null);
  };

  const refreshUser = async () => {
    try {
      const me = await api.get('/auth/me');
      setUser(me);
    } catch {}
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}
