import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, Image, ActivityIndicator, Alert, TextInput, Platform } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../src/theme';
import { api, getImageUrl } from '../src/api';

export default function AdminBatchDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [batch, setBatch] = useState<any>(null);
  const [images, setImages] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [selectMode, setSelectMode] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState('');
  const [editMetal, setEditMetal] = useState('');
  const [editCategory, setEditCategory] = useState('');

  // Upload state
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState({ done: 0, total: 0 });

  const loadBatch = useCallback(async () => {
    try {
      const b = await api.get(`/batches/${id}`);
      setBatch(b);
      setEditName(b.name);
      setEditMetal(b.metal_type);
      setEditCategory(b.category);
    } catch (e) { console.error(e); }
  }, [id]);

  const loadImages = useCallback(async (p: number = 1) => {
    try {
      setLoading(true);
      const res = await api.get(`/batches/${id}/images?page=${p}&limit=50`);
      if (p === 1) setImages(res.images || []);
      else setImages(prev => [...prev, ...(res.images || [])]);
      setPage(p);
      setTotalPages(res.pages || 1);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [id]);

  useEffect(() => { loadBatch(); loadImages(1); }, [id]);

  const saveBatchEdit = async () => {
    try {
      await api.put(`/batches/${id}`, { name: editName, metal_type: editMetal, category: editCategory });
      setEditing(false);
      loadBatch();
      loadImages(1);
      Alert.alert('Saved', 'Batch updated');
    } catch (e: any) { Alert.alert('Error', e.message); }
  };

  const toggleSelect = (imgId: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(imgId)) next.delete(imgId);
      else next.add(imgId);
      return next;
    });
  };

  const deleteSelected = () => {
    if (selected.size === 0) return;
    Alert.alert('Delete', `Delete ${selected.size} selected images?`, [
      { text: 'Cancel' },
      { text: 'Delete', style: 'destructive', onPress: async () => {
        try {
          await api.post(`/batches/${id}/images/delete`, { image_ids: Array.from(selected) });
          setSelected(new Set());
          setSelectMode(false);
          loadBatch();
          loadImages(1);
        } catch (e: any) { Alert.alert('Error', e.message); }
      }}
    ]);
  };

  const toggleVisibility = async () => {
    try {
      const res = await api.patch(`/batches/${id}/visibility`);
      Alert.alert('Updated', `Batch is now ${res.status}`);
      loadBatch();
    } catch (e: any) { Alert.alert('Error', e.message); }
  };

  const pickFiles = () => {
    if (Platform.OS === 'web') {
      const input = document.createElement('input');
      input.type = 'file'; input.accept = 'image/*'; input.multiple = true;
      input.onchange = (e: any) => {
        const files = Array.from(e.target.files || []) as File[];
        if (files.length > 0) setSelectedFiles(prev => [...prev, ...files]);
      };
      input.click();
    }
  };

  const startUpload = async () => {
    if (selectedFiles.length === 0) return;
    setUploading(true);
    setUploadProgress({ done: 0, total: selectedFiles.length });
    try {
      await api.uploadFiles(`/batches/${id}/upload`, selectedFiles, (done, total) => setUploadProgress({ done, total }));
      setSelectedFiles([]);
      loadBatch();
      loadImages(1);
      Alert.alert('Success', 'Images uploaded');
    } catch (e: any) { Alert.alert('Error', e.message); }
    finally { setUploading(false); }
  };

  if (!batch && loading) return <View style={styles.loader}><ActivityIndicator size="large" color={Colors.gold} /></View>;

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity testID="batch-detail-back" onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={24} color={Colors.text} />
        </TouchableOpacity>
        <Text style={styles.headerTitle} numberOfLines={1}>{batch?.name || 'Batch'}</Text>
        <TouchableOpacity onPress={() => setEditing(!editing)} style={styles.backBtn}>
          <Ionicons name={editing ? 'close' : 'create'} size={22} color={Colors.gold} />
        </TouchableOpacity>
      </View>

      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.content}>
        {/* Batch Info */}
        {batch && !editing && (
          <View style={styles.infoCard}>
            <View style={styles.infoRow}>
              <Text style={styles.infoLabel}>Metal</Text>
              <Text style={styles.infoValue}>{batch.metal_type}</Text>
            </View>
            <View style={styles.infoRow}>
              <Text style={styles.infoLabel}>Category</Text>
              <Text style={styles.infoValue}>{batch.category || 'None'}</Text>
            </View>
            <View style={styles.infoRow}>
              <Text style={styles.infoLabel}>Images</Text>
              <Text style={styles.infoValue}>{batch.image_count}</Text>
            </View>
            <View style={styles.infoRow}>
              <Text style={styles.infoLabel}>Status</Text>
              <Text style={[styles.infoValue, { color: batch.status === 'visible' ? Colors.success : Colors.warning }]}>{batch.status}</Text>
            </View>
            <View style={styles.infoActions}>
              <TouchableOpacity style={[styles.infoBtn, { backgroundColor: Colors.gold + '20' }]} onPress={pickFiles}>
                <Ionicons name="cloud-upload" size={16} color={Colors.gold} />
                <Text style={[styles.infoBtnText, { color: Colors.gold }]}>Upload More</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[styles.infoBtn, { backgroundColor: batch.status === 'visible' ? Colors.warning + '20' : Colors.success + '20' }]} onPress={toggleVisibility}>
                <Ionicons name={batch.status === 'visible' ? 'eye-off' : 'eye'} size={16} color={batch.status === 'visible' ? Colors.warning : Colors.success} />
                <Text style={[styles.infoBtnText, { color: batch.status === 'visible' ? Colors.warning : Colors.success }]}>
                  {batch.status === 'visible' ? 'Hide' : 'Show'}
                </Text>
              </TouchableOpacity>
            </View>
          </View>
        )}

        {/* Edit Mode */}
        {editing && (
          <View style={styles.editCard}>
            <Text style={styles.editTitle}>Edit Batch</Text>
            <TextInput style={styles.formInput} value={editName} onChangeText={setEditName} placeholder="Batch Name" placeholderTextColor={Colors.textMuted} />
            <View style={styles.formRow}>
              {['silver', 'gold', 'diamond'].map(m => (
                <TouchableOpacity key={m} style={[styles.metalBtn, editMetal === m && styles.metalBtnActive]} onPress={() => setEditMetal(m)}>
                  <Text style={[styles.metalBtnText, editMetal === m && styles.metalBtnTextActive]}>{m}</Text>
                </TouchableOpacity>
              ))}
            </View>
            <TextInput style={styles.formInput} value={editCategory} onChangeText={setEditCategory} placeholder="Category" placeholderTextColor={Colors.textMuted} />
            <TouchableOpacity style={styles.saveBtn} onPress={saveBatchEdit}>
              <Text style={styles.saveBtnText}>SAVE CHANGES</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Upload area */}
        {selectedFiles.length > 0 && (
          <View style={styles.uploadCard}>
            <Text style={styles.uploadTitle}>{selectedFiles.length} files ready</Text>
            {uploading && (
              <View style={styles.progressBar}>
                <View style={[styles.progressFill, { width: `${(uploadProgress.done / Math.max(uploadProgress.total, 1)) * 100}%` }]} />
              </View>
            )}
            {!uploading && (
              <View style={styles.uploadActions}>
                <TouchableOpacity style={styles.uploadBtn} onPress={startUpload}>
                  <Text style={styles.uploadBtnText}>UPLOAD NOW</Text>
                </TouchableOpacity>
                <TouchableOpacity onPress={() => setSelectedFiles([])}>
                  <Text style={styles.clearText}>Clear</Text>
                </TouchableOpacity>
              </View>
            )}
          </View>
        )}

        {/* Selection toolbar */}
        <View style={styles.toolbar}>
          <TouchableOpacity style={styles.toolBtn} onPress={() => { setSelectMode(!selectMode); setSelected(new Set()); }}>
            <Ionicons name={selectMode ? 'close' : 'checkbox-outline'} size={18} color={selectMode ? Colors.warning : Colors.textSecondary} />
            <Text style={[styles.toolBtnText, selectMode && { color: Colors.warning }]}>{selectMode ? 'Cancel' : 'Select'}</Text>
          </TouchableOpacity>
          {selectMode && selected.size > 0 && (
            <TouchableOpacity style={[styles.toolBtn, { backgroundColor: Colors.error + '20' }]} onPress={deleteSelected}>
              <Ionicons name="trash" size={16} color={Colors.error} />
              <Text style={[styles.toolBtnText, { color: Colors.error }]}>Delete {selected.size}</Text>
            </TouchableOpacity>
          )}
        </View>

        {/* Image Grid */}
        <View style={styles.imageGrid}>
          {images.map(img => {
            const uri = getImageUrl(img, true);
            const isSelected = selected.has(img.id);
            return (
              <TouchableOpacity
                key={img.id}
                testID={`batch-img-${img.id}`}
                style={[styles.gridItem, isSelected && styles.gridItemSelected]}
                onPress={() => {
                  if (selectMode) toggleSelect(img.id);
                  else router.push({ pathname: '/image-viewer', params: { productId: img.id, batchId: id } });
                }}
                onLongPress={() => { if (!selectMode) { setSelectMode(true); toggleSelect(img.id); } }}
              >
                <Image source={{ uri }} style={styles.gridImage} />
                {selectMode && (
                  <View style={[styles.checkbox, isSelected && styles.checkboxActive]}>
                    {isSelected && <Ionicons name="checkmark" size={14} color="#000" />}
                  </View>
                )}
              </TouchableOpacity>
            );
          })}
        </View>

        {page < totalPages && !loading && (
          <TouchableOpacity style={styles.loadMoreBtn} onPress={() => loadImages(page + 1)}>
            <Text style={styles.loadMoreText}>Load More</Text>
          </TouchableOpacity>
        )}

        {loading && images.length > 0 && <ActivityIndicator color={Colors.gold} style={{ padding: 20 }} />}

        {!loading && images.length === 0 && (
          <View style={styles.emptyState}>
            <Ionicons name="images" size={48} color={Colors.textMuted} />
            <Text style={styles.emptyText}>No images in this batch</Text>
            <TouchableOpacity style={styles.emptyUploadBtn} onPress={pickFiles}>
              <Text style={styles.emptyUploadText}>Upload Images</Text>
            </TouchableOpacity>
          </View>
        )}

        <View style={{ height: 40 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  loader: { flex: 1, backgroundColor: Colors.background, justifyContent: 'center', alignItems: 'center' },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: Spacing.lg, paddingVertical: Spacing.md },
  backBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: Colors.surface, alignItems: 'center', justifyContent: 'center' },
  headerTitle: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.text, flex: 1, textAlign: 'center', marginHorizontal: 8 },
  content: { paddingHorizontal: Spacing.lg },
  infoCard: { backgroundColor: Colors.card, borderRadius: 14, padding: Spacing.md, marginBottom: Spacing.md, borderWidth: 1, borderColor: Colors.cardBorder },
  infoRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: Colors.border },
  infoLabel: { fontSize: FontSize.sm, color: Colors.textMuted },
  infoValue: { fontSize: FontSize.sm, color: Colors.text, fontWeight: '600', textTransform: 'capitalize' },
  infoActions: { flexDirection: 'row', gap: 8, marginTop: Spacing.md },
  infoBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 10, borderRadius: 8 },
  infoBtnText: { fontSize: FontSize.sm, fontWeight: '600' },
  editCard: { backgroundColor: Colors.card, borderRadius: 14, padding: Spacing.lg, marginBottom: Spacing.md, borderWidth: 1, borderColor: Colors.borderGold },
  editTitle: { fontSize: FontSize.md, fontWeight: '700', color: Colors.text, marginBottom: Spacing.md },
  formInput: { backgroundColor: Colors.surface, borderRadius: 10, paddingHorizontal: Spacing.md, paddingVertical: 12, fontSize: FontSize.md, color: Colors.text, borderWidth: 1, borderColor: Colors.border, marginBottom: Spacing.sm },
  formRow: { flexDirection: 'row', gap: 8, marginBottom: Spacing.sm },
  metalBtn: { flex: 1, alignItems: 'center', paddingVertical: 10, borderRadius: 8, backgroundColor: Colors.surface, borderWidth: 1, borderColor: Colors.border },
  metalBtnActive: { backgroundColor: Colors.gold + '20', borderColor: Colors.gold },
  metalBtnText: { fontSize: FontSize.sm, color: Colors.textMuted, fontWeight: '500', textTransform: 'capitalize' },
  metalBtnTextActive: { color: Colors.gold },
  saveBtn: { backgroundColor: Colors.gold, paddingVertical: 14, borderRadius: 10, alignItems: 'center', marginTop: Spacing.sm },
  saveBtnText: { fontSize: FontSize.sm, fontWeight: '700', color: '#000', letterSpacing: 2 },
  uploadCard: { backgroundColor: Colors.card, borderRadius: 14, padding: Spacing.md, marginBottom: Spacing.md, borderWidth: 1, borderColor: Colors.borderGold },
  uploadTitle: { fontSize: FontSize.sm, color: Colors.gold, fontWeight: '600', marginBottom: 8 },
  progressBar: { height: 6, borderRadius: 3, backgroundColor: Colors.surface, overflow: 'hidden' },
  progressFill: { height: '100%', backgroundColor: Colors.gold, borderRadius: 3 },
  uploadActions: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 8 },
  uploadBtn: { backgroundColor: Colors.gold, paddingHorizontal: 20, paddingVertical: 10, borderRadius: 8 },
  uploadBtnText: { fontSize: FontSize.sm, fontWeight: '700', color: '#000' },
  clearText: { fontSize: FontSize.sm, color: Colors.error },
  toolbar: { flexDirection: 'row', gap: 8, marginBottom: Spacing.md },
  toolBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8, backgroundColor: Colors.surface },
  toolBtnText: { fontSize: FontSize.sm, color: Colors.textSecondary, fontWeight: '500' },
  imageGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 4 },
  gridItem: { width: '32%', aspectRatio: 1, borderRadius: 8, overflow: 'hidden', backgroundColor: Colors.surface },
  gridItemSelected: { borderWidth: 2, borderColor: Colors.gold },
  gridImage: { width: '100%', height: '100%' },
  checkbox: { position: 'absolute', top: 6, right: 6, width: 22, height: 22, borderRadius: 11, borderWidth: 2, borderColor: '#fff', backgroundColor: 'rgba(0,0,0,0.4)', alignItems: 'center', justifyContent: 'center' },
  checkboxActive: { backgroundColor: Colors.gold, borderColor: Colors.gold },
  loadMoreBtn: { alignItems: 'center', paddingVertical: 14, marginTop: Spacing.md },
  loadMoreText: { fontSize: FontSize.sm, color: Colors.gold, fontWeight: '600' },
  emptyState: { alignItems: 'center', paddingVertical: Spacing.xxl },
  emptyText: { fontSize: FontSize.md, color: Colors.textMuted, marginTop: Spacing.md },
  emptyUploadBtn: { marginTop: Spacing.md, backgroundColor: Colors.gold, paddingHorizontal: 24, paddingVertical: 12, borderRadius: 10 },
  emptyUploadText: { fontSize: FontSize.sm, fontWeight: '700', color: '#000' },
});
