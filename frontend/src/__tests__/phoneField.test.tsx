import React, { useState } from 'react';
import { fireEvent, render, screen } from '@testing-library/react-native';
import type { CountryCode } from 'libphonenumber-js';

// eslint-disable-next-line import/first
import PhoneField from '../components/PhoneField';
import { canonicalPhone } from '../phone';

function Harness({ initialCountry = 'IN' as CountryCode, onCanonical }: { initialCountry?: CountryCode; onCanonical: (v: string | null) => void }) {
  const [country, setCountry] = useState<CountryCode>(initialCountry);
  const [national, setNational] = useState('');
  return <PhoneField testID="phone-input" country={country} national={national} onChange={(c, v) => { setCountry(c); setNational(v); onCanonical(canonicalPhone(v, c)); }} />;
}

describe('PhoneField', () => {
  it('defaults to India and accepts a formatted Indian number without cutting digits', async () => {
    const spy = jest.fn();
    await render(<Harness onCanonical={spy} />);
    expect(screen.getByText('+91')).toBeTruthy();
    await fireEvent.changeText(screen.getByTestId('phone-input'), '98765-43210');
    expect(screen.getByTestId('phone-input').props.value).toBe('9876543210');
    expect(spy).toHaveLastReturnedWith(undefined);
    expect(spy.mock.calls.at(-1)?.[0]).toBe('9876543210');
    expect(screen.getByTestId('phone-input-hint').props.children).toBe('+91 98765 43210');
  });

  it('a pasted Australian number switches the selector to +61 and keeps all nine digits', async () => {
    const spy = jest.fn();
    await render(<Harness onCanonical={spy} />);
    await fireEvent.changeText(screen.getByTestId('phone-input'), '+61 412 345 678');
    expect(screen.getByText('+61')).toBeTruthy();
    expect(screen.getByTestId('phone-input').props.value).toBe('412345678');
    expect(spy.mock.calls.at(-1)?.[0]).toBe('+61412345678');
  });

  it('Australian trunk zero is accepted as typed and normalised only in the canonical value', async () => {
    const spy = jest.fn();
    await render(<Harness initialCountry="AU" onCanonical={spy} />);
    await fireEvent.changeText(screen.getByTestId('phone-input'), '0412 345 678');
    expect(screen.getByTestId('phone-input').props.value).toBe('0412345678');
    expect(spy.mock.calls.at(-1)?.[0]).toBe('+61412345678');
  });

  it('USA / Canada: pasted +1 numbers pick the right country; an incomplete number shows guidance', async () => {
    const spy = jest.fn();
    await render(<Harness onCanonical={spy} />);
    await fireEvent.changeText(screen.getByTestId('phone-input'), '+1 (416) 555-0134');
    expect(screen.getByText('+1')).toBeTruthy();
    expect(screen.getByLabelText('Country Canada +1')).toBeTruthy();
    expect(spy.mock.calls.at(-1)?.[0]).toBe('+14165550134');
    await fireEvent.changeText(screen.getByTestId('phone-input'), '415 555 26');
    expect(spy.mock.calls.at(-1)?.[0]).toBeNull();
    expect(screen.getByTestId('phone-input-hint').props.children).toMatch(/valid Canada mobile number/);
  });

  it('changing the country from the sheet re-interprets the digits already typed', async () => {
    const spy = jest.fn();
    await render(<Harness onCanonical={spy} />);
    await fireEvent.changeText(screen.getByTestId('phone-input'), '412345678');
    expect(spy.mock.calls.at(-1)?.[0]).toBeNull(); // not an Indian number
    await fireEvent.press(screen.getByTestId('phone-input-country'));
    await fireEvent.press(screen.getByTestId('phone-input-country-AU'));
    expect(screen.getByText('+61')).toBeTruthy();
    expect(screen.getByTestId('phone-input').props.value).toBe('412345678');
    expect(spy.mock.calls.at(-1)?.[0]).toBe('+61412345678');
    await fireEvent.press(screen.getByTestId('phone-input-country'));
    await fireEvent.press(screen.getByTestId('phone-input-country-US'));
    expect(spy.mock.calls.at(-1)?.[0]).toBeNull(); // 9 digits are not a US number; nothing was dropped
    expect(screen.getByTestId('phone-input').props.value).toBe('412345678');
  });
});
