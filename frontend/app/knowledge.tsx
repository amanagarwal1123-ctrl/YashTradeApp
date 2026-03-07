import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../src/theme';
import { api } from '../src/api';

const CATEGORIES = [
  { key: '', label: 'All', icon: 'layers' },
  { key: 'silver_care', label: 'Silver Care', icon: 'shield-checkmark' },
  { key: 'benefits', label: 'Benefits', icon: 'heart' },
  { key: 'gifting', label: 'Gifting Ideas', icon: 'gift' },
];

export default function KnowledgeScreen() {
  const router = useRouter();
  const [articles, setArticles] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [category, setCategory] = useState('');
  const [expandedId, setExpandedId] = useState('');

  const fetchArticles = async (cat: string = '') => {
    setLoading(true);
    try {
      const params = cat ? `?category=${cat}` : '';
      const res = await api.get(`/knowledge${params}`);
      setArticles(res.articles || []);
    } catch {} finally { setLoading(false); }
  };

  useEffect(() => { fetchArticles(category); }, [category]);

  const iconForCategory = (cat: string) => {
    switch (cat) {
      case 'silver_care': return 'shield-checkmark';
      case 'benefits': return 'heart';
      case 'gifting': return 'gift';
      default: return 'book';
    }
  };

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <ScrollView showsVerticalScrollIndicator={false}>
        <View style={styles.header}>
          <TouchableOpacity testID="back-btn" onPress={() => router.back()} style={styles.backBtn}>
            <Ionicons name="arrow-back" size={24} color={Colors.text} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Silver Knowledge</Text>
          <View style={{ width: 44 }} />
        </View>

        <Text style={styles.subtitle}>Education content you can show your customers</Text>

        {/* Categories */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.catsRow}>
          {CATEGORIES.map(c => (
            <TouchableOpacity key={c.key} testID={`cat-${c.key || 'all'}`} style={[styles.catChip, category === c.key && styles.catChipActive]} onPress={() => setCategory(c.key)}>
              <Ionicons name={c.icon as any} size={14} color={category === c.key ? Colors.gold : Colors.textMuted} />
              <Text style={[styles.catText, category === c.key && styles.catTextActive]}>{c.label}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>

        {loading ? <ActivityIndicator color={Colors.gold} style={{ marginTop: 40 }} /> : (
          <View style={styles.articlesList}>
            {articles.map(a => (
              <TouchableOpacity key={a.id} testID={`article-${a.id}`} style={styles.articleCard} onPress={() => setExpandedId(expandedId === a.id ? '' : a.id)} activeOpacity={0.85}>
                <View style={styles.articleHeader}>
                  <View style={[styles.articleIcon, { backgroundColor: Colors.gold + '15' }]}>
                    <Ionicons name={iconForCategory(a.category)} size={18} color={Colors.gold} />
                  </View>
                  <View style={styles.articleTitleArea}>
                    <Text style={styles.articleTitle}>{a.title}</Text>
                    <Text style={styles.articleCategory}>{a.category?.replace(/_/g, ' ')}</Text>
                  </View>
                  <Ionicons name={expandedId === a.id ? 'chevron-up' : 'chevron-down'} size={18} color={Colors.textMuted} />
                </View>
                {expandedId === a.id && (
                  <View style={styles.articleContent}>
                    <Text style={styles.contentText}>{a.content}</Text>
                    {a.tags?.length > 0 && (
                      <View style={styles.tagsRow}>
                        {a.tags.map((t: string) => <View key={t} style={styles.tag}><Text style={styles.tagText}>#{t}</Text></View>)}
                      </View>
                    )}
                  </View>
                )}
              </TouchableOpacity>
            ))}
            {articles.length === 0 && <Text style={styles.emptyText}>No articles found</Text>}
          </View>
        )}

        <View style={{ height: 40 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: Spacing.lg, paddingVertical: Spacing.md },
  backBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: Colors.surface, alignItems: 'center', justifyContent: 'center' },
  headerTitle: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.text },
  subtitle: { fontSize: FontSize.sm, color: Colors.textSecondary, paddingHorizontal: Spacing.lg, marginBottom: Spacing.md },
  catsRow: { paddingHorizontal: Spacing.lg, gap: 10, marginBottom: Spacing.lg },
  catChip: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 16, paddingVertical: 10, borderRadius: 20, backgroundColor: Colors.surface, borderWidth: 1, borderColor: Colors.border },
  catChipActive: { backgroundColor: Colors.gold + '15', borderColor: Colors.gold },
  catText: { fontSize: FontSize.sm, color: Colors.textSecondary },
  catTextActive: { color: Colors.gold, fontWeight: '600' },
  articlesList: { paddingHorizontal: Spacing.lg },
  articleCard: { backgroundColor: Colors.card, borderRadius: 14, marginBottom: Spacing.md, overflow: 'hidden', borderWidth: 1, borderColor: Colors.cardBorder },
  articleHeader: { flexDirection: 'row', alignItems: 'center', padding: Spacing.md, gap: 12 },
  articleIcon: { width: 40, height: 40, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  articleTitleArea: { flex: 1 },
  articleTitle: { fontSize: FontSize.md, fontWeight: '600', color: Colors.text },
  articleCategory: { fontSize: FontSize.xs, color: Colors.textMuted, marginTop: 2, textTransform: 'capitalize' },
  articleContent: { padding: Spacing.md, paddingTop: 0, borderTopWidth: 1, borderTopColor: Colors.border },
  contentText: { fontSize: FontSize.md, color: Colors.textSecondary, lineHeight: 24, marginTop: Spacing.md },
  tagsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: Spacing.md },
  tag: { backgroundColor: Colors.surface, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12 },
  tagText: { fontSize: FontSize.xs, color: Colors.textMuted },
  emptyText: { fontSize: FontSize.md, color: Colors.textMuted, textAlign: 'center', marginTop: 40 },
});
