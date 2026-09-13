import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';

const mockBack = jest.fn();
const mockGet = jest.fn<Promise<any>, [string]>();
const mockPost = jest.fn<Promise<any>, [string, any?]>();
const mockSetString = jest.fn<Promise<void>, [string]>();
const mockAlert = jest.fn();
const mockConfirm = jest.fn((_t: string, _m: string, onConfirm: () => void) => onConfirm());

jest.mock('expo-router', () => ({ useRouter: () => ({ replace: jest.fn(), push: jest.fn(), back: mockBack }) }));
jest.mock('react-native-safe-area-context', () => {
  const { View } = jest.requireActual('react-native');
  return { SafeAreaView: View, useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }) };
});
jest.mock('@expo/vector-icons', () => {
  const ReactActual = jest.requireActual('react');
  const { Text: RNText } = jest.requireActual('react-native');
  return { Ionicons: (props: { name: string }) => ReactActual.createElement(RNText, { testID: `icon-${props.name}` }, props.name) };
});
jest.mock('expo-clipboard', () => ({ setStringAsync: (...args: [string]) => mockSetString(...args) }));
jest.mock('../api', () => ({ BACKEND_URL: 'https://yash-tryon-test.emergent.host', API_BASE: 'https://yash-tryon-test.emergent.host/api',
  api: { get: (...args: [string]) => mockGet(...args), post: (...args: [string, any?]) => mockPost(...args) } }));
jest.mock('../utils/alert', () => ({ showAlert: (...args: any[]) => mockAlert(...args), confirmAlert: (...args: any[]) => (mockConfirm as any)(...args) }));
jest.mock('../context/LanguageContext', () => ({ useLang: () => ({ t: (k: string) => k, language: 'en' }) }));
jest.mock('../context/AuthContext', () => ({ useAuth: () => ({ user: { id: 'u1', role: 'admin', phone: '9999813334' }, loading: false }) }));

// eslint-disable-next-line import/first
import ReviewKeysScreen from '../../app/review-keys';
// eslint-disable-next-line import/first
import AIAssistantScreen from '../../app/ai-assistant';

const ACCOUNTS = (exists: boolean) => ['store-review-customer', 'store-review-admin', 'store-review-telecaller', 'store-review-billing'].map(id => ({
  reviewer_id: id, role: id.split('-')[2], role_label: id, exists, enabled: exists, rotated_at: null, revoked_at: null, last_login_at: null,
}));
const STATUS = {
  enabled: true, usable: true, storage: 'prefixed_collections', isolation: 'application_enforced', database: 'jewellers_app',
  accounts: ACCOUNTS(false), missing_accounts: ACCOUNTS(false).map(a => a.reviewer_id), dataset: null,
  review_state: { reason: null, detail: 'ok' }, sign_in_steps: ['1. Open the app'], store_form_text: ['Sign-in type: Reviewer ID + Access key'],
  fresh_authentication: 'OTP to the owner number',
};
const KEY = 'A'.repeat(43);

beforeEach(() => { mockGet.mockReset(); mockPost.mockReset(); mockSetString.mockReset(); mockAlert.mockReset(); mockBack.mockReset(); mockConfirm.mockClear(); });

describe('ReviewKeysScreen (owner console)', () => {
  it('shows the server-side refusal for non-owner administrators and never offers actions', async () => {
    mockGet.mockRejectedValueOnce(Object.assign(new Error('Only the owner administrator can manage store-review access'), { code: 'OWNER_ADMIN_REQUIRED' }));
    await render(<ReviewKeysScreen />);
    await waitFor(() => expect(screen.getByTestId('review-keys-error')).toBeTruthy());
    expect(screen.getByText('Owner administrator only')).toBeTruthy();
    expect(screen.queryByTestId('review-provision')).toBeNull();
    expect(mockPost).not.toHaveBeenCalled();
  });

  it('requires a fresh OTP, shows issued keys once with copy, and never rotates on a second provision', async () => {
    mockGet.mockResolvedValueOnce(STATUS);
    mockPost.mockImplementation(async (path: string, body?: any) => {
      if (path === '/admin/review/challenge') return { challenge_id: 'c1', resend_after: 60 };
      if (path === '/admin/review/keys') {
        expect(body.otp).toBe('4321'); expect(body.challenge_id).toBe('c1'); expect(body.environment).toBe('production');
        expect(body.api_base_url).toBe('https://yash-tryon-test.emergent.host/api');
        return { action: 'provision', accounts: ACCOUNTS(true), unchanged: [], detail: 'Keys are shown once; only hashes are stored.', shown_once: true,
          issued: [{ reviewer_id: 'store-review-customer', role: 'customer', role_label: 'Customer', access_key: KEY }], note_text: `PRIVATE NOTE ${KEY}` };
      }
      throw new Error('unexpected ' + path);
    });
    await render(<ReviewKeysScreen />);
    await waitFor(() => expect(screen.getByTestId('review-provision')).toBeTruthy());
    expect(screen.getByText('PRODUCTION · yash-tryon-test.emergent.host')).toBeTruthy();
    expect(screen.getByText(/application-enforced/)).toBeTruthy();
    await fireEvent.press(screen.getByTestId('review-provision'));
    await waitFor(() => expect(screen.getByTestId('review-otp-card')).toBeTruthy());
    expect(mockPost).toHaveBeenCalledWith('/admin/review/challenge');
    // No key call happens without a complete OTP.
    await fireEvent.press(screen.getByTestId('review-otp-submit'));
    expect(mockPost).not.toHaveBeenCalledWith('/admin/review/keys', expect.anything());
    await fireEvent.changeText(screen.getByTestId('review-otp-input'), '4321');
    await fireEvent.press(screen.getByTestId('review-otp-submit'));
    await waitFor(() => expect(screen.getByTestId('review-keys-result')).toBeTruthy());
    expect(screen.getByText(KEY)).toBeTruthy();
    expect(screen.getByText('New access keys — shown once')).toBeTruthy();
    await fireEvent.press(screen.getByTestId('copy-store-review-customer'));
    expect(mockSetString).toHaveBeenCalledWith(`Reviewer ID: store-review-customer\nAccess key: ${KEY}`);
    await fireEvent.press(screen.getByTestId('copy-note'));
    expect(mockSetString).toHaveBeenLastCalledWith(`PRIVATE NOTE ${KEY}`);
    // All four accounts now exist: the provision button is disabled and explains that only ROTATE issues a new key.
    const button = screen.getByTestId('review-provision');
    expect(button.props.accessibilityState?.disabled ?? button.props.disabled).toBe(true);
    expect(screen.getByText('ALL 4 ACCOUNTS EXIST — USE ROTATE FOR A NEW KEY')).toBeTruthy();
    expect(screen.getByTestId('rotate-store-review-admin')).toBeTruthy();
  });

  it('surfaces a wrong OTP without leaving the OTP step', async () => {
    mockGet.mockResolvedValueOnce({ ...STATUS, accounts: ACCOUNTS(true), missing_accounts: [] });
    mockPost.mockImplementation(async (path: string) => {
      if (path === '/admin/review/challenge') return { challenge_id: 'c2', resend_after: 60 };
      throw Object.assign(new Error('OTP is invalid, expired, or exhausted'), { code: 'OTP_INVALID', status: 400 });
    });
    await render(<ReviewKeysScreen />);
    await waitFor(() => expect(screen.getByTestId('rotate-store-review-telecaller')).toBeTruthy());
    await fireEvent.press(screen.getByTestId('rotate-store-review-telecaller'));
    expect(mockConfirm).toHaveBeenCalled();
    await waitFor(() => expect(screen.getByTestId('review-otp-card')).toBeTruthy());
    await fireEvent.changeText(screen.getByTestId('review-otp-input'), '0000');
    await fireEvent.press(screen.getByTestId('review-otp-submit'));
    await waitFor(() => expect(screen.getByTestId('review-otp-error')).toBeTruthy());
    expect(screen.getByText('OTP is invalid, expired, or exhausted')).toBeTruthy();
    expect(screen.queryByTestId('review-keys-result')).toBeNull();
  });
});

const CONSENT = {
  granted: false, version: null, current_version: '2026-09-13', recipients: [{ name: 'Anthropic PBC', service: 'Claude', role: 'AI model provider (third party)',
    via: 'Emergent LLM gateway', location: 'United States', data_sent: ['The text you type'], data_not_sent: ['Your phone number'], purpose: 'Reply', retention: 'Deleted on withdrawal.' }],
  withdrawal_effects: ['No further text is sent'], required_for: ['AI assistant conversation', 'AI assistant quick prompts'], not_required_for: ['Catalogue'],
};

describe('AIAssistantScreen consent gate', () => {
  it('blocks quick prompts and typing until consent is granted, then sends', async () => {
    mockGet.mockResolvedValue(CONSENT);
    await render(<AIAssistantScreen />);
    await waitFor(() => expect(screen.getByTestId('ai-consent-card')).toBeTruthy());
    expect(screen.getByText(/Anthropic PBC/)).toBeTruthy();
    expect(screen.queryByTestId('ai-input')).toBeNull();
    expect(screen.queryByText('How to pitch silver anklets?')).toBeNull(); // quick prompts are not offered before consent
    expect(mockPost).not.toHaveBeenCalled();
    mockPost.mockImplementation(async (path: string, body?: any) => {
      if (path === '/ai/consent') { expect(body).toEqual({ granted: true, source: 'assistant' }); return { ...CONSENT, granted: true, version: '2026-09-13' }; }
      if (path === '/ai/chat') return { response: 'Pitch by purity.', session_id: 's', message_id: 'm1', stored: true };
      throw new Error('unexpected ' + path);
    });
    await fireEvent.press(screen.getByTestId('ai-consent-allow'));
    await waitFor(() => expect(screen.getByTestId('ai-input')).toBeTruthy());
    await fireEvent.press(screen.getByText('How to pitch silver anklets?'));
    await waitFor(() => expect(screen.getByText('Pitch by purity.')).toBeTruthy());
    expect(mockPost).toHaveBeenCalledWith('/ai/chat', { message: 'How to pitch silver anklets?', session_id: '', language: 'en' });
  });

  it('declining leaves the assistant without sending anything and returns to the app', async () => {
    mockGet.mockResolvedValue(CONSENT);
    await render(<AIAssistantScreen />);
    await waitFor(() => expect(screen.getByTestId('ai-consent-decline')).toBeTruthy());
    await fireEvent.press(screen.getByTestId('ai-consent-decline'));
    expect(mockBack).toHaveBeenCalled();
    expect(mockPost).not.toHaveBeenCalled();
  });
});
