import React, { useEffect, useState, useCallback, useRef } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, TextInput, ActivityIndicator, Alert, Image, Platform, Linking } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../src/theme';
import { api, setToken, getImageUrl, cancelUpload, getLastUploadId, clearLastUploadId } from '../src/api';
import { useKeepAwake } from 'expo-keep-awake';

type PanelTab = 'dashboard' | 'requests' | 'rates' | 'products' | 'customers' | 'rewards' | 'content';
type ProductSubView = 'menu' | 'list' | 'add' | 'bulk' | 'batches' | 'batch_upload' | 'pdf_import';
type ContentSubView = 'menu' | 'about' | 'ratelist' | 'schemes' | 'brands' | 'showroom' | 'exhibitions' | 'liverates';
type Role = 'admin' | 'executive' | null;

const CANONICAL_STATUSES = ['pending', 'in_progress', 'contacted', 'resolved', 'no_response'];

export default function PanelScreen() {
  // Keep screen awake during any upload
  const [keepAwake, setKeepAwake] = useState(false);
  useKeepAwake('upload-active', { isEnabled: keepAwake });
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
  const [productSubView, setProductSubView] = useState<ProductSubView>('menu');
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

  // Content management
  const [contentSubView, setContentSubView] = useState<ContentSubView>('menu');
  const [contentData, setContentData] = useState<any[]>([]);
  const [contentForm, setContentForm] = useState<Record<string, string>>({});

  // Upload
  const [uploadBatchId, setUploadBatchId] = useState('');
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState({ done: 0, total: 0 });

  // PDF Import (Chunked)
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [pdfImporting, setPdfImporting] = useState(false);
  const [pdfResult, setPdfResult] = useState<any>(null);
  const [pdfPhase, setPdfPhase] = useState('');
  const [pdfProgress, setPdfProgress] = useState(0);
  const [pdfStage, setPdfStage] = useState<'idle' | 'validating' | 'uploading' | 'processing' | 'done' | 'error'>('idle');

  // Request detail
  const [editingReqId, setEditingReqId] = useState('');
  const [noteText, setNoteText] = useState('');

  // Add product form
  const [newProdTitle, setNewProdTitle] = useState('');
  const [newProdMetal, setNewProdMetal] = useState('silver');
  const [newProdCat, setNewProdCat] = useState('');
  const [newProdWeight, setNewProdWeight] = useState('');
  const [newProdPurity, setNewProdPurity] = useState('');
  const [newProdTouch, setNewProdTouch] = useState('');
  const [newProdLabel, setNewProdLabel] = useState('');
  const [newProdImageUrl, setNewProdImageUrl] = useState('');

  // Billing / Reward wallet
  const [custSearch, setCustSearch] = useState('');
  const [custResults, setCustResults] = useState<any[]>([]);
  const [selectedCust, setSelectedCust] = useState<any>(null);
  const [custTxns, setCustTxns] = useState<any[]>([]);
  const [custTotalEarned, setCustTotalEarned] = useState(0);
  const [custTotalDeducted, setCustTotalDeducted] = useState(0);
  const [rewardPoints, setRewardPoints] = useState('');
  const [rewardReason, setRewardReason] = useState('');
  const [rewardAction, setRewardAction] = useState<'credit' | 'debit'>('credit');
  const REASON_TYPES = ['Purchase reward', 'Special reward', 'Adjustment', 'Redemption', 'Correction'];

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
      if (u.role !== 'admin' && u.role !== 'executive' && u.role !== 'billing_executive') {
        setAuthError('Access denied. This panel is for admin and executive users only.');
        setToken(null);
        return;
      }
      setToken(res.token);
      setUser(u);
      setRole(u.role);
      setTab(u.role === 'billing_executive' ? 'rewards' : u.role === 'executive' ? 'requests' : 'dashboard');
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
        case 'products': {
          const [prodRes, batchRes] = await Promise.all([
            api.get('/products?limit=50&include_hidden=true'),
            api.get('/batches'),
          ]);
          setProducts(prodRes.products || []);
          setBatches(batchRes.batches || []);
          break;
        }
        case 'customers': { const r = await api.get('/customers?limit=100'); setCustomers(r.customers || []); break; }
      }
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [statusFilter, typeFilter]);

  useEffect(() => { if (role) { setProductSubView('menu'); loadTab(tab); } }, [tab, role]);
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
      const batch = await api.post('/batches', { name: newBatchName, metal_type: newBatchMetal, category: newBatchCat });
      setNewBatchName(''); setNewBatchCat(''); setShowBatchForm(false);
      setUploadBatchId(batch.id);
      setProductSubView('batch_upload');
      loadTab('products');
    } catch (e: any) { Alert.alert('Error', e.message); }
  };

  const addProduct = async () => {
    if (!newProdTitle.trim()) { Alert.alert('Error', 'Enter product title'); return; }
    try {
      await api.post('/products', { title: newProdTitle, metal_type: newProdMetal, category: newProdCat, approx_weight: newProdWeight, purity: newProdPurity, selling_touch: newProdTouch, selling_label: newProdLabel, images: newProdImageUrl ? [newProdImageUrl] : [] });
      Alert.alert('Success', 'Product added');
      setNewProdTitle(''); setNewProdCat(''); setNewProdWeight(''); setNewProdPurity(''); setNewProdTouch(''); setNewProdLabel(''); setNewProdImageUrl('');
      setProductSubView('list');
      loadTab('products');
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

  const pickPdfFile = () => {
    if (Platform.OS === 'web') {
      const input = document.createElement('input');
      input.type = 'file'; input.accept = '.pdf,application/pdf'; input.multiple = false;
      input.onchange = (e: any) => {
        const f = e.target.files?.[0] as File | undefined;
        if (f) { setPdfFile(f); setPdfResult(null); }
      };
      input.click();
    }
  };

  const startPdfImport = async (resumeUploadId?: string) => {
    if (!uploadBatchId || !pdfFile) return;
    setPdfImporting(true); setPdfResult(null); setPdfPhase(''); setPdfProgress(0); setPdfStage('idle');
    setKeepAwake(true);
    try {
      const result = await api.importPdfChunked(uploadBatchId, pdfFile, (stage, detail, progress) => {
        setPdfStage(stage);
        setPdfPhase(detail);
        if (progress !== undefined) setPdfProgress(progress);
      }, resumeUploadId || null);
      setPdfResult(result);
      setPdfFile(null); setPdfPhase(''); setPdfStage('done');
      clearLastUploadId();
      Alert.alert('PDF Import Complete', `${result.imported} pages converted to product images out of ${result.total_pages} total pages.`);
      loadTab('products');
    } catch (e: any) {
      const resumeId = getLastUploadId();
      setPdfResult({ error: e.message, resumeUploadId: resumeId });
      setPdfPhase(''); setPdfStage('error');
    }
    finally { setPdfImporting(false); setKeepAwake(false); }
  };

  const cancelPdfImport = () => {
    Alert.alert('Cancel Import?', 'Upload will stop. You can resume later from where it stopped.', [
      { text: 'Keep Uploading', style: 'cancel' },
      { text: 'Cancel Upload', style: 'destructive', onPress: () => { cancelUpload(); } },
    ]);
  };

  const startUpload = async () => {
    if (!uploadBatchId || !selectedFiles.length) return;
    setUploading(true); setUploadProgress({ done: 0, total: selectedFiles.length });
    setKeepAwake(true);
    try {
      await api.uploadFiles(`/batches/${uploadBatchId}/upload`, selectedFiles, (d, t) => setUploadProgress({ done: d, total: t }));
      setSelectedFiles([]); setUploadBatchId('');
      Alert.alert('Success', 'Images uploaded');
      loadTab('batches');
    } catch (e: any) { Alert.alert('Error', e.message); }
    finally { setUploading(false); setKeepAwake(false); }
  };

  const cancelImageUpload = () => {
    Alert.alert('Cancel Upload?', 'Image upload will stop.', [
      { text: 'Keep Uploading', style: 'cancel' },
      { text: 'Cancel', style: 'destructive', onPress: () => { cancelUpload(); } },
    ]);
  };

  const openWhatsApp = (phoneNum: string) => { Linking.openURL(`https://wa.me/91${phoneNum}`); };
  const openCall = (phoneNum: string) => { Linking.openURL(`tel:+91${phoneNum}`); };

  // Billing functions
  const searchCustomers = async (q: string) => {
    setCustSearch(q);
    if (q.length < 2) { setCustResults([]); return; }
    try {
      const res = await api.get(`/customers/search?q=${encodeURIComponent(q)}`);
      setCustResults(res.customers || []);
    } catch {}
  };

  const openCustomerWallet = async (cust: any) => {
    setSelectedCust(cust);
    try {
      const res = await api.get(`/rewards/customer/${cust.id}`);
      setCustTxns(res.transactions || []);
      setCustTotalEarned(res.total_earned || 0);
      setCustTotalDeducted(res.total_deducted || 0);
      setSelectedCust(res.customer || cust);
    } catch {}
  };

  const submitRewardAction = async () => {
    if (!selectedCust || !rewardPoints || parseInt(rewardPoints) <= 0) { Alert.alert('Error', 'Enter valid points'); return; }
    try {
      const endpoint = rewardAction === 'credit' ? '/rewards/credit' : '/rewards/deduct';
      const res = await api.post(endpoint, { user_id: selectedCust.id, points: parseInt(rewardPoints), reason: rewardReason || rewardAction });
      Alert.alert('Success', `${rewardAction === 'credit' ? 'Credited' : 'Deducted'} ${rewardPoints} points. New balance: ${res.new_balance}`);
      setRewardPoints(''); setRewardReason('');
      openCustomerWallet(selectedCust);
    } catch (e: any) { Alert.alert('Error', e.message); }
  };

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
    { key: 'content', label: 'Content', icon: 'document-text' },
    { key: 'customers', label: 'Customers', icon: 'people' },
  ];
  const EXEC_TABS: { key: PanelTab; label: string; icon: string }[] = [
    { key: 'requests', label: 'Requests', icon: 'call' },
  ];
  const BILLING_TABS: { key: PanelTab; label: string; icon: string }[] = [
    { key: 'rewards', label: 'Reward Wallet', icon: 'wallet' },
  ];
  const tabs = role === 'admin' ? ADMIN_TABS : role === 'billing_executive' ? BILLING_TABS : EXEC_TABS;

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
                    {r.preferred_time ? <View style={s.infoRow}><Ionicons name="time" size={14} color={Colors.textMuted} /><Text style={s.infoText}>{r.preferred_time}</Text></View> : null}
                    {r.notes ? <View style={s.infoRow}><Ionicons name="document-text" size={14} color={Colors.textMuted} /><Text style={s.infoText}>{r.notes}</Text></View> : null}
                    {r.admin_notes ? <View style={[s.infoRow, { backgroundColor: Colors.gold + '08', padding: 6, borderRadius: 6 }]}><Ionicons name="chatbox" size={14} color={Colors.gold} /><Text style={[s.infoText, { color: Colors.gold }]}>{r.admin_notes}</Text></View> : null}
                  </View>

                  {/* Linked Products */}
                  {r.linked_products?.length > 0 && (
                    <View style={{ paddingHorizontal: 0, marginTop: 8, gap: 6 }}>
                      <Text style={{ fontSize: FontSize.xs, color: Colors.textSecondary, fontWeight: '600', letterSpacing: 1 }}>SELECTED PRODUCTS</Text>
                      {r.linked_products.map((lp: any) => (
                        <View key={lp.id} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: Colors.surface, borderRadius: 8, padding: 6 }}>
                          <Image source={{ uri: getImageUrl(lp, true) }} style={{ width: 40, height: 40, borderRadius: 6, backgroundColor: Colors.card }} />
                          <View style={{ flex: 1 }}>
                            <Text style={{ fontSize: FontSize.sm, color: Colors.text, fontWeight: '500' }} numberOfLines={1}>{lp.title}</Text>
                            <Text style={{ fontSize: FontSize.xs, color: Colors.textMuted, textTransform: 'capitalize' }}>{lp.metal_type} {lp.category ? `• ${lp.category}` : ''}{lp.purity ? ` • ${lp.purity}` : ''}</Text>
                          </View>
                        </View>
                      ))}
                    </View>
                  )}
                  {r.cart_items?.length > 0 && (
                    <View style={{ marginTop: 8, gap: 4 }}>
                      <Text style={{ fontSize: FontSize.xs, color: Colors.textSecondary, fontWeight: '600', letterSpacing: 1 }}>CART ITEMS ({r.cart_count})</Text>
                      {r.cart_items.map((ci: any, idx: number) => (
                        <Text key={idx} style={{ fontSize: FontSize.sm, color: Colors.text }}>{ci.title || ci.product_id} — {ci.metal_type} • Qty: {ci.quantity}</Text>
                      ))}
                    </View>
                  )}

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

          {/* ===== PRODUCTS MANAGEMENT (unified with sub-navigation) ===== */}
          {tab === 'products' && (
            <>
              {/* Sub-navigation back bar */}
              {productSubView !== 'menu' && (
                <TouchableOpacity testID="products-back" style={s.subBackBar} onPress={() => setProductSubView('menu')}>
                  <Ionicons name="arrow-back" size={18} color={Colors.gold} />
                  <Text style={s.subBackText}>Back to Product Management</Text>
                </TouchableOpacity>
              )}

              {/* MENU — main product management home */}
              {productSubView === 'menu' && (
                <>
                  <Text style={s.sectionTitle}>PRODUCT MANAGEMENT</Text>
                  <View style={s.menuGrid}>
                    <TouchableOpacity testID="pm-add" style={s.menuCard} onPress={() => setProductSubView('add')}>
                      <View style={[s.menuCardIcon, { backgroundColor: Colors.success + '15' }]}><Ionicons name="add-circle" size={28} color={Colors.success} /></View>
                      <Text style={s.menuCardTitle}>Add Product</Text>
                      <Text style={s.menuCardHint}>Add single product with details</Text>
                    </TouchableOpacity>
                    <TouchableOpacity testID="pm-bulk" style={s.menuCard} onPress={() => { setProductSubView('batches'); loadTab('products'); }}>
                      <View style={[s.menuCardIcon, { backgroundColor: Colors.gold + '15' }]}><Ionicons name="cloud-upload" size={28} color={Colors.gold} /></View>
                      <Text style={s.menuCardTitle}>Upload Images</Text>
                      <Text style={s.menuCardHint}>Upload photos from device</Text>
                    </TouchableOpacity>
                    <TouchableOpacity testID="pm-pdf" style={s.menuCard} onPress={() => { setProductSubView('pdf_import'); loadTab('products'); }}>
                      <View style={[s.menuCardIcon, { backgroundColor: '#E91E63' + '15' }]}><Ionicons name="document-text" size={28} color="#E91E63" /></View>
                      <Text style={s.menuCardTitle}>Import PDF</Text>
                      <Text style={s.menuCardHint}>Import PDF catalogue as products</Text>
                    </TouchableOpacity>
                    <TouchableOpacity testID="pm-list" style={s.menuCard} onPress={() => { setProductSubView('list'); loadTab('products'); }}>
                      <View style={[s.menuCardIcon, { backgroundColor: Colors.info + '15' }]}><Ionicons name="grid" size={28} color={Colors.info} /></View>
                      <Text style={s.menuCardTitle}>View All Products</Text>
                      <Text style={s.menuCardHint}>{products.length} products in catalog</Text>
                    </TouchableOpacity>
                    <TouchableOpacity testID="pm-batches" style={s.menuCard} onPress={() => { setProductSubView('batches'); loadTab('products'); }}>
                      <View style={[s.menuCardIcon, { backgroundColor: '#A855F715' }]}><Ionicons name="folder" size={28} color="#A855F7" /></View>
                      <Text style={s.menuCardTitle}>Manage Batches</Text>
                      <Text style={s.menuCardHint}>{batches.length} batches • Hide/Show/Delete</Text>
                    </TouchableOpacity>
                  </View>
                </>
              )}

              {/* ADD SINGLE PRODUCT */}
              {productSubView === 'add' && (
                <View style={s.formCard}>
                  <Text style={s.formTitle}>Add New Product</Text>
                  <TextInput style={s.formInput} placeholder="Product Title *" placeholderTextColor={Colors.textMuted} value={newProdTitle} onChangeText={setNewProdTitle} />
                  <Text style={s.formLabel}>Metal Type</Text>
                  <View style={s.formRow}>{['silver', 'gold', 'diamond'].map(m => (<TouchableOpacity key={m} style={[s.metalBtn, newProdMetal === m && s.metalBtnActive]} onPress={() => setNewProdMetal(m)}><Text style={[s.metalBtnText, newProdMetal === m && s.metalBtnTextActive]}>{m}</Text></TouchableOpacity>))}</View>
                  <TextInput style={s.formInput} placeholder="Category (e.g. payal, chain)" placeholderTextColor={Colors.textMuted} value={newProdCat} onChangeText={setNewProdCat} />
                  <TextInput style={s.formInput} placeholder="Approx Weight (e.g. 45-55 grams)" placeholderTextColor={Colors.textMuted} value={newProdWeight} onChangeText={setNewProdWeight} />
                  <TextInput style={s.formInput} placeholder="Purity (e.g. 92.5)" placeholderTextColor={Colors.textMuted} value={newProdPurity} onChangeText={setNewProdPurity} />
                  <TextInput style={s.formInput} placeholder="Selling Touch (e.g. Premium, Daily Wear)" placeholderTextColor={Colors.textMuted} value={newProdTouch} onChangeText={setNewProdTouch} />
                  <TextInput style={s.formInput} placeholder="Selling Label (e.g. Best Seller, New Arrival)" placeholderTextColor={Colors.textMuted} value={newProdLabel} onChangeText={setNewProdLabel} />
                  <TextInput style={s.formInput} placeholder="Image URL (optional)" placeholderTextColor={Colors.textMuted} value={newProdImageUrl} onChangeText={setNewProdImageUrl} />
                  <TouchableOpacity style={s.saveBtn} onPress={addProduct}><Text style={s.saveBtnText}>SAVE PRODUCT</Text></TouchableOpacity>
                </View>
              )}

              {/* VIEW ALL PRODUCTS */}
              {productSubView === 'list' && (
                <>
                  <Text style={s.sectionTitle}>ALL PRODUCTS ({products.length})</Text>
                  {products.map(p => (
                    <View key={p.id} style={s.listItem}>
                      <View style={{ flex: 1 }}>
                        <Text style={s.listTitle}>{p.title}</Text>
                        <Text style={s.listMeta}>{p.metal_type} • {p.category} • {p.visibility}{p.purity ? ` • Purity: ${p.purity}` : ''}</Text>
                      </View>
                      <TouchableOpacity onPress={() => { api.delete(`/products/${p.id}`).then(() => loadTab('products')); }}><Ionicons name="trash-outline" size={16} color={Colors.error} /></TouchableOpacity>
                    </View>
                  ))}
                  {products.length === 0 && <Text style={s.emptyText}>No products yet</Text>}
                </>
              )}

              {/* PDF IMPORT — standalone view */}
              {productSubView === 'pdf_import' && (
                <>
                  <Text style={s.sectionTitle}>IMPORT PDF CATALOGUE</Text>
                  <View style={[s.formCard, { borderColor: '#E91E63' + '30' }]}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: Spacing.md }}>
                      <View style={{ width: 44, height: 44, borderRadius: 12, backgroundColor: '#E91E63' + '15', alignItems: 'center', justifyContent: 'center' }}>
                        <Ionicons name="document-text" size={24} color="#E91E63" />
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={s.formTitle}>PDF to Product Images</Text>
                        <Text style={{ color: Colors.textSecondary, fontSize: FontSize.xs }}>Each PDF page becomes a separate product image</Text>
                      </View>
                    </View>

                    {/* Step 1: Select or create batch */}
                    <Text style={[s.formLabel, { marginTop: 0 }]}>STEP 1: Select Batch</Text>
                    {batches.length > 0 ? (
                      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: Spacing.md }}>
                        <View style={{ flexDirection: 'row', gap: 8 }}>
                          {batches.map(b => (
                            <TouchableOpacity key={b.id} style={[s.chip, uploadBatchId === b.id && { backgroundColor: '#E91E63' + '20', borderColor: '#E91E63' }]} onPress={() => setUploadBatchId(b.id)}>
                              <Text style={[s.chipText, uploadBatchId === b.id && { color: '#E91E63' }]}>{b.name} ({b.image_count})</Text>
                            </TouchableOpacity>
                          ))}
                        </View>
                      </ScrollView>
                    ) : null}
                    {!uploadBatchId && (
                      <View style={{ marginBottom: Spacing.md }}>
                        <Text style={{ color: Colors.textMuted, fontSize: FontSize.sm, marginBottom: Spacing.sm }}>Or create a new batch:</Text>
                        <View style={s.formRow}>
                          <TextInput style={[s.formInput, { flex: 1, marginBottom: 0 }]} placeholder="New batch name" placeholderTextColor={Colors.textMuted} value={newBatchName} onChangeText={setNewBatchName} />
                          <TouchableOpacity style={[s.saveBtn, { flex: 0, paddingHorizontal: Spacing.lg, marginTop: 0 }]} onPress={async () => {
                            if (!newBatchName.trim()) return;
                            try {
                              const batch = await api.post('/batches', { name: newBatchName, metal_type: newBatchMetal, category: '' });
                              setUploadBatchId(batch.id);
                              setNewBatchName('');
                              loadTab('products');
                            } catch (e: any) { Alert.alert('Error', e.message); }
                          }}><Text style={s.saveBtnText}>CREATE</Text></TouchableOpacity>
                        </View>
                      </View>
                    )}
                    {uploadBatchId && <Text style={{ color: '#E91E63', fontWeight: '600', fontSize: FontSize.sm, marginBottom: Spacing.sm }}>Batch: {batches.find(b => b.id === uploadBatchId)?.name || uploadBatchId.slice(0, 8)}</Text>}

                    {/* Step 2: Select PDF */}
                    <Text style={s.formLabel}>STEP 2: Select PDF File</Text>
                    <TouchableOpacity testID="pdf-pick-btn" style={[s.pickBtn, { borderColor: '#E91E63' + '40' }]} onPress={pickPdfFile}>
                      <Ionicons name="document-text" size={40} color="#E91E63" />
                      <Text style={{ color: Colors.text, marginTop: 8, fontSize: FontSize.md, fontWeight: '700' }}>Tap to select PDF from device</Text>
                      <Text style={{ color: Colors.textMuted, fontSize: FontSize.xs, marginTop: 4 }}>PDF files only — Max 1000MB (1 GB)</Text>
                      <Text style={{ color: Colors.textMuted, fontSize: FontSize.xs }}>Each page will be extracted as a product image</Text>
                      <Text style={{ color: '#E91E63', fontSize: FontSize.xs, marginTop: 4, fontWeight: '600' }}>Chunked upload — reliable for large files</Text>
                    </TouchableOpacity>

                    {/* PDF file selected */}
                    {pdfFile && (
                      <View style={{ marginTop: Spacing.md, backgroundColor: '#E91E63' + '10', borderRadius: 12, padding: Spacing.md, borderWidth: 1, borderColor: '#E91E63' + '30' }}>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                          <Ionicons name="document-text" size={28} color="#E91E63" />
                          <View style={{ flex: 1 }}>
                            <Text style={{ color: Colors.text, fontWeight: '700', fontSize: FontSize.md }} data-testid="pdf-filename">{pdfFile.name}</Text>
                            <Text style={{ color: Colors.textSecondary, fontSize: FontSize.sm }} data-testid="pdf-filesize">{(pdfFile.size / (1024 * 1024)).toFixed(1)} MB ({Math.ceil(pdfFile.size / (5 * 1024 * 1024))} chunks)</Text>
                          </View>
                          <TouchableOpacity onPress={() => { setPdfFile(null); setPdfResult(null); setPdfStage('idle'); }} data-testid="pdf-clear-btn">
                            <Ionicons name="close-circle" size={24} color={Colors.error} />
                          </TouchableOpacity>
                        </View>
                        {pdfFile.size > 1000 * 1024 * 1024 && (
                          <Text style={{ color: Colors.error, fontSize: FontSize.sm, marginTop: 8, fontWeight: '600' }}>File exceeds 1000MB limit. Please select a smaller PDF.</Text>
                        )}
                      </View>
                    )}

                    {/* Importing progress — enhanced with progress bar */}
                    {pdfImporting && (
                      <View style={{ marginTop: Spacing.lg, paddingVertical: Spacing.lg, backgroundColor: '#1a1a2e', borderRadius: 12, padding: Spacing.lg, borderWidth: 1, borderColor: '#E91E63' + '30' }}>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: Spacing.md }}>
                          <ActivityIndicator color="#E91E63" size="small" />
                          <Text style={{ color: Colors.text, fontSize: FontSize.md, fontWeight: '700', flex: 1 }} data-testid="pdf-import-status">
                            {pdfStage === 'uploading' ? 'Uploading PDF...' : pdfStage === 'processing' ? 'Processing Pages...' : pdfStage === 'validating' ? 'Validating...' : 'Working...'}
                          </Text>
                          <Text style={{ color: '#E91E63', fontWeight: '700', fontSize: FontSize.lg }}>{pdfProgress}%</Text>
                          {/* CANCEL BUTTON */}
                          <TouchableOpacity data-testid="pdf-cancel-btn" onPress={cancelPdfImport} style={{ width: 36, height: 36, borderRadius: 18, backgroundColor: Colors.error + '20', alignItems: 'center', justifyContent: 'center' }}>
                            <Ionicons name="close" size={20} color={Colors.error} />
                          </TouchableOpacity>
                        </View>

                        {/* Progress bar */}
                        <View style={{ height: 8, backgroundColor: '#333', borderRadius: 4, overflow: 'hidden', marginBottom: Spacing.sm }}>
                          <View style={{ height: '100%', backgroundColor: '#E91E63', borderRadius: 4, width: `${Math.min(pdfProgress, 100)}%` }} />
                        </View>

                        {pdfPhase ? <Text style={{ color: '#E91E63', fontSize: FontSize.sm, marginTop: 4 }} data-testid="pdf-phase-detail">{pdfPhase}</Text> : null}

                        <View style={{ marginTop: Spacing.md, backgroundColor: '#ffffff10', borderRadius: 8, padding: Spacing.sm }}>
                          <Text style={{ color: Colors.textMuted, fontSize: FontSize.xs }}>
                            {pdfStage === 'uploading' ? 'File is being uploaded in 5MB chunks with auto-retry (5 attempts each).' : ''}
                            {pdfStage === 'processing' ? 'Server is extracting pages and creating product images.' : ''}
                          </Text>
                          <Text style={{ color: '#4CAF50', fontSize: FontSize.xs, marginTop: 2 }}>Screen will stay awake during upload. If interrupted, you can resume.</Text>
                        </View>
                      </View>
                    )}

                    {/* Import result */}
                    {pdfResult && !pdfResult.error && (
                      <View style={{ marginTop: Spacing.md, backgroundColor: Colors.success + '10', borderRadius: 12, padding: Spacing.md, borderWidth: 1, borderColor: Colors.success + '30' }}>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: Spacing.sm }}>
                          <Ionicons name="checkmark-circle" size={24} color={Colors.success} />
                          <Text style={{ color: Colors.success, fontWeight: '700', fontSize: FontSize.lg }} data-testid="pdf-import-complete">PDF Import Complete!</Text>
                        </View>
                        <Text style={{ color: Colors.text, fontSize: FontSize.md }}>Total pages in PDF: {pdfResult.total_pages}</Text>
                        <Text style={{ color: Colors.success, fontSize: FontSize.md, fontWeight: '600' }}>Successfully imported: {pdfResult.imported} pages</Text>
                        {pdfResult.failed > 0 && <Text style={{ color: Colors.error, fontSize: FontSize.md }}>Failed pages: {pdfResult.failed}</Text>}
                        {pdfResult.skipped > 0 && <Text style={{ color: '#FFA500', fontSize: FontSize.md }}>Skipped (empty): {pdfResult.skipped}</Text>}
                        <Text style={{ color: Colors.textMuted, fontSize: FontSize.xs, marginTop: Spacing.sm }}>Each imported page is now a separate product entry in your batch.</Text>
                        {pdfResult.file_size > 0 && <Text style={{ color: Colors.textMuted, fontSize: FontSize.xs }}>File size: {(pdfResult.file_size / (1024 * 1024)).toFixed(1)}MB</Text>}
                        {pdfResult.results?.filter((r: any) => r.status !== 'ok').length > 0 && (
                          <View style={{ marginTop: Spacing.sm }}>
                            <Text style={{ color: Colors.textMuted, fontSize: FontSize.xs, fontWeight: '600' }}>Page details:</Text>
                            {pdfResult.results.filter((r: any) => r.status !== 'ok').map((r: any, i: number) => (
                              <Text key={i} style={{ color: Colors.textMuted, fontSize: FontSize.xs }}>Page {r.page}: {r.status} — {r.detail || ''}</Text>
                            ))}
                          </View>
                        )}
                      </View>
                    )}
                    {pdfResult?.error && (
                      <View style={{ marginTop: Spacing.md, backgroundColor: Colors.error + '10', borderRadius: 12, padding: Spacing.md, borderWidth: 1, borderColor: Colors.error + '30' }}>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                          <Ionicons name="alert-circle" size={24} color={Colors.error} />
                          <Text style={{ color: Colors.error, fontWeight: '700', fontSize: FontSize.md }}>Import Failed</Text>
                        </View>
                        <Text style={{ color: Colors.error, fontSize: FontSize.sm }} data-testid="pdf-error-detail">{pdfResult.error}</Text>
                        <View style={{ flexDirection: 'row', gap: 10, marginTop: Spacing.md }}>
                          <TouchableOpacity onPress={() => { setPdfResult(null); setPdfStage('idle'); setPdfProgress(0); }} style={{ backgroundColor: Colors.error + '20', paddingVertical: 8, paddingHorizontal: 16, borderRadius: 8 }}>
                            <Text style={{ color: Colors.error, fontWeight: '600', fontSize: FontSize.sm }}>Dismiss</Text>
                          </TouchableOpacity>
                          {pdfFile && pdfResult.resumeUploadId && (
                            <TouchableOpacity data-testid="pdf-resume-btn" onPress={() => { startPdfImport(pdfResult.resumeUploadId); }} style={{ backgroundColor: '#E91E63' + '20', paddingVertical: 8, paddingHorizontal: 16, borderRadius: 8 }}>
                              <Text style={{ color: '#E91E63', fontWeight: '600', fontSize: FontSize.sm }}>Resume Upload</Text>
                            </TouchableOpacity>
                          )}
                        </View>
                      </View>
                    )}

                    {/* Step 3: Import button */}
                    {pdfFile && uploadBatchId && !pdfImporting && (
                      <TouchableOpacity testID="pdf-import-btn" style={[s.saveBtn, { marginTop: Spacing.lg, backgroundColor: '#E91E63' }]} onPress={startPdfImport}>
                        <Text style={[s.saveBtnText, { letterSpacing: 2 }]}>IMPORT PDF CATALOGUE</Text>
                      </TouchableOpacity>
                    )}
                    {pdfFile && !uploadBatchId && (
                      <Text style={{ color: Colors.warning, fontSize: FontSize.sm, textAlign: 'center', marginTop: Spacing.md }}>Please select or create a batch first</Text>
                    )}
                  </View>
                </>
              )}


              {/* BATCHES + BULK UPLOAD */}
              {(productSubView === 'batches' || productSubView === 'batch_upload') && (
                <>
                  {/* Create new batch */}
                  <TouchableOpacity style={[s.saveBtn, { marginBottom: Spacing.md }]} onPress={() => setShowBatchForm(!showBatchForm)}>
                    <Text style={s.saveBtnText}>{showBatchForm ? 'CANCEL' : 'CREATE NEW BATCH'}</Text>
                  </TouchableOpacity>
                  {showBatchForm && (
                    <View style={s.formCard}>
                      <Text style={s.formTitle}>New Batch / Folder</Text>
                      <Text style={[s.formLabel, { marginTop: 0 }]}>Give your batch a name like "New Payal Lot" or "Silver Articles Feb"</Text>
                      <TextInput style={s.formInput} placeholder="Batch Name *" placeholderTextColor={Colors.textMuted} value={newBatchName} onChangeText={setNewBatchName} />
                      <Text style={s.formLabel}>Metal Type</Text>
                      <View style={s.formRow}>{['silver', 'gold', 'diamond'].map(m => (<TouchableOpacity key={m} style={[s.metalBtn, newBatchMetal === m && s.metalBtnActive]} onPress={() => setNewBatchMetal(m)}><Text style={[s.metalBtnText, newBatchMetal === m && s.metalBtnTextActive]}>{m}</Text></TouchableOpacity>))}</View>
                      <TextInput style={s.formInput} placeholder="Category (optional)" placeholderTextColor={Colors.textMuted} value={newBatchCat} onChangeText={setNewBatchCat} />
                      <TouchableOpacity style={s.saveBtn} onPress={createBatch}><Text style={s.saveBtnText}>CREATE & START UPLOADING</Text></TouchableOpacity>
                    </View>
                  )}

                  {/* Active upload section */}
                  {uploadBatchId !== '' && (
                    <View style={[s.formCard, { borderColor: Colors.borderGold }]}>
                      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                        <Text style={s.formTitle}>Upload Images</Text>
                        <TouchableOpacity onPress={() => { setUploadBatchId(''); setSelectedFiles([]); }}><Ionicons name="close" size={20} color={Colors.textMuted} /></TouchableOpacity>
                      </View>
                      <Text style={{ color: Colors.textSecondary, fontSize: FontSize.sm, marginBottom: Spacing.md }}>Uploading to: {batches.find(b => b.id === uploadBatchId)?.name}</Text>
                      <TouchableOpacity style={s.pickBtn} onPress={pickFiles}>
                        <Ionicons name="cloud-upload" size={32} color={Colors.gold} />
                        <Text style={{ color: Colors.text, marginTop: 8, fontSize: FontSize.md, fontWeight: '600' }}>Tap to select images from device</Text>
                        <Text style={{ color: Colors.textMuted, fontSize: FontSize.xs, marginTop: 4 }}>JPG, PNG, WebP — Max 20MB each — Select as many as you want</Text>
                      </TouchableOpacity>
                      {selectedFiles.length > 0 && (
                        <View style={{ marginTop: Spacing.md }}>
                          <Text style={{ color: Colors.gold, fontWeight: '600' }}>{selectedFiles.length} files selected</Text>
                          <TouchableOpacity style={{ marginTop: 4 }} onPress={pickFiles}><Text style={{ color: Colors.info, fontSize: FontSize.sm }}>+ Add more files</Text></TouchableOpacity>
                        </View>
                      )}
                      {uploading && (
                        <View style={{ marginTop: Spacing.md }}>
                          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                            <ActivityIndicator color={Colors.gold} size="small" />
                            <Text style={{ color: Colors.text, fontWeight: '600', flex: 1 }}>Uploading...</Text>
                            <TouchableOpacity data-testid="image-upload-cancel-btn" onPress={cancelImageUpload} style={{ width: 32, height: 32, borderRadius: 16, backgroundColor: Colors.error + '20', alignItems: 'center', justifyContent: 'center' }}>
                              <Ionicons name="close" size={16} color={Colors.error} />
                            </TouchableOpacity>
                          </View>
                          <View style={s.progressBar}><View style={[s.progressFill, { width: `${(uploadProgress.done / Math.max(uploadProgress.total, 1)) * 100}%` }]} /></View>
                          <Text style={{ color: Colors.textSecondary, fontSize: FontSize.sm, textAlign: 'center', marginTop: 4 }}>{uploadProgress.done} / {uploadProgress.total} files uploaded</Text>
                          <Text style={{ color: '#4CAF50', fontSize: FontSize.xs, textAlign: 'center', marginTop: 2 }}>Screen stays awake during upload</Text>
                        </View>
                      )}
                      {selectedFiles.length > 0 && !uploading && (
                        <TouchableOpacity style={[s.saveBtn, { marginTop: Spacing.md }]} onPress={startUpload}><Text style={s.saveBtnText}>UPLOAD {selectedFiles.length} IMAGES</Text></TouchableOpacity>
                      )}

                      {/* PDF Import Section */}
                      <View style={{ marginTop: Spacing.lg, borderTopWidth: 1, borderTopColor: Colors.border, paddingTop: Spacing.lg }}>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: Spacing.sm }}>
                          <Ionicons name="document-text" size={20} color="#E91E63" />
                          <Text style={{ fontSize: FontSize.md, fontWeight: '700', color: Colors.text }}>Import PDF Catalogue</Text>
                        </View>
                        <Text style={{ color: Colors.textSecondary, fontSize: FontSize.xs, marginBottom: Spacing.md }}>Upload a PDF file — each page will be extracted as a separate product image</Text>
                        <TouchableOpacity style={[s.pickBtn, { borderColor: '#E91E63' + '40' }]} onPress={pickPdfFile}>
                          <Ionicons name="document-text" size={32} color="#E91E63" />
                          <Text style={{ color: Colors.text, marginTop: 8, fontSize: FontSize.md, fontWeight: '600' }}>Tap to select PDF file</Text>
                          <Text style={{ color: Colors.textMuted, fontSize: FontSize.xs, marginTop: 4 }}>PDF only — Max 300MB — Pages become product images</Text>
                        </TouchableOpacity>
                        {pdfFile && (
                          <View style={{ marginTop: Spacing.md, backgroundColor: Colors.surface, borderRadius: 10, padding: Spacing.md }}>
                            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                              <Ionicons name="document-text" size={24} color="#E91E63" />
                              <View style={{ flex: 1 }}>
                                <Text style={{ color: Colors.text, fontWeight: '600', fontSize: FontSize.sm }}>{pdfFile.name}</Text>
                                <Text style={{ color: Colors.textMuted, fontSize: FontSize.xs }}>{(pdfFile.size / (1024 * 1024)).toFixed(1)} MB</Text>
                              </View>
                              <TouchableOpacity onPress={() => setPdfFile(null)}><Ionicons name="close-circle" size={20} color={Colors.error} /></TouchableOpacity>
                            </View>
                          </View>
                        )}
                        {pdfImporting && (
                          <View style={{ marginTop: Spacing.md, alignItems: 'center' }}>
                            <ActivityIndicator color="#E91E63" size="large" />
                            <Text style={{ color: Colors.textSecondary, fontSize: FontSize.sm, marginTop: Spacing.sm }}>Extracting pages from PDF...</Text>
                            <Text style={{ color: Colors.textMuted, fontSize: FontSize.xs }}>Each page is being converted to a product image</Text>
                          </View>
                        )}
                        {pdfResult && !pdfResult.error && (
                          <View style={{ marginTop: Spacing.md, backgroundColor: Colors.success + '10', borderRadius: 10, padding: Spacing.md }}>
                            <Text style={{ color: Colors.success, fontWeight: '700', fontSize: FontSize.md }}>PDF Import Complete</Text>
                            <Text style={{ color: Colors.text, fontSize: FontSize.sm, marginTop: 4 }}>Total pages: {pdfResult.total_pages}</Text>
                            <Text style={{ color: Colors.success, fontSize: FontSize.sm }}>Imported: {pdfResult.imported} pages</Text>
                            {pdfResult.failed > 0 && <Text style={{ color: Colors.error, fontSize: FontSize.sm }}>Failed: {pdfResult.failed} pages</Text>}
                            {pdfResult.skipped > 0 && <Text style={{ color: Colors.warning, fontSize: FontSize.sm }}>Skipped: {pdfResult.skipped} pages (empty/too small)</Text>}
                            {pdfResult.results?.filter((r: any) => r.status !== 'ok').map((r: any, i: number) => (
                              <Text key={i} style={{ color: Colors.textMuted, fontSize: FontSize.xs, marginTop: 2 }}>Page {r.page}: {r.status} — {r.detail || ''}</Text>
                            ))}
                          </View>
                        )}
                        {pdfResult?.error && (
                          <View style={{ marginTop: Spacing.md, backgroundColor: Colors.error + '10', borderRadius: 10, padding: Spacing.md }}>
                            <Text style={{ color: Colors.error, fontWeight: '600' }}>Import Failed: {pdfResult.error}</Text>
                          </View>
                        )}
                        {pdfFile && !pdfImporting && (
                          <TouchableOpacity style={[s.saveBtn, { marginTop: Spacing.md, backgroundColor: '#E91E63' }]} onPress={startPdfImport}>
                            <Text style={s.saveBtnText}>IMPORT PDF CATALOGUE</Text>
                          </TouchableOpacity>
                        )}
                      </View>
                    </View>
                  )}

                  {/* Batch list */}
                  <Text style={s.sectionTitle}>ALL BATCHES ({batches.length})</Text>
                  {batches.length === 0 && <Text style={s.emptyText}>No batches yet. Create one above to start uploading.</Text>}
                  {batches.map(b => (
                    <View key={b.id} style={s.batchCard}>
                      <View style={{ flex: 1 }}>
                        <Text style={s.listTitle}>{b.name}</Text>
                        <Text style={s.listMeta}>{b.metal_type} {b.category ? `• ${b.category}` : ''} • {b.image_count} images • {new Date(b.created_at).toLocaleDateString()}</Text>
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
            </>
          )}

          {/* ===== REWARD WALLET (Billing Executive) ===== */}
          {tab === 'rewards' && (
            <>
              {/* Customer Search */}
              {!selectedCust ? (
                <>
                  <Text style={s.sectionTitle}>SEARCH CUSTOMER</Text>
                  <TextInput testID="billing-search" style={s.formInput} placeholder="Search by name, phone, city, code..." placeholderTextColor={Colors.textMuted} value={custSearch} onChangeText={searchCustomers} />
                  {custResults.map(c => (
                    <TouchableOpacity key={c.id} style={s.listItem} onPress={() => openCustomerWallet(c)}>
                      <View style={{ flex: 1 }}>
                        <Text style={s.listTitle}>{c.name || c.phone}</Text>
                        <Text style={s.listMeta}>{c.phone} • {c.city || 'No city'} • {c.customer_code} • {c.reward_points || 0} pts</Text>
                      </View>
                      <Ionicons name="chevron-forward" size={18} color={Colors.textMuted} />
                    </TouchableOpacity>
                  ))}
                  {custSearch.length >= 2 && custResults.length === 0 && <Text style={s.emptyText}>No customers found</Text>}
                </>
              ) : (
                <>
                  {/* Back to search */}
                  <TouchableOpacity style={s.subBackBar} onPress={() => { setSelectedCust(null); setCustTxns([]); setCustSearch(''); setCustResults([]); }}>
                    <Ionicons name="arrow-back" size={18} color={Colors.gold} />
                    <Text style={s.subBackText}>Back to Customer Search</Text>
                  </TouchableOpacity>

                  {/* Customer wallet card */}
                  <View style={[s.formCard, { borderColor: Colors.borderGold }]}>
                    <Text style={{ fontSize: FontSize.lg, fontWeight: '700', color: Colors.text }}>{selectedCust.name || selectedCust.phone}</Text>
                    <Text style={{ fontSize: FontSize.sm, color: Colors.textSecondary, marginTop: 2 }}>{selectedCust.phone} • {selectedCust.city} • {selectedCust.customer_code}</Text>
                    <View style={{ flexDirection: 'row', gap: 16, marginTop: Spacing.md }}>
                      <View style={{ flex: 1, alignItems: 'center', backgroundColor: Colors.gold + '10', padding: Spacing.md, borderRadius: 12 }}>
                        <Text style={{ fontSize: FontSize.xxl, fontWeight: '700', color: Colors.gold }}>{selectedCust.reward_points || 0}</Text>
                        <Text style={{ fontSize: FontSize.xs, color: Colors.textMuted }}>Current Balance</Text>
                      </View>
                      <View style={{ flex: 1, alignItems: 'center', backgroundColor: Colors.success + '10', padding: Spacing.md, borderRadius: 12 }}>
                        <Text style={{ fontSize: FontSize.lg, fontWeight: '700', color: Colors.success }}>{custTotalEarned}</Text>
                        <Text style={{ fontSize: FontSize.xs, color: Colors.textMuted }}>Total Earned</Text>
                      </View>
                      <View style={{ flex: 1, alignItems: 'center', backgroundColor: Colors.error + '10', padding: Spacing.md, borderRadius: 12 }}>
                        <Text style={{ fontSize: FontSize.lg, fontWeight: '700', color: Colors.error }}>{custTotalDeducted}</Text>
                        <Text style={{ fontSize: FontSize.xs, color: Colors.textMuted }}>Total Used</Text>
                      </View>
                    </View>
                  </View>

                  {/* Add/Deduct Points */}
                  <View style={s.formCard}>
                    <Text style={s.formTitle}>Manage Points</Text>
                    <View style={s.formRow}>
                      <TouchableOpacity style={[s.metalBtn, rewardAction === 'credit' && { backgroundColor: Colors.success + '20', borderColor: Colors.success }]} onPress={() => setRewardAction('credit')}>
                        <Text style={[s.metalBtnText, rewardAction === 'credit' && { color: Colors.success }]}>Add Points</Text>
                      </TouchableOpacity>
                      <TouchableOpacity style={[s.metalBtn, rewardAction === 'debit' && { backgroundColor: Colors.error + '20', borderColor: Colors.error }]} onPress={() => setRewardAction('debit')}>
                        <Text style={[s.metalBtnText, rewardAction === 'debit' && { color: Colors.error }]}>Deduct Points</Text>
                      </TouchableOpacity>
                    </View>
                    <TextInput style={s.formInput} placeholder="Points *" placeholderTextColor={Colors.textMuted} value={rewardPoints} onChangeText={setRewardPoints} keyboardType="number-pad" />
                    <Text style={s.formLabel}>Reason</Text>
                    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: Spacing.sm }}>
                      {REASON_TYPES.map(r => (
                        <TouchableOpacity key={r} style={[s.chip, rewardReason === r && s.chipActive]} onPress={() => setRewardReason(r)}>
                          <Text style={[s.chipText, rewardReason === r && s.chipTextActive]}>{r}</Text>
                        </TouchableOpacity>
                      ))}
                    </View>
                    <TextInput style={s.formInput} placeholder="Custom remark (optional)" placeholderTextColor={Colors.textMuted} value={rewardReason} onChangeText={setRewardReason} />
                    <TouchableOpacity style={[s.saveBtn, rewardAction === 'debit' && { backgroundColor: Colors.error }]} onPress={submitRewardAction}>
                      <Text style={s.saveBtnText}>{rewardAction === 'credit' ? 'ADD POINTS' : 'DEDUCT POINTS'}</Text>
                    </TouchableOpacity>
                  </View>

                  {/* Transaction History */}
                  <Text style={s.sectionTitle}>REWARD HISTORY ({custTxns.length})</Text>
                  {custTxns.map(t => (
                    <View key={t.id} style={s.listItem}>
                      <View style={{ flex: 1 }}>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                          <Ionicons name={t.type === 'credit' ? 'add-circle' : 'remove-circle'} size={16} color={t.type === 'credit' ? Colors.success : Colors.error} />
                          <Text style={[s.listTitle, { color: t.type === 'credit' ? Colors.success : Colors.error }]}>{t.type === 'credit' ? '+' : '-'}{t.points} pts</Text>
                        </View>
                        <Text style={s.listMeta}>{t.reason}{t.performed_by ? ` • by ${t.performed_by}` : ''}</Text>
                        <Text style={{ fontSize: FontSize.xs, color: Colors.textMuted }}>{new Date(t.created_at).toLocaleString()}</Text>
                      </View>
                    </View>
                  ))}
                  {custTxns.length === 0 && <Text style={s.emptyText}>No reward history yet</Text>}
                </>
              )}
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

          {/* ===== CONTENT MANAGEMENT ===== */}
          {tab === 'content' && (
            <>
              {contentSubView !== 'menu' && (
                <TouchableOpacity style={s.subBackBar} onPress={() => setContentSubView('menu')}>
                  <Ionicons name="arrow-back" size={18} color={Colors.gold} />
                  <Text style={s.subBackText}>Back to Content Management</Text>
                </TouchableOpacity>
              )}
              {contentSubView === 'menu' && (
                <>
                  <Text style={s.sectionTitle}>CONTENT MANAGEMENT</Text>
                  <View style={s.menuGrid}>
                    {[
                      { key: 'about', label: 'About Page', hint: 'Edit about content, benefits, locations', icon: 'information-circle', color: Colors.info },
                      { key: 'ratelist', label: 'Rate List', hint: 'Manage quantity-based rate slabs', icon: 'list', color: '#E91E63' },
                      { key: 'schemes', label: 'Schemes', hint: 'Upload scheme posters & details', icon: 'ribbon', color: '#FF9800' },
                      { key: 'brands', label: 'Brands', hint: 'Manage brand logos', icon: 'star', color: '#9C27B0' },
                      { key: 'showroom', label: 'Showroom', hint: 'Floor-wise photos & descriptions', icon: 'images', color: '#00BCD4' },
                      { key: 'exhibitions', label: 'Exhibitions', hint: 'Upcoming & past exhibitions', icon: 'calendar', color: '#795548' },
                      { key: 'liverates', label: 'Live Rates Config', hint: 'Premium & auto-fetch settings', icon: 'pulse', color: Colors.success },
                    ].map(item => (
                      <TouchableOpacity key={item.key} style={s.menuCard} onPress={async () => {
                        setContentSubView(item.key as ContentSubView);
                        setLoading(true);
                        try {
                          if (item.key === 'about') { const r = await api.get('/about'); setContentData(r.raw || []); }
                          else if (item.key === 'ratelist') { const r = await api.get('/rate-list'); setContentData(r.slabs || []); }
                          else if (item.key === 'schemes') { const r = await api.get('/schemes?active_only=false'); setContentData(r.schemes || []); }
                          else if (item.key === 'brands') { const r = await api.get('/brands?active_only=false'); setContentData(r.brands || []); }
                          else if (item.key === 'showroom') { const r = await api.get('/showroom'); setContentData(r.floors || []); }
                          else if (item.key === 'exhibitions') { const r = await api.get('/exhibitions'); setContentData(r.all || []); }
                          else if (item.key === 'liverates') { const r = await api.get('/live-rates/config'); setContentForm(r); }
                        } catch {}
                        setLoading(false);
                      }}>
                        <View style={[s.menuCardIcon, { backgroundColor: item.color + '15' }]}><Ionicons name={item.icon as any} size={28} color={item.color} /></View>
                        <Text style={s.menuCardTitle}>{item.label}</Text>
                        <Text style={s.menuCardHint}>{item.hint}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                </>
              )}

              {/* About Content Editor */}
              {contentSubView === 'about' && (
                <>
                  <Text style={s.sectionTitle}>ABOUT PAGE CONTENT</Text>
                  {contentData.map(item => (
                    <View key={item.section} style={s.formCard}>
                      <Text style={s.formTitle}>{item.section.replace(/_/g, ' ').toUpperCase()}</Text>
                      <Text style={s.formLabel}>English</Text>
                      <TextInput style={[s.formInput, { minHeight: 60 }]} value={item.content_en} onChangeText={v => setContentData(prev => prev.map(x => x.section === item.section ? { ...x, content_en: v } : x))} multiline placeholder="English content" placeholderTextColor={Colors.textMuted} />
                      <Text style={s.formLabel}>Hindi</Text>
                      <TextInput style={[s.formInput, { minHeight: 60 }]} value={item.content_hi} onChangeText={v => setContentData(prev => prev.map(x => x.section === item.section ? { ...x, content_hi: v } : x))} multiline placeholder="Hindi content" placeholderTextColor={Colors.textMuted} />
                      <Text style={s.formLabel}>Punjabi</Text>
                      <TextInput style={[s.formInput, { minHeight: 60 }]} value={item.content_pa} onChangeText={v => setContentData(prev => prev.map(x => x.section === item.section ? { ...x, content_pa: v } : x))} multiline placeholder="Punjabi content" placeholderTextColor={Colors.textMuted} />
                      <TouchableOpacity style={s.saveBtn} onPress={async () => {
                        try { await api.post('/about', { section: item.section, content_en: item.content_en, content_hi: item.content_hi, content_pa: item.content_pa }); Alert.alert('Saved', `${item.section} updated`); } catch (e: any) { Alert.alert('Error', e.message); }
                      }}><Text style={s.saveBtnText}>SAVE</Text></TouchableOpacity>
                    </View>
                  ))}
                </>
              )}

              {/* Rate List Editor */}
              {contentSubView === 'ratelist' && (
                <>
                  <Text style={s.sectionTitle}>SILVER RATE LIST - ITEM WISE ({contentData.length})</Text>
                  {contentData.map(slab => (
                    <View key={slab.id} style={s.listItem}>
                      <View style={{ flex: 1 }}>
                        <Text style={s.listTitle}>{slab.item_name || slab.slab_name || 'Item'}</Text>
                        <Text style={s.listMeta}>{slab.metal_type} • {slab.category}{slab.subcategory ? ` / ${slab.subcategory}` : ''} • Purity: {slab.purity || '-'} • Wastage: {slab.wastage || '-'} • Labour: {slab.labour_kg || '-'}</Text>
                      </View>
                      <TouchableOpacity onPress={async () => { await api.delete(`/rate-list/${slab.id}`); setContentData(prev => prev.filter(x => x.id !== slab.id)); }}><Ionicons name="trash-outline" size={16} color={Colors.error} /></TouchableOpacity>
                    </View>
                  ))}
                  <View style={s.formCard}>
                    <Text style={s.formTitle}>Add Rate List Entry</Text>
                    <Text style={s.formLabel}>Metal</Text>
                    <View style={s.formRow}>{['silver','gold','diamond'].map(m => (<TouchableOpacity key={m} style={[s.metalBtn, contentForm.metal_type === m && s.metalBtnActive]} onPress={() => setContentForm(p => ({...p, metal_type: m}))}><Text style={[s.metalBtnText, contentForm.metal_type === m && s.metalBtnTextActive]}>{m}</Text></TouchableOpacity>))}</View>
                    <TextInput style={s.formInput} placeholder="Item Name (e.g. Silver Payal)" placeholderTextColor={Colors.textMuted} value={contentForm.item_name || ''} onChangeText={v => setContentForm(p => ({...p, item_name: v}))} />
                    <View style={s.formRow}>
                      <TextInput style={[s.formInput, {flex:1}]} placeholder="Category" placeholderTextColor={Colors.textMuted} value={contentForm.category || ''} onChangeText={v => setContentForm(p => ({...p, category: v}))} />
                      <TextInput style={[s.formInput, {flex:1}]} placeholder="Subcategory" placeholderTextColor={Colors.textMuted} value={contentForm.subcategory || ''} onChangeText={v => setContentForm(p => ({...p, subcategory: v}))} />
                    </View>
                    <TextInput style={s.formInput} placeholder="Purity (e.g. 92.5%)" placeholderTextColor={Colors.textMuted} value={contentForm.purity || ''} onChangeText={v => setContentForm(p => ({...p, purity: v}))} />
                    <TextInput style={s.formInput} placeholder="Wastage (e.g. 3%)" placeholderTextColor={Colors.textMuted} value={contentForm.wastage || ''} onChangeText={v => setContentForm(p => ({...p, wastage: v}))} />
                    <TextInput style={s.formInput} placeholder="Labour in KG (e.g. ₹850/kg)" placeholderTextColor={Colors.textMuted} value={contentForm.labour_kg || ''} onChangeText={v => setContentForm(p => ({...p, labour_kg: v}))} />
                    <TouchableOpacity style={s.saveBtn} onPress={async () => {
                      try {
                        const res = await api.post('/rate-list', { metal_type: contentForm.metal_type || 'silver', item_name: contentForm.item_name || '', category: contentForm.category || '', subcategory: contentForm.subcategory || '', purity: contentForm.purity || '', wastage: contentForm.wastage || '', labour_kg: contentForm.labour_kg || '', order: contentData.length + 1 });
                        setContentData(prev => [...prev, res]); setContentForm({}); Alert.alert('Added');
                      } catch (e: any) { Alert.alert('Error', e.message); }
                    }}><Text style={s.saveBtnText}>ADD ENTRY</Text></TouchableOpacity>
                  </View>
                </>
              )}

              {/* Schemes Editor */}
              {contentSubView === 'schemes' && (
                <>
                  <Text style={s.sectionTitle}>SCHEMES ({contentData.length})</Text>
                  {contentData.map(sc => (
                    <View key={sc.id} style={s.listItem}>
                      <View style={{ flex: 1 }}>
                        <Text style={s.listTitle}>{sc.title}</Text>
                        <Text style={s.listMeta}>{sc.is_active ? 'Active' : 'Inactive'}{sc.poster_url ? ' • Has poster' : ''}</Text>
                      </View>
                      <TouchableOpacity onPress={async () => { await api.delete(`/schemes/${sc.id}`); setContentData(prev => prev.filter(x => x.id !== sc.id)); }}><Ionicons name="trash-outline" size={16} color={Colors.error} /></TouchableOpacity>
                    </View>
                  ))}
                  <View style={s.formCard}>
                    <Text style={s.formTitle}>Add Scheme</Text>
                    <TextInput style={s.formInput} placeholder="Scheme Title" placeholderTextColor={Colors.textMuted} value={contentForm.title || ''} onChangeText={v => setContentForm(p => ({...p, title: v}))} />
                    <TextInput style={s.formInput} placeholder="Description" placeholderTextColor={Colors.textMuted} value={contentForm.description || ''} onChangeText={v => setContentForm(p => ({...p, description: v}))} multiline />
                    <TextInput style={s.formInput} placeholder="Poster Image URL" placeholderTextColor={Colors.textMuted} value={contentForm.poster_url || ''} onChangeText={v => setContentForm(p => ({...p, poster_url: v}))} />
                    <TouchableOpacity style={s.saveBtn} onPress={async () => {
                      try {
                        const res = await api.post('/schemes', { title: contentForm.title || '', description: contentForm.description || '', poster_url: contentForm.poster_url || '', is_active: true, order: contentData.length });
                        setContentData(prev => [...prev, res]); setContentForm({}); Alert.alert('Added');
                      } catch (e: any) { Alert.alert('Error', e.message); }
                    }}><Text style={s.saveBtnText}>ADD SCHEME</Text></TouchableOpacity>
                  </View>
                </>
              )}

              {/* Brands Editor */}
              {contentSubView === 'brands' && (
                <>
                  <Text style={s.sectionTitle}>BRANDS ({contentData.length})</Text>
                  {contentData.map(br => (
                    <View key={br.id} style={s.listItem}>
                      <View style={{ flex: 1 }}><Text style={s.listTitle}>{br.name}</Text><Text style={s.listMeta}>{br.is_active ? 'Active' : 'Inactive'}</Text></View>
                      <TouchableOpacity onPress={async () => { await api.delete(`/brands/${br.id}`); setContentData(prev => prev.filter(x => x.id !== br.id)); }}><Ionicons name="trash-outline" size={16} color={Colors.error} /></TouchableOpacity>
                    </View>
                  ))}
                  <View style={s.formCard}>
                    <Text style={s.formTitle}>Add Brand</Text>
                    <TextInput style={s.formInput} placeholder="Brand Name" placeholderTextColor={Colors.textMuted} value={contentForm.name || ''} onChangeText={v => setContentForm(p => ({...p, name: v}))} />
                    <TextInput style={s.formInput} placeholder="Logo URL" placeholderTextColor={Colors.textMuted} value={contentForm.logo_url || ''} onChangeText={v => setContentForm(p => ({...p, logo_url: v}))} />
                    <TextInput style={s.formInput} placeholder="Description" placeholderTextColor={Colors.textMuted} value={contentForm.desc || ''} onChangeText={v => setContentForm(p => ({...p, desc: v}))} />
                    <TouchableOpacity style={s.saveBtn} onPress={async () => {
                      try {
                        const res = await api.post('/brands', { name: contentForm.name || '', logo_url: contentForm.logo_url || '', description: contentForm.desc || '', is_active: true, order: contentData.length });
                        setContentData(prev => [...prev, res]); setContentForm({}); Alert.alert('Added');
                      } catch (e: any) { Alert.alert('Error', e.message); }
                    }}><Text style={s.saveBtnText}>ADD BRAND</Text></TouchableOpacity>
                  </View>
                </>
              )}

              {/* Showroom Editor */}
              {contentSubView === 'showroom' && (
                <>
                  <Text style={s.sectionTitle}>SHOWROOM FLOORS ({contentData.length})</Text>
                  {contentData.map(fl => (
                    <View key={fl.id} style={s.listItem}>
                      <View style={{ flex: 1 }}><Text style={s.listTitle}>{fl.floor_name}</Text><Text style={s.listMeta}>{fl.products_available || 'No products listed'}</Text></View>
                      <TouchableOpacity onPress={async () => { await api.delete(`/showroom/${fl.id}`); setContentData(prev => prev.filter(x => x.id !== fl.id)); }}><Ionicons name="trash-outline" size={16} color={Colors.error} /></TouchableOpacity>
                    </View>
                  ))}
                  <View style={s.formCard}>
                    <Text style={s.formTitle}>Add Floor</Text>
                    <TextInput style={s.formInput} placeholder="Floor Name (e.g. Second Floor)" placeholderTextColor={Colors.textMuted} value={contentForm.floor_name || ''} onChangeText={v => setContentForm(p => ({...p, floor_name: v}))} />
                    <TextInput style={s.formInput} placeholder="Description" placeholderTextColor={Colors.textMuted} value={contentForm.description || ''} onChangeText={v => setContentForm(p => ({...p, description: v}))} multiline />
                    <TextInput style={s.formInput} placeholder="Products Available (e.g. Gold Wholesale)" placeholderTextColor={Colors.textMuted} value={contentForm.products_available || ''} onChangeText={v => setContentForm(p => ({...p, products_available: v}))} />
                    <TextInput style={s.formInput} placeholder="Photo URLs (comma separated)" placeholderTextColor={Colors.textMuted} value={contentForm.photos || ''} onChangeText={v => setContentForm(p => ({...p, photos: v}))} />
                    <TouchableOpacity style={s.saveBtn} onPress={async () => {
                      try {
                        const photos = (contentForm.photos || '').split(',').map((u: string) => u.trim()).filter(Boolean);
                        const res = await api.post('/showroom', { floor_name: contentForm.floor_name || '', description: contentForm.description || '', products_available: contentForm.products_available || '', photos, order: contentData.length });
                        setContentData(prev => [...prev, res]); setContentForm({}); Alert.alert('Added');
                      } catch (e: any) { Alert.alert('Error', e.message); }
                    }}><Text style={s.saveBtnText}>ADD FLOOR</Text></TouchableOpacity>
                  </View>
                </>
              )}

              {/* Exhibitions Editor */}
              {contentSubView === 'exhibitions' && (
                <>
                  <Text style={s.sectionTitle}>EXHIBITIONS ({contentData.length})</Text>
                  {contentData.map(ex => (
                    <View key={ex.id} style={s.listItem}>
                      <View style={{ flex: 1 }}>
                        <Text style={s.listTitle}>{ex.title}</Text>
                        <Text style={s.listMeta}>{ex.is_upcoming ? 'Upcoming' : 'Past'} • {ex.date || 'No date'}{ex.location ? ` • ${ex.location}` : ''}</Text>
                      </View>
                      <TouchableOpacity onPress={async () => { await api.delete(`/exhibitions/${ex.id}`); setContentData(prev => prev.filter(x => x.id !== ex.id)); }}><Ionicons name="trash-outline" size={16} color={Colors.error} /></TouchableOpacity>
                    </View>
                  ))}
                  <View style={s.formCard}>
                    <Text style={s.formTitle}>Add Exhibition</Text>
                    <TextInput style={s.formInput} placeholder="Exhibition Title" placeholderTextColor={Colors.textMuted} value={contentForm.title || ''} onChangeText={v => setContentForm(p => ({...p, title: v}))} />
                    <TextInput style={s.formInput} placeholder="Date (e.g. March 15-17, 2026)" placeholderTextColor={Colors.textMuted} value={contentForm.date || ''} onChangeText={v => setContentForm(p => ({...p, date: v}))} />
                    <TextInput style={s.formInput} placeholder="Location" placeholderTextColor={Colors.textMuted} value={contentForm.location || ''} onChangeText={v => setContentForm(p => ({...p, location: v}))} />
                    <TextInput style={s.formInput} placeholder="Description" placeholderTextColor={Colors.textMuted} value={contentForm.desc || ''} onChangeText={v => setContentForm(p => ({...p, desc: v}))} multiline />
                    <TextInput style={s.formInput} placeholder="Poster URL" placeholderTextColor={Colors.textMuted} value={contentForm.poster_url || ''} onChangeText={v => setContentForm(p => ({...p, poster_url: v}))} />
                    <View style={s.formRow}>
                      <TouchableOpacity style={[s.metalBtn, contentForm.is_upcoming !== 'false' && s.metalBtnActive]} onPress={() => setContentForm(p => ({...p, is_upcoming: 'true'}))}><Text style={[s.metalBtnText, contentForm.is_upcoming !== 'false' && s.metalBtnTextActive]}>Upcoming</Text></TouchableOpacity>
                      <TouchableOpacity style={[s.metalBtn, contentForm.is_upcoming === 'false' && s.metalBtnActive]} onPress={() => setContentForm(p => ({...p, is_upcoming: 'false'}))}><Text style={[s.metalBtnText, contentForm.is_upcoming === 'false' && s.metalBtnTextActive]}>Past</Text></TouchableOpacity>
                    </View>
                    <TouchableOpacity style={s.saveBtn} onPress={async () => {
                      try {
                        const res = await api.post('/exhibitions', { title: contentForm.title || '', date: contentForm.date || '', location: contentForm.location || '', description: contentForm.desc || '', poster_url: contentForm.poster_url || '', is_upcoming: contentForm.is_upcoming !== 'false', is_active: true });
                        setContentData(prev => [...prev, res]); setContentForm({}); Alert.alert('Added');
                      } catch (e: any) { Alert.alert('Error', e.message); }
                    }}><Text style={s.saveBtnText}>ADD EXHIBITION</Text></TouchableOpacity>
                  </View>
                </>
              )}

              {/* Live Rates Config */}
              {contentSubView === 'liverates' && (
                <View style={s.formCard}>
                  <Text style={s.formTitle}>Live Rate Configuration</Text>
                  <Text style={[s.formLabel, { marginTop: 0 }]}>Physical Rate = Live Market Rate + Fixed Premium</Text>
                  <Text style={s.formLabel}>Silver Premium (₹/gram)</Text>
                  <TextInput style={s.formInput} value={String(contentForm.silver_premium || 0)} onChangeText={v => setContentForm(p => ({...p, silver_premium: v}))} keyboardType="decimal-pad" placeholder="0.70" placeholderTextColor={Colors.textMuted} />
                  <Text style={s.formLabel}>Gold Premium (₹/gram)</Text>
                  <TextInput style={s.formInput} value={String(contentForm.gold_premium || 0)} onChangeText={v => setContentForm(p => ({...p, gold_premium: v}))} keyboardType="decimal-pad" placeholder="70" placeholderTextColor={Colors.textMuted} />
                  <Text style={s.formLabel}>Auto-Fetch Enabled</Text>
                  <View style={s.formRow}>
                    <TouchableOpacity style={[s.metalBtn, contentForm.auto_fetch_enabled !== false && s.metalBtnActive]} onPress={() => setContentForm(p => ({...p, auto_fetch_enabled: true as any}))}><Text style={[s.metalBtnText, contentForm.auto_fetch_enabled !== false && s.metalBtnTextActive]}>Yes</Text></TouchableOpacity>
                    <TouchableOpacity style={[s.metalBtn, contentForm.auto_fetch_enabled === false && s.metalBtnActive]} onPress={() => setContentForm(p => ({...p, auto_fetch_enabled: false as any}))}><Text style={[s.metalBtnText, contentForm.auto_fetch_enabled === false && s.metalBtnTextActive]}>No</Text></TouchableOpacity>
                  </View>
                  <Text style={s.formLabel}>Fetch Interval (seconds)</Text>
                  <TextInput style={s.formInput} value={String(contentForm.fetch_interval_seconds || 60)} onChangeText={v => setContentForm(p => ({...p, fetch_interval_seconds: v}))} keyboardType="number-pad" placeholder="60" placeholderTextColor={Colors.textMuted} />
                  <TouchableOpacity style={s.saveBtn} onPress={async () => {
                    try {
                      await api.post('/live-rates/config', { silver_premium: parseFloat(String(contentForm.silver_premium)) || 0, gold_premium: parseFloat(String(contentForm.gold_premium)) || 0, auto_fetch_enabled: contentForm.auto_fetch_enabled !== false, fetch_interval_seconds: parseInt(String(contentForm.fetch_interval_seconds)) || 60 });
                      Alert.alert('Saved', 'Live rate config updated');
                    } catch (e: any) { Alert.alert('Error', e.message); }
                  }}><Text style={s.saveBtnText}>SAVE CONFIG</Text></TouchableOpacity>
                </View>
              )}
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
  pickBtn: { alignItems: 'center', paddingVertical: Spacing.xl, borderRadius: 12, borderWidth: 2, borderStyle: 'dashed', borderColor: Colors.gold + '40', backgroundColor: Colors.gold + '05' },
  progressBar: { height: 6, borderRadius: 3, backgroundColor: Colors.surface, overflow: 'hidden', marginTop: 8 },
  progressFill: { height: '100%', backgroundColor: Colors.gold, borderRadius: 3 },
  // Sub-nav back bar
  subBackBar: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 12, marginBottom: Spacing.sm, borderBottomWidth: 1, borderBottomColor: Colors.border },
  subBackText: { fontSize: FontSize.sm, color: Colors.gold, fontWeight: '600' },
  // Menu grid
  menuGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 12 },
  menuCard: { width: '47%', backgroundColor: Colors.card, borderRadius: 16, padding: Spacing.lg, borderWidth: 1, borderColor: Colors.cardBorder },
  menuCardIcon: { width: 52, height: 52, borderRadius: 14, alignItems: 'center', justifyContent: 'center', marginBottom: Spacing.sm },
  menuCardTitle: { fontSize: FontSize.md, fontWeight: '700', color: Colors.text, marginBottom: 4 },
  menuCardHint: { fontSize: FontSize.xs, color: Colors.textMuted, lineHeight: 16 },
});
