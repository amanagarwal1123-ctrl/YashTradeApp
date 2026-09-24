import { useCallback } from 'react';
import { Alert, Platform } from 'react-native';
import { useRouter } from 'expo-router';
import { useAuth } from '../context/AuthContext';
import { confirmAlert } from '../utils/alert';

export const SIGN_IN_PROMPT = {
  title: 'Sign in to continue',
  body: 'Cart, wishlist and price enquiries need your account. Sign in with your mobile number to continue.',
};

/**
 * Runs `action` for a signed-in user. A guest (iOS catalogue preview) gets a short explanation and a Sign in button
 * instead — account features are never silently attempted without a session.
 */
export function useRequireSignIn() {
  const { user } = useAuth();
  const router = useRouter();
  return useCallback((action: () => void) => {
    if (user) { action(); return; }
    const go = () => router.push('/login');
    if (Platform.OS === 'web') { confirmAlert(SIGN_IN_PROMPT.title, SIGN_IN_PROMPT.body, go, 'Sign in'); return; }
    Alert.alert(SIGN_IN_PROMPT.title, SIGN_IN_PROMPT.body, [{ text: 'Not now', style: 'cancel' }, { text: 'Sign in', onPress: go }]);
  }, [user, router]);
}
