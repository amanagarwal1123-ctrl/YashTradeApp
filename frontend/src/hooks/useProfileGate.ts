import { useCallback, useEffect, useRef, useState } from 'react';
import { useFocusEffect, useRouter } from 'expo-router';
import { Alert, Platform } from 'react-native';
import { useAuth } from '../context/AuthContext';
import { isProfileComplete } from '../components/customer/ProfileCards';

/**
 * Requests to the team (call / video call / cart selection) need name, shop name and place. When the backend answers
 * 428 PROFILE_INCOMPLETE the caller opens the profile form via `promptProfile`; once the customer saves and comes back,
 * the ORIGINAL request is re-sent automatically. `run` wraps the submit function.
 */
export function useProfileGate() {
  const { user, refreshUser } = useAuth();
  const router = useRouter();
  const pending = useRef<null | (() => Promise<void>)>(null);
  const [awaitingProfile, setAwaitingProfile] = useState(false);

  const openProfile = useCallback(() => {
    setAwaitingProfile(true);
    router.push({ pathname: '/edit-profile', params: { complete: '1', resume: '1' } });
  }, [router]);

  const promptProfile = useCallback((retry: () => Promise<void>) => {
    pending.current = retry;
    const title = 'Complete your profile';
    const message = 'Add your name, shop name and place so our team knows who to contact. Your request will be sent right after.';
    if (Platform.OS === 'web') {
      if (window.confirm(`${title}\n\n${message}`)) openProfile(); else pending.current = null;
    } else {
      Alert.alert(title, message, [
        { text: 'Later', style: 'cancel', onPress: () => { pending.current = null; } },
        { text: 'Complete profile', onPress: openProfile },
      ]);
    }
  }, [openProfile]);

  // Back on this screen after the profile form: refresh the session user and resume the pending request.
  useFocusEffect(useCallback(() => {
    if (!awaitingProfile) return;
    setAwaitingProfile(false);
    refreshUser();
  }, [awaitingProfile, refreshUser]));

  useEffect(() => {
    if (!awaitingProfile && pending.current && isProfileComplete(user)) {
      const retry = pending.current;
      pending.current = null;
      retry();
    }
  }, [user, awaitingProfile]);

  /** Run a submit; on PROFILE_INCOMPLETE ask to complete the profile and resume afterwards. Returns true when handled. */
  const gate = useCallback((error: any, retry: () => Promise<void>) => {
    if (error?.code !== 'PROFILE_INCOMPLETE' && error?.status !== 428) return false;
    promptProfile(retry);
    return true;
  }, [promptProfile]);

  return { gate, awaitingProfile };
}
