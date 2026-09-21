import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react-native';

/**
 * R09-B (found in the 21 Sep browser run): staff need an in-app way to revisit "New customer query" alerts when push
 * is delayed or denied. The central workspace therefore carries an Alerts entry to the shared notification history
 * for telecallers and administrators; billing (read-only, never alerted) does not get one.
 */
const mockPush = jest.fn();
let mockUser: any = { id: 't1', role: 'telecaller', name: 'Tele One' };
let mockUnread = 0;

jest.mock('@expo/vector-icons', () => {
  const ReactActual = jest.requireActual('react');
  const { Text: RNText } = jest.requireActual('react-native');
  return { Ionicons: (props: { name: string }) => ReactActual.createElement(RNText, { testID: `icon-${props.name}` }, props.name) };
});
jest.mock('expo-image', () => ({ Image: () => null }));
jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockPush, replace: jest.fn(), back: jest.fn() }),
  useLocalSearchParams: () => ({}),
  useFocusEffect: (effect: () => void | (() => void)) => { const ReactActual = jest.requireActual('react'); ReactActual.useEffect(effect, [effect]); },
}));
jest.mock('../api', () => ({ api: { get: async (path: string) => {
  if (path.startsWith('/requests?')) return { requests: [], total: 0, counts: {}, sort: 'fresh' };
  if (path === '/requests/catalog') return { types: [], head_labels: {} };
  if (path === '/requests/queue/status') return null;
  if (path === '/requests/staff-options') return { users: [] };
  if (path === '/notifications/inbox?page=1&limit=1') return { unread: mockUnread, total: mockUnread, notifications: [] };
  throw new Error(`unexpected GET ${path}`);
} } }));
jest.mock('../context/AuthContext', () => ({ useAuth: () => ({ user: mockUser, logout: jest.fn(), loading: false }) }));
jest.mock('../push', () => ({ pushSupported: () => false, permissionState: async () => 'granted', enablePush: async () => 'granted' }));
jest.mock('../components/staff/RequestDetail', () => () => null);
jest.mock('../components/staff/CompletionReports', () => () => null);

// eslint-disable-next-line import/first
import RequestsWorkspace from '../components/staff/RequestsWorkspace';

beforeEach(() => { mockPush.mockReset(); mockUser = { id: 't1', role: 'telecaller', name: 'Tele One' }; mockUnread = 0; });

describe('R09-B – staff can revisit query alerts from the workspace', () => {
  it('telecaller: the Alerts button opens the shared notification history', async () => {
    render(<RequestsWorkspace />);
    fireEvent.press(await screen.findByTestId('requests-alerts'));
    expect(mockPush).toHaveBeenCalledWith('/notifications');
  });

  it('the Alerts button carries the unread count (bell, 21 Sep)', async () => {
    mockUnread = 4;
    render(<RequestsWorkspace />);
    expect(await screen.findByText('Alerts (4)')).toBeTruthy();
    expect(screen.getByTestId('icon-notifications')).toBeTruthy();
  });

  it('administrator gets the same entry', async () => {
    mockUser = { id: 'a1', role: 'admin', name: 'Admin' };
    render(<RequestsWorkspace />);
    expect(await screen.findByTestId('requests-alerts')).toBeTruthy();
  });

  it('billing (read-only, never alerted) has no Alerts entry', async () => {
    mockUser = { id: 'b1', role: 'billing_executive', name: 'Billing' };
    render(<RequestsWorkspace />);
    await screen.findByTestId('requests-title');
    expect(screen.queryByTestId('requests-alerts')).toBeNull();
  });
});
