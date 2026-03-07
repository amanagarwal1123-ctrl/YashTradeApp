import React, { useState, useRef, useEffect } from 'react';
import { View, Text, StyleSheet, TextInput, TouchableOpacity, FlatList, KeyboardAvoidingView, Platform, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../src/theme';
import { api } from '../src/api';

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
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState('');
  const flatListRef = useRef<FlatList>(null);

  const sendMessage = async (text?: string) => {
    const msg = text || input.trim();
    if (!msg || loading) return;
    setInput('');
    const userMsg: Message = { id: Date.now().toString(), role: 'user', content: msg };
    setMessages(prev => [...prev, userMsg]);

    setLoading(true);
    try {
      const res = await api.post('/ai/chat', { message: msg, session_id: sessionId });
      if (res.session_id) setSessionId(res.session_id);
      const aiMsg: Message = { id: (Date.now() + 1).toString(), role: 'assistant', content: res.response };
      setMessages(prev => [...prev, aiMsg]);
    } catch (e) {
      setMessages(prev => [...prev, { id: (Date.now() + 1).toString(), role: 'assistant', content: 'Sorry, I encountered an error. Please try again.' }]);
    } finally { setLoading(false); }
  };

  const renderMessage = ({ item }: { item: Message }) => (
    <View style={[styles.msgRow, item.role === 'user' && styles.msgRowUser]}>
      {item.role === 'assistant' && <View style={styles.aiAvatar}><Ionicons name="sparkles" size={14} color={Colors.gold} /></View>}
      <View style={[styles.msgBubble, item.role === 'user' ? styles.userBubble : styles.aiBubble]}>
        <Text style={[styles.msgText, item.role === 'user' && styles.userMsgText]}>{item.content}</Text>
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

      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={{ flex: 1 }} keyboardVerticalOffset={0}>
        {messages.length === 0 ? (
          <View style={styles.emptyState}>
            <Ionicons name="sparkles" size={48} color={Colors.gold} />
            <Text style={styles.emptyTitle}>Yash Trade AI</Text>
            <Text style={styles.emptySubtitle}>Ask me about selling tips, silver knowledge, trends, and customer education content.</Text>
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

        <View style={styles.inputRow}>
          <TextInput testID="ai-input" style={styles.input} placeholder="Ask anything about jewellery business..." placeholderTextColor={Colors.textMuted} value={input} onChangeText={setInput} multiline onSubmitEditing={() => sendMessage()} />
          <TouchableOpacity testID="send-btn" style={[styles.sendBtn, (!input.trim() || loading) && { opacity: 0.4 }]} onPress={() => sendMessage()} disabled={!input.trim() || loading}>
            <Ionicons name="send" size={18} color="#000" />
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
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
