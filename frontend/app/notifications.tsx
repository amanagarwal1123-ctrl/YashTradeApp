import React, { useCallback, useState } from 'react';
import { ActivityIndicator, Linking, RefreshControl, ScrollView, StyleSheet, Switch, Text, TouchableOpacity, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, useRouter } from 'expo-router';
import { Image } from 'expo-image';
import { Ionicons } from '@expo/vector-icons';
import { Colors, FontSize, Spacing } from '../src/theme';
import { api, SessionChangedError } from '../src/api';
import { useAuth } from '../src/context/AuthContext';
import { authorizedDestination, useSafeBack } from '../src/navigation';
import { enablePush, permissionState, pushSupported, PermissionState } from '../src/push';
import { IMAGE_PLACEHOLDER } from '../src/imagePlaceholder';

/**
 * In-app notification history (R09-B): every alert sent to this account is revisitable here, with read state, even when
 * push was delayed or denied. Also hosts the OS-permission prompt (contextual, never at install) and the promotional
 * opt-out, which is separate from operational query/account alerts and from the OS permission itself.
 */
export default function NotificationsScreen() {
  const { user } = useAuth();
  const router = useRouter();
  const back = useSafeBack(user?.role);
  const [data, setData] = useState<any>(null);
  const [prefs, setPrefs] = useState<any>(null);
  const [push, setPush] = useState<{ state: PermissionState; canAskAgain: boolean } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [page, setPage] = useState(1);

  const load = useCallback(async () => {
    try {
      const [inbox, preferences] = await Promise.all([api.get(`/notifications/inbox?page=${page}&limit=30`), api.get('/notifications/preferences')]);
      setData(inbox); setPrefs(preferences); setError('');
      if (pushSupported()) setPush(await permissionState());
    } catch (e: any) { if (!(e instanceof SessionChangedError)) setError(e.message); }
    finally { setLoading(false); }
  }, [page]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const openItem = async (n: any) => {
    if (!n.read_at) {
      setData((prev: any) => prev ? { ...prev, unread: Math.max(0, prev.unread - 1), notifications: prev.notifications.map((x: any) => x.id === n.id ? { ...x, read_at: new Date().toISOString() } : x) } : prev);
      api.post(`/notifications/inbox/${n.id}/read`).catch(() => {});
    }
    const destination = authorizedDestination(n.destination, user?.role);
    if (destination && destination !== '/notifications') router.push(destination as any);
  };

  const toggleMarketing = async (value: boolean) => {
    setPrefs((p: any) => ({ ...p, marketing: value }));
    try { setPrefs(await api.put('/notifications/preferences', { marketing: value })); } catch (e: any) { setError(e.message); load(); }
  };

  const allow = async () => {
    const state = await enablePush();
    setPush({ state, canAskAgain: state !== 'blocked' });
  };

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      <View style={styles.header}>
        <TouchableOpacity testID="notifications-back" onPress={back} style={styles.backBtn} accessibilityLabel="Back"><Ionicons name="arrow-back" size={24} color={Colors.text} /></TouchableOpacity>
        <Text style={styles.title}>Notifications{data?.unread ? ` (${data.unread})` : ''}</Text>
        {!!data?.unread && <TouchableOpacity testID="notifications-read-all" onPress={async () => { await api.post('/notifications/inbox/read-all').catch(() => {}); load(); }} style={styles.readAll}><Text style={styles.readAllText}>Mark all read</Text></TouchableOpacity>}
      </View>
      <ScrollView contentContainerStyle={styles.content} refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor={Colors.gold} />}>
        {!!error && <Text testID="notifications-error" style={styles.error}>{error}</Text>}

        {/* OS permission: explained, contextual, never nagging; Settings when blocked */}
        {push && push.state !== 'granted' && (
          <View style={styles.card} testID="notifications-permission-card">
            <Text style={styles.cardLabel}>PHONE ALERTS</Text>
            <Text style={styles.cardText}>{user?.role === 'customer'
              ? 'Get a phone alert when your enquiry is answered and, if you wish, about new collections. You can use the app fully without alerts.'
              : 'Get a phone alert the moment a customer sends a new query. You can keep working without alerts; the list refreshes on its own.'}</Text>
            {push.state === 'blocked'
              ? <TouchableOpacity testID="notifications-open-settings" style={styles.primaryBtn} onPress={() => Linking.openSettings()}><Text style={styles.primaryBtnText}>Open Settings to allow notifications</Text></TouchableOpacity>
              : <TouchableOpacity testID="notifications-allow" style={styles.primaryBtn} onPress={allow}><Text style={styles.primaryBtnText}>Allow notifications</Text></TouchableOpacity>}
          </View>
        )}
        {push?.state === 'unsupported' && <Text style={styles.muted} testID="notifications-unsupported">Phone alerts need the installed app on a real device; this preview shows the in-app history only.</Text>}

        {/* Promotional consent is separate from operational alerts and from the OS permission */}
        {prefs && (
          <View style={styles.card} testID="notifications-preferences">
            <View style={styles.switchRow}>
              <View style={{ flex: 1 }}>
                <Text style={styles.cardText}>Offers & new collections</Text>
                <Text style={styles.muted}>Promotional alerts. Query and account alerts are not affected by this switch.</Text>
              </View>
              <Switch testID="notifications-marketing-switch" value={!!prefs.marketing} onValueChange={toggleMarketing} trackColor={{ true: Colors.gold, false: Colors.border }} thumbColor="#fff" />
            </View>
          </View>
        )}

        {loading && !data && <ActivityIndicator color={Colors.gold} style={{ marginTop: 24 }} />}
        {data?.notifications.length === 0 && <Text style={styles.muted} testID="notifications-empty">No notifications yet.</Text>}
        {data?.notifications.map((n: any) => (
          <TouchableOpacity key={n.id} testID={`notification-${n.id}`} style={[styles.item, !n.read_at && styles.itemUnread]} onPress={() => openItem(n)} accessibilityRole="button" accessibilityLabel={n.title}>
            {n.image_url ? <Image source={{ uri: n.image_url }} placeholder={IMAGE_PLACEHOLDER} contentFit="cover" cachePolicy="memory-disk" style={styles.itemImage} /> :
              <View style={[styles.itemImage, styles.itemIcon]}><Ionicons name={n.kind === 'marketing' ? 'megaphone-outline' : 'chatbubble-ellipses-outline'} size={20} color={Colors.gold} /></View>}
            <View style={{ flex: 1 }}>
              <Text style={styles.itemTitle}>{n.title}</Text>
              <Text style={styles.itemBody}>{n.body}</Text>
              <Text style={styles.muted}>{new Date(n.created_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })}{n.read_at ? '' : ' · new'}</Text>
            </View>
          </TouchableOpacity>
        ))}
        {data && data.pages > 1 && (
          <View style={styles.pager}>
            <TouchableOpacity testID="notifications-prev" disabled={page <= 1} onPress={() => setPage(page - 1)} style={[styles.pagerBtn, page <= 1 && { opacity: 0.4 }]}><Text style={styles.cardText}>Previous</Text></TouchableOpacity>
            <Text style={styles.muted}>Page {page} / {data.pages}</Text>
            <TouchableOpacity testID="notifications-next" disabled={page >= data.pages} onPress={() => setPage(page + 1)} style={[styles.pagerBtn, page >= data.pages && { opacity: 0.4 }]}><Text style={styles.cardText}>Next</Text></TouchableOpacity>
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: Spacing.md, paddingVertical: Spacing.sm, gap: Spacing.sm },
  backBtn: { minWidth: 44, minHeight: 44, alignItems: 'center', justifyContent: 'center' },
  title: { flex: 1, fontSize: FontSize.xl, fontWeight: '700', color: Colors.text },
  readAll: { minHeight: 44, justifyContent: 'center', paddingHorizontal: Spacing.sm },
  readAllText: { color: Colors.gold, fontWeight: '600', fontSize: FontSize.sm },
  content: { padding: Spacing.lg, gap: Spacing.md, paddingBottom: 40 },
  card: { backgroundColor: Colors.card, borderRadius: 14, padding: Spacing.lg, gap: Spacing.sm, borderWidth: 1, borderColor: Colors.border },
  cardLabel: { color: Colors.gold, fontSize: FontSize.xs, fontWeight: '700', letterSpacing: 1 },
  cardText: { color: Colors.text, fontSize: FontSize.base, lineHeight: 22 },
  muted: { color: Colors.textSecondary, fontSize: FontSize.xs, lineHeight: 18 },
  error: { color: Colors.error, fontSize: FontSize.sm },
  primaryBtn: { backgroundColor: Colors.gold, borderRadius: 10, minHeight: 48, alignItems: 'center', justifyContent: 'center', paddingHorizontal: Spacing.md },
  primaryBtnText: { color: '#000', fontWeight: '700', fontSize: FontSize.sm },
  switchRow: { flexDirection: 'row', alignItems: 'center', gap: Spacing.md },
  item: { flexDirection: 'row', gap: Spacing.md, backgroundColor: Colors.card, borderRadius: 12, padding: Spacing.md, borderWidth: 1, borderColor: Colors.border, minHeight: 72 },
  itemUnread: { borderColor: Colors.gold },
  itemImage: { width: 56, height: 56, borderRadius: 10, backgroundColor: Colors.surface },
  itemIcon: { alignItems: 'center', justifyContent: 'center' },
  itemTitle: { color: Colors.text, fontWeight: '700', fontSize: FontSize.base },
  itemBody: { color: Colors.textSecondary, fontSize: FontSize.sm, marginTop: 2, marginBottom: 4 },
  pager: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: Spacing.md },
  pagerBtn: { minHeight: 44, justifyContent: 'center', paddingHorizontal: Spacing.md, borderRadius: 10, borderWidth: 1, borderColor: Colors.border },
});
