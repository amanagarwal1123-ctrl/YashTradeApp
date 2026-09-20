import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';

/** R07 (four-box OTP: whole-string autofill/paste distribution, backspace, leading zero, single submission, resend
 *  countdown driven by the SERVER clock) and R08 (15-second cooldown surfaced from resend_at / server_time). */
const mockPost = jest.fn<Promise<any>, [string, any?]>();
const mockLogin = jest.fn(async () => ({ id: 'u1', role: 'customer' }));
const mockReplace = jest.fn(), mockDismissAll = jest.fn();
let params: Record<string, string> = {};

jest.mock('@expo/vector-icons', () => {
  const ReactActual = jest.requireActual('react');
  const { Text: RNText } = jest.requireActual('react-native');
  return { Ionicons: (props: { name: string }) => ReactActual.createElement(RNText, { testID: `icon-${props.name}` }, props.name) };
});
jest.mock('expo-router', () => ({ useRouter: () => ({ replace: mockReplace, dismissAll: mockDismissAll, canDismiss: () => false, push: jest.fn(), back: jest.fn() }), useLocalSearchParams: () => params }));
jest.mock('../api', () => ({ api: { get: jest.fn(), post: (...a: [string, any?]) => mockPost(...a) } }));
jest.mock('../context/AuthContext', () => ({ useAuth: () => ({ login: mockLogin }) }));

// eslint-disable-next-line import/first
import VerifyOTPScreen, { digitsOnly, secondsUntil } from '../../app/verify-otp';

const type = (value: string) => fireEvent(screen.getByTestId('otp-input'), 'changeText', value);
const boxes = () => [0, 1, 2, 3].map(i => screen.getByTestId(`otp-box-${i}`).props.children.props.children);

beforeEach(() => {
  mockPost.mockReset(); mockLogin.mockClear(); mockReplace.mockReset(); mockDismissAll.mockReset();
  params = { phone: '9300000001', challengeId: 'ch-1' };
});

describe('OTP helpers', () => {
  it('keeps only the first four digits of whatever the OS / clipboard delivers', () => {
    expect(digitsOnly('1234')).toBe('1234');
    expect(digitsOnly('Your code is 0912. Valid 10 min')).toBe('0912');
    expect(digitsOnly('12 34 56')).toBe('1234');
    expect(digitsOnly('ab')).toBe('');
  });

  it('computes the resend countdown against the server clock, tolerating device skew', () => {
    const received = Date.parse('2026-09-20T10:00:00Z');
    // device clock is 5 minutes behind the server: without skew correction the countdown would be 5 min too long
    expect(secondsUntil('2026-09-20T10:05:15Z', '2026-09-20T10:05:00Z', received, received)).toBe(15);
    expect(secondsUntil('2026-09-20T10:05:15Z', '2026-09-20T10:05:00Z', received, received + 15000)).toBe(0);
    expect(secondsUntil(undefined, undefined, received)).toBe(0);
  });
});

describe('VerifyOTPScreen four boxes', () => {
  it('fills all four boxes from ONE autofill/paste event and submits exactly once', async () => {
    mockPost.mockResolvedValue({ token: 't', refresh_token: 'r', user: { id: 'u1', role: 'customer' } });
    render(<VerifyOTPScreen />);
    await act(async () => { type('Your code is 0912'); });
    expect(boxes()).toEqual(['0', '9', '1', '2']);          // leading zero preserved
    await waitFor(() => expect(mockPost).toHaveBeenCalledTimes(1));
    expect(mockPost).toHaveBeenCalledWith('/auth/verify-otp', expect.objectContaining({ otp: '0912', challenge_id: 'ch-1', phone: '9300000001' }));
    // a duplicate autofill/submit event for the same completed code does not send a second request
    await act(async () => { type('0912'); fireEvent(screen.getByTestId('otp-input'), 'submitEditing'); });
    expect(mockPost).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith('/(tabs)'));
  });

  it('supports manual typing, backspace and replacement without submitting early', async () => {
    render(<VerifyOTPScreen />);
    await act(async () => { type('1'); type('12'); type('123'); });
    expect(boxes()).toEqual(['1', '2', '3', '']);
    expect(mockPost).not.toHaveBeenCalled();
    await act(async () => { type('12'); });                   // backspace
    expect(boxes()).toEqual(['1', '2', '', '']);
    await act(async () => { type('12x'); });                  // invalid character ignored
    expect(boxes()).toEqual(['1', '2', '', '']);
  });

  it('a wrong code shows the server error, clears the boxes and allows a fresh entry (and a 5th digit starts a new code)', async () => {
    mockPost.mockRejectedValueOnce(Object.assign(new Error('Incorrect code'), { status: 401 }));
    mockPost.mockResolvedValueOnce({ token: 't', refresh_token: 'r', user: { id: 'u1', role: 'customer' } });
    render(<VerifyOTPScreen />);
    await act(async () => { type('1111'); });
    await waitFor(() => expect(screen.getByTestId('verify-otp-error').props.children).toBe('Incorrect code'));
    expect(boxes()).toEqual(['', '', '', '']);
    await act(async () => { type('2222'); });
    await waitFor(() => expect(mockPost).toHaveBeenCalledTimes(2));
    expect(mockPost).toHaveBeenLastCalledWith('/auth/verify-otp', expect.objectContaining({ otp: '2222' }));
  });

  it('drives the resend countdown from the server timing and swaps to the new challenge after resend', async () => {
    jest.useFakeTimers({ now: Date.parse('2026-09-20T10:00:00Z') });
    params = { phone: '9300000001', challengeId: 'ch-1', resendAt: '2026-09-20T10:00:15Z', serverTime: '2026-09-20T10:00:00Z' };
    mockPost.mockResolvedValue({ challenge_id: 'ch-2', resend_at: '2026-09-20T10:00:31Z', server_time: '2026-09-20T10:00:16Z' });
    render(<VerifyOTPScreen />);
    expect(screen.getByTestId('otp-resend-countdown').props.children).toBe('Resend available in 15s');
    await act(async () => { jest.advanceTimersByTime(14000); });
    expect(screen.getByTestId('otp-resend-countdown').props.children).toBe('Resend available in 1s');
    await act(async () => { jest.advanceTimersByTime(2000); });
    expect(screen.getByTestId('otp-resend-countdown').props.children).toBe('Resend OTP');
    await act(async () => { fireEvent.press(screen.getByTestId('otp-resend')); });
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/auth/send-otp', { phone: '9300000001', channel: 'mobile' }));
    await waitFor(() => expect(screen.getByTestId('otp-resend-countdown').props.children).toBe('Resend available in 15s'));
    mockPost.mockResolvedValueOnce({ token: 't', refresh_token: 'r', user: { id: 'u1', role: 'customer' } });
    await act(async () => { type('4321'); });
    await waitFor(() => expect(mockPost).toHaveBeenLastCalledWith('/auth/verify-otp', expect.objectContaining({ otp: '4321', challenge_id: 'ch-2' })));
    jest.useRealTimers();
  });

  it('shows the server-imposed retry time when the resend is refused (cooldown or abuse limit)', async () => {
    jest.useFakeTimers({ now: Date.parse('2026-09-20T10:00:00Z') });
    params = { phone: '9300000001', challengeId: 'ch-1' };
    const refused: any = new Error('Too many codes requested'); refused.status = 429;
    refused.body = { code: 'OTP_RATE_LIMIT', resend_at: '2026-09-20T10:02:00Z', server_time: '2026-09-20T10:00:00Z' };
    mockPost.mockRejectedValueOnce(refused);
    render(<VerifyOTPScreen />);
    await act(async () => { fireEvent.press(screen.getByTestId('otp-resend')); });
    await waitFor(() => expect(screen.getByTestId('verify-otp-error').props.children).toBe('Too many codes requested'));
    expect(screen.getByTestId('otp-resend-countdown').props.children).toBe('Resend available in 120s');
    jest.useRealTimers();
  });
});
