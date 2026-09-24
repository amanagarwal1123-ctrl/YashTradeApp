import React from 'react';
import { Alert, Platform } from 'react-native';
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';

/**
 * Account features stay behind sign-in for the iOS guest preview: product detail and the photo viewer read freely,
 * but cart / wishlist / enquiry taps show "Sign in to continue" (never a silent 401) and lead to the login screen.
 * The login screen itself can be left again on iOS only ("Browse the collection"); Android keeps it as the root.
 */
const mockPush = jest.fn(), mockReplace = jest.fn(), mockBack = jest.fn();
let mockCanGoBack = false;
let mockUser: any = null;
const mockGet = jest.fn<Promise<any>, [string]>();
const mockPost = jest.fn<Promise<any>, [string, any?]>();

jest.mock('@expo/vector-icons', () => {
  const ReactActual = jest.requireActual('react');
  const { Text: RNText } = jest.requireActual('react-native');
  return { Ionicons: (props: { name: string }) => ReactActual.createElement(RNText, { testID: `icon-${props.name}` }, props.name) };
});
jest.mock('expo-image', () => ({ Image: () => null }));
jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockPush, replace: mockReplace, back: mockBack, canGoBack: () => mockCanGoBack }),
  useLocalSearchParams: () => ({ id: 'p1' }),
}));
jest.mock('../api', () => ({
  api: { get: (p: string) => mockGet(p), post: (p: string, b?: any) => mockPost(p, b) },
  getProductGallery: () => ['https://example.test/full.jpg'], productThumb: () => 'https://example.test/t.jpg', sizedUrl: (u: string) => u,
  SessionChangedError: class SessionChangedError extends Error {},
}));
jest.mock('../dataCache', () => ({ swrGet: async (_path: string, onData: (d: any) => void) => { onData({ id: 'p1', title: 'Silver Payal', metal_type: 'silver', category: 'payal', images: ['https://example.test/full.jpg'] }); } }));
jest.mock('../components/ZoomableImage', () => ({ __esModule: true, default: ({ children }: any) => children }));
jest.mock('../context/AuthContext', () => ({ useAuth: () => ({ user: mockUser, loading: false }) }));
jest.mock('../context/LanguageContext', () => ({ useLang: () => ({ language: 'en', setLang: jest.fn(), t: (k: string) => k }) }));
jest.mock('../phone', () => ({ canonicalPhone: () => '', COUNTRIES: [{ code: 'IN', label: 'India' }], DEFAULT_COUNTRY: 'IN' }));
jest.mock('../components/PhoneField', () => ({ __esModule: true, default: () => null }));
jest.mock('../i18n', () => ({ LANGUAGE_OPTIONS: [{ key: 'en', native: 'English' }] }));
jest.mock('expo-constants', () => ({ __esModule: true, default: { expoConfig: { extra: {} } } }));

// eslint-disable-next-line import/first
import ProductDetail from '../../app/product/[id]';
// eslint-disable-next-line import/first
import LoginScreen from '../../app/login';

beforeEach(() => {
  (Platform as any).OS = 'ios';
  mockPush.mockReset(); mockReplace.mockReset(); mockBack.mockReset(); mockGet.mockReset(); mockPost.mockReset();
  mockUser = null; mockCanGoBack = false;
  jest.spyOn(Alert, 'alert').mockImplementation(() => {});
});
afterEach(() => jest.restoreAllMocks());

const pressSignInInPrompt = () => {
  const calls = (Alert.alert as jest.Mock).mock.calls;
  const buttons = calls[calls.length - 1][2] as { text: string; onPress?: () => void }[];
  buttons.find(b => b.text === 'Sign in')!.onPress!();
};

describe('guest gate on product detail', () => {
  it('reads the product without touching the wishlist, and turns cart / wishlist / enquiry taps into a sign-in prompt', async () => {
    render(<ProductDetail />);
    expect(await screen.findByText('Silver Payal')).toBeTruthy();
    expect(mockGet).not.toHaveBeenCalledWith('/wishlist');

    fireEvent.press(screen.getByTestId('add-to-cart-btn'));
    expect(mockPost).not.toHaveBeenCalled();
    expect(Alert.alert).toHaveBeenCalledWith('Sign in to continue', expect.stringContaining('need your account'), expect.any(Array));
    pressSignInInPrompt();
    expect(mockPush).toHaveBeenLastCalledWith('/login');

    fireEvent.press(screen.getByTestId('wishlist-btn'));
    expect(mockPost).not.toHaveBeenCalled();
    for (const id of ['ask-price-btn', 'video-call-btn', 'hold-item-btn', 'reorder-btn']) fireEvent.press(screen.getByTestId(id));
    expect(mockPush).not.toHaveBeenCalledWith(expect.objectContaining({ pathname: '/request-call' }));
    expect(Alert.alert).toHaveBeenCalledTimes(6);
  });

  it('keeps the signed-in behaviour unchanged: wishlist check runs and the actions go straight through', async () => {
    mockUser = { id: 'c1', role: 'customer' };
    mockGet.mockResolvedValue({ products: [{ id: 'p1' }] });
    mockPost.mockResolvedValue({ wishlisted: false, added: true });
    render(<ProductDetail />);
    expect(await screen.findByText('Silver Payal')).toBeTruthy();
    await waitFor(() => expect(mockGet).toHaveBeenCalledWith('/wishlist'));
    fireEvent.press(screen.getByTestId('add-to-cart-btn'));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/cart/add', { product_id: 'p1' }));
    fireEvent.press(screen.getByTestId('ask-price-btn'));
    expect(mockPush).toHaveBeenCalledWith({ pathname: '/request-call', params: { type: 'ask_price', productId: 'p1' } });
    expect(Alert.alert).not.toHaveBeenCalled();
  });
});

describe('login screen exit on iOS only', () => {
  it('iOS: "Browse the collection" goes back when there is history, otherwise to the catalogue preview', () => {
    render(<LoginScreen />);
    fireEvent.press(screen.getByTestId('login-browse-btn'));
    expect(mockReplace).toHaveBeenCalledWith('/guest-preview');
    mockCanGoBack = true;
    fireEvent.press(screen.getByTestId('login-browse-btn'));
    expect(mockBack).toHaveBeenCalledTimes(1);
    expect(screen.getByText('Yash Trade App - Wholesale silver & gold jewellery')).toBeTruthy();
    expect(screen.queryByText(/Google Play/)).toBeNull();
  });

  it('Android: login stays the root screen without an exit control', () => {
    (Platform as any).OS = 'android';
    render(<LoginScreen />);
    expect(screen.queryByTestId('login-browse-btn')).toBeNull();
    expect(screen.getByText('Yash Trade App - Wholesale silver & gold jewellery')).toBeTruthy();
  });
});
