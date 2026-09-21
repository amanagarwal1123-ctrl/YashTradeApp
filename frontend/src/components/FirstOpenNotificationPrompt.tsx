import React, { useEffect, useState } from 'react';
import { Modal, Pressable, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Colors, FontSize, Spacing } from '../theme';
import { useAuth } from '../context/AuthContext';
import { firstOpenPromptDue, markFirstOpenPromptSeen, requestPermission, syncPushIfGranted } from '../push';

/**
 * First-open notification prompt (owner decision, 21 Sep 2026): on the very first launch — before sign-in — a short
 * branded explanation is shown, then the OS dialog. Shown once per install on Android and iOS; "Not now", a denial
 * or a dismissal is never re-asked at launch (the bell → Notifications screen keeps the Allow / Open Settings path).
 * Never shown on web, on simulators, or when the OS has already decided (permission kept across an iOS reinstall).
 */
export function FirstOpenNotificationPrompt() {
  const { user } = useAuth();
  const insets = useSafeAreaInsets();
  const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    firstOpenPromptDue().then(due => { if (alive && due) setVisible(true); }).catch(() => {});
    return () => { alive = false; };
  }, []);

  const later = async () => {
    setVisible(false);
    await markFirstOpenPromptSeen();
  };

  const allow = async () => {
    if (busy) return;
    setBusy(true);
    await markFirstOpenPromptSeen();
    try {
      const state = await requestPermission();
      if (state === 'granted' && user) await syncPushIfGranted(); // registers the token now; otherwise sign-in does it
    } finally {
      setBusy(false);
      setVisible(false);
    }
  };

  if (!visible) return null;
  return (
    <Modal transparent animationType="slide" visible onRequestClose={later} statusBarTranslucent>
      <View style={styles.fill}>
        <Pressable style={styles.backdrop} onPress={later} accessibilityLabel="Not now" />
        <View style={[styles.sheet, { paddingBottom: Math.max(insets.bottom, Spacing.lg) }]} testID="first-open-notification-prompt">
          <View style={styles.iconWrap}><Ionicons name="notifications" size={30} color="#000" /></View>
          <Text style={styles.title}>Stay updated</Text>
          <Text style={styles.text}>Allow notifications to get enquiry updates and offers from Yash. You can change this any time from the bell icon.</Text>
          <TouchableOpacity testID="first-open-notification-continue" style={styles.primary} onPress={allow} disabled={busy} accessibilityRole="button">
            <Text style={styles.primaryText}>Continue</Text>
          </TouchableOpacity>
          <TouchableOpacity testID="first-open-notification-later" style={styles.secondary} onPress={later} disabled={busy} accessibilityRole="button">
            <Text style={styles.secondaryText}>Not now</Text>
          </TouchableOpacity>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, justifyContent: 'flex-end' },
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(0,0,0,0.6)' },
  sheet: { backgroundColor: Colors.modal, borderTopLeftRadius: 24, borderTopRightRadius: 24, paddingHorizontal: Spacing.lg, paddingTop: Spacing.lg, gap: Spacing.md, alignItems: 'center', borderTopWidth: 1, borderColor: Colors.borderGold },
  iconWrap: { width: 64, height: 64, borderRadius: 32, backgroundColor: Colors.gold, alignItems: 'center', justifyContent: 'center' },
  title: { color: Colors.text, fontSize: FontSize.xl, fontWeight: '700' },
  text: { color: Colors.textSecondary, fontSize: FontSize.base, lineHeight: 22, textAlign: 'center' },
  primary: { alignSelf: 'stretch', backgroundColor: Colors.gold, borderRadius: 12, minHeight: 50, alignItems: 'center', justifyContent: 'center', marginTop: Spacing.sm },
  primaryText: { color: '#000', fontWeight: '700', fontSize: FontSize.base },
  secondary: { alignSelf: 'stretch', minHeight: 48, alignItems: 'center', justifyContent: 'center' },
  secondaryText: { color: Colors.textSecondary, fontWeight: '600', fontSize: FontSize.md },
});
