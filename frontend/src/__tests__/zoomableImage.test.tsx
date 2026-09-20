import React from 'react';
import { Text } from 'react-native';
import { act, render } from '@testing-library/react-native';

/** R02: the viewer's transform maths and the reset-on-image-switch contract. Native pinch/pan gestures themselves can
 *  only be exercised on a device; this covers the deterministic parts (pan bounds, focal maths, reset semantics). */
jest.mock('react-native-reanimated', () => require('react-native-reanimated/mock'));
jest.mock('react-native-gesture-handler', () => {
  const ReactActual = jest.requireActual('react');
  const { View } = jest.requireActual('react-native');
  const chain: any = new Proxy(() => chain, { get: () => () => chain, apply: () => chain });
  return {
    GestureDetector: ({ children }: any) => ReactActual.createElement(View, null, children),
    Gesture: { Pinch: () => chain, Pan: () => chain, Tap: () => chain, Simultaneous: () => chain },
  };
});

// eslint-disable-next-line import/first
import ZoomableImage, { clampOffset, DOUBLE_TAP_SCALE, MAX_SCALE, MIN_SCALE } from '../components/ZoomableImage';

describe('clampOffset (bounded pan)', () => {
  it('never lets a scaled image leave a gap on either side of the viewport', () => {
    expect(clampOffset(500, 390, 1)).toBe(0);            // not zoomed: no pan at all
    expect(Math.abs(clampOffset(-500, 390, 1))).toBe(0);
    expect(clampOffset(1000, 390, 2)).toBe(195);         // 2x: half of the overflow each side
    expect(clampOffset(-1000, 390, 2)).toBe(-195);
    expect(clampOffset(50, 390, 2)).toBe(50);            // inside the bounds: untouched
    expect(clampOffset(9999, 390, MAX_SCALE)).toBe((390 * MAX_SCALE - 390) / 2);
  });

  it('exposes sane scale limits for double-tap and pinch', () => {
    expect(MIN_SCALE).toBe(1);
    expect(DOUBLE_TAP_SCALE).toBeGreaterThan(MIN_SCALE);
    expect(MAX_SCALE).toBeGreaterThanOrEqual(DOUBLE_TAP_SCALE);
  });
});

describe('ZoomableImage reset contract', () => {
  it('renders its child inside the accessible viewport and reports "not zoomed" on mount', () => {
    const onZoomChange = jest.fn();
    const tree = render(<ZoomableImage width={390} height={500} resetKey="p1:0" onZoomChange={onZoomChange} testID="zoom-area"><Text>photo</Text></ZoomableImage>);
    expect(tree.getByText('photo')).toBeTruthy();
    expect(tree.getByTestId('zoom-area').props.accessibilityLabel).toMatch(/Pinch to zoom/);
    expect(onZoomChange).toHaveBeenLastCalledWith(false);
  });

  it('resets (zoomed=false) whenever the selected image or the viewport changes, and not on unrelated rerenders', () => {
    const onZoomChange = jest.fn();
    const tree = render(<ZoomableImage width={390} height={500} resetKey="p1:0" onZoomChange={onZoomChange}><Text>a</Text></ZoomableImage>);
    const calls = onZoomChange.mock.calls.length;
    act(() => { tree.rerender(<ZoomableImage width={390} height={500} resetKey="p1:0" onZoomChange={onZoomChange}><Text>a</Text></ZoomableImage>); });
    expect(onZoomChange.mock.calls.length).toBe(calls);                       // same image: transform kept
    act(() => { tree.rerender(<ZoomableImage width={390} height={500} resetKey="p2:0" onZoomChange={onZoomChange}><Text>b</Text></ZoomableImage>); });
    expect(onZoomChange.mock.calls.length).toBe(calls + 1);                   // next product: reset
    act(() => { tree.rerender(<ZoomableImage width={390} height={500} resetKey="p2:1" onZoomChange={onZoomChange}><Text>b</Text></ZoomableImage>); });
    expect(onZoomChange.mock.calls.length).toBe(calls + 2);                   // next photo of the same product: reset
    act(() => { tree.rerender(<ZoomableImage width={844} height={300} resetKey="p2:1" onZoomChange={onZoomChange}><Text>b</Text></ZoomableImage>); });
    expect(onZoomChange.mock.calls.length).toBe(calls + 3);                   // rotation / viewport change: reset
    expect(onZoomChange.mock.calls.every(([zoomed]) => zoomed === false)).toBe(true);
  });
});
