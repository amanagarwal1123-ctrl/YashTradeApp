import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, TextInput, ActivityIndicator, Alert, Platform } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../src/theme';
import { api } from '../src/api';

interface Batch {
  id: string; name: string; metal_type: string; category: string;
  status: string; image_count: number; upload_type: string; created_at: string;
}

export default function AdminBatchesScreen() {
  const router = useRouter();
  const [batches, setBatches] = useState<Batch[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchText, setSearchText] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [newMetal, setNewMetal] = useState('silver');
  const [newCategory, setNewCategory] = useState('');
  const [creating, setCreating] = useState(false);

  // Upload state
  const [uploadBatchId, setUploadBatchId] = useState('');
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState({ done: 0, total: 0 });
  const [uploadResult, setUploadResult] = useState('');

  const loadBatches = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (searchText) params.set('search', searchText);
      const res = await api.get(`/batches?${params}`);
      setBatches(res.batches || []);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [searchText]);

  useEffect(() => { loadBatches(); }, []);

  const createBatch = async () => {
    if (!newName.trim()) { Alert.alert('Error', 'Enter batch name'); return; }
    setCreating(true);
    try {
      const batch = await api.post('/batches', { name: newName, metal_type: newMetal, category: newCategory });
      setShowCreate(false);
      setNewName(''); setNewCategory('');
      // Auto-open upload for new batch
      setUploadBatchId(batch.id);
      loadBatches();
    } catch (e: any) { Alert.alert('Error', e.message); }
    finally { setCreating(false); }
  };

  const toggleVisibility = async (batchId: string) => {
    try {
      const res = await api.patch(`/batches/${batchId}/visibility`);
      Alert.alert('Updated', `Batch is now ${res.status}`);
      loadBatches();
    } catch (e: any) { Alert.alert('Error', e.message); }
  };

  const deleteBatch = (batchId: string, name: string) => {
    Alert.alert('Delete Batch', `Delete "${name}" and all its images? This cannot be undone.`, [
      { text: 'Cancel' },
      { text: 'Delete', style: 'destructive', onPress: async () => {
        try { await api.delete(`/batches/${batchId}`); loadBatches(); }
        catch (e: any) { Alert.alert('Error', e.message); }
      }}
    ]);
  };

  const pickFiles = () => {
    if (Platform.OS === 'web') {
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = 'image/*';
      input.multiple = true;
      input.onchange = (e: any) => {
        const files = Array.from(e.target.files || []) as File[];
        if (files.length > 0) setSelectedFiles(prev => [...prev, ...files]);
      };
      input.click();
    } else {
      Alert.alert('Info', 'File upload is available via web browser');
    }
  };

  const startUpload = async () => {
    if (!uploadBatchId || selectedFiles.length === 0) return;
    setUploading(true);
    setUploadProgress({ done: 0, total: selectedFiles.length });
    setUploadResult('');
    try {
      const results = await api.uploadFiles(
        `/batches/${uploadBatchId}/upload`,
        selectedFiles,
        (done, total) => setUploadProgress({ done, total })
      );
      const totalUploaded = results.reduce((sum: number, r: any) => sum + (r.uploaded || 0), 0);
      const totalFailed = results.reduce((sum: number, r: any) => sum + (r.failed || 0), 0);
      setUploadResult(`Uploaded: ${totalUploaded} | Failed: ${totalFailed}`);
      setSelectedFiles([]);
      loadBatches();
    } catch (e: any) {
      setUploadResult(`Error: ${e.message}`);
    }
    finally { setUploading(false); }
  };

  const removeFile = (index: number) => {
    setSelectedFiles(prev => prev.filter((_, i) => i !== index));
  };

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity testID="batches-back-btn" onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={24} color={Colors.text} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Batch Manager</Text>
        <TouchableOpacity testID="create-batch-btn" onPress={() => setShowCreate(!showCreate)} style={styles.backBtn}>
          <Ionicons name={showCreate ? 'close' : 'add'} size={24} color={Colors.gold} />
        </TouchableOpacity>
      </View>

      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.content}>
        {/* Search */}
        <View style={styles.searchBox}>
          <Ionicons name="search" size={18} color={Colors.textMuted} />
          <TextInput testID="batch-search" style={styles.searchInput} placeholder="Search batches..." placeholderTextColor={Colors.textMuted} value={searchText} onChangeText={setSearchText} onSubmitEditing={loadBatches} returnKeyType="search" />
        </View>

        {/* Create Batch */}
        {showCreate && (
          <View style={styles.formCard}>
            <Text style={styles.formTitle}>New Batch</Text>
            <TextInput testID="batch-name-input" style={styles.formInput} placeholder="Batch Name *  e.g. New Payal Lot" placeholderTextColor={Colors.textMuted} value={newName} onChangeText={setNewName} />
            <Text style={styles.formLabel}>Metal Type</Text>
            <View style={styles.formRow}>
              {['silver', 'gold', 'diamond'].map(m => (
                <TouchableOpacity key={m} style={[styles.metalBtn, newMetal === m && styles.metalBtnActive]} onPress={() => setNewMetal(m)}>
                  <Text style={[styles.metalBtnText, newMetal === m && styles.metalBtnTextActive]}>{m}</Text>
                </TouchableOpacity>
              ))}
            </View>
            <TextInput style={styles.formInput} placeholder="Category (optional)  e.g. payal, chain" placeholderTextColor={Colors.textMuted} value={newCategory} onChangeText={setNewCategory} />
            <TouchableOpacity testID="save-batch-btn" style={styles.saveBtn} onPress={createBatch} disabled={creating}>
              {creating ? <ActivityIndicator color="#000" /> : <Text style={styles.saveBtnText}>CREATE BATCH</Text>}
            </TouchableOpacity>
          </View>
        )}

        {/* File Upload Section */}
        {uploadBatchId && (
          <View style={styles.uploadCard}>
            <View style={styles.uploadHeader}>
              <Text style={styles.formTitle}>Upload Images</Text>
              <TouchableOpacity onPress={() => { setUploadBatchId(''); setSelectedFiles([]); setUploadResult(''); }}>
                <Ionicons name="close-circle" size={24} color={Colors.textMuted} />
              </TouchableOpacity>
            </View>
            <Text style={styles.uploadSubtext}>
              Uploading to: {batches.find(b => b.id === uploadBatchId)?.name || 'batch'}
            </Text>

            <TouchableOpacity testID="pick-files-btn" style={styles.pickFilesBtn} onPress={pickFiles}>
              <Ionicons name="cloud-upload" size={28} color={Colors.gold} />
              <Text style={styles.pickFilesText}>Tap to select images</Text>
              <Text style={styles.pickFilesHint}>JPG, PNG, WebP - Max 20MB each</Text>
            </TouchableOpacity>

            {selectedFiles.length > 0 && (
              <View style={styles.fileList}>
                <Text style={styles.fileListTitle}>{selectedFiles.length} files selected</Text>
                {selectedFiles.slice(0, 10).map((f, i) => (
                  <View key={i} style={styles.fileItem}>
                    <Ionicons name="image" size={16} color={Colors.textSecondary} />
                    <Text style={styles.fileName} numberOfLines={1}>{f.name}</Text>
                    <Text style={styles.fileSize}>{(f.size / 1024).toFixed(0)}KB</Text>
                    <TouchableOpacity onPress={() => removeFile(i)}>
                      <Ionicons name="close" size={16} color={Colors.error} />
                    </TouchableOpacity>
                  </View>
                ))}
                {selectedFiles.length > 10 && <Text style={styles.moreFiles}>+{selectedFiles.length - 10} more files</Text>}

                <TouchableOpacity testID="add-more-files-btn" style={styles.addMoreBtn} onPress={pickFiles}>
                  <Ionicons name="add" size={16} color={Colors.gold} />
                  <Text style={styles.addMoreText}>Add more files</Text>
                </TouchableOpacity>
              </View>
            )}

            {uploading && (
              <View style={styles.progressContainer}>
                <View style={styles.progressBar}>
                  <View style={[styles.progressFill, { width: `${(uploadProgress.done / Math.max(uploadProgress.total, 1)) * 100}%` }]} />
                </View>
                <Text style={styles.progressText}>{uploadProgress.done} / {uploadProgress.total} files</Text>
              </View>
            )}

            {uploadResult ? <Text style={styles.uploadResultText}>{uploadResult}</Text> : null}

            {selectedFiles.length > 0 && !uploading && (
              <TouchableOpacity testID="start-upload-btn" style={styles.uploadBtn} onPress={startUpload}>
                <Ionicons name="cloud-upload" size={18} color="#000" />
                <Text style={styles.uploadBtnText}>UPLOAD {selectedFiles.length} IMAGES</Text>
              </TouchableOpacity>
            )}
          </View>
        )}

        {/* Batch List */}
        <Text style={styles.sectionTitle}>ALL BATCHES ({batches.length})</Text>

        {loading ? <ActivityIndicator color={Colors.gold} style={{ marginTop: 20 }} /> : (
          batches.map(batch => (
            <TouchableOpacity
              key={batch.id}
              testID={`batch-item-${batch.id}`}
              style={styles.batchCard}
              onPress={() => router.push({ pathname: '/admin-batch-detail', params: { id: batch.id } })}
            >
              <View style={styles.batchHeader}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.batchName}>{batch.name}</Text>
                  <Text style={styles.batchMeta}>
                    {batch.metal_type} {batch.category ? `• ${batch.category}` : ''} • {batch.image_count} images • {batch.upload_type === 'file' ? 'File Upload' : 'URL Upload'}
                  </Text>
                  <Text style={styles.batchDate}>{new Date(batch.created_at).toLocaleDateString()}</Text>
                </View>
                <View style={[styles.statusBadge, { backgroundColor: batch.status === 'visible' ? Colors.success + '20' : Colors.warning + '20' }]}>
                  <Text style={[styles.statusText, { color: batch.status === 'visible' ? Colors.success : Colors.warning }]}>
                    {batch.status}
                  </Text>
                </View>
              </View>
              <View style={styles.batchActions}>
                <TouchableOpacity
                  testID={`upload-to-${batch.id}`}
                  style={[styles.miniBtn, { backgroundColor: Colors.gold + '20' }]}
                  onPress={(e) => { e.stopPropagation(); setUploadBatchId(batch.id); setSelectedFiles([]); setUploadResult(''); }}
                >
                  <Ionicons name="cloud-upload" size={14} color={Colors.gold} />
                  <Text style={[styles.miniBtnText, { color: Colors.gold }]}>Upload</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.miniBtn, { backgroundColor: batch.status === 'visible' ? Colors.warning + '20' : Colors.success + '20' }]}
                  onPress={(e) => { e.stopPropagation(); toggleVisibility(batch.id); }}
                >
                  <Ionicons name={batch.status === 'visible' ? 'eye-off' : 'eye'} size={14} color={batch.status === 'visible' ? Colors.warning : Colors.success} />
                  <Text style={[styles.miniBtnText, { color: batch.status === 'visible' ? Colors.warning : Colors.success }]}>
                    {batch.status === 'visible' ? 'Hide' : 'Show'}
                  </Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.miniBtn, { backgroundColor: Colors.error + '20' }]}
                  onPress={(e) => { e.stopPropagation(); deleteBatch(batch.id, batch.name); }}
                >
                  <Ionicons name="trash" size={14} color={Colors.error} />
                  <Text style={[styles.miniBtnText, { color: Colors.error }]}>Delete</Text>
                </TouchableOpacity>
              </View>
            </TouchableOpacity>
          ))
        )}

        {!loading && batches.length === 0 && (
          <View style={styles.emptyState}>
            <Ionicons name="folder-open" size={48} color={Colors.textMuted} />
            <Text style={styles.emptyText}>No batches yet</Text>
            <Text style={styles.emptyHint}>Create a batch and start uploading images</Text>
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
  content: { paddingHorizontal: Spacing.lg },
  searchBox: { flexDirection: 'row', alignItems: 'center', backgroundColor: Colors.surface, borderRadius: 12, paddingHorizontal: Spacing.md, gap: 8, marginBottom: Spacing.md },
  searchInput: { flex: 1, fontSize: FontSize.md, color: Colors.text, paddingVertical: 12 },
  formCard: { backgroundColor: Colors.card, borderRadius: 16, padding: Spacing.lg, marginBottom: Spacing.md, borderWidth: 1, borderColor: Colors.cardBorder },
  formTitle: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.text, marginBottom: Spacing.md },
  formLabel: { fontSize: FontSize.xs, color: Colors.textSecondary, fontWeight: '600', letterSpacing: 1, marginBottom: 6, marginTop: Spacing.sm },
  formInput: { backgroundColor: Colors.surface, borderRadius: 10, paddingHorizontal: Spacing.md, paddingVertical: 12, fontSize: FontSize.md, color: Colors.text, borderWidth: 1, borderColor: Colors.border, marginBottom: Spacing.sm },
  formRow: { flexDirection: 'row', gap: 8, marginBottom: Spacing.sm },
  metalBtn: { flex: 1, alignItems: 'center', paddingVertical: 10, borderRadius: 8, backgroundColor: Colors.surface, borderWidth: 1, borderColor: Colors.border },
  metalBtnActive: { backgroundColor: Colors.gold + '20', borderColor: Colors.gold },
  metalBtnText: { fontSize: FontSize.sm, color: Colors.textMuted, fontWeight: '500', textTransform: 'capitalize' },
  metalBtnTextActive: { color: Colors.gold },
  saveBtn: { backgroundColor: Colors.gold, paddingVertical: 14, borderRadius: 10, alignItems: 'center', marginTop: Spacing.sm },
  saveBtnText: { fontSize: FontSize.sm, fontWeight: '700', color: '#000', letterSpacing: 2 },
  uploadCard: { backgroundColor: Colors.card, borderRadius: 16, padding: Spacing.lg, marginBottom: Spacing.md, borderWidth: 1, borderColor: Colors.borderGold },
  uploadHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  uploadSubtext: { fontSize: FontSize.sm, color: Colors.textSecondary, marginBottom: Spacing.md },
  pickFilesBtn: { alignItems: 'center', paddingVertical: Spacing.lg, borderRadius: 12, borderWidth: 2, borderStyle: 'dashed', borderColor: Colors.gold + '40', backgroundColor: Colors.gold + '08' },
  pickFilesText: { fontSize: FontSize.md, color: Colors.text, fontWeight: '600', marginTop: 8 },
  pickFilesHint: { fontSize: FontSize.xs, color: Colors.textMuted, marginTop: 4 },
  fileList: { marginTop: Spacing.md },
  fileListTitle: { fontSize: FontSize.sm, color: Colors.gold, fontWeight: '600', marginBottom: 8 },
  fileItem: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: Colors.border },
  fileName: { flex: 1, fontSize: FontSize.sm, color: Colors.text },
  fileSize: { fontSize: FontSize.xs, color: Colors.textMuted },
  moreFiles: { fontSize: FontSize.sm, color: Colors.textSecondary, textAlign: 'center', paddingVertical: 8 },
  addMoreBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 10, marginTop: 8, borderRadius: 8, borderWidth: 1, borderColor: Colors.gold + '40' },
  addMoreText: { fontSize: FontSize.sm, color: Colors.gold, fontWeight: '600' },
  progressContainer: { marginTop: Spacing.md },
  progressBar: { height: 8, borderRadius: 4, backgroundColor: Colors.surface, overflow: 'hidden' },
  progressFill: { height: '100%', backgroundColor: Colors.gold, borderRadius: 4 },
  progressText: { fontSize: FontSize.sm, color: Colors.textSecondary, textAlign: 'center', marginTop: 6 },
  uploadResultText: { fontSize: FontSize.sm, color: Colors.success, textAlign: 'center', marginTop: Spacing.sm, fontWeight: '600' },
  uploadBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: Colors.gold, paddingVertical: 14, borderRadius: 10, marginTop: Spacing.md },
  uploadBtnText: { fontSize: FontSize.sm, fontWeight: '700', color: '#000', letterSpacing: 1 },
  sectionTitle: { fontSize: FontSize.xs, color: Colors.textSecondary, letterSpacing: 2, fontWeight: '700', marginTop: Spacing.md, marginBottom: Spacing.md },
  batchCard: { backgroundColor: Colors.card, borderRadius: 14, padding: Spacing.md, marginBottom: Spacing.sm, borderWidth: 1, borderColor: Colors.cardBorder },
  batchHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' },
  batchName: { fontSize: FontSize.md, fontWeight: '700', color: Colors.text, marginBottom: 4 },
  batchMeta: { fontSize: FontSize.xs, color: Colors.textSecondary, textTransform: 'capitalize' },
  batchDate: { fontSize: FontSize.xs, color: Colors.textMuted, marginTop: 2 },
  statusBadge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6 },
  statusText: { fontSize: FontSize.xs, fontWeight: '600', textTransform: 'uppercase' },
  batchActions: { flexDirection: 'row', gap: 8, marginTop: Spacing.sm },
  miniBtn: { flexDirection: 'row', alignItems: 'center', gap: 4, flex: 1, justifyContent: 'center', paddingVertical: 8, borderRadius: 8 },
  miniBtnText: { fontSize: FontSize.xs, fontWeight: '600' },
  emptyState: { alignItems: 'center', paddingVertical: Spacing.xxl },
  emptyText: { fontSize: FontSize.md, color: Colors.textMuted, marginTop: Spacing.md },
  emptyHint: { fontSize: FontSize.sm, color: Colors.textMuted, marginTop: 4 },
});
