import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, TextInput, ActivityIndicator, Alert, FlatList } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../src/theme';
import { api } from '../src/api';

type Tab = 'dashboard' | 'products' | 'rates' | 'requests' | 'customers' | 'rewards';

export default function AdminScreen() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<Tab>('dashboard');
  const [dashData, setDashData] = useState<any>(null);
  const [products, setProducts] = useState<any[]>([]);
  const [requests, setRequests] = useState<any[]>([]);
  const [customers, setCustomers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  // Rate form
  const [silverRate, setSilverRate] = useState('');
  const [goldRate, setGoldRate] = useState('');
  const [silverMov, setSilverMov] = useState('stable');
  const [goldMov, setGoldMov] = useState('stable');
  const [marketSummary, setMarketSummary] = useState('');

  // Product form
  const [showAddProduct, setShowAddProduct] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [newMetal, setNewMetal] = useState('silver');
  const [newCategory, setNewCategory] = useState('');
  const [newWeight, setNewWeight] = useState('');
  const [newImageUrl, setNewImageUrl] = useState('');

  const loadTab = async (tab: Tab) => {
    setLoading(true);
    try {
      switch (tab) {
        case 'dashboard': setDashData(await api.get('/analytics/dashboard')); break;
        case 'products': { const r = await api.get('/products?limit=50'); setProducts(r.products || []); break; }
        case 'requests': { const r = await api.get('/requests'); setRequests(r.requests || []); break; }
        case 'customers': { const r = await api.get('/customers?limit=50'); setCustomers(r.customers || []); break; }
        case 'rates': {
          const r = await api.get('/rates/latest');
          if (r.silver_rate) { setSilverRate(String(r.silver_rate)); setGoldRate(String(r.gold_rate)); }
          break;
        }
      }
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  };

  useEffect(() => { loadTab(activeTab); }, [activeTab]);

  const updateRates = async () => {
    if (!silverRate || !goldRate) { Alert.alert('Error', 'Enter both rates'); return; }
    try {
      await api.post('/rates', { silver_rate: parseFloat(silverRate), gold_rate: parseFloat(goldRate), silver_movement: silverMov, gold_movement: goldMov, market_summary: marketSummary });
      Alert.alert('Success', 'Rates updated!');
    } catch (e: any) { Alert.alert('Error', e.message); }
  };

  const addProduct = async () => {
    if (!newTitle) { Alert.alert('Error', 'Enter product title'); return; }
    try {
      await api.post('/products', {
        title: newTitle, description: newDesc, metal_type: newMetal, category: newCategory,
        approx_weight: newWeight, images: newImageUrl ? [newImageUrl] : [],
      });
      Alert.alert('Success', 'Product added!');
      setShowAddProduct(false);
      setNewTitle(''); setNewDesc(''); setNewCategory(''); setNewWeight(''); setNewImageUrl('');
      loadTab('products');
    } catch (e: any) { Alert.alert('Error', e.message); }
  };

  const updateRequestStatus = async (id: string, status: string) => {
    try {
      await api.patch(`/requests/${id}`, { status, assigned_to: '', notes: '' });
      loadTab('requests');
    } catch (e: any) { Alert.alert('Error', e.message); }
  };

  const TABS: { key: Tab; label: string; icon: string }[] = [
    { key: 'dashboard', label: 'Dashboard', icon: 'stats-chart' },
    { key: 'products', label: 'Products', icon: 'grid' },
    { key: 'rates', label: 'Rates', icon: 'trending-up' },
    { key: 'requests', label: 'Requests', icon: 'call' },
    { key: 'customers', label: 'Customers', icon: 'people' },
  ];

  const StatCard = ({ label, value, icon, color }: any) => (
    <View style={styles.statCard}>
      <Ionicons name={icon} size={20} color={color || Colors.gold} />
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity testID="admin-back-btn" onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={24} color={Colors.text} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Admin Panel</Text>
        <View style={{ width: 44 }} />
      </View>

      {/* Tab Bar */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.tabBar}>
        {TABS.map(t => (
          <TouchableOpacity key={t.key} testID={`admin-tab-${t.key}`} style={[styles.tab, activeTab === t.key && styles.tabActive]} onPress={() => setActiveTab(t.key)}>
            <Ionicons name={t.icon as any} size={16} color={activeTab === t.key ? Colors.gold : Colors.textMuted} />
            <Text style={[styles.tabText, activeTab === t.key && styles.tabTextActive]}>{t.label}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      {loading ? <ActivityIndicator color={Colors.gold} style={{ marginTop: 40 }} /> : (
        <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.content}>
          {/* DASHBOARD */}
          {activeTab === 'dashboard' && dashData && (
            <>
              <View style={styles.statsGrid}>
                <StatCard label="Customers" value={dashData.total_users} icon="people" color={Colors.info} />
                <StatCard label="Products" value={dashData.total_products} icon="grid" color={Colors.success} />
                <StatCard label="Requests" value={dashData.total_requests} icon="call" color={Colors.warning} />
                <StatCard label="Pending" value={dashData.pending_requests} icon="time" color={Colors.error} />
              </View>
              <View style={styles.statCard}>
                <Text style={styles.statLabel}>Total Reward Points in System</Text>
                <Text style={[styles.statValue, { color: Colors.gold }]}>{dashData.total_reward_points} pts</Text>
              </View>
              <Text style={styles.sectionTitle}>RECENT REQUESTS</Text>
              {dashData.recent_requests?.map((r: any) => (
                <View key={r.id} style={styles.listItem}>
                  <View>
                    <Text style={styles.listTitle}>{r.request_type?.replace(/_/g, ' ')} - {r.user_name || r.user_phone}</Text>
                    <Text style={styles.listMeta}>{r.category} • {new Date(r.created_at).toLocaleDateString()}</Text>
                  </View>
                  <View style={[styles.statusBadge, { backgroundColor: r.status === 'pending' ? Colors.warning + '20' : Colors.success + '20' }]}>
                    <Text style={[styles.statusText, { color: r.status === 'pending' ? Colors.warning : Colors.success }]}>{r.status}</Text>
                  </View>
                </View>
              ))}
            </>
          )}

          {/* PRODUCTS */}
          {activeTab === 'products' && (
            <>
              <TouchableOpacity testID="add-product-btn" style={styles.actionBtn} onPress={() => setShowAddProduct(!showAddProduct)}>
                <Ionicons name={showAddProduct ? 'close' : 'add'} size={18} color="#000" />
                <Text style={styles.actionBtnText}>{showAddProduct ? 'Cancel' : 'Add Product'}</Text>
              </TouchableOpacity>

              {showAddProduct && (
                <View style={styles.formCard}>
                  <TextInput testID="new-title" style={styles.formInput} placeholder="Product Title *" placeholderTextColor={Colors.textMuted} value={newTitle} onChangeText={setNewTitle} />
                  <TextInput style={styles.formInput} placeholder="Description" placeholderTextColor={Colors.textMuted} value={newDesc} onChangeText={setNewDesc} multiline />
                  <View style={styles.formRow}>
                    {['silver', 'gold', 'diamond'].map(m => (
                      <TouchableOpacity key={m} style={[styles.metalBtn, newMetal === m && styles.metalBtnActive]} onPress={() => setNewMetal(m)}>
                        <Text style={[styles.metalBtnText, newMetal === m && styles.metalBtnTextActive]}>{m}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                  <TextInput style={styles.formInput} placeholder="Category (e.g., payal, chain)" placeholderTextColor={Colors.textMuted} value={newCategory} onChangeText={setNewCategory} />
                  <TextInput style={styles.formInput} placeholder="Approx Weight" placeholderTextColor={Colors.textMuted} value={newWeight} onChangeText={setNewWeight} />
                  <TextInput style={styles.formInput} placeholder="Image URL" placeholderTextColor={Colors.textMuted} value={newImageUrl} onChangeText={setNewImageUrl} />
                  <TouchableOpacity testID="save-product-btn" style={styles.saveBtn} onPress={addProduct}>
                    <Text style={styles.saveBtnText}>SAVE PRODUCT</Text>
                  </TouchableOpacity>
                </View>
              )}

              <Text style={styles.sectionTitle}>ALL PRODUCTS ({products.length})</Text>
              {products.map(p => (
                <View key={p.id} style={styles.listItem}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.listTitle}>{p.title}</Text>
                    <Text style={styles.listMeta}>{p.metal_type} • {p.category} • {p.approx_weight}</Text>
                  </View>
                  <TouchableOpacity onPress={() => { Alert.alert('Delete', 'Delete this product?', [{ text: 'Cancel' }, { text: 'Delete', style: 'destructive', onPress: () => api.delete(`/products/${p.id}`).then(() => loadTab('products')) }]); }}>
                    <Ionicons name="trash-outline" size={18} color={Colors.error} />
                  </TouchableOpacity>
                </View>
              ))}
            </>
          )}

          {/* RATES */}
          {activeTab === 'rates' && (
            <View style={styles.formCard}>
              <Text style={styles.formTitle}>Update Daily Rates</Text>
              <Text style={styles.formLabel}>Silver Rate (₹/gram)</Text>
              <TextInput testID="admin-silver-rate" style={styles.formInput} value={silverRate} onChangeText={setSilverRate} keyboardType="decimal-pad" placeholder="e.g., 96.50" placeholderTextColor={Colors.textMuted} />
              <Text style={styles.formLabel}>Gold Rate (₹/gram)</Text>
              <TextInput testID="admin-gold-rate" style={styles.formInput} value={goldRate} onChangeText={setGoldRate} keyboardType="decimal-pad" placeholder="e.g., 7450" placeholderTextColor={Colors.textMuted} />
              <Text style={styles.formLabel}>Silver Movement</Text>
              <View style={styles.formRow}>
                {['up', 'down', 'stable'].map(m => (
                  <TouchableOpacity key={m} style={[styles.metalBtn, silverMov === m && styles.metalBtnActive]} onPress={() => setSilverMov(m)}>
                    <Text style={[styles.metalBtnText, silverMov === m && styles.metalBtnTextActive]}>{m}</Text>
                  </TouchableOpacity>
                ))}
              </View>
              <Text style={styles.formLabel}>Gold Movement</Text>
              <View style={styles.formRow}>
                {['up', 'down', 'stable'].map(m => (
                  <TouchableOpacity key={m} style={[styles.metalBtn, goldMov === m && styles.metalBtnActive]} onPress={() => setGoldMov(m)}>
                    <Text style={[styles.metalBtnText, goldMov === m && styles.metalBtnTextActive]}>{m}</Text>
                  </TouchableOpacity>
                ))}
              </View>
              <Text style={styles.formLabel}>Market Summary</Text>
              <TextInput style={styles.formInput} value={marketSummary} onChangeText={setMarketSummary} placeholder="e.g., Silver up 1.2% today" placeholderTextColor={Colors.textMuted} />
              <TouchableOpacity testID="update-rates-btn" style={styles.saveBtn} onPress={updateRates}>
                <Text style={styles.saveBtnText}>UPDATE RATES</Text>
              </TouchableOpacity>
            </View>
          )}

          {/* REQUESTS */}
          {activeTab === 'requests' && (
            <>
              <Text style={styles.sectionTitle}>ALL REQUESTS ({requests.length})</Text>
              {requests.map(r => (
                <View key={r.id} style={styles.requestCard}>
                  <View style={styles.requestHeader}>
                    <Text style={styles.listTitle}>{r.request_type?.replace(/_/g, ' ')}</Text>
                    <View style={[styles.statusBadge, { backgroundColor: r.status === 'pending' ? Colors.warning + '20' : r.status === 'done' ? Colors.success + '20' : Colors.info + '20' }]}>
                      <Text style={[styles.statusText, { color: r.status === 'pending' ? Colors.warning : r.status === 'done' ? Colors.success : Colors.info }]}>{r.status}</Text>
                    </View>
                  </View>
                  <Text style={styles.listMeta}>{r.user_name || r.user_phone} • {r.category} • {r.preferred_time}</Text>
                  {r.notes ? <Text style={styles.notesText}>Notes: {r.notes}</Text> : null}
                  {r.status === 'pending' && (
                    <View style={styles.requestActions}>
                      <TouchableOpacity style={[styles.miniBtn, { backgroundColor: Colors.success + '20' }]} onPress={() => updateRequestStatus(r.id, 'assigned')}>
                        <Text style={[styles.miniBtnText, { color: Colors.success }]}>Assign</Text>
                      </TouchableOpacity>
                      <TouchableOpacity style={[styles.miniBtn, { backgroundColor: Colors.gold + '20' }]} onPress={() => updateRequestStatus(r.id, 'done')}>
                        <Text style={[styles.miniBtnText, { color: Colors.gold }]}>Done</Text>
                      </TouchableOpacity>
                      <TouchableOpacity style={[styles.miniBtn, { backgroundColor: Colors.error + '20' }]} onPress={() => updateRequestStatus(r.id, 'no_response')}>
                        <Text style={[styles.miniBtnText, { color: Colors.error }]}>No Response</Text>
                      </TouchableOpacity>
                    </View>
                  )}
                </View>
              ))}
            </>
          )}

          {/* CUSTOMERS */}
          {activeTab === 'customers' && (
            <>
              <Text style={styles.sectionTitle}>ALL CUSTOMERS ({customers.length})</Text>
              {customers.map(c => (
                <View key={c.id} style={styles.listItem}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.listTitle}>{c.name || c.phone}</Text>
                    <Text style={styles.listMeta}>{c.customer_type} • {c.city || 'No city'} • {c.customer_code} • {c.reward_points} pts</Text>
                  </View>
                </View>
              ))}
            </>
          )}

          <View style={{ height: 40 }} />
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: Spacing.lg, paddingVertical: Spacing.md },
  backBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: Colors.surface, alignItems: 'center', justifyContent: 'center' },
  headerTitle: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.text },
  tabBar: { paddingHorizontal: Spacing.lg, gap: 6, paddingBottom: Spacing.md },
  tab: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 20, backgroundColor: Colors.surface },
  tabActive: { backgroundColor: Colors.gold + '20' },
  tabText: { fontSize: FontSize.sm, color: Colors.textMuted, fontWeight: '500' },
  tabTextActive: { color: Colors.gold, fontWeight: '600' },
  content: { paddingHorizontal: Spacing.lg },
  statsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: Spacing.md },
  statCard: { flex: 1, minWidth: '45%', backgroundColor: Colors.card, borderRadius: 14, padding: Spacing.md, alignItems: 'center', gap: 6, borderWidth: 1, borderColor: Colors.cardBorder },
  statValue: { fontSize: FontSize.xl, fontWeight: '700', color: Colors.text },
  statLabel: { fontSize: FontSize.xs, color: Colors.textMuted },
  sectionTitle: { fontSize: FontSize.xs, color: Colors.textSecondary, letterSpacing: 2, fontWeight: '700', marginTop: Spacing.lg, marginBottom: Spacing.md },
  listItem: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: Colors.border },
  listTitle: { fontSize: FontSize.md, color: Colors.text, fontWeight: '600', textTransform: 'capitalize' },
  listMeta: { fontSize: FontSize.xs, color: Colors.textMuted, marginTop: 2, textTransform: 'capitalize' },
  statusBadge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6 },
  statusText: { fontSize: FontSize.xs, fontWeight: '600', textTransform: 'uppercase' },
  actionBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, backgroundColor: Colors.gold, paddingVertical: 12, borderRadius: 10 },
  actionBtnText: { fontSize: FontSize.sm, fontWeight: '700', color: '#000' },
  formCard: { backgroundColor: Colors.card, borderRadius: 16, padding: Spacing.lg, marginTop: Spacing.md, borderWidth: 1, borderColor: Colors.cardBorder },
  formTitle: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.text, marginBottom: Spacing.md },
  formLabel: { fontSize: FontSize.xs, color: Colors.textSecondary, fontWeight: '600', letterSpacing: 1, marginBottom: 6, marginTop: Spacing.md },
  formInput: { backgroundColor: Colors.surface, borderRadius: 10, paddingHorizontal: Spacing.md, paddingVertical: 12, fontSize: FontSize.md, color: Colors.text, borderWidth: 1, borderColor: Colors.border, marginBottom: 4 },
  formRow: { flexDirection: 'row', gap: 8, marginBottom: Spacing.sm },
  metalBtn: { flex: 1, alignItems: 'center', paddingVertical: 10, borderRadius: 8, backgroundColor: Colors.surface, borderWidth: 1, borderColor: Colors.border },
  metalBtnActive: { backgroundColor: Colors.gold + '20', borderColor: Colors.gold },
  metalBtnText: { fontSize: FontSize.sm, color: Colors.textMuted, fontWeight: '500', textTransform: 'capitalize' },
  metalBtnTextActive: { color: Colors.gold },
  saveBtn: { backgroundColor: Colors.gold, paddingVertical: 14, borderRadius: 10, alignItems: 'center', marginTop: Spacing.md },
  saveBtnText: { fontSize: FontSize.sm, fontWeight: '700', color: '#000', letterSpacing: 2 },
  requestCard: { backgroundColor: Colors.card, borderRadius: 12, padding: Spacing.md, marginBottom: Spacing.sm, borderWidth: 1, borderColor: Colors.cardBorder },
  requestHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 },
  notesText: { fontSize: FontSize.sm, color: Colors.textSecondary, marginTop: 4, fontStyle: 'italic' },
  requestActions: { flexDirection: 'row', gap: 8, marginTop: Spacing.sm },
  miniBtn: { flex: 1, alignItems: 'center', paddingVertical: 8, borderRadius: 8 },
  miniBtnText: { fontSize: FontSize.xs, fontWeight: '600' },
});
