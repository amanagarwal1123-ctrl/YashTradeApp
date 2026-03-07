import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, TextInput, ActivityIndicator, Alert, Image, Platform, Linking } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../src/theme';
import { api, setToken, getImageUrl } from '../src/api';

type PanelTab = 'dashboard' | 'requests' | 'rates' | 'products' | 'batches' | 'customers';
type Role = 'admin' | 'executive' | null;

const CANONICAL_STATUSES = ['pending', 'in_progress', 'contacted', 'resolved', 'no_response'];

export default function PanelScreen() {
  // Auth
  const [role, setRole] = useState<Role>(null);
  const [user, setUser] = useState<any>(null);
  const [phone, setPhone] = useState('');
  const [otp, setOtp] = useState('');
  const [authStep, setAuthStep] = useState<'phone' | 'otp' | 'done'>('phone');
  const [authLoading, setAuthLoading] = useState(false);
  const [authError, setAuthError] = useState('');

  // Panel
  const [tab, setTab] = useState<PanelTab>('dashboard');
  const [loading, setLoading] = useState(false);

  // Data
  const [dashData, setDashData] = useState<any>(null);
  const [requests, setRequests] = useState<any[]>([]);
  const [statusFilter, setStatusFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [products, setProducts] = useState<any[]>([]);
  const [batches, setBatches] = useState<any[]>([]);
  const [customers, setCustomers] = useState<any[]>([]);

  // Rates
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

  // Batch create
  const [newBatchName, setNewBatchName] = useState('');
  const [newBatchMetal, setNewBatchMetal] = useState('silver');
  const [newBatchCat, setNewBatchCat] = useState('');
  const [showBatchForm, setShowBatchForm] = useState(false);

  // Upload
  const [uploadBatchId, setUploadBatchId] = useState('');
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState({ done: 0, total: 0 });

  // Request detail
  const [editingReqId, setEditingReqId] = useState('');
  const [noteText, setNoteText] = useState('');

  // === AUTH ===
  const sendOtp = async () => {
    if (phone.length < 10) { setAuthError('Enter valid 10-digit number'); return; }
    setAuthLoading(true); setAuthError('');
    try {
      await api.post('/auth/send-otp', { phone });
      setAuthStep('otp');
    } catch (e: any) { setAuthError(e.message); }
    finally { setAuthLoading(false); }
  };

  const verifyOtp = async () => {
    setAuthLoading(true); setAuthError('');
    try {
      const res = await api.post('/auth/verify-otp', { phone, otp });
      const u = res.user;
      if (u.role !== 'admin' && u.role !== 'executive') {
        setAuthError('Access denied. This panel is for admin and executive users only.');
        setToken(null);
        return;
      }
      setToken(res.token);
      setUser(u);
      setRole(u.role);
      setAuthStep('done');
    } catch (e: any) { setAuthError(e.message); }
    finally { setAuthLoading(false); }
  };

  const panelLogout = () => {
    setToken(null); setUser(null); setRole(null);
    setAuthStep('phone'); setPhone(''); setOtp('');
  };

  // === DATA LOADING ===
  const loadTab = useCallback(async (t: PanelTab) => {
    setLoading(true);
    try {
      switch (t) {
        case 'dashboard': setDashData(await api.get('/analytics/dashboard')); break;
        case 'requests': {
          const params = new URLSearchParams();
          if (statusFilter) params.set('status', statusFilter);
          if (typeFilter) params.set('request_type', typeFilter);
          const r = await api.get(`/requests?${params}`);
          setRequests(r.requests || []);
          break;
        }
        case 'rates': {
          const r = await api.get('/rates/latest');
          setSilverDollar(String(r.silver_dollar_rate || '')); setSilverMcx(String(r.silver_mcx_rate || ''));
          setSilverPhysical(String(r.silver_physical_rate || '')); setSilverPhysicalMode(r.silver_physical_mode || 'manual');
          setSilverPremium(String(r.silver_physical_premium || 0)); setSilverMov(r.silver_movement || 'stable');
          setGoldDollar(String(r.gold_dollar_rate || '')); setGoldMcx(String(r.gold_mcx_rate || ''));
          setGoldPhysical(String(r.gold_physical_rate || '')); setGoldPhysicalMode(r.gold_physical_mode || 'manual');
          setGoldPremium(String(r.gold_physical_premium || 0)); setGoldMov(r.gold_movement || 'stable');
          setMarketSummary(r.market_summary || '');
          break;
        }
        case 'products': { const r = await api.get('/products?limit=50&include_hidden=true'); setProducts(r.products || []); break; }
        case 'batches': { const r = await api.get('/batches'); setBatches(r.batches || []); break; }
        case 'customers': { const r = await api.get('/customers?limit=100'); setCustomers(r.customers || []); break; }
      }
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [statusFilter, typeFilter]);

  useEffect(() => { if (role) loadTab(tab); }, [tab, role]);
  useEffect(() => { if (role && tab === 'requests') loadTab('requests'); }, [statusFilter, typeFilter]);

  // === ACTIONS ===
  const updateRates = async () => {
    try {
      await api.post('/rates', {
        silver_dollar_rate: parseFloat(silverDollar) || 0, silver_mcx_rate: parseFloat(silverMcx) || 0, silver_physical_rate: parseFloat(silverPhysical) || 0,
        silver_physical_mode: silverPhysicalMode, silver_physical_premium: parseFloat(silverPremium) || 0, silver_physical_base: 'mcx', silver_movement: silverMov,
        gold_dollar_rate: parseFloat(goldDollar) || 0, gold_mcx_rate: parseFloat(goldMcx) || 0, gold_physical_rate: parseFloat(goldPhysical) || 0,
        gold_physical_mode: goldPhysicalMode, gold_physical_premium: parseFloat(goldPremium) || 0, gold_physical_base: 'mcx', gold_movement: goldMov,
        market_summary: marketSummary
      });
      Alert.alert('Success', 'Rates updated');
    } catch (e: any) { Alert.alert('Error', e.message); }
  };

  const updateRequestStatus = async (id: string, status: string) => {
    try {
      await api.patch(`/requests/${id}`, { status, assigned_to: user?.name || '', notes: noteText || '' });
      setEditingReqId(''); setNoteText('');
      loadTab('requests');
    } catch (e: any) { Alert.alert('Error', e.message); }
  };

  const createBatch = async () => {
    if (!newBatchName.trim()) return;
    try {
      await api.post('/batches', { name: newBatchName, metal_type: newBatchMetal, category: newBatchCat });
      setNewBatchName(''); setNewBatchCat(''); setShowBatchForm(false);
      loadTab('batches');
    } catch (e: any) { Alert.alert('Error', e.message); }
  };

  const toggleBatchVisibility = async (id: string) => {
    try { await api.patch(`/batches/${id}/visibility`); loadTab('batches'); } catch {}
  };

  const deleteBatch = (id: string, name: string) => {
    Alert.alert('Delete', `Delete "${name}"?`, [{ text: 'Cancel' }, { text: 'Delete', style: 'destructive', onPress: async () => { await api.delete(`/batches/${id}`); loadTab('batches'); } }]);
  };

  const pickFiles = () => {
    if (Platform.OS === 'web') {
      const input = document.createElement('input');
      input.type = 'file'; input.accept = 'image/*'; input.multiple = true;
      input.onchange = (e: any) => { const f = Array.from(e.target.files || []) as File[]; if (f.length) setSelectedFiles(prev => [...prev, ...f]); };
      input.click();
    }
  };

  const startUpload = async () => {
    if (!uploadBatchId || !selectedFiles.length) return;
    setUploading(true); setUploadProgress({ done: 0, total: selectedFiles.length });
    try {
      await api.uploadFiles(`/batches/${uploadBatchId}/upload`, selectedFiles, (d, t) => setUploadProgress({ done: d, total: t }));
      setSelectedFiles([]); setUploadBatchId('');
      Alert.alert('Success', 'Images uploaded');
      loadTab('batches');
    } catch (e: any) { Alert.alert('Error', e.message); }
    finally { setUploading(false); }
  };

  const openWhatsApp = (phoneNum: string) => { Linking.openURL(`https://wa.me/91${phoneNum}`); };
  const openCall = (phoneNum: string) => { Linking.openURL(`tel:+91${phoneNum}`); };

  const statusColor = (s: string) => {
    switch (s) { case 'pending': return Colors.warning; case 'in_progress': return Colors.info; case 'contacted': return '#A855F7'; case 'resolved': return Colors.success; case 'no_response': return Colors.error; default: return Colors.textMuted; }
  };

  const typeIcon = (t: string) => {
    switch (t) { case 'video_call': return 'videocam'; case 'call': return 'call'; case 'ask_price': return 'pricetag'; case 'ask_similar': return 'copy'; case 'hold_item': return 'bookmark'; case 'quick_reorder': return 'refresh'; default: return 'chatbox'; }
  };

  // === LOGIN SCREEN ===
  if (authStep !== 'done') {
    return (
      <SafeAreaView style={s.container}>
        <View style={s.loginBox}>
          <Ionicons name="shield-checkmark" size={48} color={Colors.gold} />
          <Text style={s.loginTitle}>Yash Trade Panel</Text>
          <Text style={s.loginSub}>Admin & Executive Access Only</Text>
          {authStep === 'phone' ? (
            <>
              <TextInput testID="panel-phone" style={s.loginInput} placeholder="Phone number" placeholderTextColor={Colors.textMuted} value={phone} onChangeText={t => { setPhone(t.replace(/[^0-9]/g, '')); setAuthError(''); }} keyboardType="phone-pad" maxLength={10} />
              <TouchableOpacity testID="panel-send-otp" style={s.loginBtn} onPress={sendOtp} disabled={authLoading}>
                {authLoading ? <ActivityIndicator color="#000" /> : <Text style={s.loginBtnText}>GET OTP</Text>}
              </TouchableOpacity>
            </>
          ) : (
            <>
              <TextInput testID="panel-otp" style={s.loginInput} placeholder="Enter OTP" placeholderTextColor={Colors.textMuted} value={otp} onChangeText={setOtp} keyboardType="number-pad" maxLength={4} />
              <TouchableOpacity testID="panel-verify" style={s.loginBtn} onPress={verifyOtp} disabled={authLoading}>
                {authLoading ? <ActivityIndicator color="#000" /> : <Text style={s.loginBtnText}>VERIFY</Text>}
              </TouchableOpacity>
              <TouchableOpacity onPress={() => setAuthStep('phone')}><Text style={s.loginLink}>Change number</Text></TouchableOpacity>
            </>
          )}
          {authError ? <Text style={s.loginError}>{authError}</Text> : null}
          <Text style={s.loginHint}>Demo OTP: 1234</Text>
        </View>
      </SafeAreaView>
    );
  }

  // === TABS ===
  const ADMIN_TABS: { key: PanelTab; label: string; icon: string }[] = [
    { key: 'dashboard', label: 'Dashboard', icon: 'stats-chart' },
    { key: 'requests', label: 'Requests', icon: 'call' },
    { key: 'rates', label: 'Rates', icon: 'trending-up' },
    { key: 'products', label: 'Products', icon: 'grid' },
    { key: 'batches', label: 'Batches', icon: 'folder' },
    { key: 'customers', label: 'Customers', icon: 'people' },
  ];
  const EXEC_TABS: { key: PanelTab; label: string; icon: string }[] = [
    { key: 'requests', label: 'Requests', icon: 'call' },
  ];
  const tabs = role === 'admin' ? ADMIN_TABS : EXEC_TABS;

  return (
    <SafeAreaView style={s.container} edges={['top']}>
      {/* Header */}
      <View style={s.header}>
        <Text style={s.headerTitle}>Yash Trade Panel</Text>
        <View style={s.headerRight}>
          <Text style={s.headerUser}>{user?.name || user?.phone}</Text>
          <View style={[s.roleBadge, { backgroundColor: role === 'admin' ? Colors.gold + '20' : Colors.info + '20' }]}>
            <Text style={[s.roleText, { color: role === 'admin' ? Colors.gold : Colors.info }]}>{role?.toUpperCase()}</Text>
          </View>
          <TouchableOpacity testID="panel-logout" onPress={panelLogout} style={s.logoutBtn}><Ionicons name="log-out-outline" size={18} color={Colors.error} /></TouchableOpacity>
        </View>
      </View>

      {/* Tab bar */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.tabBar}>
        {tabs.map(t => (
          <TouchableOpacity key={t.key} testID={`panel-tab-${t.key}`} style={[s.tabItem, tab === t.key && s.tabActive]} onPress={() => setTab(t.key)}>
            <Ionicons name={t.icon as any} size={16} color={tab === t.key ? Colors.gold : Colors.textMuted} />
            <Text style={[s.tabLabel, tab === t.key && s.tabLabelActive]}>{t.label}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      {loading ? <ActivityIndicator color={Colors.gold} style={{ marginTop: 40 }} /> : (
        <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={s.content}>

          {/* ===== DASHBOARD ===== */}
          {tab === 'dashboard' && dashData && (
            <>
              <View style={s.statsGrid}>
                {[
                  { label: 'Customers', value: dashData.total_users, icon: 'people', color: Colors.info },
                  { label: 'Products', value: dashData.total_products, icon: 'grid', color: Colors.success },
                  { label: 'Batches', value: dashData.total_batches, icon: 'folder', color: '#A855F7' },
                  { label: 'Uploaded', value: dashData.uploaded_images, icon: 'cloud-upload', color: Colors.gold },
                  { label: 'Requests', value: dashData.total_requests, icon: 'call', color: Colors.warning },
                  { label: 'Pending', value: dashData.pending_requests, icon: 'time', color: Colors.error },
                ].map(c => (
                  <View key={c.label} style={s.statCard}>
                    <Ionicons name={c.icon as any} size={20} color={c.color} />
                    <Text style={s.statVal}>{c.value}</Text>
                    <Text style={s.statLbl}>{c.label}</Text>
                  </View>
                ))}
              </View>
              <Text style={s.sectionTitle}>RECENT REQUESTS</Text>
              {dashData.recent_requests?.map((r: any) => (
                <View key={r.id} style={s.listItem}>
                  <Text style={s.listTitle}>{r.request_type?.replace(/_/g, ' ')} — {r.user_name || r.user_phone}</Text>
                  <View style={[s.badge, { backgroundColor: statusColor(r.status) + '20' }]}><Text style={[s.badgeText, { color: statusColor(r.status) }]}>{r.status}</Text></View>
                </View>
              ))}
            </>
          )}

          {/* ===== REQUESTS (Executive core) ===== */}
          {tab === 'requests' && (
            <>
              {/* Filters */}
              <View style={s.filterSection}>
                <Text style={s.filterLabel}>Status:</Text>
                <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.filterRow}>
                  {['', ...CANONICAL_STATUSES].map(st => (
                    <TouchableOpacity key={st} style={[s.chip, statusFilter === st && { backgroundColor: (st ? statusColor(st) : Colors.gold) + '20', borderColor: st ? statusColor(st) : Colors.gold }]} onPress={() => setStatusFilter(st)}>
                      <Text style={[s.chipText, statusFilter === st && { color: st ? statusColor(st) : Colors.gold }]}>{st ? st.replace(/_/g, ' ') : 'All'}</Text>
                    </TouchableOpacity>
                  ))}
                </ScrollView>
              </View>
              <View style={s.filterSection}>
                <Text style={s.filterLabel}>Type:</Text>
                <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.filterRow}>
                  {['', 'call', 'video_call', 'ask_price', 'ask_similar', 'hold_item', 'quick_reorder'].map(tp => (
                    <TouchableOpacity key={tp} style={[s.chip, typeFilter === tp && s.chipActive]} onPress={() => setTypeFilter(tp)}>
                      <Text style={[s.chipText, typeFilter === tp && s.chipTextActive]}>{tp ? tp.replace(/_/g, ' ') : 'All'}</Text>
                    </TouchableOpacity>
                  ))}
                </ScrollView>
              </View>

              <Text style={s.sectionTitle}>REQUESTS ({requests.length})</Text>
              {requests.map(r => (
                <View key={r.id} style={s.reqCard}>
                  <View style={s.reqTop}>
                    <View style={[s.reqIcon, { backgroundColor: statusColor(r.status) + '15' }]}>
                      <Ionicons name={typeIcon(r.request_type) as any} size={18} color={statusColor(r.status)} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={s.reqType}>{r.request_type?.replace(/_/g, ' ')}</Text>
                      <Text style={s.reqTime}>{new Date(r.created_at).toLocaleString()}</Text>
                    </View>
                    <View style={[s.badge, { backgroundColor: statusColor(r.status) + '20' }]}>
                      <Text style={[s.badgeText, { color: statusColor(r.status) }]}>{r.status?.replace(/_/g, ' ')}</Text>
                    </View>
                  </View>

                  {/* Customer info */}
                  <View style={s.reqInfo}>
                    <View style={s.infoRow}><Ionicons name="person" size={14} color={Colors.textMuted} /><Text style={s.infoText}>{r.user_name || 'Unknown'}</Text></View>
                    <View style={s.infoRow}><Ionicons name="call" size={14} color={Colors.textMuted} /><Text style={s.infoText}>{r.user_phone}</Text></View>
                    {r.user_city ? <View style={s.infoRow}><Ionicons name="location" size={14} color={Colors.textMuted} /><Text style={s.infoText}>{r.user_city}</Text></View> : null}
                    {r.category ? <View style={s.infoRow}><Ionicons name="grid" size={14} color={Colors.textMuted} /><Text style={s.infoText}>{r.category}</Text></View> : null}
                    {r.notes ? <View style={s.infoRow}><Ionicons name="document-text" size={14} color={Colors.textMuted} /><Text style={s.infoText}>{r.notes}</Text></View> : null}
                    {r.admin_notes ? <View style={[s.infoRow, { backgroundColor: Colors.gold + '08', padding: 6, borderRadius: 6 }]}><Ionicons name="chatbox" size={14} color={Colors.gold} /><Text style={[s.infoText, { color: Colors.gold }]}>{r.admin_notes}</Text></View> : null}
                  </View>

                  {/* Quick contact */}
                  {r.user_phone && (
                    <View style={s.contactRow}>
                      <TouchableOpacity testID={`wa-${r.id}`} style={[s.contactBtn, { backgroundColor: '#25D36620' }]} onPress={() => openWhatsApp(r.user_phone)}>
                        <Ionicons name="logo-whatsapp" size={16} color="#25D366" /><Text style={[s.contactBtnText, { color: '#25D366' }]}>WhatsApp</Text>
                      </TouchableOpacity>
                      <TouchableOpacity testID={`call-${r.id}`} style={[s.contactBtn, { backgroundColor: Colors.success + '20' }]} onPress={() => openCall(r.user_phone)}>
                        <Ionicons name="call" size={16} color={Colors.success} /><Text style={[s.contactBtnText, { color: Colors.success }]}>Call</Text>
                      </TouchableOpacity>
                    </View>
                  )}

                  {/* Notes input */}
                  {editingReqId === r.id && (
                    <TextInput style={s.noteInput} placeholder="Add notes..." placeholderTextColor={Colors.textMuted} value={noteText} onChangeText={setNoteText} multiline />
                  )}

                  {/* Status actions */}
                  <View style={s.actionsRow}>
                    {r.status === 'pending' && <>
                      <TouchableOpacity style={[s.actBtn, { backgroundColor: Colors.info + '15' }]} onPress={() => updateRequestStatus(r.id, 'in_progress')}><Text style={[s.actText, { color: Colors.info }]}>In Progress</Text></TouchableOpacity>
                      <TouchableOpacity style={[s.actBtn, { backgroundColor: '#A855F715' }]} onPress={() => updateRequestStatus(r.id, 'contacted')}><Text style={[s.actText, { color: '#A855F7' }]}>Contacted</Text></TouchableOpacity>
                    </>}
                    {['pending', 'in_progress', 'contacted'].includes(r.status) && <>
                      <TouchableOpacity style={[s.actBtn, { backgroundColor: Colors.success + '15' }]} onPress={() => { if (editingReqId !== r.id) setEditingReqId(r.id); else updateRequestStatus(r.id, 'resolved'); }}>
                        <Text style={[s.actText, { color: Colors.success }]}>Resolved</Text>
                      </TouchableOpacity>
                      <TouchableOpacity style={[s.actBtn, { backgroundColor: Colors.error + '15' }]} onPress={() => updateRequestStatus(r.id, 'no_response')}>
                        <Text style={[s.actText, { color: Colors.error }]}>No Response</Text>
                      </TouchableOpacity>
                    </>}
                    {editingReqId !== r.id && (
                      <TouchableOpacity style={[s.actBtn, { backgroundColor: Colors.gold + '15' }]} onPress={() => setEditingReqId(r.id)}>
                        <Ionicons name="create" size={12} color={Colors.gold} /><Text style={[s.actText, { color: Colors.gold }]}>Notes</Text>
                      </TouchableOpacity>
                    )}
                  </View>
                </View>
              ))}
              {requests.length === 0 && <Text style={s.emptyText}>No requests found</Text>}
            </>
          )}

          {/* ===== RATES ===== */}
          {tab === 'rates' && (
            <View style={s.formCard}>
              <Text style={s.formTitle}>Update Daily Rates</Text>
              <Text style={[s.formLabel, { color: Colors.silver }]}>SILVER RATES</Text>
              <View style={s.formRow}>
                <View style={{ flex: 1 }}><Text style={s.formLabel}>Dollar $/oz</Text><TextInput style={s.formInput} value={silverDollar} onChangeText={setSilverDollar} keyboardType="decimal-pad" placeholder="31.25" placeholderTextColor={Colors.textMuted} /></View>
                <View style={{ flex: 1 }}><Text style={s.formLabel}>MCX Rs/g</Text><TextInput style={s.formInput} value={silverMcx} onChangeText={setSilverMcx} keyboardType="decimal-pad" placeholder="95.80" placeholderTextColor={Colors.textMuted} /></View>
              </View>
              <Text style={s.formLabel}>Physical Mode</Text>
              <View style={s.formRow}>{['manual', 'calculated'].map(m => (<TouchableOpacity key={m} style={[s.metalBtn, silverPhysicalMode === m && s.metalBtnActive]} onPress={() => setSilverPhysicalMode(m)}><Text style={[s.metalBtnText, silverPhysicalMode === m && s.metalBtnTextActive]}>{m}</Text></TouchableOpacity>))}</View>
              {silverPhysicalMode === 'manual' ? (
                <><Text style={s.formLabel}>Physical Rate Rs/g</Text><TextInput style={s.formInput} value={silverPhysical} onChangeText={setSilverPhysical} keyboardType="decimal-pad" placeholder="96.50" placeholderTextColor={Colors.textMuted} /></>
              ) : (
                <><Text style={s.formLabel}>Premium over MCX (Rs)</Text><TextInput style={s.formInput} value={silverPremium} onChangeText={setSilverPremium} keyboardType="decimal-pad" placeholder="0.70" placeholderTextColor={Colors.textMuted} /></>
              )}
              <Text style={s.formLabel}>Movement</Text>
              <View style={s.formRow}>{['up', 'down', 'stable'].map(m => (<TouchableOpacity key={m} style={[s.metalBtn, silverMov === m && s.metalBtnActive]} onPress={() => setSilverMov(m)}><Text style={[s.metalBtnText, silverMov === m && s.metalBtnTextActive]}>{m}</Text></TouchableOpacity>))}</View>
              <View style={{ height: 1, backgroundColor: Colors.border, marginVertical: 16 }} />
              <Text style={[s.formLabel, { color: Colors.gold }]}>GOLD RATES</Text>
              <View style={s.formRow}>
                <View style={{ flex: 1 }}><Text style={s.formLabel}>Dollar $/oz</Text><TextInput style={s.formInput} value={goldDollar} onChangeText={setGoldDollar} keyboardType="decimal-pad" placeholder="2385" placeholderTextColor={Colors.textMuted} /></View>
                <View style={{ flex: 1 }}><Text style={s.formLabel}>MCX Rs/g</Text><TextInput style={s.formInput} value={goldMcx} onChangeText={setGoldMcx} keyboardType="decimal-pad" placeholder="7380" placeholderTextColor={Colors.textMuted} /></View>
              </View>
              <Text style={s.formLabel}>Physical Mode</Text>
              <View style={s.formRow}>{['manual', 'calculated'].map(m => (<TouchableOpacity key={m} style={[s.metalBtn, goldPhysicalMode === m && s.metalBtnActive]} onPress={() => setGoldPhysicalMode(m)}><Text style={[s.metalBtnText, goldPhysicalMode === m && s.metalBtnTextActive]}>{m}</Text></TouchableOpacity>))}</View>
              {goldPhysicalMode === 'manual' ? (
                <><Text style={s.formLabel}>Physical Rate Rs/g</Text><TextInput style={s.formInput} value={goldPhysical} onChangeText={setGoldPhysical} keyboardType="decimal-pad" placeholder="7450" placeholderTextColor={Colors.textMuted} /></>
              ) : (
                <><Text style={s.formLabel}>Premium over MCX (Rs)</Text><TextInput style={s.formInput} value={goldPremium} onChangeText={setGoldPremium} keyboardType="decimal-pad" placeholder="70" placeholderTextColor={Colors.textMuted} /></>
              )}
              <Text style={s.formLabel}>Movement</Text>
              <View style={s.formRow}>{['up', 'down', 'stable'].map(m => (<TouchableOpacity key={m} style={[s.metalBtn, goldMov === m && s.metalBtnActive]} onPress={() => setGoldMov(m)}><Text style={[s.metalBtnText, goldMov === m && s.metalBtnTextActive]}>{m}</Text></TouchableOpacity>))}</View>
              <Text style={s.formLabel}>Market Summary</Text>
              <TextInput style={s.formInput} value={marketSummary} onChangeText={setMarketSummary} placeholder="e.g., Silver up 1.2% today" placeholderTextColor={Colors.textMuted} />
              <TouchableOpacity testID="panel-update-rates" style={s.saveBtn} onPress={updateRates}><Text style={s.saveBtnText}>UPDATE RATES</Text></TouchableOpacity>
            </View>
          )}

          {/* ===== PRODUCTS ===== */}
          {tab === 'products' && (
            <>
              <Text style={s.sectionTitle}>ALL PRODUCTS ({products.length})</Text>
              {products.map(p => (
                <View key={p.id} style={s.listItem}>
                  <View style={{ flex: 1 }}>
                    <Text style={s.listTitle}>{p.title}</Text>
                    <Text style={s.listMeta}>{p.metal_type} • {p.category} • {p.visibility}</Text>
                  </View>
                  <TouchableOpacity onPress={() => { api.delete(`/products/${p.id}`).then(() => loadTab('products')); }}><Ionicons name="trash-outline" size={16} color={Colors.error} /></TouchableOpacity>
                </View>
              ))}
            </>
          )}

          {/* ===== BATCHES ===== */}
          {tab === 'batches' && (
            <>
              <View style={s.formRow}>
                <TouchableOpacity testID="panel-new-batch" style={[s.saveBtn, { flex: 1 }]} onPress={() => setShowBatchForm(!showBatchForm)}>
                  <Text style={s.saveBtnText}>{showBatchForm ? 'CANCEL' : 'NEW BATCH'}</Text>
                </TouchableOpacity>
              </View>
              {showBatchForm && (
                <View style={s.formCard}>
                  <TextInput style={s.formInput} placeholder="Batch Name *" placeholderTextColor={Colors.textMuted} value={newBatchName} onChangeText={setNewBatchName} />
                  <View style={s.formRow}>{['silver', 'gold', 'diamond'].map(m => (<TouchableOpacity key={m} style={[s.metalBtn, newBatchMetal === m && s.metalBtnActive]} onPress={() => setNewBatchMetal(m)}><Text style={[s.metalBtnText, newBatchMetal === m && s.metalBtnTextActive]}>{m}</Text></TouchableOpacity>))}</View>
                  <TextInput style={s.formInput} placeholder="Category (optional)" placeholderTextColor={Colors.textMuted} value={newBatchCat} onChangeText={setNewBatchCat} />
                  <TouchableOpacity style={s.saveBtn} onPress={createBatch}><Text style={s.saveBtnText}>CREATE</Text></TouchableOpacity>
                </View>
              )}

              {/* Upload section */}
              {uploadBatchId !== '' && (
                <View style={[s.formCard, { borderColor: Colors.borderGold }]}>
                  <View style={s.formRow}>
                    <Text style={[s.formTitle, { flex: 1 }]}>Upload to: {batches.find(b => b.id === uploadBatchId)?.name}</Text>
                    <TouchableOpacity onPress={() => { setUploadBatchId(''); setSelectedFiles([]); }}><Ionicons name="close" size={20} color={Colors.textMuted} /></TouchableOpacity>
                  </View>
                  <TouchableOpacity style={s.pickBtn} onPress={pickFiles}>
                    <Ionicons name="cloud-upload" size={24} color={Colors.gold} />
                    <Text style={{ color: Colors.text, marginTop: 4 }}>Select images</Text>
                  </TouchableOpacity>
                  {selectedFiles.length > 0 && <Text style={{ color: Colors.gold, marginTop: 8 }}>{selectedFiles.length} files selected</Text>}
                  {uploading && <View style={s.progressBar}><View style={[s.progressFill, { width: `${(uploadProgress.done / Math.max(uploadProgress.total, 1)) * 100}%` }]} /></View>}
                  {selectedFiles.length > 0 && !uploading && (
                    <TouchableOpacity style={s.saveBtn} onPress={startUpload}><Text style={s.saveBtnText}>UPLOAD {selectedFiles.length} IMAGES</Text></TouchableOpacity>
                  )}
                </View>
              )}

              <Text style={s.sectionTitle}>ALL BATCHES ({batches.length})</Text>
              {batches.map(b => (
                <View key={b.id} style={s.batchCard}>
                  <View style={{ flex: 1 }}>
                    <Text style={s.listTitle}>{b.name}</Text>
                    <Text style={s.listMeta}>{b.metal_type} {b.category ? `• ${b.category}` : ''} • {b.image_count} images</Text>
                  </View>
                  <View style={[s.badge, { backgroundColor: b.status === 'visible' ? Colors.success + '20' : Colors.warning + '20' }]}>
                    <Text style={[s.badgeText, { color: b.status === 'visible' ? Colors.success : Colors.warning }]}>{b.status}</Text>
                  </View>
                  <View style={s.batchActions}>
                    <TouchableOpacity style={[s.miniBtn, { backgroundColor: Colors.gold + '20' }]} onPress={() => { setUploadBatchId(b.id); setSelectedFiles([]); }}>
                      <Ionicons name="cloud-upload" size={14} color={Colors.gold} />
                    </TouchableOpacity>
                    <TouchableOpacity style={[s.miniBtn, { backgroundColor: b.status === 'visible' ? Colors.warning + '20' : Colors.success + '20' }]} onPress={() => toggleBatchVisibility(b.id)}>
                      <Ionicons name={b.status === 'visible' ? 'eye-off' : 'eye'} size={14} color={b.status === 'visible' ? Colors.warning : Colors.success} />
                    </TouchableOpacity>
                    <TouchableOpacity style={[s.miniBtn, { backgroundColor: Colors.error + '20' }]} onPress={() => deleteBatch(b.id, b.name)}>
                      <Ionicons name="trash" size={14} color={Colors.error} />
                    </TouchableOpacity>
                  </View>
                </View>
              ))}
            </>
          )}

          {/* ===== CUSTOMERS ===== */}
          {tab === 'customers' && (
            <>
              <Text style={s.sectionTitle}>ALL CUSTOMERS ({customers.length})</Text>
              {customers.map(c => (
                <View key={c.id} style={s.listItem}>
                  <View style={{ flex: 1 }}>
                    <Text style={s.listTitle}>{c.name || c.phone}</Text>
                    <Text style={s.listMeta}>{c.customer_type} • {c.city || 'No city'} • {c.customer_code} • {c.reward_points} pts</Text>
                  </View>
                  <View style={s.contactRow}>
                    <TouchableOpacity onPress={() => openWhatsApp(c.phone)}><Ionicons name="logo-whatsapp" size={18} color="#25D366" /></TouchableOpacity>
                    <TouchableOpacity onPress={() => openCall(c.phone)}><Ionicons name="call" size={18} color={Colors.success} /></TouchableOpacity>
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

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  // Login
  loginBox: { flex: 1, justifyContent: 'center', alignItems: 'center', paddingHorizontal: Spacing.xl },
  loginTitle: { fontSize: FontSize.xl, fontWeight: '700', color: Colors.text, marginTop: Spacing.md },
  loginSub: { fontSize: FontSize.sm, color: Colors.textSecondary, marginBottom: Spacing.xl },
  loginInput: { width: '100%', maxWidth: 320, backgroundColor: Colors.surface, borderRadius: 12, paddingHorizontal: Spacing.md, paddingVertical: 14, fontSize: FontSize.lg, color: Colors.text, borderWidth: 1, borderColor: Colors.border, marginBottom: Spacing.md, textAlign: 'center' },
  loginBtn: { width: '100%', maxWidth: 320, backgroundColor: Colors.gold, borderRadius: 12, paddingVertical: 14, alignItems: 'center' },
  loginBtnText: { fontSize: FontSize.base, fontWeight: '700', color: '#000', letterSpacing: 2 },
  loginLink: { color: Colors.gold, fontSize: FontSize.sm, marginTop: Spacing.md },
  loginError: { color: Colors.error, fontSize: FontSize.sm, marginTop: Spacing.md, textAlign: 'center' },
  loginHint: { fontSize: FontSize.xs, color: Colors.textMuted, marginTop: Spacing.lg },
  // Header
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: Spacing.lg, paddingVertical: Spacing.md, borderBottomWidth: 1, borderBottomColor: Colors.border },
  headerTitle: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.gold },
  headerRight: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  headerUser: { fontSize: FontSize.sm, color: Colors.textSecondary },
  roleBadge: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 4 },
  roleText: { fontSize: 9, fontWeight: '700', letterSpacing: 1 },
  logoutBtn: { padding: 6 },
  // Tabs
  tabBar: { paddingHorizontal: Spacing.lg, gap: 6, paddingVertical: Spacing.sm, borderBottomWidth: 1, borderBottomColor: Colors.border },
  tabItem: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 20, backgroundColor: Colors.surface },
  tabActive: { backgroundColor: Colors.gold + '20' },
  tabLabel: { fontSize: FontSize.sm, color: Colors.textMuted, fontWeight: '500' },
  tabLabelActive: { color: Colors.gold, fontWeight: '600' },
  content: { paddingHorizontal: Spacing.lg, paddingTop: Spacing.md },
  // Stats
  statsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  statCard: { width: '30%', minWidth: 100, backgroundColor: Colors.card, borderRadius: 14, padding: Spacing.md, alignItems: 'center', gap: 4, borderWidth: 1, borderColor: Colors.cardBorder },
  statVal: { fontSize: FontSize.xl, fontWeight: '700', color: Colors.text },
  statLbl: { fontSize: FontSize.xs, color: Colors.textMuted },
  // Common
  sectionTitle: { fontSize: FontSize.xs, color: Colors.textSecondary, letterSpacing: 2, fontWeight: '700', marginTop: Spacing.lg, marginBottom: Spacing.md },
  listItem: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: Colors.border },
  listTitle: { fontSize: FontSize.md, color: Colors.text, fontWeight: '600', textTransform: 'capitalize' },
  listMeta: { fontSize: FontSize.xs, color: Colors.textMuted, marginTop: 2, textTransform: 'capitalize' },
  badge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6 },
  badgeText: { fontSize: FontSize.xs, fontWeight: '600', textTransform: 'capitalize' },
  emptyText: { fontSize: FontSize.md, color: Colors.textMuted, textAlign: 'center', marginTop: 40 },
  // Requests
  filterSection: { marginBottom: Spacing.sm },
  filterLabel: { fontSize: FontSize.xs, color: Colors.textMuted, fontWeight: '600', marginBottom: 4 },
  filterRow: { gap: 6 },
  chip: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 16, backgroundColor: Colors.surface, borderWidth: 1, borderColor: Colors.border },
  chipActive: { backgroundColor: Colors.gold + '15', borderColor: Colors.gold },
  chipText: { fontSize: FontSize.xs, color: Colors.textMuted, fontWeight: '500', textTransform: 'capitalize' },
  chipTextActive: { color: Colors.gold },
  reqCard: { backgroundColor: Colors.card, borderRadius: 14, marginBottom: Spacing.md, overflow: 'hidden', borderWidth: 1, borderColor: Colors.cardBorder, padding: Spacing.md },
  reqTop: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  reqIcon: { width: 36, height: 36, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  reqType: { fontSize: FontSize.md, fontWeight: '600', color: Colors.text, textTransform: 'capitalize' },
  reqTime: { fontSize: FontSize.xs, color: Colors.textMuted },
  reqInfo: { marginTop: Spacing.sm, gap: 4 },
  infoRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  infoText: { fontSize: FontSize.sm, color: Colors.textSecondary },
  contactRow: { flexDirection: 'row', gap: 8, marginTop: Spacing.sm },
  contactBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8 },
  contactBtnText: { fontSize: FontSize.sm, fontWeight: '600' },
  noteInput: { backgroundColor: Colors.surface, borderRadius: 10, padding: 12, fontSize: FontSize.sm, color: Colors.text, borderWidth: 1, borderColor: Colors.border, minHeight: 50, marginTop: Spacing.sm, textAlignVertical: 'top' },
  actionsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: Spacing.sm },
  actBtn: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8 },
  actText: { fontSize: FontSize.xs, fontWeight: '600' },
  // Forms
  formCard: { backgroundColor: Colors.card, borderRadius: 16, padding: Spacing.lg, marginBottom: Spacing.md, borderWidth: 1, borderColor: Colors.cardBorder },
  formTitle: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.text, marginBottom: Spacing.md },
  formLabel: { fontSize: FontSize.xs, color: Colors.textSecondary, fontWeight: '600', letterSpacing: 1, marginBottom: 4, marginTop: Spacing.sm },
  formInput: { backgroundColor: Colors.surface, borderRadius: 10, paddingHorizontal: Spacing.md, paddingVertical: 12, fontSize: FontSize.md, color: Colors.text, borderWidth: 1, borderColor: Colors.border, marginBottom: 4 },
  formRow: { flexDirection: 'row', gap: 8, marginBottom: Spacing.sm },
  metalBtn: { flex: 1, alignItems: 'center', paddingVertical: 10, borderRadius: 8, backgroundColor: Colors.surface, borderWidth: 1, borderColor: Colors.border },
  metalBtnActive: { backgroundColor: Colors.gold + '20', borderColor: Colors.gold },
  metalBtnText: { fontSize: FontSize.sm, color: Colors.textMuted, fontWeight: '500', textTransform: 'capitalize' },
  metalBtnTextActive: { color: Colors.gold },
  saveBtn: { backgroundColor: Colors.gold, paddingVertical: 14, borderRadius: 10, alignItems: 'center', marginTop: Spacing.sm },
  saveBtnText: { fontSize: FontSize.sm, fontWeight: '700', color: '#000', letterSpacing: 2 },
  // Batches
  batchCard: { flexDirection: 'row', alignItems: 'center', backgroundColor: Colors.card, borderRadius: 14, padding: Spacing.md, marginBottom: Spacing.sm, borderWidth: 1, borderColor: Colors.cardBorder, flexWrap: 'wrap', gap: 8 },
  batchActions: { flexDirection: 'row', gap: 6 },
  miniBtn: { width: 34, height: 34, borderRadius: 8, alignItems: 'center', justifyContent: 'center' },
  pickBtn: { alignItems: 'center', paddingVertical: Spacing.lg, borderRadius: 12, borderWidth: 2, borderStyle: 'dashed', borderColor: Colors.gold + '40' },
  progressBar: { height: 6, borderRadius: 3, backgroundColor: Colors.surface, overflow: 'hidden', marginTop: 8 },
  progressFill: { height: '100%', backgroundColor: Colors.gold, borderRadius: 3 },
});
