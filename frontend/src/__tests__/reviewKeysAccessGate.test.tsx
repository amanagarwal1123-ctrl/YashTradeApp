import React from 'react';
import { render, screen, waitFor } from '@testing-library/react-native';

const mockReplace = jest.fn();
const mockGet = jest.fn<Promise<any>, [string]>();
const mockPost = jest.fn<Promise<any>, [string, any?]>();
let mockAuthState: { user: any; loading: boolean } = { user: null, loading: true };

jest.mock('expo-router', () => ({ useRouter: () => ({ replace: mockReplace, push: jest.fn(), back: jest.fn() }) }));
jest.mock('react-native-safe-area-context', () => {
  const { View } = jest.requireActual('react-native');
  return { SafeAreaView: View, useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }) };
});
jest.mock('@expo/vector-icons', () => {
  const ReactActual = jest.requireActual('react');
  const { Text: RNText } = jest.requireActual('react-native');
  return { Ionicons: (props: { name: string }) => ReactActual.createElement(RNText, { testID: `icon-${props.name}` }, props.name) };
});
jest.mock('expo-clipboard', () => ({ setStringAsync: jest.fn(async () => {}) }));
jest.mock('../api', () => ({ BACKEND_URL: 'https://yash-tryon-test.emergent.host', API_BASE: 'https://yash-tryon-test.emergent.host/api',
  api: { get: (...args: [string]) => mockGet(...args), post: (...args: [string, any?]) => mockPost(...args) } }));
jest.mock('../utils/alert', () => ({ showAlert: jest.fn(), confirmAlert: jest.fn() }));
jest.mock('../context/AuthContext', () => ({ useAuth: () => mockAuthState }));

// eslint-disable-next-line import/first
import ReviewKeysScreen from '../../app/review-keys';

const OWNER_STATUS = {
  enabled: true, usable: true, storage: 'prefixed_collections', isolation: 'application_enforced', database: 'jewellers_app',
  accounts: ['store-review-customer', 'store-review-admin', 'store-review-telecaller', 'store-review-billing'].map(id => ({
    reviewer_id: id, role: id.split('-')[2], role_label: id, exists: true, enabled: true, rotated_at: null, revoked_at: null, last_login_at: null })),
  missing_accounts: [], dataset: { users: 11, products: 12, requests: 11 }, review_state: { reason: null, detail: 'ok' },
  sign_in_steps: ['1. Open the app'], store_form_text: ['Sign-in type: Reviewer ID + Access key'], fresh_authentication: 'OTP to the owner number',
};
const refusal = (code: string, message: string) => Object.assign(new Error(message), { status: 403, code });

beforeEach(() => { mockReplace.mockReset(); mockGet.mockReset(); mockPost.mockReset(); });

describe('ReviewKeysScreen access gate (authorisation stays server-side)', () => {
  it('while the session is still hydrating it neither redirects nor calls the console API', async () => {
    mockAuthState = { user: null, loading: true };
    await render(<ReviewKeysScreen />);
    await new Promise(r => setTimeout(r, 30));
    expect(mockReplace).not.toHaveBeenCalled();
    expect(mockGet).not.toHaveBeenCalled();
    expect(screen.queryByTestId('review-keys-error')).toBeNull();
  });

  it('signed-out (hydration finished with no session, e.g. direct URL on web) redirects to /login without any API call', async () => {
    mockAuthState = { user: null, loading: false };
    await render(<ReviewKeysScreen />);
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith('/login'));
    expect(mockGet).not.toHaveBeenCalled();
  });

  it('owner administrator sees the account table and actions', async () => {
    mockAuthState = { user: { id: 'owner', role: 'admin', phone: '9999813334' }, loading: false };
    mockGet.mockResolvedValueOnce(OWNER_STATUS);
    await render(<ReviewKeysScreen />);
    await waitFor(() => expect(screen.getByTestId('review-account-store-review-admin')).toBeTruthy());
    expect(mockGet).toHaveBeenCalledWith('/admin/review/status');
    expect(screen.getByTestId('review-reset-data')).toBeTruthy();
    expect(screen.getByTestId('rotate-store-review-customer')).toBeTruthy();
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it('reviewer administrator (review scope) gets the server refusal card, no redirect, no actions', async () => {
    mockAuthState = { user: { id: 'review-admin-0001', role: 'admin', review_environment: true }, loading: false };
    mockGet.mockRejectedValueOnce(refusal('REVIEW_SCOPE_FORBIDDEN', 'Reviewer accounts cannot manage store-review access'));
    await render(<ReviewKeysScreen />);
    await waitFor(() => expect(screen.getByTestId('review-keys-error')).toBeTruthy());
    expect(screen.getByText('Not available in the store-review environment')).toBeTruthy();
    expect(screen.queryByTestId('review-provision')).toBeNull();
    expect(screen.queryByTestId('review-reset-data')).toBeNull();
    expect(mockReplace).not.toHaveBeenCalled();
    expect(mockPost).not.toHaveBeenCalled();
  });

  it('non-owner administrator gets the owner-only refusal card, no redirect, no actions', async () => {
    mockAuthState = { user: { id: 'other-admin', role: 'admin', phone: '9100000001' }, loading: false };
    mockGet.mockRejectedValueOnce(refusal('OWNER_ADMIN_REQUIRED', 'Only the owner administrator can manage store-review access'));
    await render(<ReviewKeysScreen />);
    await waitFor(() => expect(screen.getByText('Owner administrator only')).toBeTruthy());
    expect(screen.queryByTestId('review-provision')).toBeNull();
    expect(mockReplace).not.toHaveBeenCalled();
    expect(mockPost).not.toHaveBeenCalled();
  });
});
