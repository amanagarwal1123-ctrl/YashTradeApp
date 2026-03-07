import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, TextInput, ActivityIndicator, Alert, FlatList } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../src/theme';
import { api } from '../src/api';

type Tab = 'dashboard' | 'products' | 'rates' | 'requests' | 'customers' | 'batches';

export default function AdminScreen() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<Tab>('dashboard');
  const [dashData, setDashData] = useState<any>(null);
  const [products, setProducts] = useState<any[]>([]);
  const [requests, setRequests] = useState<any[]>([]);
  const [customers, setCustomers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  // Rate form - 6 rates + premium
  const [silverDollar, setSilverDollar] = useState('');
  const [silverMcx, setSilverMcx] = useState('');
  const [silverPhysical, setSilverPhysical] = useState('');
  const [silverPhysicalMode, setSilverPhysicalMode] = useState('manual');
  const [silverPremium, setSilverPremium] = useState('0');
  const [silverMov, setSilverMov] = useState('stable');
  const [goldDollar, setGoldDollar] = useState('');
  const [goldMcx, setGoldMcx] = useState('');
  const [goldPhysical, setGoldPhysical] = useState('');
  const [goldPhysicalMode, setGoldPhysicalMode] = useState('manual');
  const [goldPremium, setGoldPremium] = useState('0');
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

  // Bulk upload
  const [showBulkUpload, setShowBulkUpload] = useState(false);
  const [bulkUrls, setBulkUrls] = useState('');
  const [bulkMetal, setBulkMetal] = useState('silver');
  const [bulkCategory, setBulkCategory] = useState('');
  const [bulkBatchName, setBulkBatchName] = useState('');
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState('');

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
          if (r.silver_dollar_rate !== undefined) {
            setSilverDollar(String(r.silver_dollar_rate || '')); setSilverMcx(String(r.silver_mcx_rate || '')); setSilverPhysical(String(r.silver_physical_rate || ''));
            setSilverPhysicalMode(r.silver_physical_mode || 'manual'); setSilverPremium(String(r.silver_physical_premium || 0));
            setGoldDollar(String(r.gold_dollar_rate || '')); setGoldMcx(String(r.gold_mcx_rate || '')); setGoldPhysical(String(r.gold_physical_rate || ''));
            setGoldPhysicalMode(r.gold_physical_mode || 'manual'); setGoldPremium(String(r.gold_physical_premium || 0));
            setSilverMov(r.silver_movement || 'stable'); setGoldMov(r.gold_movement || 'stable');
            setMarketSummary(r.market_summary || '');
          }
          break;
        }
      }
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  };

  useEffect(() => { loadTab(activeTab); }, [activeTab]);

  const updateRates = async () => {
    if (!silverDollar && !silverMcx && !silverPhysical) { Alert.alert('Error', 'Enter at least one silver rate'); return; }
    try {
      await api.post('/rates', {
        silver_dollar_rate: parseFloat(silverDollar) || 0, silver_mcx_rate: parseFloat(silverMcx) || 0, silver_physical_rate: parseFloat(silverPhysical) || 0,
        silver_physical_mode: silverPhysicalMode, silver_physical_premium: parseFloat(silverPremium) || 0, silver_physical_base: 'mcx', silver_movement: silverMov,
        gold_dollar_rate: parseFloat(goldDollar) || 0, gold_mcx_rate: parseFloat(goldMcx) || 0, gold_physical_rate: parseFloat(goldPhysical) || 0,
        gold_physical_mode: goldPhysicalMode, gold_physical_premium: parseFloat(goldPremium) || 0, gold_physical_base: 'mcx', gold_movement: goldMov,
        market_summary: marketSummary
      });
      Alert.alert('Success', 'Rates updated!');
    } catch (e: any) { Alert.alert('Error', e.message); }
  };

  const bulkUpload = async () => {
    const urls = bulkUrls.split('\n').map(u => u.trim()).filter(u => u);
    if (urls.length === 0) { Alert.alert('Error', 'Paste image URLs (one per line)'); return; }
    setUploading(true); setUploadResult('');
    try {
      const res = await api.post('/products/bulk', { image_urls: urls, metal_type: bulkMetal, category: bulkCategory, batch_name: bulkBatchName });
      setUploadResult(`Uploaded ${res.count} images (Batch: ${res.batch_name})`);
      setBulkUrls('');
      Alert.alert('Success', `${res.count} images uploaded!`);
    } catch (e: any) { Alert.alert('Error', e.message); }
    finally { setUploading(false); }
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
    { key: 'batches', label: 'Batches', icon: 'folder' },
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
              <View style={styles.formRow}>
                <TouchableOpacity testID="add-product-btn" style={[styles.actionBtn, { flex: 1 }]} onPress={() => { setShowAddProduct(!showAddProduct); setShowBulkUpload(false); }}>
                  <Ionicons name={showAddProduct ? 'close' : 'add'} size={18} color="#000" />
                  <Text style={styles.actionBtnText}>{showAddProduct ? 'Cancel' : 'Add Product'}</Text>
                </TouchableOpacity>
                <TouchableOpacity testID="bulk-upload-btn" style={[styles.actionBtn, { flex: 1, backgroundColor: '#A855F7' }]} onPress={() => { setShowBulkUpload(!showBulkUpload); setShowAddProduct(false); }}>
                  <Ionicons name={showBulkUpload ? 'close' : 'cloud-upload'} size={18} color="#fff" />
                  <Text style={[styles.actionBtnText, { color: '#fff' }]}>{showBulkUpload ? 'Cancel' : 'Bulk Upload'}</Text>
                </TouchableOpacity>
              </View>

              {/* BULK UPLOAD SECTION */}
              {showBulkUpload && (
                <View style={styles.formCard}>
                  <Text style={styles.formTitle}>Bulk Photo Upload</Text>
                  <Text style={[styles.formLabel, { color: Colors.textSecondary }]}>Paste image URLs below (one per line). No title/description needed.</Text>
                  <TextInput testID="bulk-urls" style={[styles.formInput, { minHeight: 120 }]} placeholder={'https://example.com/photo1.jpg\nhttps://example.com/photo2.jpg\nhttps://example.com/photo3.jpg'} placeholderTextColor={Colors.textMuted} value={bulkUrls} onChangeText={setBulkUrls} multiline textAlignVertical="top" />
                  <Text style={styles.formLabel}>Batch Name (optional)</Text>
                  <TextInput style={styles.formInput} placeholder="e.g., New Silver Collection Feb 2026" placeholderTextColor={Colors.textMuted} value={bulkBatchName} onChangeText={setBulkBatchName} />
                  <Text style={styles.formLabel}>Metal Type</Text>
                  <View style={styles.formRow}>
                    {['silver', 'gold', 'diamond'].map(m => (
                      <TouchableOpacity key={m} style={[styles.metalBtn, bulkMetal === m && styles.metalBtnActive]} onPress={() => setBulkMetal(m)}><Text style={[styles.metalBtnText, bulkMetal === m && styles.metalBtnTextActive]}>{m}</Text></TouchableOpacity>
                    ))}
                  </View>
                  <Text style={styles.formLabel}>Category (optional)</Text>
                  <TextInput style={styles.formInput} placeholder="e.g., payal, chain, articles" placeholderTextColor={Colors.textMuted} value={bulkCategory} onChangeText={setBulkCategory} />
                  {uploadResult ? <Text style={[styles.formLabel, { color: Colors.success }]}>{uploadResult}</Text> : null}
                  <TouchableOpacity testID="do-bulk-upload" style={[styles.saveBtn, { backgroundColor: '#A855F7' }]} onPress={bulkUpload} disabled={uploading}>
                    {uploading ? <ActivityIndicator color="#fff" /> : <Text style={[styles.saveBtnText, { color: '#fff' }]}>UPLOAD {bulkUrls.split('\n').filter(u => u.trim()).length} IMAGES</Text>}
                  </TouchableOpacity>
                </View>
              )}

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
              {/* Silver */}
              <Text style={[styles.formLabel, { color: Colors.silver, fontSize: FontSize.md }]}>SILVER RATES</Text>
              <View style={styles.formRow}>
                <View style={{ flex: 1 }}><Text style={styles.formLabel}>Dollar $/oz</Text><TextInput style={styles.formInput} value={silverDollar} onChangeText={setSilverDollar} keyboardType="decimal-pad" placeholder="31.25" placeholderTextColor={Colors.textMuted} /></View>
                <View style={{ flex: 1 }}><Text style={styles.formLabel}>MCX ₹/g</Text><TextInput style={styles.formInput} value={silverMcx} onChangeText={setSilverMcx} keyboardType="decimal-pad" placeholder="95.80" placeholderTextColor={Colors.textMuted} /></View>
              </View>
              <Text style={styles.formLabel}>Physical Rate Mode</Text>
              <View style={styles.formRow}>
                {['manual', 'calculated'].map(m => (
                  <TouchableOpacity key={m} style={[styles.metalBtn, silverPhysicalMode === m && styles.metalBtnActive]} onPress={() => setSilverPhysicalMode(m)}><Text style={[styles.metalBtnText, silverPhysicalMode === m && styles.metalBtnTextActive]}>{m}</Text></TouchableOpacity>
                ))}
              </View>
              {silverPhysicalMode === 'manual' ? (
                <><Text style={styles.formLabel}>Physical Rate ₹/g (Manual)</Text><TextInput style={styles.formInput} value={silverPhysical} onChangeText={setSilverPhysical} keyboardType="decimal-pad" placeholder="96.50" placeholderTextColor={Colors.textMuted} /></>
              ) : (
                <><Text style={styles.formLabel}>Premium over MCX (₹)</Text><TextInput style={styles.formInput} value={silverPremium} onChangeText={setSilverPremium} keyboardType="decimal-pad" placeholder="0.70" placeholderTextColor={Colors.textMuted} />
                <Text style={[styles.formLabel, { color: Colors.gold }]}>Physical = MCX ({silverMcx || '0'}) + Premium ({silverPremium || '0'}) = ₹{(parseFloat(silverMcx || '0') + parseFloat(silverPremium || '0')).toFixed(2)}</Text></>
              )}
              <Text style={styles.formLabel}>Silver Movement</Text>
              <View style={styles.formRow}>
                {['up', 'down', 'stable'].map(m => (<TouchableOpacity key={m} style={[styles.metalBtn, silverMov === m && styles.metalBtnActive]} onPress={() => setSilverMov(m)}><Text style={[styles.metalBtnText, silverMov === m && styles.metalBtnTextActive]}>{m}</Text></TouchableOpacity>))}
              </View>

              <View style={{ height: 1, backgroundColor: Colors.border, marginVertical: 16 }} />

              {/* Gold */}
              <Text style={[styles.formLabel, { color: Colors.gold, fontSize: FontSize.md }]}>GOLD RATES</Text>
              <View style={styles.formRow}>
                <View style={{ flex: 1 }}><Text style={styles.formLabel}>Dollar $/oz</Text><TextInput style={styles.formInput} value={goldDollar} onChangeText={setGoldDollar} keyboardType="decimal-pad" placeholder="2385" placeholderTextColor={Colors.textMuted} /></View>
                <View style={{ flex: 1 }}><Text style={styles.formLabel}>MCX ₹/g</Text><TextInput style={styles.formInput} value={goldMcx} onChangeText={setGoldMcx} keyboardType="decimal-pad" placeholder="7380" placeholderTextColor={Colors.textMuted} /></View>
              </View>
              <Text style={styles.formLabel}>Physical Rate Mode</Text>
              <View style={styles.formRow}>
                {['manual', 'calculated'].map(m => (
                  <TouchableOpacity key={m} style={[styles.metalBtn, goldPhysicalMode === m && styles.metalBtnActive]} onPress={() => setGoldPhysicalMode(m)}><Text style={[styles.metalBtnText, goldPhysicalMode === m && styles.metalBtnTextActive]}>{m}</Text></TouchableOpacity>
                ))}
              </View>
              {goldPhysicalMode === 'manual' ? (
                <><Text style={styles.formLabel}>Physical Rate ₹/g (Manual)</Text><TextInput style={styles.formInput} value={goldPhysical} onChangeText={setGoldPhysical} keyboardType="decimal-pad" placeholder="7450" placeholderTextColor={Colors.textMuted} /></>
              ) : (
                <><Text style={styles.formLabel}>Premium over MCX (₹)</Text><TextInput style={styles.formInput} value={goldPremium} onChangeText={setGoldPremium} keyboardType="decimal-pad" placeholder="70" placeholderTextColor={Colors.textMuted} />
                <Text style={[styles.formLabel, { color: Colors.gold }]}>Physical = MCX ({goldMcx || '0'}) + Premium ({goldPremium || '0'}) = ₹{(parseFloat(goldMcx || '0') + parseFloat(goldPremium || '0')).toFixed(0)}</Text></>
              )}
              <Text style={styles.formLabel}>Gold Movement</Text>
              <View style={styles.formRow}>
                {['up', 'down', 'stable'].map(m => (<TouchableOpacity key={m} style={[styles.metalBtn, goldMov === m && styles.metalBtnActive]} onPress={() => setGoldMov(m)}><Text style={[styles.metalBtnText, goldMov === m && styles.metalBtnTextActive]}>{m}</Text></TouchableOpacity>))}
              </View>

              <Text style={styles.formLabel}>Market Summary</Text>
              <TextInput style={styles.formInput} value={marketSummary} onChangeText={setMarketSummary} placeholder="e.g., Silver up 1.2% today" placeholderTextColor={Colors.textMuted} />
              <TouchableOpacity testID="update-rates-btn" style={styles.saveBtn} onPress={updateRates}><Text style={styles.saveBtnText}>UPDATE RATES</Text></TouchableOpacity>
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
                    <View style={[styles.statusBadge, { backgroundColor: r.status === 'pending' ? Colors.warning + '20' : r.status === 'resolved' ? Colors.success + '20' : Colors.info + '20' }]}>
                      <Text style={[styles.statusText, { color: r.status === 'pending' ? Colors.warning : r.status === 'resolved' ? Colors.success : Colors.info }]}>{r.status}</Text>
                    </View>
                  </View>
                  <Text style={styles.listMeta}>{r.user_name || r.user_phone} • {r.category} • {r.preferred_time}</Text>
                  {r.notes ? <Text style={styles.notesText}>Notes: {r.notes}</Text> : null}
                    {r.status === 'pending' && (
                    <View style={styles.requestActions}>
                      <TouchableOpacity style={[styles.miniBtn, { backgroundColor: Colors.info + '20' }]} onPress={() => updateRequestStatus(r.id, 'in_progress')}>
                        <Text style={[styles.miniBtnText, { color: Colors.info }]}>In Progress</Text>
                      </TouchableOpacity>
                      <TouchableOpacity style={[styles.miniBtn, { backgroundColor: Colors.success + '20' }]} onPress={() => updateRequestStatus(r.id, 'resolved')}>
                        <Text style={[styles.miniBtnText, { color: Colors.success }]}>Resolved</Text>
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

          {/* BATCHES - Quick link to full manager */}
          {activeTab === 'batches' && (
            <>
              <TouchableOpacity testID="open-batch-manager" style={styles.batchManagerBtn} onPress={() => router.push('/admin-batches')}>
                <Ionicons name="folder-open" size={28} color={Colors.gold} />
                <Text style={styles.batchManagerText}>Open Batch Manager</Text>
                <Text style={styles.batchManagerHint}>Upload images, manage batches, hide/show content</Text>
              </TouchableOpacity>
              <View style={styles.batchInfoCard}>
                <Ionicons name="information-circle" size={18} color={Colors.info} />
                <Text style={styles.batchInfoText}>Use the Batch Manager to upload real image files from your device. Create batches, organize by metal/category, and manage your entire photo library.</Text>
              </View>
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
  batchManagerBtn: { backgroundColor: Colors.card, borderRadius: 16, padding: Spacing.xl, alignItems: 'center', marginTop: Spacing.md, borderWidth: 1, borderColor: Colors.borderGold, gap: 8 },
  batchManagerText: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.gold },
  batchManagerHint: { fontSize: FontSize.sm, color: Colors.textSecondary, textAlign: 'center' },
  batchInfoCard: { flexDirection: 'row', gap: 10, backgroundColor: Colors.info + '10', borderRadius: 12, padding: Spacing.md, marginTop: Spacing.md, alignItems: 'flex-start' },
  batchInfoText: { flex: 1, fontSize: FontSize.sm, color: Colors.textSecondary, lineHeight: 20 },
});
