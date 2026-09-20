import React, { ReactNode } from 'react';
import { Platform, StyleProp, ViewStyle } from 'react-native';
import { KeyboardAvoidingView, KeyboardAwareScrollView } from 'react-native-keyboard-controller';
import type { KeyboardAwareScrollViewProps } from 'react-native-keyboard-controller';

/**
 * The ONE keyboard-aware layout used by every input screen (R06). Built on react-native-keyboard-controller, which
 * reads the real keyboard frame on Android (edge-to-edge, `adjustResize` or not) and iOS instead of guessing.
 *
 * - `KeyboardAwareScreen`: form screens. Scrolls so the focused field, its label/error and the action below it stay
 *   `bottomOffset` above the keyboard; taps on buttons while the keyboard is open are delivered (`handled`).
 * - `KeyboardAvoiding`: screens that own their scroller (lists, chats, OTP boxes). Pads the layout by the keyboard
 *   height; `offset` is the height of any header the layout does not know about (never both padding and offset).
 */
export function KeyboardAwareScreen({ children, keyboardShouldPersistTaps = 'handled', bottomOffset = 24, showsVerticalScrollIndicator = false, ...rest }: KeyboardAwareScrollViewProps) {
  return (
    <KeyboardAwareScrollView bottomOffset={bottomOffset} keyboardShouldPersistTaps={keyboardShouldPersistTaps} showsVerticalScrollIndicator={showsVerticalScrollIndicator} {...rest}>
      {children}
    </KeyboardAwareScrollView>
  );
}

export function KeyboardAvoiding({ children, style, offset = 0 }: { children: ReactNode; style?: StyleProp<ViewStyle>; offset?: number }) {
  return (
    <KeyboardAvoidingView style={style} behavior={Platform.OS === 'ios' ? 'padding' : 'height'} keyboardVerticalOffset={offset}>
      {children}
    </KeyboardAvoidingView>
  );
}
