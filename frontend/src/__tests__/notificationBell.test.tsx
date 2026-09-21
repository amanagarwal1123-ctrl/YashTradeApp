import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';

/**
 * Bell icon (owner request 21 Sep 2026): one entry point to the Notifications screen on every role's home, with the
 * account's unread count; silent when signed out or offline.
 */
const mockPush = jest.fn();
let mockUser: any = { id: 'c1', role: 'customer' };
let mockInbox: any = { unread: 3, total: 3, notifications: [] };

jest.mock('@expo/vector-icons', () => {
  const ReactActual = jest.requireActual('react');
  const { Text: RNText } = jest.requireActual('react-native');
  return { Ionicons: (props: { name: string }) => ReactActual.createElement(RNText, { testID: `icon-${props.name}` }, props.name) };
});
jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockPush, replace: jest.fn(), back: jest.fn() }),
  useFocusEffect: (effect: () => void | (() => void)) => { const ReactActual = jest.requireActual('react'); ReactActual.useEffect(effect, [effect]); },
}));
jest.mock('../api', () => ({ api: { get: async (path: string) => {
  if (path === '/notifications/inbox?page=1&limit=1') { if (mockInbox instanceof Error) throw mockInbox; return mockInbox; }
  throw new Error(`unexpected GET ${path}`);
} } }));
jest.mock('../context/AuthContext', () => ({ useAuth: () => ({ user: mockUser, loading: false }) }));

// eslint-disable-next-line import/first
import { NotificationBell } from '../components/NotificationBell';

beforeEach(() => { mockPush.mockReset(); mockUser = { id: 'c1', role: 'customer' }; mockInbox = { unread: 3, total: 3, notifications: [] }; });

describe('notification bell', () => {
  it('opens the Notifications screen and shows the unread count', async () => {
    render(<NotificationBell />);
    expect(await screen.findByTestId('notifications-btn-badge')).toHaveTextContent('3');
    expect(screen.getByTestId('icon-notifications')).toBeTruthy();
    fireEvent.press(screen.getByTestId('notifications-btn'));
    expect(mockPush).toHaveBeenCalledWith('/notifications');
  });

  it('shows the outline bell without a badge when everything is read, and caps the badge at 99+', async () => {
    mockInbox = { unread: 0 };
    render(<NotificationBell testID="tc-alerts" />);
    await waitFor(() => expect(screen.getByTestId('icon-notifications-outline')).toBeTruthy());
    expect(screen.queryByTestId('tc-alerts-badge')).toBeNull();

    mockInbox = { unread: 250 };
    render(<NotificationBell testID="panel-alerts" />);
    expect(await screen.findByTestId('panel-alerts-badge')).toHaveTextContent('99+');
  });

  it('stays quiet when the inbox cannot be loaded or nobody is signed in', async () => {
    mockInbox = new Error('offline');
    render(<NotificationBell />);
    await waitFor(() => expect(screen.getByTestId('icon-notifications-outline')).toBeTruthy());
    expect(screen.queryByTestId('notifications-btn-badge')).toBeNull();

    mockUser = null;
    mockInbox = { unread: 5 };
    render(<NotificationBell testID="anon" />);
    await waitFor(() => expect(screen.getByTestId('anon')).toBeTruthy());
    expect(screen.queryByTestId('anon-badge')).toBeNull();
  });
});
