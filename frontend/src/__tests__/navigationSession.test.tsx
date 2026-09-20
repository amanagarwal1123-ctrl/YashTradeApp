import React from 'react';
import { Platform, Text } from 'react-native';
import { act, render, waitFor } from '@testing-library/react-native';

/** R01: back navigation helpers and the durable-session rule (only a confirmed security event ends the session). */
const mockGet = jest.fn<Promise<any>, [string]>();
const mockPost = jest.fn<Promise<any>, [string, any?]>();
const mockReplace = jest.fn(), mockBack = jest.fn(), mockDismissAll = jest.fn();
let canGoBack = false, canDismiss = false;
const secure: Record<string, string> = {};

jest.mock('@react-native-async-storage/async-storage', () => require('@react-native-async-storage/async-storage/jest/async-storage-mock'));
jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(async (k: string) => secure[k] ?? null),
  setItemAsync: jest.fn(async (k: string, v: string) => { secure[k] = v; }),
  deleteItemAsync: jest.fn(async (k: string) => { delete secure[k]; }),
}));
jest.mock('expo-router', () => ({
  useRouter: () => ({ replace: mockReplace, back: mockBack, dismissAll: mockDismissAll, push: jest.fn(), canGoBack: () => canGoBack, canDismiss: () => canDismiss }),
}));
jest.mock('../api', () => {
  const actual = jest.requireActual('../api');
  return { ...actual, api: { get: (...args: [string]) => mockGet(...args), post: (...args: [string, any?]) => mockPost(...args) } };
});
jest.mock('../push', () => ({ syncPushIfGranted: jest.fn(async () => {}), unlinkPush: jest.fn(async () => null) }));

// eslint-disable-next-line import/first
import { authorizedDestination, homeRouteFor, resetToHome, useSafeBack } from '../navigation';
// eslint-disable-next-line import/first
import { AuthProvider, useAuth } from '../context/AuthContext';
// eslint-disable-next-line import/first
import { setToken, TransientError } from '../api';

describe('R01-A role homes, history reset and deep-link authorisation', () => {
  it('maps every role to its root screen and unknown roles to login', () => {
    expect(homeRouteFor('customer')).toBe('/(tabs)');
    expect(homeRouteFor('telecaller')).toBe('/telecaller');
    for (const r of ['admin', 'billing_executive', 'upload_executive']) expect(homeRouteFor(r)).toBe('/panel');
    expect(homeRouteFor(undefined)).toBe('/login');
  });

  it('resetToHome dismisses every modal then REPLACES the history with the role home (login/OTP unreachable by back)', () => {
    canDismiss = true;
    const router = { canDismiss: () => canDismiss, dismissAll: mockDismissAll, replace: mockReplace } as any;
    resetToHome(router, 'telecaller');
    expect(mockDismissAll).toHaveBeenCalledTimes(1);
    expect(mockReplace).toHaveBeenCalledWith('/telecaller');
    expect(mockBack).not.toHaveBeenCalled();
  });

  it('useSafeBack goes back when there is history and falls back to the role home (never login) when there is none', () => {
    canGoBack = true;
    let back!: () => void;
    function Probe() { back = useSafeBack('customer'); return <Text>x</Text>; }
    render(<Probe />);
    act(() => back());
    expect(mockBack).toHaveBeenCalledTimes(1);
    canGoBack = false;
    act(() => back());
    expect(mockReplace).toHaveBeenLastCalledWith('/(tabs)');
  });

  it('routes notification / deep-link destinations only where the signed-in role is allowed', () => {
    expect(authorizedDestination('/staff-requests?request=abc', 'telecaller')).toBe('/staff-requests?request=abc');
    expect(authorizedDestination('/staff-requests?request=abc', 'customer')).toBe('/(tabs)');
    expect(authorizedDestination('/telecaller', 'admin')).toBe('/staff-requests');
    expect(authorizedDestination('/admin-notifications', 'billing_executive')).toBe('/panel');
    expect(authorizedDestination('/admin-notifications', 'admin')).toBe('/admin-notifications');
    expect(authorizedDestination('/pdf-import', 'upload_executive')).toBe('/pdf-import');
    expect(authorizedDestination('/pdf-import', 'telecaller')).toBe('/telecaller');
    expect(authorizedDestination('/wishlist', 'admin')).toBe('/panel');
    expect(authorizedDestination('/product/p1', 'customer')).toBe('/product/p1');
    expect(authorizedDestination('https://evil.example', 'customer')).toBe('/(tabs)');
    expect(authorizedDestination('//evil.example', 'customer')).toBe('/(tabs)');
    expect(authorizedDestination('/notifications', undefined)).toBe('/login');
  });
});

let captured: ReturnType<typeof useAuth> | null = null;
function Probe() {
  captured = useAuth();
  return <Text>{captured.loading ? 'loading' : captured.user ? `user:${captured.user.id}:${captured.offline ? 'offline' : 'online'}` : 'signed-out'}</Text>;
}
const ME = { id: 'u-cust', role: 'customer', phone: '9300000001', name: 'C', shop_name: 'S', location: 'L' };

describe('R01-B durable session on a device (SecureStore)', () => {
  beforeEach(() => { (Platform as any).OS = 'android'; mockGet.mockReset(); mockPost.mockReset(); setToken(null); for (const k of Object.keys(secure)) delete secure[k]; });

  it('keeps the credentials and restores the profile snapshot when /auth/me fails with a network error (not a logout)', async () => {
    secure.auth_token = 'jwt-old'; secure.auth_user = JSON.stringify(ME);
    mockGet.mockRejectedValueOnce(new TransientError('Network unavailable'));
    const tree = render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(tree.getByText('user:u-cust:offline')).toBeTruthy());
    expect(secure.auth_token).toBe('jwt-old');
    expect(secure.auth_user).toBeTruthy();
  });

  it('keeps the credentials on a 5xx and on ordinary transient statuses', async () => {
    secure.auth_token = 'jwt-old'; secure.auth_user = JSON.stringify(ME);
    const e: any = new Error('Request failed (503)'); e.status = 503; e.transient = true;
    mockGet.mockRejectedValueOnce(e);
    const tree = render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(tree.getByText('user:u-cust:offline')).toBeTruthy());
    expect(secure.auth_token).toBe('jwt-old');
  });

  it('ends the session ONLY when the server confirms it is gone (401 after a failed refresh / revoked account)', async () => {
    secure.auth_token = 'jwt-old'; secure.auth_user = JSON.stringify(ME);
    const e: any = new Error('Session expired; please sign in again'); e.status = 401;
    mockGet.mockRejectedValueOnce(e);
    const tree = render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(tree.getByText('signed-out')).toBeTruthy());
    expect(secure.auth_token).toBeUndefined();
    expect(secure.auth_user).toBeUndefined();
  });

  it('a validated session is stored for the next cold start and explicit logout clears everything', async () => {
    mockGet.mockResolvedValue(ME);
    mockPost.mockResolvedValue({ logged_out: true });
    const tree = render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(tree.getByText('signed-out')).toBeTruthy());
    await act(async () => { await captured!.login('jwt-access', ME as any, 'refresh-1'); });
    await waitFor(() => expect(tree.getByText('user:u-cust:online')).toBeTruthy());
    expect(secure.auth_token).toBe('jwt-access');
    expect(secure.refresh_token).toBe('refresh-1');
    expect(JSON.parse(secure.auth_user).role).toBe('customer');
    await act(async () => { await captured!.logout(); });
    await waitFor(() => expect(tree.getByText('signed-out')).toBeTruthy());
    expect(mockPost).toHaveBeenCalledWith('/auth/logout', undefined);
    expect(secure.auth_token).toBeUndefined();
    expect(secure.refresh_token).toBeUndefined();
    expect(secure.auth_user).toBeUndefined();
  });
});
