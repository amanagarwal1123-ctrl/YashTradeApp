import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator, Alert } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../../src/theme';
import { api } from '../../src/api';
import { useAuth } from '../../src/context/AuthContext';
import { useLang } from '../../src/context/LanguageContext';
import { LANGUAGE_OPTIONS } from '../../src/i18n';

export default function ProfileScreen() {
  const { user, logout, refreshUser } = useAuth();
  const { t, language, setLang } = useLang();
  const router = useRouter();
  const [requests, setRequests] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        await refreshUser();
        const res = await api.get('/requests/my');
        setRequests(res.requests || []);
      } catch {} finally { setLoading(false); }
    })();
  }, []);

  const handleLogout = () => {
    Alert.alert('Logout', 'Are you sure?', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Logout', style: 'destructive', onPress: () => { logout(); router.replace('/login'); } },
    ]);
  };

  const MenuItem = ({ icon, label, value, onPress, testID }: any) => (
    <TouchableOpacity testID={testID} style={styles.menuItem} onPress={onPress}>
      <View style={styles.menuLeft}>
        <Ionicons name={icon} size={20} color={Colors.gold} />
        <Text style={styles.menuLabel}>{label}</Text>
      </View>
      {value ? <Text style={styles.menuValue}>{value}</Text> : <Ionicons name="chevron-forward" size={18} color={Colors.textMuted} />}
    </TouchableOpacity>
  );

  if (loading) return <View style={styles.loader}><ActivityIndicator size="large" color={Colors.gold} /></View>;

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <ScrollView showsVerticalScrollIndicator={false}>
        <View style={styles.header}>
          <Text style={styles.headerTitle}>Profile</Text>
        </View>

        {/* Profile Card */}
        <View style={styles.profileCard}>
          <View style={styles.avatar}>
            <Text style={styles.avatarText}>{(user?.name || user?.phone || '?')[0].toUpperCase()}</Text>
          </View>
          <View style={styles.profileInfo}>
            <Text style={styles.profileName}>{user?.name || 'Jeweller'}</Text>
            <Text style={styles.profilePhone}>+91 {user?.phone}</Text>
            <View style={styles.profileBadges}>
              <View style={styles.typeBadge}><Text style={styles.typeBadgeText}>{user?.customer_type?.toUpperCase()}</Text></View>
              {user?.customer_code && <Text style={styles.codeText}>Code: {user.customer_code}</Text>}
            </View>
          </View>
        </View>

        {/* Wallet Summary */}
        <TouchableOpacity testID="wallet-summary" style={styles.walletCard} onPress={() => router.push('/rewards')}>
          <View style={styles.walletLeft}>
            <Ionicons name="wallet" size={24} color={Colors.gold} />
            <View>
              <Text style={styles.walletLabel}>Reward Points</Text>
              <Text style={styles.walletValue}>{user?.reward_points || 0} pts</Text>
            </View>
          </View>
          <View style={styles.walletRight}>
            <Text style={styles.walletInr}>≈ ₹{user?.reward_points || 0}</Text>
            <Ionicons name="chevron-forward" size={18} color={Colors.gold} />
          </View>
        </TouchableOpacity>

        {/* Menu Items */}
        <View style={styles.menuSection}>
          <Text style={styles.menuSectionTitle}>ACCOUNT</Text>
          <MenuItem testID="my-orders-btn" icon="receipt" label="My Requests" value={`${requests.length}`} onPress={() => router.push('/my-requests')} />
          <MenuItem testID="wishlist-btn" icon="heart" label="Wishlist" onPress={() => router.push('/wishlist')} />
          <MenuItem testID="rewards-btn" icon="gift" label="Rewards History" onPress={() => router.push('/rewards')} />
        </View>

        <View style={styles.menuSection}>
          <Text style={styles.menuSectionTitle}>{t('settings')}</Text>
          <View style={styles.langRow}>
            <Text style={styles.menuLabel}>{t('language')}</Text>
            <View style={styles.langOptions}>
              {LANGUAGE_OPTIONS.map(lo => (
                <TouchableOpacity key={lo.key} testID={`lang-${lo.key}`} style={[styles.langBtn, language === lo.key && styles.langBtnActive]} onPress={() => setLang(lo.key)}>
                  <Text style={[styles.langBtnText, language === lo.key && styles.langBtnTextActive]}>{lo.native}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>
        </View>

        <View style={styles.menuSection}>
          <Text style={styles.menuSectionTitle}>{t('tools')}</Text>
          <MenuItem testID="calc-menu-btn" icon="calculator" label="Silver Calculator" onPress={() => router.push('/(tabs)/calculator')} />
          <MenuItem testID="ai-menu-btn" icon="sparkles" label="AI Assistant" onPress={() => router.push('/ai-assistant')} />
          <MenuItem testID="knowledge-menu-btn" icon="book" label="Silver Knowledge" onPress={() => router.push('/knowledge')} />
        </View>

        <View style={styles.menuSection}>
          <Text style={styles.menuSectionTitle}>CONTACT</Text>
          <MenuItem testID="call-menu-btn" icon="call" label="Request Call" onPress={() => router.push('/request-call')} />
          <MenuItem testID="video-menu-btn" icon="videocam" label="Request Video Call" onPress={() => router.push({ pathname: '/request-call', params: { type: 'video_call' } })} />
        </View>

        {(user?.role === 'admin' || user?.role === 'executive') && (
          <View style={styles.menuSection}>
            <Text style={styles.menuSectionTitle}>{user.role === 'admin' ? t('admin') : 'EXECUTIVE'}</Text>
            {user.role === 'admin' && <MenuItem testID="admin-menu-btn" icon="settings" label={t('admin_dashboard')} onPress={() => router.push('/admin')} />}
            <MenuItem testID="exec-menu-btn" icon="headset" label={t('executive_panel')} onPress={() => router.push('/executive')} />
          </View>
        )}

        <TouchableOpacity testID="logout-btn" style={styles.logoutBtn} onPress={handleLogout}>
          <Ionicons name="log-out-outline" size={20} color={Colors.error} />
          <Text style={styles.logoutText}>Logout</Text>
        </TouchableOpacity>

        {/* Recent Requests */}
        {requests.length > 0 && (
          <View style={styles.recentSection}>
            <Text style={styles.menuSectionTitle}>RECENT REQUESTS</Text>
            {requests.slice(0, 5).map(r => (
              <View key={r.id} style={styles.requestItem}>
                <View style={styles.requestLeft}>
                  <Ionicons name={r.request_type === 'video_call' ? 'videocam' : r.request_type === 'call' ? 'call' : 'chatbox'} size={16} color={Colors.gold} />
                  <View>
                    <Text style={styles.requestType}>{r.request_type?.replace(/_/g, ' ')}</Text>
                    <Text style={styles.requestDate}>{new Date(r.created_at).toLocaleDateString()}</Text>
                  </View>
                </View>
                <View style={[styles.statusBadge, { backgroundColor: r.status === 'pending' ? Colors.warning + '20' : r.status === 'resolved' ? Colors.success + '20' : Colors.info + '20' }]}>
                  <Text style={[styles.statusText, { color: r.status === 'pending' ? Colors.warning : r.status === 'resolved' ? Colors.success : Colors.info }]}>{r.status}</Text>
                </View>
              </View>
            ))}
          </View>
        )}

        <View style={{ height: 40 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  loader: { flex: 1, backgroundColor: Colors.background, justifyContent: 'center', alignItems: 'center' },
  header: { paddingHorizontal: Spacing.lg, paddingTop: Spacing.md, paddingBottom: Spacing.sm },
  headerTitle: { fontSize: FontSize.xl, fontWeight: '700', color: Colors.text },
  profileCard: { flexDirection: 'row', alignItems: 'center', marginHorizontal: Spacing.lg, padding: Spacing.lg, backgroundColor: Colors.card, borderRadius: 16, borderWidth: 1, borderColor: Colors.borderGold, gap: 16 },
  avatar: { width: 56, height: 56, borderRadius: 28, backgroundColor: Colors.gold + '20', alignItems: 'center', justifyContent: 'center' },
  avatarText: { fontSize: FontSize.xl, fontWeight: '700', color: Colors.gold },
  profileInfo: { flex: 1 },
  profileName: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.text },
  profilePhone: { fontSize: FontSize.sm, color: Colors.textSecondary, marginTop: 2 },
  profileBadges: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 6 },
  typeBadge: { backgroundColor: Colors.gold + '20', paddingHorizontal: 8, paddingVertical: 2, borderRadius: 4 },
  typeBadgeText: { fontSize: 9, fontWeight: '700', color: Colors.gold, letterSpacing: 1 },
  codeText: { fontSize: FontSize.xs, color: Colors.textMuted },
  walletCard: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginHorizontal: Spacing.lg, marginTop: Spacing.md, padding: Spacing.lg, backgroundColor: Colors.card, borderRadius: 16, borderWidth: 1, borderColor: Colors.borderGold },
  walletLeft: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  walletLabel: { fontSize: FontSize.xs, color: Colors.textSecondary },
  walletValue: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.gold },
  walletRight: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  walletInr: { fontSize: FontSize.md, color: Colors.textSecondary },
  menuSection: { marginTop: Spacing.lg, paddingHorizontal: Spacing.lg },
  menuSectionTitle: { fontSize: FontSize.xs, color: Colors.textMuted, letterSpacing: 2, fontWeight: '700', marginBottom: Spacing.sm },
  menuItem: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: Colors.border },
  menuLeft: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  menuLabel: { fontSize: FontSize.md, color: Colors.text },
  menuValue: { fontSize: FontSize.sm, color: Colors.textSecondary },
  logoutBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, marginHorizontal: Spacing.lg, marginTop: Spacing.xl, paddingVertical: 14, borderRadius: 12, borderWidth: 1, borderColor: Colors.error + '40' },
  logoutText: { fontSize: FontSize.md, color: Colors.error, fontWeight: '600' },
  langRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 12 },
  langOptions: { flexDirection: 'row', gap: 6 },
  langBtn: { paddingHorizontal: 14, paddingVertical: 6, borderRadius: 8, backgroundColor: Colors.surface, borderWidth: 1, borderColor: Colors.border },
  langBtnActive: { backgroundColor: Colors.gold + '20', borderColor: Colors.gold },
  langBtnText: { fontSize: FontSize.sm, color: Colors.textMuted },
  langBtnTextActive: { color: Colors.gold, fontWeight: '600' },
  recentSection: { marginTop: Spacing.xl, paddingHorizontal: Spacing.lg },
  requestItem: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: Colors.border },
  requestLeft: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  requestType: { fontSize: FontSize.sm, color: Colors.text, fontWeight: '500', textTransform: 'capitalize' },
  requestDate: { fontSize: FontSize.xs, color: Colors.textMuted },
  statusBadge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6 },
  statusText: { fontSize: FontSize.xs, fontWeight: '600', textTransform: 'uppercase' },
});
