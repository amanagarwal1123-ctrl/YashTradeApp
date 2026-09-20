/**
 * Cross-platform pinch / pan / double-tap zoom built on the project's installed gesture stack
 * (react-native-gesture-handler 2.28 + react-native-reanimated 4.1). React Native's ScrollView zoom props are
 * iOS-only, so Android needs real gesture handling; the same code runs on iOS and (touch / double-click) on web.
 *
 * Behaviour: pinch scales around the focal point, pan is bounded to the scaled image, double-tap toggles 1x / 2.5x at
 * the tapped point, scale snaps back to 1x when released below it, and `resetKey` (a new image) resets the transform.
 * While zoomed the horizontal pan is consumed here so it never swipes to the next product or triggers navigation.
 */
import React, { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, { runOnJS, useAnimatedStyle, useSharedValue, withTiming } from 'react-native-reanimated';

export const MIN_SCALE = 1;
export const MAX_SCALE = 5;
export const DOUBLE_TAP_SCALE = 2.5;

/** Pan limits for a scaled image inside a viewport: the image may never leave a gap on either side. */
export const clampOffset = (offset: number, viewport: number, scale: number) => {
  'worklet';
  const max = Math.max(0, (viewport * scale - viewport) / 2);
  return Math.min(max, Math.max(-max, offset));
};

type Props = {
  width: number;
  height: number;
  resetKey: string;
  onZoomChange?: (zoomed: boolean) => void;
  children: React.ReactNode;
  testID?: string;
};

export default function ZoomableImage({ width, height, resetKey, onZoomChange, children, testID }: Props) {
  const scale = useSharedValue(1);
  const savedScale = useSharedValue(1);
  const translateX = useSharedValue(0);
  const translateY = useSharedValue(0);
  const savedX = useSharedValue(0);
  const savedY = useSharedValue(0);

  const reset = () => {
    scale.value = withTiming(1);
    savedScale.value = 1;
    translateX.value = withTiming(0);
    translateY.value = withTiming(0);
    savedX.value = 0;
    savedY.value = 0;
    onZoomChange?.(false);
  };
  // A new image (or a viewport change after rotation) starts at 1x: the previous transform never leaks across photos.
  useEffect(() => { reset(); }, [resetKey, width, height]); // eslint-disable-line react-hooks/exhaustive-deps

  const notify = (zoomed: boolean) => { onZoomChange?.(zoomed); };

  const pinch = Gesture.Pinch()
    .onUpdate(e => {
      const next = Math.min(MAX_SCALE, Math.max(0.8, savedScale.value * e.scale));
      // Keep the focal point under the fingers: translate against the focal offset as the scale changes.
      const focalX = e.focalX - width / 2;
      const focalY = e.focalY - height / 2;
      const ratio = next / scale.value;
      translateX.value = clampOffset(focalX - (focalX - translateX.value) * ratio, width, next);
      translateY.value = clampOffset(focalY - (focalY - translateY.value) * ratio, height, next);
      scale.value = next;
    })
    .onEnd(() => {
      if (scale.value < MIN_SCALE) {
        scale.value = withTiming(1); translateX.value = withTiming(0); translateY.value = withTiming(0);
        savedScale.value = 1; savedX.value = 0; savedY.value = 0;
        runOnJS(notify)(false);
        return;
      }
      savedScale.value = scale.value; savedX.value = translateX.value; savedY.value = translateY.value;
      runOnJS(notify)(scale.value > 1.01);
    });

  const pan = Gesture.Pan()
    .minPointers(1)
    .maxPointers(2)
    .onUpdate(e => {
      if (savedScale.value <= 1) return; // not zoomed: leave horizontal swipes to the parent (prev/next buttons stay tappable)
      translateX.value = clampOffset(savedX.value + e.translationX, width, scale.value);
      translateY.value = clampOffset(savedY.value + e.translationY, height, scale.value);
    })
    .onEnd(() => { savedX.value = translateX.value; savedY.value = translateY.value; });

  const doubleTap = Gesture.Tap()
    .numberOfTaps(2)
    .maxDelay(260)
    .onEnd(e => {
      if (scale.value > 1.01) {
        scale.value = withTiming(1); translateX.value = withTiming(0); translateY.value = withTiming(0);
        savedScale.value = 1; savedX.value = 0; savedY.value = 0;
        runOnJS(notify)(false);
      } else {
        const focalX = e.x - width / 2;
        const focalY = e.y - height / 2;
        const nextX = clampOffset(-focalX * (DOUBLE_TAP_SCALE - 1), width, DOUBLE_TAP_SCALE);
        const nextY = clampOffset(-focalY * (DOUBLE_TAP_SCALE - 1), height, DOUBLE_TAP_SCALE);
        scale.value = withTiming(DOUBLE_TAP_SCALE); translateX.value = withTiming(nextX); translateY.value = withTiming(nextY);
        savedScale.value = DOUBLE_TAP_SCALE; savedX.value = nextX; savedY.value = nextY;
        runOnJS(notify)(true);
      }
    });

  const composed = Gesture.Simultaneous(pinch, pan, doubleTap);
  const animatedStyle = useAnimatedStyle(() => ({
    transform: [{ translateX: translateX.value }, { translateY: translateY.value }, { scale: scale.value }],
  }));

  return (
    <GestureDetector gesture={composed}>
      <View style={[styles.viewport, { width, height }]} testID={testID} accessible accessibilityLabel="Zoomable product photograph. Pinch to zoom, double tap to toggle zoom.">
        <Animated.View style={[styles.content, animatedStyle]}>{children}</Animated.View>
      </View>
    </GestureDetector>
  );
}

const styles = StyleSheet.create({
  viewport: { overflow: 'hidden', alignItems: 'center', justifyContent: 'center' },
  content: { width: '100%', height: '100%' },
});
