import React from 'react';
import { Platform } from 'react-native';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';

/**
 * App Store guideline 5.1.1(v) (rejection of 24 Sep 2026): browsing products may not require registration. iOS opens
 * on a read-only preview of the public catalogue, capped at 100 products; every account feature still asks to sign in.
 * Android/web are never routed here (`homeRouteFor` → /login), so their login-first flow is unchanged.
 */
const mockPush = jest.fn(), mockReplace = jest.fn();
let mockUser: any = null;
let mockAuthLoading = false;
const mockGet = jest.fn<Promise<any>, [string]>();
const TOTAL = 260;

jest.mock('@expo/vector-icons', () => {
  const ReactActual = jest.requireActual('react');
  const { Text: RNText } = jest.requireActual('react-native');
  return { Ionicons: (props: { name: string }) => ReactActual.createElement(RNText, { testID: `icon-${props.name}` }, props.name) };
});
jest.mock('expo-image', () => ({ Image: () => null }));
jest.mock('expo-router', () => ({ useRouter: () => ({ push: mockPush, replace: mockReplace, back: jest.fn(), canGoBack: () => false }) }));
jest.mock('../api', () => ({ api: { get: (path: string) => mockGet(path) }, productImage: () => 'https://example.test/p.jpg' }));
jest.mock('../context/AuthContext', () => ({ useAuth: () => ({ user: mockUser, loading: mockAuthLoading }) }));
jest.mock('../context/LanguageContext', () => ({ useLang: () => ({ language: 'en', setLang: jest.fn(), t: (k: string) => k }) }));

// eslint-disable-next-line import/first
import GuestPreviewScreen from '../../app/guest-preview';

const productsPage = (page: number, limit = 20) => ({
  products: Array.from({ length: limit }, (_, i) => { const n = (page - 1) * limit + i + 1; return { id: `p${n}`, title: `Payal ${n}`, metal_type: 'silver', category: 'payal', approx_weight: `${n} g` }; }),
  total: TOTAL, page, pages: Math.ceil(TOTAL / limit),
});

beforeEach(() => {
  (Platform as any).OS = 'ios';
  mockPush.mockReset(); mockReplace.mockReset(); mockGet.mockReset(); mockUser = null; mockAuthLoading = false;
  mockGet.mockImplementation(async (path: string) => {
    const m = /page=(\d+)&limit=(\d+)/.exec(path);
    if (!m) throw new Error(`unexpected GET ${path}`);
    return productsPage(Number(m[1]), Number(m[2]));
  });
});

describe('iOS guest catalogue preview', () => {
  it('loads the public catalogue without a session, opens a product read-only and offers Sign in', async () => {
    render(<GuestPreviewScreen />);
    expect(await screen.findByTestId('guest-item-p1')).toBeTruthy();
    expect(mockGet).toHaveBeenCalledWith('/products?page=1&limit=20');
    expect(screen.getByText(/Browse up to 100 products without an account/)).toBeTruthy();
    fireEvent.press(screen.getByTestId('guest-item-p1'));
    expect(mockPush).toHaveBeenCalledWith({ pathname: '/product/[id]', params: { id: 'p1' } });
    fireEvent.press(screen.getByTestId('guest-sign-in'));
    expect(mockPush).toHaveBeenCalledWith('/login');
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it('stops at 100 products and shows the end-of-preview card with the full catalogue count and a Sign in button', async () => {
    render(<GuestPreviewScreen />);
    await screen.findByTestId('guest-item-p1');
    const list = screen.getByTestId('guest-list');
    for (let i = 0; i < 6; i++) {
      await act(async () => { fireEvent(list, 'onEndReached'); });
      await waitFor(() => expect(screen.queryByTestId('guest-loading-more')).toBeNull());
    }
    // pages 1..5 only: the sixth pull must not request page 6
    expect(mockGet).toHaveBeenCalledTimes(5);
    expect(mockGet).not.toHaveBeenCalledWith('/products?page=6&limit=20');
    expect(list.props.data).toHaveLength(100);
    const end = await screen.findByTestId('guest-preview-end');
    expect(end).toBeTruthy();
    expect(screen.getByText('End of preview')).toBeTruthy();
    expect(screen.getByText(new RegExp(`browse all ${TOTAL} products`))).toBeTruthy();
    fireEvent.press(screen.getByTestId('guest-end-sign-in'));
    expect(mockPush).toHaveBeenCalledWith('/login');
  });

  it('shows a retry state when the catalogue cannot be loaded', async () => {
    mockGet.mockRejectedValueOnce(new Error('Network unavailable'));
    render(<GuestPreviewScreen />);
    expect(await screen.findByTestId('guest-error')).toBeTruthy();
    fireEvent.press(screen.getByTestId('guest-retry'));
    expect(await screen.findByTestId('guest-item-p1')).toBeTruthy();
  });

  it('sends a signed-in account straight to its own home instead of the preview', async () => {
    mockUser = { id: 'c1', role: 'customer' };
    render(<GuestPreviewScreen />);
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith('/(tabs)'));
    mockReplace.mockReset();
    mockUser = { id: 'a1', role: 'admin' };
    render(<GuestPreviewScreen />);
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith('/panel'));
  });
});
