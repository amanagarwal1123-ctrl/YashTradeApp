import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../src/theme';
import { api } from '../src/api';
import { showAlert, confirmAlert } from '../src/utils/alert';
import { useAuth } from '../src/context/AuthContext';
import AiConsentCard, { AiConsentInfo } from '../src/components/AiConsentCard';

/** Profile → AI data sharing: view the recorded consent, grant it, or withdraw it (which deletes stored AI chat history). */
export default function AiConsentScreen() {
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();
  const [info, setInfo] = useState<AiConsentInfo | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = async () => {
    try { setInfo(await api.get('/ai/consent')); setError(''); }
    catch (e: any) { setError(e?.message || 'Could not load your AI data-sharing settings'); }
  };
  useEffect(() => {
    if (authLoading) return;
    if (!user) { router.replace('/login'); return; }
    load();
  }, [authLoading, user?.id]);

  const allow = async () => {
    setBusy(true);
    try { setInfo(await api.post('/ai/consent', { granted: true, source: 'profile' })); }
    catch (e: any) { showAlert('Could not record consent', e?.message); }
    finally { setBusy(false); }
  };

  const withdraw = () => {
    confirmAlert('Withdraw AI data sharing?', 'No more text will be sent to the AI provider and your stored AI chat history in the app will be deleted now. The provider\'s own copy is not erased by this. You can allow again later.', async () => {
      setBusy(true);
      try {
        const res = await api.post('/ai/consent', { granted: false, source: 'profile' });
        setInfo(res);
        showAlert('AI data sharing withdrawn', `${res.history_deleted} stored chat message(s) deleted from the app. ${res.provider_copy || ''}`);
      } catch (e: any) { showAlert('Could not withdraw', e?.message); }
      finally { setBusy(false); }
    }, 'Withdraw');
  };

  return (
    <SafeAreaView style={st.container} edges={['top']}>
      <View style={st.header}>
        <TouchableOpacity testID="ai-consent-back" onPress={() => router.back()} style={st.backBtn}>
          <Ionicons name="arrow-back" size={24} color={Colors.text} />
        </TouchableOpacity>
        <Text style={st.headerTitle}>AI Data Sharing</Text>
        <View style={{ width: 44 }} />
      </View>
      <ScrollView contentContainerStyle={st.content}>
        {!info ? (
          error ? (
            <View style={st.center}>
              <Text testID="ai-consent-screen-error" style={st.muted}>{error}</Text>
              <TouchableOpacity testID="ai-consent-screen-retry" style={st.retryBtn} onPress={load}><Text style={st.retryText}>TRY AGAIN</Text></TouchableOpacity>
            </View>
          ) : <ActivityIndicator color={Colors.gold} style={{ marginTop: 40 }} />
        ) : info.granted ? (
          <View style={st.card} testID="ai-consent-granted">
            <View style={st.statusRow}>
              <Ionicons name="checkmark-circle" size={22} color={Colors.success} />
              <Text style={st.statusText}>AI data sharing is ON</Text>
            </View>
            <Text style={st.muted}>Allowed on {info.granted_at ? new Date(info.granted_at).toLocaleString() : '—'} · version {info.version}</Text>
            {info.recipients.map(r => (
              <View key={r.name} style={st.recipient}>
                <Text style={st.recipientName}>{r.name} · {r.service}</Text>
                <Text style={st.muted}>{r.role}. Sent via {r.via}. Location: {r.location}.</Text>
                <Text style={st.sub}>SENT</Text>
                {r.data_sent.map(d => <Text key={d} style={st.item}>• {d}</Text>)}
                <Text style={st.sub}>NEVER SENT</Text>
                {r.data_not_sent.map(d => <Text key={d} style={st.item}>• {d}</Text>)}
                <Text style={st.sub}>RETENTION</Text>
                <Text style={st.item}>{r.retention}</Text>
              </View>
            ))}
            <Text style={st.sub}>WITHDRAWING WILL</Text>
            {info.withdrawal_effects.map(e => <Text key={e} style={st.item}>• {e}</Text>)}
            <TouchableOpacity testID="ai-consent-withdraw" style={[st.dangerBtn, busy && { opacity: 0.5 }]} onPress={withdraw} disabled={busy}>
              {busy ? <ActivityIndicator color="#fff" /> : <Text style={st.dangerText}>WITHDRAW AND DELETE AI CHAT HISTORY</Text>}
            </TouchableOpacity>
          </View>
        ) : (
          <>
            {info.withdrawn_at ? <Text testID="ai-consent-off" style={st.offNote}>AI data sharing is OFF (withdrawn {new Date(info.withdrawn_at).toLocaleString()}). Your stored AI chat history was deleted.</Text> : null}
            <AiConsentCard info={info} busy={busy} onAllow={allow} onDecline={() => router.back()} declineLabel="Keep it off" />
          </>
        )}
        <View style={{ height: 40 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const st = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: Spacing.lg, paddingVertical: Spacing.md },
  backBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: Colors.surface, alignItems: 'center', justifyContent: 'center' },
  headerTitle: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.text },
  content: { paddingHorizontal: Spacing.lg },
  center: { alignItems: 'center', paddingTop: 40 },
  card: { backgroundColor: Colors.card, borderRadius: 16, borderWidth: 1, borderColor: Colors.cardBorder, padding: Spacing.md, gap: 6 },
  statusRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  statusText: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.text },
  muted: { fontSize: FontSize.xs, color: Colors.textMuted, lineHeight: 17 },
  recipient: { backgroundColor: Colors.surface, borderRadius: 12, padding: Spacing.sm, marginTop: 6, gap: 3 },
  recipientName: { fontSize: FontSize.md, fontWeight: '700', color: Colors.text },
  sub: { fontSize: FontSize.xs, color: Colors.textSecondary, letterSpacing: 1.2, fontWeight: '600', marginTop: 6 },
  item: { fontSize: FontSize.xs, color: Colors.textSecondary, lineHeight: 17 },
  dangerBtn: { backgroundColor: Colors.error, borderRadius: 10, paddingVertical: 14, alignItems: 'center', marginTop: Spacing.md, minHeight: 48 },
  dangerText: { fontSize: FontSize.xs, fontWeight: '700', color: '#fff', letterSpacing: 1 },
  offNote: { fontSize: FontSize.sm, color: Colors.textSecondary, marginBottom: Spacing.md, lineHeight: 20 },
  retryBtn: { marginTop: Spacing.md, borderWidth: 1, borderColor: Colors.gold, borderRadius: 10, paddingHorizontal: 20, minHeight: 44, justifyContent: 'center' },
  retryText: { color: Colors.gold, fontWeight: '700', fontSize: FontSize.sm, letterSpacing: 1 },
});
