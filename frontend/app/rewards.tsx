import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../src/theme';
import { api } from '../src/api';
import { useAuth } from '../src/context/AuthContext';

export default function RewardsScreen() {
  const router = useRouter();
  const { user, refreshUser } = useAuth();
  const [wallet, setWallet] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const w = await api.get('/rewards/wallet');
        setWallet(w);
        await refreshUser();
      } catch {} finally { setLoading(false); }
    })();
  }, []);

  if (loading) return <View style={styles.loader}><ActivityIndicator size="large" color={Colors.gold} /></View>;

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <ScrollView showsVerticalScrollIndicator={false}>
        <View style={styles.header}>
          <TouchableOpacity testID="back-btn" onPress={() => router.back()} style={styles.backBtn}>
            <Ionicons name="arrow-back" size={24} color={Colors.text} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>My Rewards</Text>
          <View style={{ width: 44 }} />
        </View>

        {/* Wallet Card */}
        <View style={styles.walletCard}>
          <Ionicons name="wallet" size={40} color={Colors.gold} />
          <Text style={styles.walletPoints}>{wallet?.current_points || 0}</Text>
          <Text style={styles.walletLabel}>Reward Points</Text>
          <Text style={styles.walletValue}>≈ ₹{wallet?.current_points || 0}</Text>
          <View style={styles.walletStats}>
            <View style={styles.walletStat}>
              <Text style={styles.statValue}>{wallet?.total_earned || 0}</Text>
              <Text style={styles.statLabel}>Earned</Text>
            </View>
            <View style={styles.walletDivider} />
            <View style={styles.walletStat}>
              <Text style={styles.statValue}>{wallet?.total_redeemed || 0}</Text>
              <Text style={styles.statLabel}>Redeemed</Text>
            </View>
          </View>
        </View>

        {/* How to Earn */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>HOW TO EARN</Text>
          <View style={styles.earnCard}>
            <View style={styles.earnItem}>
              <View style={[styles.earnIcon, { backgroundColor: Colors.success + '15' }]}>
                <Ionicons name="download" size={18} color={Colors.success} />
              </View>
              <View style={styles.earnInfo}>
                <Text style={styles.earnLabel}>App Install & Verify</Text>
                <Text style={styles.earnPoints}>+100 pts</Text>
              </View>
            </View>
            <View style={styles.earnItem}>
              <View style={[styles.earnIcon, { backgroundColor: Colors.gold + '15' }]}>
                <Ionicons name="cart" size={18} color={Colors.gold} />
              </View>
              <View style={styles.earnInfo}>
                <Text style={styles.earnLabel}>Every ₹1000 Purchase</Text>
                <Text style={styles.earnPoints}>+10 pts</Text>
              </View>
            </View>
            <View style={styles.earnItem}>
              <View style={[styles.earnIcon, { backgroundColor: Colors.info + '15' }]}>
                <Ionicons name="videocam" size={18} color={Colors.info} />
              </View>
              <View style={styles.earnInfo}>
                <Text style={styles.earnLabel}>First Video Selection</Text>
                <Text style={styles.earnPoints}>+25 pts</Text>
              </View>
            </View>
          </View>
        </View>

        {/* Recent Transactions */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>RECENT ACTIVITY</Text>
          {wallet?.recent_transactions?.length > 0 ? (
            wallet.recent_transactions.map((t: any) => (
              <View key={t.id} style={styles.txnItem}>
                <View style={styles.txnLeft}>
                  <Ionicons name={t.type === 'credit' ? 'add-circle' : 'remove-circle'} size={20} color={t.type === 'credit' ? Colors.success : Colors.error} />
                  <View>
                    <Text style={styles.txnReason}>{t.reason}</Text>
                    <Text style={styles.txnDate}>{new Date(t.created_at).toLocaleDateString()}</Text>
                  </View>
                </View>
                <Text style={[styles.txnPoints, { color: t.type === 'credit' ? Colors.success : Colors.error }]}>
                  {t.type === 'credit' ? '+' : '-'}{t.points} pts
                </Text>
              </View>
            ))
          ) : (
            <Text style={styles.emptyText}>No transactions yet</Text>
          )}
        </View>

        <View style={{ height: 40 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  loader: { flex: 1, backgroundColor: Colors.background, justifyContent: 'center', alignItems: 'center' },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: Spacing.lg, paddingVertical: Spacing.md },
  backBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: Colors.surface, alignItems: 'center', justifyContent: 'center' },
  headerTitle: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.text },
  walletCard: { marginHorizontal: Spacing.lg, backgroundColor: Colors.card, borderRadius: 20, padding: Spacing.xl, alignItems: 'center', borderWidth: 1, borderColor: Colors.borderGold },
  walletPoints: { fontSize: 48, fontWeight: '700', color: Colors.gold, marginTop: Spacing.md },
  walletLabel: { fontSize: FontSize.sm, color: Colors.textSecondary, marginTop: 4 },
  walletValue: { fontSize: FontSize.lg, color: Colors.text, fontWeight: '600', marginTop: 4 },
  walletStats: { flexDirection: 'row', marginTop: Spacing.lg, gap: 32 },
  walletStat: { alignItems: 'center' },
  walletDivider: { width: 1, height: 32, backgroundColor: Colors.border },
  statValue: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.text },
  statLabel: { fontSize: FontSize.xs, color: Colors.textMuted, marginTop: 2 },
  section: { paddingHorizontal: Spacing.lg, marginTop: Spacing.xl },
  sectionTitle: { fontSize: FontSize.xs, color: Colors.textSecondary, letterSpacing: 2, fontWeight: '700', marginBottom: Spacing.md },
  earnCard: { backgroundColor: Colors.card, borderRadius: 16, padding: Spacing.md, gap: 4 },
  earnItem: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 10 },
  earnIcon: { width: 36, height: 36, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  earnInfo: { flex: 1, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  earnLabel: { fontSize: FontSize.sm, color: Colors.text },
  earnPoints: { fontSize: FontSize.sm, color: Colors.gold, fontWeight: '700' },
  txnItem: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: Colors.border },
  txnLeft: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  txnReason: { fontSize: FontSize.sm, color: Colors.text },
  txnDate: { fontSize: FontSize.xs, color: Colors.textMuted },
  txnPoints: { fontSize: FontSize.md, fontWeight: '700' },
  emptyText: { fontSize: FontSize.sm, color: Colors.textMuted, textAlign: 'center', paddingVertical: 24 },
});
