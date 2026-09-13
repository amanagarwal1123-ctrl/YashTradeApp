import React from 'react';
import { Platform, Text } from 'react-native';
import { act, render, waitFor } from '@testing-library/react-native';

const mockGet = jest.fn<Promise<any>, [string]>();
const mockPost = jest.fn<Promise<any>, [string, any?]>();

jest.mock('@react-native-async-storage/async-storage', () => require('@react-native-async-storage/async-storage/jest/async-storage-mock'));
jest.mock('expo-secure-store', () => ({ getItemAsync: jest.fn(async () => null), setItemAsync: jest.fn(async () => {}), deleteItemAsync: jest.fn(async () => {}) }));
jest.mock('../api', () => {
  const actual = jest.requireActual('../api');
  return { ...actual, api: { get: (...args: [string]) => mockGet(...args), post: (...args: [string, any?]) => mockPost(...args) } };
});

// eslint-disable-next-line import/first
import { AuthProvider, useAuth } from '../context/AuthContext';
// eslint-disable-next-line import/first
import { getToken, setToken } from '../api';

const ME = { id: 'u-admin', role: 'admin', phone: '9100000000', name: 'Admin' };
let captured: ReturnType<typeof useAuth> | null = null;
function Probe() {
  captured = useAuth();
  return <Text testID="probe">{captured.loading ? 'loading' : captured.user ? `user:${captured.user.id}` : 'signed-out'}</Text>;
}
const mount = () => render(<AuthProvider><Probe /></AuthProvider>);

beforeEach(() => { mockGet.mockReset(); mockPost.mockReset(); captured = null; setToken(null); (Platform as any).OS = 'web'; });

describe('AuthProvider on web (memory-only session)', () => {
  it('starts signed out without calling /auth/me when no in-memory token exists', async () => {
    const tree = await mount();
    await waitFor(() => expect(tree.getByText('signed-out')).toBeTruthy());
    expect(mockGet).not.toHaveBeenCalled();
  });

  it('re-hydrates from the in-memory token when the provider is remounted by a navigator reset', async () => {
    mockGet.mockResolvedValue(ME);
    const first = await mount();
    await waitFor(() => expect(first.getByText('signed-out')).toBeTruthy());
    await act(async () => { await captured!.login('jwt-access', ME as any, 'refresh-1'); });
    await waitFor(() => expect(first.getByText('user:u-admin')).toBeTruthy());
    expect(getToken()).toBe('jwt-access');

    await first.unmount(); // the root layout remounts on a web history reset: React state is gone, the module token is not
    const second = await mount();
    await waitFor(() => expect(second.getByText('user:u-admin')).toBeTruthy());
    expect(mockGet).toHaveBeenLastCalledWith('/auth/me'); // the server, not the client, decides whether the session is still valid
    expect(second.queryByText('signed-out')).toBeNull();
  });

  it('shows the hydrating state (never signed-out) until the server has answered for a remembered token', async () => {
    setToken('jwt-access');
    let release!: (v: any) => void;
    mockGet.mockReturnValueOnce(new Promise(resolve => { release = resolve; }));
    const tree = await mount();
    expect(tree.getByText('loading')).toBeTruthy();
    await act(async () => { release(ME); });
    await waitFor(() => expect(tree.getByText('user:u-admin')).toBeTruthy());
  });

  it('drops the session when the server rejects the remembered token', async () => {
    setToken('stale-jwt');
    mockGet.mockRejectedValueOnce(Object.assign(new Error('Session revoked; sign in again'), { status: 401, code: 'SESSION_REVOKED' }));
    const tree = await mount();
    await waitFor(() => expect(tree.getByText('signed-out')).toBeTruthy());
    expect(getToken()).toBeNull();
  });

  it('logout clears the in-memory token so a later remount starts signed out', async () => {
    mockGet.mockResolvedValue(ME);
    mockPost.mockResolvedValue({});
    const first = await mount();
    await waitFor(() => expect(first.getByText('signed-out')).toBeTruthy());
    await act(async () => { await captured!.login('jwt-access', ME as any); });
    await waitFor(() => expect(first.getByText('user:u-admin')).toBeTruthy());
    await act(async () => { await captured!.logout(); });
    expect(mockPost).toHaveBeenCalledWith('/auth/logout');
    expect(getToken()).toBeNull();
    await first.unmount();
    mockGet.mockClear();
    const second = await mount();
    await waitFor(() => expect(second.getByText('signed-out')).toBeTruthy());
    expect(mockGet).not.toHaveBeenCalled();
  });
});
