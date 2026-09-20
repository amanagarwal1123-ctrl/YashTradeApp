import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';

/** R05 client side: MCX is DISPLAYED and EDITED in market units (silver INR/kg, gold INR/10 g) and saved through the
 *  unit-aware field; the canonical INR/g number is shown alongside, never re-labelled. */
const mockGet = jest.fn<Promise<any>, [string]>();
const mockPost = jest.fn<Promise<any>, [string, any?]>();
jest.mock('../api', () => ({ api: { get: (...a: [string]) => mockGet(...a), post: (...a: [string, any?]) => mockPost(...a), put: jest.fn(), delete: jest.fn() } }));
jest.mock('expo-router', () => ({ useRouter: () => ({ replace: jest.fn(), push: jest.fn() }), useFocusEffect: (cb: () => any) => { const React = jest.requireActual('react'); React.useEffect(() => cb(), [cb]); } }));
jest.mock('../context/AuthContext', () => ({ useAuth: () => ({ user: { id: 'u_admin', role: 'admin', name: 'Owner' } }) }));
jest.mock('@expo/vector-icons', () => {
  const ReactActual = jest.requireActual('react');
  const { Text: RNText } = jest.requireActual('react-native');
  return { Ionicons: (props: { name: string }) => ReactActual.createElement(RNText, null, props.name) };
});

// eslint-disable-next-line import/first
import StaffRates from '../../app/staff-rates';

const RATES = { version: 7, units: { mcx_display: { silver: 'INR/kg', gold: 'INR/10g' } }, mcx_units_verified: true,
  silver_physical_rate: 102.5, silver_mcx_rate: 100, silver_mcx_display_rate: 100000, silver_physical_mode: 'calculated', silver_physical_premium: 2.5, silver_purity: '999',
  gold_physical_rate: 7540, gold_mcx_rate: 7500, gold_mcx_display_rate: 75000, gold_physical_mode: 'manual', gold_purity: '24K' };

beforeEach(() => {
  mockGet.mockReset(); mockPost.mockReset();
  mockGet.mockImplementation(async (path: string) => path === '/rates/latest' ? RATES : { slabs: [] });
});

describe('StaffRates MCX units', () => {
  it('shows silver per kg and gold per 10 g with the canonical INR/g beside them', async () => {
    render(<StaffRates />);
    await waitFor(() => expect(screen.getByTestId('current-mcx-silver')).toBeTruthy());
    const text = (id: string) => screen.getByTestId(id).props.children.flat(Infinity).join('');
    expect(text('current-mcx-silver')).toContain('MCX 100000 INR/kg (= 100 INR/g)');
    expect(text('current-mcx-silver')).toContain('physical = MCX + 2.5 INR/g premium');
    expect(text('current-mcx-gold')).toContain('MCX 75000 INR/10g (= 7500 INR/g)');
    expect(screen.queryByTestId('mcx-unverified-silver')).toBeNull();
  });

  it('saves the edited quote through the unit-aware display field (never the INR/g field) and confirms both numbers', async () => {
    mockPost.mockResolvedValue({ ...RATES, version: 8, silver_mcx_display_rate: 101000, silver_mcx_rate: 101, silver_physical_rate: 103.5 });
    render(<StaffRates />);
    await waitFor(() => expect(screen.getByTestId('rate-mcx').props.value).toBe('100000'));   // primed from the server in market units
    await act(async () => { fireEvent(screen.getByTestId('rate-mcx'), 'changeText', '101000'); });
    await act(async () => { fireEvent.press(screen.getByTestId('rate-save')); });
    await waitFor(() => expect(mockPost).toHaveBeenCalledTimes(1));
    const [path, body] = mockPost.mock.calls[0];
    expect(path).toBe('/rates');
    expect(body).toMatchObject({ version: 7, silver_mcx_display_rate: 101000, silver_physical_mode: 'calculated', silver_physical_premium: 2.5 });
    expect(body).not.toHaveProperty('silver_mcx_rate');
    expect(body).not.toHaveProperty('gold_mcx_display_rate');        // the other metal is untouched
    await waitFor(() => expect(screen.getByTestId('rates-confirmation').props.children).toContain('MCX 101000 INR/kg (= 101 INR/g)'));
  });

  it('flags a stored quote whose unit basis was never confirmed', async () => {
    mockGet.mockImplementation(async (path: string) => path === '/rates/latest' ? { ...RATES, mcx_units_verified: false } : { slabs: [] });
    render(<StaffRates />);
    await waitFor(() => expect(screen.getByTestId('mcx-unverified-silver')).toBeTruthy());
    expect(screen.getByTestId('mcx-unverified-gold')).toBeTruthy();
  });
});
