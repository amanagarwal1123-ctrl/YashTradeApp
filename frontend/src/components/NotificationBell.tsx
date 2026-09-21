import React, { useCallback, useState } from 'react';
import { StyleProp, StyleSheet, Text, TouchableOpacity, View, ViewStyle } from 'react-native';
import { useFocusEffect, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors } from '../theme';
import { api } from '../api';
import { useAuth } from '../context/AuthContext';

/**
 * Bell entry point to the Notifications screen (recent 100 alerts + the turn-on-notifications banner). Shows the
 * account's unread count, refreshed each time the hosting screen gains focus; silent when offline or signed out.
 */
export function NotificationBell({ testID = 'notifications-btn', size = 22, style, accessibilityLabel = 'Notifications' }:
  { testID?: string; size?: number; style?: StyleProp<ViewStyle>; accessibilityLabel?: string }) {
  const router = useRouter();
  const { user } = useAuth();
  const [unread, setUnread] = useState(0);

  useFocusEffect(useCallback(() => {
    let alive = true;
    if (!user) { setUnread(0); return; }
    api.get('/notifications/inbox?page=1&limit=1').then((inbox: any) => { if (alive) setUnread(inbox?.unread || 0); }).catch(() => {});
    return () => { alive = false; };
  }, [user?.id]));

  return (
    <TouchableOpacity testID={testID} style={[styles.btn, style]} onPress={() => router.push('/notifications')} accessibilityRole="button" accessibilityLabel={unread ? `${accessibilityLabel}, ${unread} unread` : accessibilityLabel}>
      <Ionicons name={unread ? 'notifications' : 'notifications-outline'} size={size} color={Colors.text} />
      {unread > 0 && <View style={styles.badge} testID={`${testID}-badge`}><Text style={styles.badgeText}>{unread > 99 ? '99+' : unread}</Text></View>}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  btn: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  badge: { position: 'absolute', top: 2, right: 2, minWidth: 16, height: 16, borderRadius: 8, paddingHorizontal: 3, backgroundColor: Colors.error, alignItems: 'center', justifyContent: 'center' },
  badgeText: { fontSize: 9, color: Colors.text, fontWeight: '700' },
});
