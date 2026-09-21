import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';

/**
 * First-open notification prompt (owner decision 21 Sep 2026): a branded explanation card on the very first launch,
 * before sign-in, then the OS dialog. Continue → OS dialog (token registered only when someone is signed in);
 * Not now → nothing, and neither path is ever shown again at launch.
 */
let mockDue = true;
let mockUser: any = null;
const mockRequestPermission = jest.fn(async (): Promise<string> => 'granted');
const mockMarkSeen = jest.fn(async () => {});
const mockSync = jest.fn(async () => {});

jest.mock('@expo/vector-icons', () => {
  const ReactActual = jest.requireActual('react');
  const { Text: RNText } = jest.requireActual('react-native');
  return { Ionicons: (props: { name: string }) => ReactActual.createElement(RNText, { testID: `icon-${props.name}` }, props.name) };
});
jest.mock('react-native-safe-area-context', () => ({ useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }) }));
jest.mock('../context/AuthContext', () => ({ useAuth: () => ({ user: mockUser, loading: false }) }));
jest.mock('../push', () => ({
  firstOpenPromptDue: async () => mockDue,
  markFirstOpenPromptSeen: () => mockMarkSeen(),
  requestPermission: () => mockRequestPermission(),
  syncPushIfGranted: () => mockSync(),
}));

// eslint-disable-next-line import/first
import { FirstOpenNotificationPrompt } from '../components/FirstOpenNotificationPrompt';

beforeEach(() => { mockDue = true; mockUser = null; mockRequestPermission.mockClear(); mockMarkSeen.mockClear(); mockSync.mockClear(); });

describe('first-open notification prompt', () => {
  it('shows the explanation card on the first open and opens the OS dialog on Continue (signed out: no token registration)', async () => {
    render(<FirstOpenNotificationPrompt />);
    expect(await screen.findByTestId('first-open-notification-prompt')).toBeTruthy();
    expect(screen.getByText('Allow notifications to get enquiry updates and offers from Yash. You can change this any time from the bell icon.')).toBeTruthy();
    expect(mockRequestPermission).not.toHaveBeenCalled(); // the OS dialog waits for the user's tap

    await act(async () => { fireEvent.press(screen.getByTestId('first-open-notification-continue')); });
    await waitFor(() => expect(screen.queryByTestId('first-open-notification-prompt')).toBeNull());
    expect(mockRequestPermission).toHaveBeenCalledTimes(1);
    expect(mockMarkSeen).toHaveBeenCalledTimes(1);
    expect(mockSync).not.toHaveBeenCalled();
  });

  it('registers the push token right away when an account is already signed in and the OS granted', async () => {
    mockUser = { id: 'c1', role: 'customer' };
    render(<FirstOpenNotificationPrompt />);
    const continueBtn = await screen.findByTestId('first-open-notification-continue');
    await act(async () => { fireEvent.press(continueBtn); });
    await waitFor(() => expect(mockSync).toHaveBeenCalledTimes(1));
  });

  it('does not register a token when the OS dialog was denied', async () => {
    mockUser = { id: 'c1', role: 'customer' };
    mockRequestPermission.mockResolvedValueOnce('denied');
    render(<FirstOpenNotificationPrompt />);
    const continueBtn = await screen.findByTestId('first-open-notification-continue');
    await act(async () => { fireEvent.press(continueBtn); });
    await waitFor(() => expect(screen.queryByTestId('first-open-notification-prompt')).toBeNull());
    expect(mockSync).not.toHaveBeenCalled();
    expect(mockMarkSeen).toHaveBeenCalledTimes(1);
  });

  it('Not now closes the card without the OS dialog and marks the prompt as seen for good', async () => {
    render(<FirstOpenNotificationPrompt />);
    const laterBtn = await screen.findByTestId('first-open-notification-later');
    await act(async () => { fireEvent.press(laterBtn); });
    await waitFor(() => expect(screen.queryByTestId('first-open-notification-prompt')).toBeNull());
    expect(mockRequestPermission).not.toHaveBeenCalled();
    expect(mockMarkSeen).toHaveBeenCalledTimes(1);
  });

  it('renders nothing on later launches (prompt already answered or OS already decided)', async () => {
    mockDue = false;
    render(<FirstOpenNotificationPrompt />);
    await act(async () => { await Promise.resolve(); });
    expect(screen.queryByTestId('first-open-notification-prompt')).toBeNull();
    expect(mockRequestPermission).not.toHaveBeenCalled();
  });
});
