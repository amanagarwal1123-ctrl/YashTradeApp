import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';

const mockReplace = jest.fn();
const mockPush = jest.fn();
const mockBack = jest.fn();
const mockPost = jest.fn<Promise<any>, [string, any?]>();
const mockLogin = jest.fn<Promise<any>, [string, any, string?]>();

jest.mock('expo-router', () => ({ useRouter: () => ({ replace: mockReplace, push: mockPush, back: mockBack }) }));
jest.mock('react-native-safe-area-context', () => {
  const { View } = jest.requireActual('react-native');
  return { SafeAreaView: View, useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }) };
});
jest.mock('@expo/vector-icons', () => {
  const ReactActual = jest.requireActual('react');
  const { Text: RNText } = jest.requireActual('react-native');
  return { Ionicons: (props: { name: string }) => ReactActual.createElement(RNText, { testID: `icon-${props.name}` }, props.name) };
});
jest.mock('../api', () => ({ BACKEND_URL: 'https://backend.test', api: { post: (...args: [string, any?]) => mockPost(...args) } }));
jest.mock('../context/AuthContext', () => ({ useAuth: () => ({ login: (...args: [string, any, string?]) => mockLogin(...args) }) }));
jest.mock('../context/LanguageContext', () => ({ useLang: () => ({ language: 'en', setLang: jest.fn() }) }));
jest.mock('@react-native-async-storage/async-storage', () => require('@react-native-async-storage/async-storage/jest/async-storage-mock'));

// eslint-disable-next-line import/first
import ReviewAccessScreen from '../../app/review-access';
// eslint-disable-next-line import/first
import LoginScreen from '../../app/login';
// eslint-disable-next-line import/first
import HelpScreen from '../../app/help';

const KEY = 'k'.repeat(44); // issued keys are >= 40 characters; the screen requires at least 20
const DESTINATIONS: Record<string, string> = {
  customer: '/(tabs)', admin: '/panel', billing_executive: '/panel', telecaller: '/telecaller', upload_executive: '/panel',
};
const REVIEWER_IDS: Record<string, string> = {
  customer: 'store-review-customer', admin: 'store-review-admin', billing_executive: 'store-review-billing', telecaller: 'store-review-telecaller', upload_executive: 'store-review-upload',
};

async function fillAndSubmit(reviewerId: string, key: string) {
  await fireEvent.changeText(screen.getByTestId('reviewer-id-input'), reviewerId);
  await fireEvent.changeText(screen.getByTestId('reviewer-key-input'), key);
  await fireEvent.press(screen.getByTestId('review-login-btn'));
}

beforeEach(() => { mockReplace.mockReset(); mockPush.mockReset(); mockBack.mockReset(); mockPost.mockReset(); mockLogin.mockReset(); });

describe('login screen -> Help -> App review access', () => {
  it('no longer shows a reviewer link on the login screen; the footer offers Help, which needs no session', async () => {
    await render(<LoginScreen />);
    expect(screen.queryByText('Store reviewer access')).toBeNull();
    expect(screen.queryByTestId('review-access-link')).toBeNull();
    await fireEvent.press(screen.getByTestId('login-help-link'));
    expect(mockPush).toHaveBeenCalledWith('/help');
    expect(mockPost).not.toHaveBeenCalled(); // opening Help triggers no OTP or API request
  });

  it('Help lists "App review access" and routes to the existing /review-access screen without any API call', async () => {
    await render(<HelpScreen />);
    expect(screen.getByText('App review access')).toBeTruthy();
    expect(screen.getByTestId('help-privacy-btn')).toBeTruthy();
    expect(screen.getByTestId('help-enroll-btn')).toBeTruthy();
    await fireEvent.press(screen.getByTestId('help-review-access-link'));
    expect(mockPush).toHaveBeenCalledWith('/review-access');
    expect(mockPost).not.toHaveBeenCalled();
    await fireEvent.press(screen.getByTestId('help-back-btn'));
    expect(mockBack).toHaveBeenCalledTimes(1);
  });
});

describe('ReviewAccessScreen', () => {
  it('explains the synthetic environment and keeps SIGN IN disabled until an ID and a plausible key are present', async () => {
    await render(<ReviewAccessScreen />);
    expect(screen.getByTestId('review-notice')).toBeTruthy();
    expect(screen.getByText('Synthetic review environment')).toBeTruthy();
    const button = screen.getByTestId('review-login-btn');
    expect(button.props.accessibilityState?.disabled ?? button.props.disabled).toBe(true);
    await fireEvent.changeText(screen.getByTestId('reviewer-id-input'), 'store-review-customer');
    await fireEvent.changeText(screen.getByTestId('reviewer-key-input'), 'too-short');
    expect(screen.getByTestId('review-login-btn').props.accessibilityState?.disabled ?? true).toBe(true);
    await fireEvent.press(screen.getByTestId('review-login-btn'));
    expect(mockPost).not.toHaveBeenCalled();
    await fireEvent.changeText(screen.getByTestId('reviewer-key-input'), KEY);
    expect(screen.getByTestId('review-login-btn').props.accessibilityState?.disabled ?? false).toBe(false);
  });

  it.each(Object.keys(DESTINATIONS))('signs in as the %s reviewer with the server-decided role and opens that role\'s home', async (role) => {
    const user = { id: `review-${role}-0001`, role, review_environment: true };
    mockPost.mockResolvedValue({ token: 'jwt-' + role, refresh_token: 'review.refresh-' + role, user, review_environment: true });
    mockLogin.mockResolvedValue(user);
    await render(<ReviewAccessScreen />);
    await fillAndSubmit(`  ${REVIEWER_IDS[role]}  `, `${KEY} `);
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith(DESTINATIONS[role]));
    expect(mockPost).toHaveBeenCalledTimes(1);
    expect(mockPost).toHaveBeenCalledWith('/auth/review/login', { reviewer_id: REVIEWER_IDS[role], access_key: KEY }); // trimmed, nothing else sent
    expect(mockLogin).toHaveBeenCalledWith('jwt-' + role, user, 'review.refresh-' + role);
    expect(screen.queryByTestId('review-login-error')).toBeNull();
  });

  it('shows the server outcome without navigating: unavailable environment, rate limit, wrong credentials', async () => {
    await render(<ReviewAccessScreen />);
    mockPost.mockRejectedValueOnce(Object.assign(new Error('The store-review environment is not configured on this server'), { status: 503, code: 'REVIEW_UNAVAILABLE' }));
    await fillAndSubmit('store-review-customer', KEY);
    await waitFor(() => expect(screen.getByTestId('review-login-error').props.children).toBe('Store-review access is not enabled on this server.'));
    mockPost.mockRejectedValueOnce(Object.assign(new Error('Too many attempts; please wait before trying again'), { status: 429, code: 'OTP_RATE_LIMIT' }));
    await fireEvent.press(screen.getByTestId('review-login-btn'));
    await waitFor(() => expect(screen.getByTestId('review-login-error').props.children).toBe('Too many attempts. Please wait a minute and try again.'));
    mockPost.mockRejectedValueOnce(Object.assign(new Error('Reviewer ID or access key is incorrect'), { status: 401, code: 'REVIEW_CREDENTIALS_INVALID' }));
    await fireEvent.press(screen.getByTestId('review-login-btn'));
    await waitFor(() => expect(screen.getByTestId('review-login-error').props.children).toBe('Reviewer ID or access key is incorrect'));
    expect(mockPost).toHaveBeenCalledTimes(3);
    expect(mockLogin).not.toHaveBeenCalled();
    expect(mockReplace).not.toHaveBeenCalled();
    // Editing either field clears the message.
    await fireEvent.changeText(screen.getByTestId('reviewer-key-input'), KEY + 'x');
    expect(screen.queryByTestId('review-login-error')).toBeNull();
  });

  it('hides the key by default, can reveal it, and the back control returns to the login screen', async () => {
    await render(<ReviewAccessScreen />);
    expect(screen.getByTestId('reviewer-key-input').props.secureTextEntry).toBe(true);
    await fireEvent.press(screen.getByTestId('reviewer-key-toggle'));
    expect(screen.getByTestId('reviewer-key-input').props.secureTextEntry).toBe(false);
    await fireEvent.press(screen.getByTestId('review-back-btn'));
    expect(mockBack).toHaveBeenCalledTimes(1);
  });
});
