import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';

const mockPost = jest.fn<Promise<any>, [string, any?]>();
const mockAlert = jest.fn();
const mockPush = jest.fn();
const mockRefresh = jest.fn(async () => {});
let mockUser: any = null;

jest.mock('@expo/vector-icons', () => {
  const ReactActual = jest.requireActual('react');
  const { Text: RNText } = jest.requireActual('react-native');
  return { Ionicons: (props: { name: string }) => ReactActual.createElement(RNText, { testID: `icon-${props.name}` }, props.name) };
});
jest.mock('expo-router', () => ({ useRouter: () => ({ push: mockPush, replace: jest.fn(), back: jest.fn() }), useFocusEffect: jest.fn() }));
jest.mock('../api', () => ({ api: { get: jest.fn(), post: (...a: [string, any?]) => mockPost(...a) } }));
jest.mock('../utils/alert', () => ({ showAlert: (...a: any[]) => mockAlert(...a), confirmAlert: jest.fn() }));
jest.mock('../context/AuthContext', () => ({ useAuth: () => ({ user: mockUser, refreshUser: mockRefresh }) }));
jest.mock('../context/LanguageContext', () => ({ useLang: () => ({ language: 'en', setLang: jest.fn() }) }));

// eslint-disable-next-line import/first
import { CompleteProfileCard, ProfileConflictCard, isProfileComplete } from '../components/customer/ProfileCards';

beforeEach(() => { mockPost.mockReset(); mockAlert.mockReset(); mockPush.mockReset(); mockRefresh.mockClear(); mockUser = null; });

describe('Home profile cards (app-first sign-up)', () => {
  it('shows the complete-profile card only for customers missing name / shop / place and opens the profile form', async () => {
    mockUser = { id: 'u1', role: 'customer', phone: '9300000001', name: '', shop_name: '', location: '' };
    await render(<CompleteProfileCard />);
    await fireEvent.press(screen.getByTestId('complete-profile-card'));
    expect(mockPush).toHaveBeenCalledWith({ pathname: '/edit-profile', params: { complete: '1' } });
    expect(isProfileComplete(mockUser)).toBe(false);
  });

  it('hides the card once the profile is complete', async () => {
    mockUser = { id: 'u1', role: 'customer', name: 'A', shop_name: 'B', location: 'C' };
    const view = await render(<CompleteProfileCard />);
    expect(view.queryByTestId('complete-profile-card')).toBeNull();
    expect(isProfileComplete({ name: 'A', shop_name: 'B', city: 'Only legacy city' })).toBe(true);
  });

  it('never shows the card to staff', async () => {
    mockUser = { id: 'a1', role: 'admin', name: '', shop_name: '' };
    const view = await render(<CompleteProfileCard />);
    expect(view.queryByTestId('complete-profile-card')).toBeNull();
  });

  it('asks field by field which value to keep after a website registration, requires every choice, then saves and refreshes', async () => {
    mockUser = { id: 'u1', role: 'customer', name: 'Web Name', shop_name: 'Shop', location: 'Ludhiana',
      profile_conflicts: { name: { previous: 'App Name', kept: 'Web Name' }, location: { previous: 'Amritsar', kept: 'Ludhiana' } } };
    mockPost.mockResolvedValue({});
    await render(<ProfileConflictCard />);
    expect(screen.getByTestId('profile-conflict-card')).toBeTruthy();
    expect(screen.getByText('App Name')).toBeTruthy();
    expect(screen.getByText('Ludhiana')).toBeTruthy();
    // Save is disabled until every conflicting field has a choice.
    await fireEvent.press(screen.getByTestId('conflict-name-previous'));
    await fireEvent.press(screen.getByTestId('conflict-save'));
    expect(mockPost).not.toHaveBeenCalled();
    await fireEvent.press(screen.getByTestId('conflict-location-kept'));
    await fireEvent.press(screen.getByTestId('conflict-save'));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith('/auth/profile/conflicts/resolve', { choices: { name: 'previous', location: 'kept' } }));
    await waitFor(() => expect(mockRefresh).toHaveBeenCalled());
    expect(mockAlert).toHaveBeenCalledWith('Profile updated');
  });

  it('renders nothing when there are no conflicts', async () => {
    mockUser = { id: 'u1', role: 'customer', name: 'A', shop_name: 'B', location: 'C', profile_conflicts: {} };
    const view = await render(<ProfileConflictCard />);
    expect(view.queryByTestId('profile-conflict-card')).toBeNull();
  });
});
