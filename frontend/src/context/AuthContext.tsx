import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { api, setToken } from '../api';

interface User {
  id: string;
  phone: string;
  name: string;
  city: string;
  customer_code: string;
  customer_type: string;
  role: string;
  reward_points: number;
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
        const token = await AsyncStorage.getItem('auth_token');
        if (token) {
          setToken(token);
          const me = await api.get('/auth/me');
          setUser(me);
        }
      } catch (e) {
        await AsyncStorage.removeItem('auth_token');
        setToken(null);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const login = async (token: string, userData: User) => {
    await AsyncStorage.setItem('auth_token', token);
    setToken(token);
    setUser(userData);
  };

  const logout = async () => {
    await AsyncStorage.removeItem('auth_token');
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
