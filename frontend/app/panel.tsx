import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, TextInput, ActivityIndicator, Image, Platform, Linking } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { activateKeepAwakeAsync, deactivateKeepAwake } from 'expo-keep-awake';
import { Colors, Spacing, FontSize } from '../src/theme';
import { api, setToken, resolveFileUrl, cancelUpload, getLastUploadId, clearLastUploadId } from '../src/api';
import { useAuth } from '../src/context/AuthContext';
import { showAlert, confirmAlert } from '../src/utils/alert';
import SmsDiagnostics from '../src/components/panel/SmsDiagnostics';
import DeletionRequests from '../src/components/staff/DeletionRequests';
import StaffPhoneChange from '../src/components/panel/StaffPhoneChange';
import AccountActions from '../src/components/panel/AccountActions';
import PhoneField from '../src/components/PhoneField';
import { KeyboardAwareScreen } from '../src/components/KeyboardScreen';
import { ROLE_LABELS, useRootBackHandler } from '../src/navigation';
import { canonicalPhone, displayPhone, telLink, DEFAULT_COUNTRY } from '../src/phone';
import type { CountryCode } from 'libphonenumber-js';
import { downloadSample } from '../src/pdfClient';

type PanelTab = 'dashboard' | 'requests' | 'rates' | 'products' | 'customers' | 'deletions' | 'rewards' | 'content' | 'executives' | 'sms' | 'review' | 'notifications' | 'reports';
type ProductSubView = 'menu' | 'list' | 'add' | 'bulk' | 'batches' | 'batch_upload' | 'pdf_import';
type ContentSubView = 'menu' | 'about' | 'ratelist' | 'schemes' | 'brands' | 'showroom' | 'exhibitions' | 'banners';
type Role = 'admin' | 'telecaller' | 'billing_executive' | 'upload_executive' | null;
/** Roles that sign in to this panel; telecallers are redirected to their own Requests home. */
const PANEL_ROLES = ['admin', 'telecaller', 'billing_executive', 'upload_executive'];
const STAFF_ROLE_OPTIONS: { key: string; label: string }[] = [
  { key: 'executive', label: 'Telecaller' },
  { key: 'billing_executive', label: 'Billing Executive' },
  { key: 'upload_executive', label: 'Upload Executive' },
];

const KEEP_AWAKE_TAG = 'yash-panel-upload';
/** First tab after sign-in: billing lands on its wallet, an Upload Executive on Products, everyone else on the dashboard. */
const defaultTabFor = (role: string): PanelTab => role === 'billing_executive' ? 'rewards' : role === 'upload_executive' ? 'products' : 'dashboard';

export default function PanelScreen() {
  // Auth
  const [role, setRole] = useState<Role>(null);
  const [user, setUser] = useState<any>(null);
  const [phone, setPhone] = useState('');
  const [panelCountry, setPanelCountry] = useState<CountryCode>(DEFAULT_COUNTRY);
  const panelCanonical = canonicalPhone(phone, panelCountry);
  const [otp, setOtp] = useState('');
  const [authStep, setAuthStep] = useState<'phone' | 'otp' | 'done'>('phone');
  const [authLoading, setAuthLoading] = useState(false);
  const [authError, setAuthError] = useState('');

  // Panel
  const [tab, setTab] = useState<PanelTab>('dashboard');
  const [productSubView, setProductSubView] = useState<ProductSubView>('menu');
  const [loading, setLoading] = useState(false);
  // Android system back on the staff root: leave a product sub-view first, then return to the role's default tab,
  // then stay on the panel (never exit, never show login) — R01-A.
  const onRootBack = useCallback(() => {
    if (productSubView !== 'menu') { setProductSubView('menu'); return true; }
    const home = defaultTabFor(role || '');
    if (tab !== home) { setTab(home); return true; }
    return true;
  }, [productSubView, tab, role]);
  useRootBackHandler(onRootBack);

  // Data
  const [dashData, setDashData] = useState<any>(null);
  const [products, setProducts] = useState<any[]>([]);
  const [batches, setBatches] = useState<any[]>([]);

  // Executives management
  const [executives, setExecutives] = useState<any[]>([]);
  const [execForm, setExecForm] = useState({ name: '', phone: '', code: '', role: 'executive' });
  const [execCountry, setExecCountry] = useState<CountryCode>(DEFAULT_COUNTRY);
  const [phoneChangeStaff, setPhoneChangeStaff] = useState<any>(null);
  const [editingExecId, setEditingExecId] = useState('');
  const [showExecForm, setShowExecForm] = useState(false);

  // Batch create
  const [newBatchName, setNewBatchName] = useState('');
  const [newBatchMetal, setNewBatchMetal] = useState('silver');
  const [newBatchCat, setNewBatchCat] = useState('');
  const [showBatchForm, setShowBatchForm] = useState(false);

  // Content management
  const [contentSubView, setContentSubView] = useState<ContentSubView>('menu');
  const [contentData, setContentData] = useState<any[]>([]);
  const [contentForm, setContentForm] = useState<Record<string, any>>({});

  // Banners
  const [editingBannerId, setEditingBannerId] = useState('');
  const [bannerUploading, setBannerUploading] = useState(false);

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
  const router = useRouter();
  const { user: appUser, loading: appAuthLoading, logout: appLogout, login: appLogin } = useAuth();

  // Unified login: reuse the app session when a staff member is already authenticated
  useEffect(() => {
    if (appAuthLoading || authStep === 'done') return;
    if (appUser) {
      if (appUser.role === 'customer') { router.replace('/(tabs)'); return; }
      if (appUser.role === 'telecaller') { router.replace('/telecaller'); return; }
      if (PANEL_ROLES.includes(appUser.role)) {
        setUser(appUser);
        setRole(appUser.role as Role);
        setTab(defaultTabFor(appUser.role));
        setAuthStep('done');
      }
    }
  }, [appUser, appAuthLoading]);

  const sendOtp = async () => {
    if (!panelCanonical) { setAuthError('Enter a valid phone number for the selected country'); return; }
    setAuthLoading(true); setAuthError('');
    try {
      await api.post('/auth/send-otp', { phone: panelCanonical });
      setAuthStep('otp');
    } catch (e: any) { setAuthError(e.message); }
    finally { setAuthLoading(false); }
  };

  const verifyOtp = async () => {
    setAuthLoading(true); setAuthError('');
    try {
      const res = await api.post('/auth/verify-otp', { phone: panelCanonical, otp });
      const u = res.user;
      if (!PANEL_ROLES.includes(u.role)) {
        setAuthError('Access denied. This panel is for admin and executive users only.');
        setToken(null);
        return;
      }
      const canonical = await appLogin(res.token, u, res.refresh_token);
      if (canonical.role === 'telecaller') { router.replace('/telecaller'); return; }
      setUser(canonical);
      setRole(canonical.role as Role);
      setTab(defaultTabFor(canonical.role));
      setAuthStep('done');
    } catch (e: any) { setAuthError(e.message); }
    finally { setAuthLoading(false); }
  };

  const panelLogout = async () => {
    await appLogout();
    setUser(null); setRole(null);
    setAuthStep('phone'); setPhone(''); setOtp('');
    router.replace('/login');
  };

  // === DATA LOADING ===
  const loadTab = useCallback(async (t: PanelTab, silent = false) => {
    if (!silent) setLoading(true);
    try {
      switch (t) {
        case 'dashboard': setDashData(await api.get('/analytics/dashboard')); break;
        case 'products': {
          const [prodRes, batchRes] = await Promise.all([
            api.get('/products?limit=1&include_hidden=true'),
            api.get('/batches'),
          ]);
          setProducts(prodRes.products || []);
          setBatches(batchRes.batches || []);
          break;
        }
        case 'executives': { const r = await api.get('/executives'); setExecutives(r.executives || []); break; }
      }
    } catch (e) { console.error(e); }
    finally { if (!silent) setLoading(false); }
  }, []);

  useEffect(() => { if (role) { setProductSubView('menu'); loadTab(tab); } }, [tab, role]);

  // Keep the mobile screen awake during long uploads (native only — expo-keep-awake breaks the web panel)
  useEffect(() => {
    if (Platform.OS === 'web') return;
    const busy = uploading || pdfImporting || bannerUploading;
    if (busy) {
      activateKeepAwakeAsync(KEEP_AWAKE_TAG).catch(() => {});
    } else {
      try { deactivateKeepAwake(KEEP_AWAKE_TAG); } catch {}
    }
    return () => { try { deactivateKeepAwake(KEEP_AWAKE_TAG); } catch {} };
  }, [uploading, pdfImporting, bannerUploading]);

  // === ACTIONS ===
  const createBatch = async () => {
    if (!newBatchName.trim()) return;
    try {
      const batch = await api.post('/batches', { name: newBatchName, metal_type: newBatchMetal, category: newBatchCat });
      setNewBatchName(''); setNewBatchCat(''); setShowBatchForm(false);
      setUploadBatchId(batch.id);
      setProductSubView('batch_upload');
      loadTab('products');
    } catch (e: any) { showAlert('Error', e.message); }
  };

  const addProduct = async () => {
    if (!newProdTitle.trim()) { showAlert('Error', 'Enter product title'); return; }
    try {
      await api.post('/products', { title: newProdTitle, metal_type: newProdMetal, category: newProdCat, approx_weight: newProdWeight, purity: newProdPurity, selling_touch: newProdTouch, selling_label: newProdLabel, images: newProdImageUrl ? [newProdImageUrl] : [] });
      showAlert('Success', 'Product added');
      setNewProdTitle(''); setNewProdCat(''); setNewProdWeight(''); setNewProdPurity(''); setNewProdTouch(''); setNewProdLabel(''); setNewProdImageUrl('');
      setProductSubView('list');
      loadTab('products');
    } catch (e: any) { showAlert('Error', e.message); }
  };

  const toggleBatchVisibility = async (id: string) => {
    try { await api.patch(`/batches/${id}/visibility`); loadTab('products'); } catch {}
  };

  const deleteBatch = (id: string, name: string) => {
    confirmAlert('Delete', `Delete "${name}"?`, async () => { await api.delete(`/batches/${id}`); loadTab('products'); }, 'Delete');
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
    router.push({ pathname: '/pdf-import', params: { batchId: uploadBatchId } });
    return;
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
    try {
      const result = await api.importPdfChunked(uploadBatchId, pdfFile, (stage: 'idle' | 'validating' | 'uploading' | 'processing' | 'done' | 'error', detail: string, progress?: number) => {
        setPdfStage(stage);
        setPdfPhase(detail);
        if (progress !== undefined) setPdfProgress(progress);
      }, resumeUploadId || null);
      setPdfResult(result);
      setPdfFile(null); setPdfPhase(''); setPdfStage('done');
      clearLastUploadId();
      showAlert('PDF Import Complete', `${result.imported} pages converted to product images out of ${result.total_pages} total pages.`);
      loadTab('products');
    } catch (e: any) {
      const resumeId = getLastUploadId();
      setPdfResult({ error: e.message, resumeUploadId: resumeId });
      setPdfPhase(''); setPdfStage('error');
    }
    finally { setPdfImporting(false); }
  };

  const cancelPdfImport = () => {
    confirmAlert('Cancel Import?', 'Upload will stop. You can resume later from where it stopped.', () => { cancelUpload(); }, 'Cancel Upload');
  };

  const startUpload = async () => {
    if (!uploadBatchId || !selectedFiles.length) return;
    setUploading(true); setUploadProgress({ done: 0, total: selectedFiles.length });
    try {
      await api.uploadFiles(`/batches/${uploadBatchId}/upload`, selectedFiles, (d, t) => setUploadProgress({ done: d, total: t }));
      setSelectedFiles([]); setUploadBatchId('');
      showAlert('Success', 'Images uploaded');
      loadTab('products');
    } catch (e: any) { showAlert('Error', e.message); }
    finally { setUploading(false); }
  };

  const cancelImageUpload = () => {
    confirmAlert('Cancel Upload?', 'Image upload will stop.', () => { cancelUpload(); }, 'Cancel');
  };

  // Contact actions keep each number's own country code (+91 / +1 / +61) — never a hard-coded "91" prefix.
  const openCall = (phoneNum: string) => { Linking.openURL(telLink(phoneNum)); };

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
    if (!selectedCust || !rewardPoints || parseInt(rewardPoints) <= 0) { showAlert('Error', 'Enter valid points'); return; }
    try {
      const endpoint = rewardAction === 'credit' ? '/rewards/credit' : '/rewards/deduct';
      const res = await api.post(endpoint, { user_id: selectedCust.id, points: parseInt(rewardPoints), reason: rewardReason || rewardAction });
      showAlert('Success', `${rewardAction === 'credit' ? 'Credited' : 'Deducted'} ${rewardPoints} points. New balance: ${res.new_balance}`);
      setRewardPoints(''); setRewardReason('');
      openCustomerWallet(selectedCust);
    } catch (e: any) { showAlert('Error', e.message); }
  };

  const statusColor = (s: string) => {
    switch (s) { case 'pending': return Colors.warning; case 'in_progress': return Colors.info; case 'contacted': return '#A855F7'; case 'resolved': return Colors.success; case 'no_response': return Colors.error; default: return Colors.textMuted; }
  };

  // === LOGIN SCREEN ===
  if (authStep !== 'done') {
    return (
      <SafeAreaView style={s.container}>
        <KeyboardAwareScreen contentContainerStyle={s.loginBox}>
          <Ionicons name="shield-checkmark" size={48} color={Colors.gold} />
          <Text style={s.loginTitle}>Yash Trade Panel</Text>
          <Text style={s.loginSub}>Admin & Executive Access Only</Text>
          {authStep === 'phone' ? (
            <>
              <View style={{ width: '100%', maxWidth: 320, marginBottom: Spacing.md }}>
                <PhoneField testID="panel-phone" country={panelCountry} national={phone} onChange={(c, v) => { setPanelCountry(c); setPhone(v); setAuthError(''); }} placeholder="Phone number" />
              </View>
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
        </KeyboardAwareScreen>
      </SafeAreaView>
    );
  }

  // === TABS ===
  // Contents domain (Products + Content pages): administrators and Upload Executives. Everything else is admin-only
  // or billing-only; the server enforces the same matrix on every endpoint.
  const CONTENT_TABS: { key: PanelTab; label: string; icon: string }[] = [
    { key: 'products', label: 'Products', icon: 'grid' },
    { key: 'content', label: 'Content', icon: 'document-text' },
  ];
  const ADMIN_TABS: { key: PanelTab; label: string; icon: string }[] = [
    { key: 'dashboard', label: 'Dashboard', icon: 'stats-chart' },
    { key: 'requests', label: 'Requests', icon: 'call' },
    { key: 'reports', label: 'Completion reports', icon: 'bar-chart' },
    { key: 'rates', label: 'Rates', icon: 'trending-up' },
    ...CONTENT_TABS,
    { key: 'notifications', label: 'Notifications', icon: 'notifications' },
    { key: 'customers', label: 'Customers', icon: 'people' },
    // Account-deletion ledger: app/website cleanup vs provider erasure (Play / App Store compliance log).
    { key: 'deletions', label: 'Deletions', icon: 'shield-checkmark' },
    { key: 'executives', label: 'Staff', icon: 'people-circle' },
    { key: 'sms', label: 'SMS', icon: 'chatbox-ellipses' },
    // Owner-only console (server-side authorisation); hidden inside store-review sessions where it can never apply.
    ...(!(appUser as any)?.review_environment ? [{ key: 'review' as PanelTab, label: 'Store review', icon: 'key' }] : []),
  ];
  const EXEC_TABS: { key: PanelTab; label: string; icon: string }[] = [
    { key: 'requests', label: 'Requests', icon: 'call' },
  ];
  const BILLING_TABS: { key: PanelTab; label: string; icon: string }[] = [
    { key: 'rewards', label: 'Reward Wallet', icon: 'wallet' },
    { key: 'requests', label: 'Pending queries', icon: 'time-outline' },
    { key: 'rates', label: 'Rates & rate list', icon: 'trending-up' },
  ];
  const tabs = role === 'admin' ? ADMIN_TABS : role === 'billing_executive' ? BILLING_TABS : role === 'upload_executive' ? CONTENT_TABS : EXEC_TABS;

  return (
    <SafeAreaView style={s.container} edges={['top']}>
      {/* Header */}
      <View style={s.header}>
        <Text style={s.headerTitle}>Yash Trade Panel</Text>
        <View style={s.headerRight}>
          <Text style={s.headerUser}>{user?.name || user?.phone}</Text>
          <View style={[s.roleBadge, { backgroundColor: role === 'admin' ? Colors.gold + '20' : Colors.info + '20' }]}>
            <Text style={[s.roleText, { color: role === 'admin' ? Colors.gold : Colors.info }]} testID="panel-role-badge">{ROLE_LABELS[role || ''] || role}</Text>
          </View>
          <TouchableOpacity testID="panel-logout" onPress={panelLogout} style={s.logoutBtn}><Ionicons name="log-out-outline" size={18} color={Colors.error} /></TouchableOpacity>
        </View>
      </View>

      {/* Tab bar */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.tabBar}>
        {tabs.map(t => (
          <TouchableOpacity key={t.key} testID={`panel-tab-${t.key}`} style={[s.tabItem, tab === t.key && s.tabActive]} onPress={() => {
            if(t.key === 'requests') router.push('/staff-requests');
            else if(t.key === 'reports') router.push({ pathname: '/staff-requests', params: { section: 'reports' } } as any);
            else if(t.key === 'rates') router.push('/staff-rates');
            else if(t.key === 'customers') router.push('/customer-directory');
            else if(t.key === 'notifications') router.push('/admin-notifications');
            else if(t.key === 'review') router.push('/review-keys');
            else setTab(t.key);
          }}>
            <Ionicons name={t.icon as any} size={16} color={tab === t.key ? Colors.gold : Colors.textMuted} />
            <Text style={[s.tabLabel, tab === t.key && s.tabLabelActive]}>{t.label}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      {loading ? <ActivityIndicator color={Colors.gold} style={{ marginTop: 40 }} /> : (
        <KeyboardAwareScreen contentContainerStyle={s.content}>

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
                    <TouchableOpacity testID="pm-add" style={s.menuCard} onPress={() => router.push('/catalog-author')}>
                      <View style={[s.menuCardIcon, { backgroundColor: Colors.success + '15' }]}><Ionicons name="add-circle" size={28} color={Colors.success} /></View>
                      <Text style={s.menuCardTitle}>Add Product</Text>
                      <Text style={s.menuCardHint}>Add single product with details</Text>
                    </TouchableOpacity>
                    <TouchableOpacity testID="pm-bulk" style={s.menuCard} onPress={() => { setProductSubView('batches'); loadTab('products'); }}>
                      <View style={[s.menuCardIcon, { backgroundColor: Colors.gold + '15' }]}><Ionicons name="cloud-upload" size={28} color={Colors.gold} /></View>
                      <Text style={s.menuCardTitle}>Upload Images</Text>
                      <Text style={s.menuCardHint}>Upload photos from device</Text>
                    </TouchableOpacity>
                    <TouchableOpacity testID="pm-pdf" style={s.menuCard} onPress={() => router.push('/pdf-import')}>
                      <View style={[s.menuCardIcon, { backgroundColor: '#E91E63' + '15' }]}><Ionicons name="document-text" size={28} color="#E91E63" /></View>
                      <Text style={s.menuCardTitle}>Import PDF</Text>
                      <Text style={s.menuCardHint}>Import PDF catalogue as products</Text>
                    </TouchableOpacity>
                    <TouchableOpacity testID="pm-list" style={s.menuCard} onPress={() => router.push('/product-catalog')}>
                      <View style={[s.menuCardIcon, { backgroundColor: Colors.info + '15' }]}><Ionicons name="grid" size={28} color={Colors.info} /></View>
                      <Text style={s.menuCardTitle}>View All Products</Text>
                      <Text style={s.menuCardHint}>Search and browse paginated catalog</Text>
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
                            } catch (e: any) { showAlert('Error', e.message); }
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
                      <Text style={{ color: Colors.textMuted, fontSize: FontSize.xs, marginTop: 4 }}>Use Reviewed PDF Import for current server limits</Text>
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
                            <Text style={{ color: Colors.textSecondary, fontSize: FontSize.sm }} data-testid="pdf-filesize">{(pdfFile.size / (1024 * 1024)).toFixed(1)} MB ({Math.ceil(pdfFile.size / (25 * 1024 * 1024))} chunks)</Text>
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
                            {pdfStage === 'uploading' ? 'File is being uploaded in 25MB chunks with auto-retry (5 attempts each).' : ''}
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
                      <TouchableOpacity testID="pdf-import-btn" style={[s.saveBtn, { marginTop: Spacing.lg, backgroundColor: '#E91E63' }]} onPress={() => startPdfImport()}>
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
                      <Text style={[s.formLabel, { marginTop: 0 }]}>{'Give your batch a name like "New Payal Lot" or "Silver Articles Feb"'}</Text>
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
                        <Text style={{ color: Colors.textSecondary, fontSize: FontSize.xs, marginBottom: Spacing.md }}>Open the reviewed importer for product blocks, square crops and hidden draft confirmation.</Text>
                        <TouchableOpacity testID="batch-download-pdf-sample" style={s.pickBtn} onPress={() => downloadSample().catch((e: any) => showAlert('Download failed', e.message))}><Ionicons name="download-outline" size={22} color={Colors.gold}/><Text style={s.formLabel}>Download Sample PDF</Text></TouchableOpacity>
                        <TouchableOpacity style={[s.pickBtn, { borderColor: '#E91E63' + '40' }]} onPress={pickPdfFile}>
                          <Ionicons name="document-text" size={32} color="#E91E63" />
                          <Text style={{ color: Colors.text, marginTop: 8, fontSize: FontSize.md, fontWeight: '600' }}>Tap to select PDF file</Text>
                          <Text style={{ color: Colors.textMuted, fontSize: FontSize.xs, marginTop: 4 }}>Server limits, upload/resume and review are shown in the shared importer.</Text>
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
                          <TouchableOpacity style={[s.saveBtn, { marginTop: Spacing.md, backgroundColor: '#E91E63' }]} onPress={() => startPdfImport()}>
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
                        <Text style={s.listMeta}>{displayPhone(c.phone)} • {c.city || 'No city'} • {c.customer_code} • {c.reward_points || 0} pts</Text>
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

          {/* ===== ACCOUNT DELETION LEDGER (Admin only): app/website cleanup vs provider erasure ===== */}
          {tab === 'deletions' && role === 'admin' && <DeletionRequests />}

          {/* ===== EXECUTIVES MANAGEMENT (Admin only) ===== */}
          {tab === 'executives' && (
            <>
              <Text style={s.sectionTitle}>STAFF MANAGEMENT · TELECALLERS, BILLING, UPLOAD EXECUTIVES</Text>
              
              {/* Add/Edit Executive Form */}
              <TouchableOpacity style={[s.saveBtn, { marginBottom: Spacing.md }]} onPress={() => { setShowExecForm(!showExecForm); setEditingExecId(''); setExecForm({ name: '', phone: '', code: '', role: 'executive' }); }}>
                <Text style={s.saveBtnText}>{showExecForm ? 'CANCEL' : '+ ADD STAFF MEMBER'}</Text>
              </TouchableOpacity>

              {showExecForm && (
                <View style={s.formCard}>
                  <Text style={s.formTitle}>{editingExecId ? 'Edit staff member' : 'Add staff member'}</Text>
                  <Text style={s.formLabel}>Name *</Text>
                  <TextInput style={s.formInput} value={execForm.name} onChangeText={v => setExecForm(p => ({...p, name: v}))} placeholder="e.g. Riya Sharma" placeholderTextColor={Colors.textMuted} testID="exec-name-input" />
                  <Text style={s.formLabel}>Mobile Number *</Text>
                  {editingExecId ? (
                    <View style={[s.formInput, { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }]}>
                      <Text style={{ color: Colors.text }} testID="exec-current-phone">{displayPhone(execForm.phone)}</Text>
                      {execForm.role !== 'admin' && (
                        <TouchableOpacity testID="exec-change-phone-btn" onPress={() => setPhoneChangeStaff(executives.find(e => e.id === editingExecId))} style={{ minHeight: 44, justifyContent: 'center' }}>
                          <Text style={{ color: Colors.gold, fontWeight: '700' }}>Change login number</Text>
                        </TouchableOpacity>
                      )}
                    </View>
                  ) : (
                    <PhoneField testID="exec-phone-input" country={execCountry} national={execForm.phone} onChange={(c, v) => { setExecCountry(c); setExecForm(p => ({ ...p, phone: v })); }} />
                  )}
                  <Text style={s.formLabel}>Staff Code *</Text>
                  <TextInput style={s.formInput} value={execForm.code} onChangeText={v => setExecForm(p => ({...p, code: v.toUpperCase()}))} placeholder="e.g. EXEC02" placeholderTextColor={Colors.textMuted} testID="exec-code-input" />
                  <Text style={s.formLabel}>Role</Text>
                  <View style={s.formRow}>
                    {STAFF_ROLE_OPTIONS.map(r => (
                      <TouchableOpacity key={r.key} testID={`exec-role-${r.key}`} style={[s.metalBtn, (execForm.role === r.key || (r.key === 'executive' && execForm.role === 'telecaller')) && s.metalBtnActive]} onPress={() => setExecForm(p => ({...p, role: r.key}))}>
                        <Text style={[s.metalBtnText, (execForm.role === r.key || (r.key === 'executive' && execForm.role === 'telecaller')) && s.metalBtnTextActive]}>{r.label}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                  {execForm.role === 'upload_executive' && <Text style={s.emptyText} testID="exec-role-upload-note">Upload Executives get the Products and Content tools only (PDF/photo imports, catalogue, banners, pages) — no customers, queries, billing or notifications.</Text>}
                  <TouchableOpacity style={[s.saveBtn, { marginTop: Spacing.md }]} testID="exec-save-btn" onPress={async () => {
                    const canonical = editingExecId ? execForm.phone : canonicalPhone(execForm.phone, execCountry);
                    if (!execForm.name.trim() || !canonical || !execForm.code.trim()) { showAlert('Error', 'Name, a valid phone number and Code are required'); return; }
                    try {
                      if (editingExecId) {
                        // The login number is changed only through the audited "Change login number" operation.
                        await api.put(`/executives/${editingExecId}`, { name: execForm.name, customer_code: execForm.code, role: execForm.role });
                        showAlert('Success', 'Staff member updated');
                      } else {
                        await api.post('/executives', { name: execForm.name, phone: canonical, code: execForm.code, role: execForm.role });
                        showAlert('Success', `"${execForm.name}" created. They can now login with ${displayPhone(canonical)} and OTP.`);
                      }
                      setShowExecForm(false); setEditingExecId('');
                      setExecForm({ name: '', phone: '', code: '', role: 'executive' });
                      loadTab('executives');
                    } catch (e: any) { showAlert('Error', e.message); }
                  }}>
                    <Text style={s.saveBtnText}>{editingExecId ? 'UPDATE STAFF MEMBER' : 'CREATE STAFF MEMBER'}</Text>
                  </TouchableOpacity>
                </View>
              )}

              {/* Staff list */}
              {executives.length === 0 && !showExecForm && <Text style={s.emptyText}>No staff added yet. Tap above to add one.</Text>}
              {executives.map(ex => (
                <View key={ex.id} style={s.reqCard} testID={`exec-card-${ex.id}`}>
                  <View style={s.reqTop}>
                    <View style={[s.reqIcon, { backgroundColor: ex.role === 'billing_executive' ? '#FF980015' : ex.role === 'upload_executive' ? Colors.success + '15' : '#A855F715' }]}>
                      <Ionicons name={ex.role === 'upload_executive' ? 'cloud-upload' : 'person-circle'} size={22} color={ex.role === 'billing_executive' ? '#FF9800' : ex.role === 'upload_executive' ? Colors.success : '#A855F7'} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={s.reqType}>{ex.name}</Text>
                      <Text style={s.reqTime}>{displayPhone(ex.phone)} • {ex.customer_code} • {ROLE_LABELS[ex.role] || ex.role?.replace(/_/g, ' ')}</Text>
                    </View>
                    <View style={[s.badge, { backgroundColor: ex.status === 'active' ? Colors.success + '20' : Colors.error + '20' }]}>
                      <Text style={[s.badgeText, { color: ex.status === 'active' ? Colors.success : Colors.error }]} testID={`exec-status-${ex.id}`}>{ex.status}</Text>
                    </View>
                  </View>
                  <View style={s.actionsRow}>
                    <TouchableOpacity testID={`exec-edit-${ex.id}`} style={[s.actBtn, { backgroundColor: Colors.gold + '15' }]} onPress={() => {
                      setEditingExecId(ex.id); setShowExecForm(true);
                      setExecForm({ name: ex.name, phone: ex.phone, code: ex.customer_code || '', role: ex.role });
                    }}>
                      <Ionicons name="create" size={12} color={Colors.gold} /><Text style={[s.actText, { color: Colors.gold }]}>Edit</Text>
                    </TouchableOpacity>
                    <TouchableOpacity testID={`exec-call-${ex.id}`} style={[s.actBtn, { backgroundColor: Colors.info + '15' }]} onPress={() => openCall(ex.phone)}>
                      <Ionicons name="call" size={12} color={Colors.info} /><Text style={[s.actText, { color: Colors.info }]}>Call</Text>
                    </TouchableOpacity>
                  </View>
                  {/* Disable (reversible) / Re-enable / Delete (erasure workflow) are distinct, server-enforced operations */}
                  <AccountActions kind="staff" account={ex} onChanged={() => loadTab('executives', true)} />
                </View>
              ))}
            </>
          )}


          {/* ===== SMS PROVIDER DIAGNOSTICS (Admin only) ===== */}
          {tab === 'sms' && role === 'admin' && <SmsDiagnostics />}

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
                      // Rate slabs are a pricing (billing/admin) control, not content: not offered to Upload Executives.
                      ...(role === 'admin' ? [{ key: 'ratelist', label: 'Rate List', hint: 'Manage quantity-based rate slabs', icon: 'list', color: '#E91E63' }] : []),
                      { key: 'schemes', label: 'Schemes', hint: 'Upload scheme posters & details', icon: 'ribbon', color: '#FF9800' },
                      { key: 'brands', label: 'Brands', hint: 'Manage brand logos', icon: 'star', color: '#9C27B0' },
                      { key: 'showroom', label: 'Showroom', hint: 'Floor-wise photos & descriptions', icon: 'images', color: '#00BCD4' },
                      { key: 'exhibitions', label: 'Exhibitions', hint: 'Upcoming & past exhibitions', icon: 'calendar', color: '#795548' },
                      { key: 'banners', label: 'Home Banners', hint: 'Manage carousel banners on Home', icon: 'albums', color: Colors.success },
                    ].map(item => (
                      <TouchableOpacity key={item.key} testID={`content-${item.key}`} style={s.menuCard} onPress={async () => {
                        setContentSubView(item.key as ContentSubView);
                        setContentForm({});
                        setEditingBannerId('');
                        setLoading(true);
                        try {
                          if (item.key === 'about') { const r = await api.get('/about'); setContentData(r.raw || []); }
                          else if (item.key === 'ratelist') { router.push('/staff-rates'); }
                          else if (item.key === 'schemes') { const r = await api.get('/schemes?active_only=false'); setContentData(r.schemes || []); }
                          else if (item.key === 'brands') { const r = await api.get('/brands?active_only=false'); setContentData(r.brands || []); }
                          else if (item.key === 'showroom') { const r = await api.get('/showroom'); setContentData(r.floors || []); }
                          else if (item.key === 'exhibitions') { const r = await api.get('/exhibitions'); setContentData(r.all || []); }
                          else if (item.key === 'banners') { const r = await api.get('/banners/all'); setContentData(r.banners || []); }
                        } catch (e: any) { showAlert('Error', e?.message || 'Could not load content.'); }
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
                        try { await api.post('/about', { section: item.section, content_en: item.content_en, content_hi: item.content_hi, content_pa: item.content_pa }); showAlert('Saved', `${item.section} updated`); } catch (e: any) { showAlert('Error', e.message); }
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
                      <TouchableOpacity testID={`legacy-slab-delete-${slab.id}`} onPress={async () => { try { await api.delete(`/rate-list/${slab.id}?version=${slab.version||0}`); setContentData(prev => prev.filter(x => x.id !== slab.id)); } catch(e:any) { showAlert('Error',e.message); } }}><Ionicons name="trash-outline" size={16} color={Colors.error} /></TouchableOpacity>
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
                        setContentData(prev => [...prev, res]); setContentForm({}); showAlert('Added');
                      } catch (e: any) { showAlert('Error', e.message); }
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
                        setContentData(prev => [...prev, res]); setContentForm({}); showAlert('Added');
                      } catch (e: any) { showAlert('Error', e.message); }
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
                        setContentData(prev => [...prev, res]); setContentForm({}); showAlert('Added');
                      } catch (e: any) { showAlert('Error', e.message); }
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
                        setContentData(prev => [...prev, res]); setContentForm({}); showAlert('Added');
                      } catch (e: any) { showAlert('Error', e.message); }
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
                        setContentData(prev => [...prev, res]); setContentForm({}); showAlert('Added');
                      } catch (e: any) { showAlert('Error', e.message); }
                    }}><Text style={s.saveBtnText}>ADD EXHIBITION</Text></TouchableOpacity>
                  </View>
                </>
              )}

              {/* Home Banners Editor */}
              {contentSubView === 'banners' && (
                <>
                  <Text style={s.sectionTitle}>HOME BANNERS ({contentData.length})</Text>
                  {contentData.map(bn => (
                    <View key={bn.id} style={s.formCard} data-testid={`banner-row-${bn.id}`}>
                      <View style={{ flexDirection: 'row', gap: 10 }}>
                        {bn.image_url ? (
                          <Image source={{ uri: resolveFileUrl(bn.image_url) }} style={{ width: 88, height: 44, borderRadius: 8, backgroundColor: Colors.surface }} />
                        ) : (
                          <View style={{ width: 88, height: 44, borderRadius: 8, backgroundColor: Colors.surface, alignItems: 'center', justifyContent: 'center' }}>
                            <Ionicons name="image-outline" size={18} color={Colors.textMuted} />
                          </View>
                        )}
                        <View style={{ flex: 1 }}>
                          <Text style={s.listTitle}>{bn.title}</Text>
                          <Text style={s.listMeta}>
                            Order: {bn.order ?? 0} • {bn.is_active ? 'Active' : 'Inactive'}
                            {bn.cta_type && bn.cta_type !== 'none' ? ` • CTA: ${bn.cta_type}` : ''}
                            {bn.start_date || bn.end_date ? ` • ${bn.start_date || '...'} → ${bn.end_date || '...'}` : ''}
                          </Text>
                        </View>
                      </View>
                      <View style={s.actionsRow}>
                        <TouchableOpacity style={[s.actBtn, { backgroundColor: Colors.gold + '15' }]} onPress={() => {
                          setEditingBannerId(bn.id);
                          setContentForm({ title: bn.title || '', subtitle: bn.subtitle || '', image_url: bn.image_url || '', cta_label: bn.cta_label || '', cta_type: bn.cta_type || 'none', cta_target: bn.cta_target || '', order: String(bn.order ?? 0), is_active: bn.is_active !== false, start_date: bn.start_date || '', end_date: bn.end_date || '' });
                        }}>
                          <Ionicons name="create" size={12} color={Colors.gold} /><Text style={[s.actText, { color: Colors.gold }]}>Edit</Text>
                        </TouchableOpacity>
                        <TouchableOpacity style={[s.actBtn, { backgroundColor: (bn.is_active ? Colors.warning : Colors.success) + '15' }]} onPress={async () => {
                          try {
                            const updated = await api.put(`/banners/${bn.id}`, { is_active: !bn.is_active });
                            setContentData(prev => prev.map(x => x.id === bn.id ? updated : x));
                          } catch (e: any) { showAlert('Error', e?.message || 'Could not update banner.'); }
                        }}>
                          <Text style={[s.actText, { color: bn.is_active ? Colors.warning : Colors.success }]}>{bn.is_active ? 'Deactivate' : 'Activate'}</Text>
                        </TouchableOpacity>
                        <TouchableOpacity style={[s.actBtn, { backgroundColor: Colors.error + '15' }]} onPress={() => {
                          confirmAlert('Delete Banner', `Delete "${bn.title}"?`, async () => {
                            try { await api.delete(`/banners/${bn.id}`); setContentData(prev => prev.filter(x => x.id !== bn.id)); }
                            catch (e: any) { showAlert('Error', e?.message || 'Could not delete banner.'); }
                          }, 'Delete');
                        }}>
                          <Ionicons name="trash-outline" size={12} color={Colors.error} /><Text style={[s.actText, { color: Colors.error }]}>Delete</Text>
                        </TouchableOpacity>
                      </View>
                    </View>
                  ))}
                  {contentData.length === 0 && <Text style={s.emptyText}>No banners yet. Add your first banner below.</Text>}

                  <View style={s.formCard} data-testid="banner-form">
                    <Text style={s.formTitle}>{editingBannerId ? 'Edit Banner' : 'Add Banner'}</Text>
                    <TextInput testID="banner-title" style={s.formInput} placeholder="Title *" placeholderTextColor={Colors.textMuted} value={contentForm.title || ''} onChangeText={v => setContentForm(p => ({ ...p, title: v }))} />
                    <TextInput testID="banner-subtitle" style={s.formInput} placeholder="Subtitle (optional)" placeholderTextColor={Colors.textMuted} value={contentForm.subtitle || ''} onChangeText={v => setContentForm(p => ({ ...p, subtitle: v }))} />

                    <Text style={s.formLabel}>Banner Image</Text>
                    {contentForm.image_url ? (
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: Spacing.sm }}>
                        <Image source={{ uri: resolveFileUrl(contentForm.image_url) }} style={{ width: 132, height: 60, borderRadius: 8, backgroundColor: Colors.surface }} />
                        <TouchableOpacity onPress={() => setContentForm(p => ({ ...p, image_url: '' }))}>
                          <Ionicons name="close-circle" size={22} color={Colors.error} />
                        </TouchableOpacity>
                      </View>
                    ) : null}
                    <TouchableOpacity testID="banner-upload-btn" style={[s.pickBtn, { paddingVertical: Spacing.md }]} disabled={bannerUploading} onPress={() => {
                      if (Platform.OS === 'web') {
                        const input = document.createElement('input');
                        input.type = 'file'; input.accept = 'image/*'; input.multiple = false;
                        input.onchange = async (e: any) => {
                          const f = e.target.files?.[0] as File | undefined;
                          if (!f) return;
                          setBannerUploading(true);
                          try {
                            const res = await api.uploadSingle('/banners/upload', f);
                            setContentForm(p => ({ ...p, image_url: res.image_url }));
                          } catch (err: any) { showAlert('Error', err?.message || 'Image upload failed.'); }
                          finally { setBannerUploading(false); }
                        };
                        input.click();
                      }
                    }}>
                      {bannerUploading ? <ActivityIndicator color={Colors.gold} /> : (
                        <>
                          <Ionicons name="cloud-upload" size={24} color={Colors.gold} />
                          <Text style={{ color: Colors.text, marginTop: 6, fontSize: FontSize.sm, fontWeight: '600' }}>{contentForm.image_url ? 'Replace image' : 'Upload banner image'}</Text>
                          <Text style={{ color: Colors.textMuted, fontSize: FontSize.xs, marginTop: 2 }}>Recommended ~2.2:1 (e.g. 1320x600) — JPG/PNG, max 10MB</Text>
                        </>
                      )}
                    </TouchableOpacity>

                    <TextInput style={s.formInput} placeholder="CTA Label (optional, e.g. Shop Now)" placeholderTextColor={Colors.textMuted} value={contentForm.cta_label || ''} onChangeText={v => setContentForm(p => ({ ...p, cta_label: v }))} />
                    <Text style={s.formLabel}>CTA Destination</Text>
                    <View style={s.formRow}>{['none', 'feed', 'product', 'url'].map(ct => (
                      <TouchableOpacity key={ct} style={[s.metalBtn, (contentForm.cta_type || 'none') === ct && s.metalBtnActive]} onPress={() => setContentForm(p => ({ ...p, cta_type: ct }))}>
                        <Text style={[s.metalBtnText, (contentForm.cta_type || 'none') === ct && s.metalBtnTextActive]}>{ct}</Text>
                      </TouchableOpacity>
                    ))}</View>
                    {(contentForm.cta_type && contentForm.cta_type !== 'none') ? (
                      <TextInput style={s.formInput} placeholder={contentForm.cta_type === 'product' ? 'Product ID' : contentForm.cta_type === 'feed' ? 'Metal (silver/gold/diamond) or category (optional)' : 'https:// link'} placeholderTextColor={Colors.textMuted} value={contentForm.cta_target || ''} onChangeText={v => setContentForm(p => ({ ...p, cta_target: v }))} />
                    ) : null}

                    <View style={s.formRow}>
                      <View style={{ flex: 1 }}><Text style={s.formLabel}>Display Order</Text><TextInput style={s.formInput} keyboardType="number-pad" placeholder="0" placeholderTextColor={Colors.textMuted} value={String(contentForm.order ?? '')} onChangeText={v => setContentForm(p => ({ ...p, order: v }))} /></View>
                      <View style={{ flex: 1 }}>
                        <Text style={s.formLabel}>Status</Text>
                        <View style={s.formRow}>
                          <TouchableOpacity style={[s.metalBtn, contentForm.is_active !== false && s.metalBtnActive]} onPress={() => setContentForm(p => ({ ...p, is_active: true }))}><Text style={[s.metalBtnText, contentForm.is_active !== false && s.metalBtnTextActive]}>Active</Text></TouchableOpacity>
                          <TouchableOpacity style={[s.metalBtn, contentForm.is_active === false && s.metalBtnActive]} onPress={() => setContentForm(p => ({ ...p, is_active: false }))}><Text style={[s.metalBtnText, contentForm.is_active === false && s.metalBtnTextActive]}>Inactive</Text></TouchableOpacity>
                        </View>
                      </View>
                    </View>
                    <View style={s.formRow}>
                      <View style={{ flex: 1 }}><Text style={s.formLabel}>Start Date (optional)</Text><TextInput style={s.formInput} placeholder="YYYY-MM-DD" placeholderTextColor={Colors.textMuted} value={contentForm.start_date || ''} onChangeText={v => setContentForm(p => ({ ...p, start_date: v }))} /></View>
                      <View style={{ flex: 1 }}><Text style={s.formLabel}>End Date (optional)</Text><TextInput style={s.formInput} placeholder="YYYY-MM-DD" placeholderTextColor={Colors.textMuted} value={contentForm.end_date || ''} onChangeText={v => setContentForm(p => ({ ...p, end_date: v }))} /></View>
                    </View>

                    <TouchableOpacity testID="banner-save-btn" style={s.saveBtn} onPress={async () => {
                      if (!(contentForm.title || '').trim()) { showAlert('Error', 'Banner title is required'); return; }
                      const dateOk = (d: string) => !d || /^\d{4}-\d{2}-\d{2}$/.test(d);
                      if (!dateOk(contentForm.start_date || '') || !dateOk(contentForm.end_date || '')) { showAlert('Error', 'Dates must be in YYYY-MM-DD format'); return; }
                      const payload = {
                        title: (contentForm.title || '').trim(),
                        subtitle: contentForm.subtitle || '',
                        image_url: contentForm.image_url || '',
                        cta_label: contentForm.cta_label || '',
                        cta_type: contentForm.cta_type || 'none',
                        cta_target: contentForm.cta_target || '',
                        order: parseInt(String(contentForm.order)) || 0,
                        is_active: contentForm.is_active !== false,
                        start_date: contentForm.start_date || '',
                        end_date: contentForm.end_date || '',
                      };
                      try {
                        if (editingBannerId) {
                          const updated = await api.put(`/banners/${editingBannerId}`, payload);
                          setContentData(prev => prev.map(x => x.id === editingBannerId ? updated : x).sort((a, b) => (a.order || 0) - (b.order || 0)));
                          showAlert('Saved', 'Banner updated');
                        } else {
                          const created = await api.post('/banners', payload);
                          setContentData(prev => [...prev, created].sort((a, b) => (a.order || 0) - (b.order || 0)));
                          showAlert('Added', 'Banner created');
                        }
                        setContentForm({});
                        setEditingBannerId('');
                      } catch (e: any) { showAlert('Error', e?.message || 'Could not save banner.'); }
                    }}><Text style={s.saveBtnText}>{editingBannerId ? 'SAVE CHANGES' : 'ADD BANNER'}</Text></TouchableOpacity>
                    {editingBannerId ? (
                      <TouchableOpacity style={{ alignItems: 'center', marginTop: Spacing.sm }} onPress={() => { setEditingBannerId(''); setContentForm({}); }}>
                        <Text style={{ color: Colors.textMuted, fontSize: FontSize.sm }}>Cancel editing</Text>
                      </TouchableOpacity>
                    ) : null}
                  </View>
                </>
              )}
            </>
          )}

          <View style={{ height: 40 }} />
        </KeyboardAwareScreen>
      )}
      {/* Rendered outside the tab body so the outcome message survives the staff-list reload that follows a commit. */}
      {phoneChangeStaff && (
        <StaffPhoneChange staff={phoneChangeStaff} onClose={() => setPhoneChangeStaff(null)}
          onChanged={() => { setShowExecForm(false); setEditingExecId(''); loadTab('executives', true); }} />
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  // Login
  loginBox: { flexGrow: 1, justifyContent: 'center', alignItems: 'center', paddingHorizontal: Spacing.xl },
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
  custBadge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 },
  custBadgeText: { fontSize: 9, fontWeight: '700', letterSpacing: 0.5 },
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
