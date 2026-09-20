import React, { useState, useRef, useEffect } from 'react';
import { View, Text, StyleSheet, TextInput, TouchableOpacity, FlatList, ActivityIndicator, ScrollView } from 'react-native';
import { KeyboardAvoiding } from '../src/components/KeyboardScreen';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../src/theme';
import { api } from '../src/api';
import { showAlert } from '../src/utils/alert';
import { useLang } from '../src/context/LanguageContext';
import { useAuth } from '../src/context/AuthContext';
import AiConsentCard, { AiConsentInfo } from '../src/components/AiConsentCard';

interface Message { id: string; role: 'user' | 'assistant'; content: string; }

const QUICK_PROMPTS = [
  'How to pitch silver anklets?',
  'Why does silver turn black?',
  'Festive season stock suggestions',
  'Silver cleaning tips for customers',
  'WhatsApp message for new collection',
  'Best gifting items under ₹5000',
];

export default function AIAssistantScreen() {
  const router = useRouter();
  const { t, language } = useLang();
  const { user, loading: authLoading } = useAuth();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState('');
  const [consent, setConsent] = useState<AiConsentInfo | null>(null);
  const [consentBusy, setConsentBusy] = useState(false);
  const [consentError, setConsentError] = useState('');
  const flatListRef = useRef<FlatList>(null);

  const loadConsent = async () => {
    try { setConsent(await api.get('/ai/consent')); setConsentError(''); }
    catch (e: any) { setConsentError(e?.message || 'Could not load the AI data-sharing terms'); }
  };
  // Wait for the stored session to be restored before the first authenticated call (cold-start deep links).
  useEffect(() => {
    if (authLoading) return;
    if (!user) { router.replace('/login'); return; }
    loadConsent();
  }, [authLoading, user?.id]);

  const allowConsent = async () => {
    setConsentBusy(true);
    try { setConsent(await api.post('/ai/consent', { granted: true, source: 'assistant' })); }
    catch (e: any) { showAlert('Could not record consent', e?.message || 'Please try again.'); }
    finally { setConsentBusy(false); }
  };

  const sendMessage = async (text?: string) => {
    const msg = text || input.trim();
    if (!msg || loading) return;
    if (!consent?.granted) { loadConsent(); return; } // consent gate covers typed messages AND quick prompts
    setInput('');
    const userMsg: Message = { id: Date.now().toString(), role: 'user', content: msg };
    setMessages(prev => [...prev, userMsg]);

    setLoading(true);
    try {
      const res = await api.post('/ai/chat', { message: msg, session_id: sessionId, language });
      if (res.session_id) setSessionId(res.session_id);
      const aiMsg: Message = { id: res.message_id || (Date.now() + 1).toString(), role: 'assistant', content: res.response };
      setMessages(prev => [...prev, aiMsg]);
      if (res.stored === false && res.notice) showAlert('Not saved', res.notice);
    } catch (e: any) {
      if (e?.code === 'AI_CONSENT_REQUIRED') { setMessages(prev => prev.filter(m => m.id !== userMsg.id)); await loadConsent(); }
      else setMessages(prev => [...prev, { id: (Date.now() + 1).toString(), role: 'assistant', content: 'Sorry, I encountered an error. Please try again.' }]);
    } finally { setLoading(false); }
  };

  const renderMessage = ({ item }: { item: Message }) => (
    <View style={[styles.msgRow, item.role === 'user' && styles.msgRowUser]}>
      {item.role === 'assistant' && <View style={styles.aiAvatar}><Ionicons name="sparkles" size={14} color={Colors.gold} /></View>}
      <View style={[styles.msgBubble, item.role === 'user' ? styles.userBubble : styles.aiBubble]}>
        <Text style={[styles.msgText, item.role === 'user' && styles.userMsgText]}>{item.content}</Text>
        {item.role === 'assistant' && <TouchableOpacity testID={`report-ai-${item.id}`} style={styles.reportButton} onPress={async () => {
          try { await api.post('/ai/reports', { message_id: item.id, reason: 'Problematic generated content' }); showAlert('Reported', 'This message is hidden from future history and queued for moderation.'); }
          catch (e: any) { showAlert('Report not sent', e.message); }
        }}><Ionicons name="flag-outline" size={16} color={Colors.warning}/><Text style={styles.reportText}>Report content</Text></TouchableOpacity>}
      </View>
    </View>
  );

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity testID="back-btn" onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={24} color={Colors.text} />
        </TouchableOpacity>
        <View style={styles.headerCenter}>
          <Ionicons name="sparkles" size={20} color={Colors.gold} />
          <Text style={styles.headerTitle}>AI Assistant</Text>
        </View>
        <View style={{ width: 44 }} />
      </View>

      <KeyboardAvoiding style={{ flex: 1 }}>
        {consent && !consent.granted ? (
          <ScrollView contentContainerStyle={styles.consentWrap} keyboardShouldPersistTaps="handled">
            <AiConsentCard info={consent} busy={consentBusy} onAllow={allowConsent} onDecline={() => router.back()} declineLabel="Not now — back to the app" />
          </ScrollView>
        ) : !consent ? (
          <View style={styles.emptyState}>
            {consentError ? (
              <>
                <Text testID="ai-consent-error" style={styles.emptySubtitle}>{consentError}</Text>
                <TouchableOpacity testID="ai-consent-retry" style={styles.retryBtn} onPress={loadConsent}><Text style={styles.retryText}>TRY AGAIN</Text></TouchableOpacity>
              </>
            ) : <ActivityIndicator color={Colors.gold} />}
          </View>
        ) : messages.length === 0 ? (
          <View style={styles.emptyState}>
            <Ionicons name="sparkles" size={48} color={Colors.gold} />
            <Text style={styles.emptyTitle}>{t('ai_title')}</Text>
            <Text style={styles.emptySubtitle}>{t('ai_subtitle')}</Text>
            <View style={styles.promptsGrid}>
              {QUICK_PROMPTS.map(p => (
                <TouchableOpacity key={p} testID={`prompt-${p.slice(0, 10)}`} style={styles.promptCard} onPress={() => sendMessage(p)}>
                  <Text style={styles.promptText}>{p}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>
        ) : (
          <FlatList
            ref={flatListRef}
            data={messages}
            keyExtractor={item => item.id}
            renderItem={renderMessage}
            contentContainerStyle={styles.messagesList}
            onContentSizeChange={() => flatListRef.current?.scrollToEnd()}
            ListFooterComponent={loading ? <View style={styles.loadingRow}><ActivityIndicator color={Colors.gold} /><Text style={styles.loadingText}>Thinking...</Text></View> : null}
          />
        )}

        {consent?.granted ? <View style={styles.inputRow}>
          <TextInput testID="ai-input" style={styles.input} placeholder="Ask anything about jewellery business..." placeholderTextColor={Colors.textMuted} value={input} onChangeText={setInput} multiline onSubmitEditing={() => sendMessage()} />
          <TouchableOpacity testID="send-btn" style={[styles.sendBtn, (!input.trim() || loading) && { opacity: 0.4 }]} onPress={() => sendMessage()} disabled={!input.trim() || loading}>
            <Ionicons name="send" size={18} color="#000" />
          </TouchableOpacity>
        </View> : null}
      </KeyboardAvoiding>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  consentWrap: { padding: Spacing.lg, paddingBottom: 40 },
  retryBtn: { marginTop: Spacing.md, borderWidth: 1, borderColor: Colors.gold, borderRadius: 10, paddingHorizontal: 20, minHeight: 44, justifyContent: 'center' },
  retryText: { color: Colors.gold, fontWeight: '700', fontSize: FontSize.sm, letterSpacing: 1 },
  reportButton: { minHeight: 44, flexDirection: 'row', gap: 8, alignItems: 'center' },
  reportText: { color: Colors.warning, fontSize: 12 },
  container: { flex: 1, backgroundColor: Colors.background },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: Spacing.lg, paddingVertical: Spacing.md, borderBottomWidth: 1, borderBottomColor: Colors.border },
  backBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: Colors.surface, alignItems: 'center', justifyContent: 'center' },
  headerCenter: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  headerTitle: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.text },
  emptyState: { flex: 1, alignItems: 'center', paddingTop: 60, paddingHorizontal: Spacing.lg },
  emptyTitle: { fontSize: FontSize.xl, fontWeight: '700', color: Colors.text, marginTop: Spacing.md },
  emptySubtitle: { fontSize: FontSize.md, color: Colors.textSecondary, textAlign: 'center', marginTop: Spacing.sm, lineHeight: 22 },
  promptsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: Spacing.xl, justifyContent: 'center' },
  promptCard: { backgroundColor: Colors.card, borderRadius: 12, paddingVertical: 12, paddingHorizontal: 16, borderWidth: 1, borderColor: Colors.border, maxWidth: '47%' },
  promptText: { fontSize: FontSize.sm, color: Colors.textSecondary },
  messagesList: { paddingHorizontal: Spacing.lg, paddingVertical: Spacing.md },
  msgRow: { flexDirection: 'row', marginBottom: Spacing.md, alignItems: 'flex-start', gap: 8 },
  msgRowUser: { justifyContent: 'flex-end' },
  aiAvatar: { width: 28, height: 28, borderRadius: 14, backgroundColor: Colors.gold + '20', alignItems: 'center', justifyContent: 'center', marginTop: 4 },
  msgBubble: { maxWidth: '80%', borderRadius: 16, padding: 14 },
  userBubble: { backgroundColor: Colors.gold, borderBottomRightRadius: 4 },
  aiBubble: { backgroundColor: Colors.card, borderBottomLeftRadius: 4, borderWidth: 1, borderColor: Colors.cardBorder },
  msgText: { fontSize: FontSize.md, color: Colors.text, lineHeight: 22 },
  userMsgText: { color: '#000' },
  loadingRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 8 },
  loadingText: { fontSize: FontSize.sm, color: Colors.textMuted },
  inputRow: { flexDirection: 'row', alignItems: 'flex-end', paddingHorizontal: Spacing.lg, paddingVertical: Spacing.sm, gap: 8, borderTopWidth: 1, borderTopColor: Colors.border },
  input: { flex: 1, backgroundColor: Colors.surface, borderRadius: 20, paddingHorizontal: Spacing.md, paddingVertical: 12, fontSize: FontSize.md, color: Colors.text, maxHeight: 100, borderWidth: 1, borderColor: Colors.border },
  sendBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: Colors.gold, alignItems: 'center', justifyContent: 'center' },
});
