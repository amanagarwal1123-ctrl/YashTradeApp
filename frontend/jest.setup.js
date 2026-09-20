/* Native boundaries only. The behaviour under test (screens, hooks, contexts) is never mocked here. */

// react-native-keyboard-controller is a native module (no Expo Go / Jest binding). Its official Jest mock renders
// KeyboardAwareScrollView as ScrollView and KeyboardAvoidingView as View, so the wrapped screens still render
// their real content; keyboard AVOIDANCE itself is a native-runtime property and is not proven by these tests.
jest.mock('react-native-keyboard-controller', () => require('react-native-keyboard-controller/jest'));
