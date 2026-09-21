import React from 'react';
import { BackHandler, Keyboard, Platform } from 'react-native';
import { act, render } from '@testing-library/react-native';

/**
 * F09 (independent review): the root Android back listener must be bound to navigation FOCUS, not to mounting.
 * A root screen stays mounted under product / image-viewer / notifications / modal routes; while one of those is
 * focused the root listener must not exist, so the pushed screen's own Back keeps working. `useFocusEffect` is the
 * navigation boundary here (its focus/blur semantics come from React Navigation and are driven by the test).
 */
const focus = { focused: true, version: 0 };
jest.mock('expo-router', () => ({
  useRouter: () => ({ replace: jest.fn(), back: jest.fn(), push: jest.fn() }),
  useFocusEffect: (cb: () => void | (() => void)) => {
    const ReactActual = jest.requireActual('react');
    // React Navigation runs the effect when the screen gains focus and its cleanup when it loses focus.
    ReactActual.useEffect(() => (focus.focused ? cb() : undefined), [cb, focus.version]);
  },
}));

// eslint-disable-next-line import/first
import { useRootBackHandler } from '../navigation';

type Handler = () => boolean;
let listeners: Handler[] = [];
const pressBack = () => { for (const h of [...listeners].reverse()) { if (h()) return true; } return false; };

function Root({ onBack }: { onBack?: () => boolean }) { useRootBackHandler(onBack); return null; }

beforeEach(() => {
  (Platform as any).OS = 'android';
  listeners = []; focus.focused = true; focus.version = 0;
  jest.spyOn(BackHandler, 'addEventListener').mockImplementation(((_: string, handler: Handler) => {
    listeners.push(handler);
    return { remove: () => { listeners = listeners.filter(h => h !== handler); } };
  }) as any);
  jest.spyOn(Keyboard, 'isVisible').mockReturnValue(false);
  jest.spyOn(Keyboard, 'dismiss').mockImplementation(() => {});
});
afterEach(() => jest.restoreAllMocks());

describe('F09 – root back handler is focus-scoped', () => {
  it('while the root is focused: Back is consumed (keyboard dismissed first, then onBack, then stay put)', () => {
    const onBack = jest.fn(() => false);
    render(<Root onBack={onBack} />);
    expect(listeners).toHaveLength(1);
    (Keyboard.isVisible as jest.Mock).mockReturnValue(true);
    expect(pressBack()).toBe(true);
    expect(Keyboard.dismiss).toHaveBeenCalledTimes(1);
    expect(onBack).not.toHaveBeenCalled();
    (Keyboard.isVisible as jest.Mock).mockReturnValue(false);
    expect(pressBack()).toBe(true);
    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it('when another route is focused over the (still mounted) root, the root listener is REMOVED and Back is not swallowed', () => {
    const onBack = jest.fn(() => true);
    const view = render(<Root onBack={onBack} />);
    expect(listeners).toHaveLength(1);
    // push product / image viewer / notifications: the root loses focus but stays mounted
    act(() => { focus.focused = false; focus.version += 1; view.rerender(<Root onBack={onBack} />); });
    expect(listeners).toHaveLength(0);
    expect(pressBack()).toBe(false); // nothing consumed: the pushed screen's own Back / navigator pop proceeds
    expect(onBack).not.toHaveBeenCalled();
    // back on the root: the listener is registered again exactly once
    act(() => { focus.focused = true; focus.version += 1; view.rerender(<Root onBack={onBack} />); });
    expect(listeners).toHaveLength(1);
    expect(pressBack()).toBe(true);
    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it('a screen pushed over the root registers its own handler which wins (LIFO) even if the root were focused', () => {
    render(<Root onBack={jest.fn(() => true)} />);
    const pushed = jest.fn(() => true);
    const sub = BackHandler.addEventListener('hardwareBackPress', pushed);
    expect(pressBack()).toBe(true);
    expect(pushed).toHaveBeenCalledTimes(1);
    sub.remove();
  });

  it('registers nothing on iOS / web (no hardware back button)', () => {
    (Platform as any).OS = 'ios';
    render(<Root />);
    expect(listeners).toHaveLength(0);
  });
});
