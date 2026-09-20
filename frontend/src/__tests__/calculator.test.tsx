import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react-native';

/** R04: numeric fields keep their identity while typing (no remount → no keyboard loss), incomplete decimals survive,
 *  multi-item rows are keyed by stable ids, calculations follow the typed values. */
jest.mock('@expo/vector-icons', () => {
  const ReactActual = jest.requireActual('react');
  const { Text: RNText } = jest.requireActual('react-native');
  return { Ionicons: (props: { name: string }) => ReactActual.createElement(RNText, { testID: `icon-${props.name}` }, props.name) };
});
jest.mock('react-native-keyboard-controller', () => {
  const ReactActual = jest.requireActual('react');
  const { ScrollView, View } = jest.requireActual('react-native');
  return {
    KeyboardAwareScrollView: ReactActual.forwardRef((props: any, ref: any) => ReactActual.createElement(ScrollView, { ...props, ref })),
    KeyboardToolbar: (props: any) => ReactActual.createElement(View, { testID: 'keyboard-toolbar', ...props }),
  };
});

// eslint-disable-next-line import/first
import CalculatorScreen, { sanitizeDecimal } from '../../app/(tabs)/calculator';

describe('sanitizeDecimal', () => {
  it('keeps digits and one decimal point exactly as typed', () => {
    expect(sanitizeDecimal('123.')).toBe('123.');
    expect(sanitizeDecimal('123.45')).toBe('123.45');
    expect(sanitizeDecimal('1.2.3')).toBe('1.23');
    expect(sanitizeDecimal('12a,b3')).toBe('123');
    expect(sanitizeDecimal('.5')).toBe('.5');
  });
});

describe('CalculatorScreen', () => {
  it('accepts continuous decimal typing in the SAME field instance and keeps the unfinished "123." value', async () => {
    render(<CalculatorScreen />);
    const before = screen.getByTestId('weight-input');
    const instance = before;
    for (const v of ['1', '12', '123', '123.', '123.4', '123.45']) {
      await act(async () => { fireEvent(screen.getByTestId('weight-input'), 'changeText', v); });
      expect(screen.getByTestId('weight-input').props.value).toBe(v);
    }
    expect(screen.getByTestId('weight-input')).toBe(instance); // no remount between keystrokes
    await act(async () => { fireEvent(screen.getByTestId('rate-input'), 'changeText', '100'); });
    await act(async () => { fireEvent(screen.getByTestId('making-input'), 'changeText', '50'); });
    // 123.45 g × 100 + 50 = 12395 → GST 3 % = 371.85 → total 12766.85
    expect(screen.getByTestId('single-total').props.children.join('')).toBe('₹12766.85');
    expect(screen.getByTestId('keyboard-toolbar')).toBeTruthy(); // iOS "Done" action for the decimal keyboard
  });

  it('multi-item rows keep their values when another row is removed (rows keyed by stable ids)', async () => {
    render(<CalculatorScreen />);
    await act(async () => { fireEvent.press(screen.getByTestId('multi-mode-btn')); });
    await act(async () => { fireEvent.press(screen.getByTestId('add-item-btn')); });
    expect(screen.getAllByTestId(/calc-item-weight-/)).toHaveLength(2);
    for (const v of ['1', '10', '10.', '10.5']) {
      await act(async () => { fireEvent(screen.getByTestId('calc-item-weight-1'), 'changeText', v); });
      expect(screen.getByTestId('calc-item-weight-1').props.value).toBe(v);
    }
    // deleting the FIRST row must not clear the second one (it becomes row 0, same data, same key)
    await act(async () => { fireEvent.press(screen.getByTestId('calc-item-remove-0')); });
    expect(screen.getAllByTestId(/calc-item-weight-/)).toHaveLength(1);
    expect(screen.getByTestId('calc-item-weight-0').props.value).toBe('10.5');
  });
});
