import React, { useState, useEffect } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, Image, ActivityIndicator, ScrollView, Platform, Dimensions } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../src/theme';
import { api, getImageUrl } from '../src/api';

const { width: SW } = Dimensions.get('window');
const PREVIEW_SIZE = SW - 48;
const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';

export default function TryOnScreen() {
  const { productId } = useLocalSearchParams<{ productId?: string }>();
  const router = useRouter();
  const [product, setProduct] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [userPhotoB64, setUserPhotoB64] = useState<string | null>(null);
  const [userPhotoUri, setUserPhotoUri] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [bodyArea, setBodyArea] = useState('auto');
  const [scale, setScale] = useState(0.45);
  const [posY, setPosY] = useState(0.25);
  const [showOriginal, setShowOriginal] = useState(false);

  useEffect(() => {
    if (productId) {
      (async () => {
        try {
          const p = await api.get(`/products/${productId}`);
          setProduct(p);
        } catch {} finally { setLoading(false); }
      })();
    } else { setLoading(false); }
  }, [productId]);

  const pickPhoto = () => {
    if (Platform.OS === 'web') {
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = 'image/*';
      input.onchange = (e: any) => {
        const file = e.target.files?.[0];
        if (file) {
          const reader = new FileReader();
          reader.onload = () => {
            const full = reader.result as string;
            setUserPhotoUri(full);
            setUserPhotoB64(full.split(',')[1]);
            setResultUrl(null);
            setError('');
          };
          reader.readAsDataURL(file);
        }
      };
      input.click();
    }
  };

  const generateTryOn = async () => {
    if (!product || !userPhotoB64) return;
    setGenerating(true);
    setError('');
    setResultUrl(null);
    try {
      const res = await api.post('/ai/try-on', {
        product_id: product.id,
        user_photo_base64: userPhotoB64,
        body_area: bodyArea,
        scale: scale,
        offset_x: 0.5,
        offset_y: posY,
      });
      if (res.image_url) {
        setResultUrl(`${BACKEND}${res.image_url}`);
      }
    } catch (e: any) {
      setError(e.message || 'Failed to generate try-on');
    } finally {
      setGenerating(false);
    }
  };

  // Auto-generate when photo is uploaded
  useEffect(() => {
    if (userPhotoB64 && product) generateTryOn();
  }, [userPhotoB64]);

  const bodyHint = (() => {
    const cat = (product?.category || '').toLowerCase();
    if (['necklace', 'chain', 'pendant'].includes(cat)) return 'Upload a photo of your neck/chest area';
    if (['earrings', 'nose_ring'].includes(cat)) return 'Upload a photo showing your face/ears';
    if (['bracelet', 'kadaa', 'bangles'].includes(cat)) return 'Upload a photo of your wrist/hand';
    if (cat === 'payal') return 'Upload a photo of your ankle area';
    return 'Upload a photo where you want to see this jewellery worn';
  })();

  if (loading) return <View style={s.loader}><ActivityIndicator size="large" color={Colors.gold} /></View>;

  const productImgUri = product ? getImageUrl(product, false) : '';
  const bodyAreas = [
    { key: 'neck', label: 'Neck/Chest' },
    { key: 'wrist', label: 'Wrist/Hand' },
    { key: 'ear', label: 'Face/Ears' },
    { key: 'ankle', label: 'Ankle' },
  ];

  return (
    <SafeAreaView style={s.container} edges={['top']}>
      <ScrollView showsVerticalScrollIndicator={false}>
        {/* Header */}
        <View style={s.header}>
          <TouchableOpacity onPress={() => router.back()} style={s.backBtn}>
            <Ionicons name="arrow-back" size={24} color={Colors.text} />
          </TouchableOpacity>
          <Text style={s.headerTitle}>AI Try-On</Text>
          <View style={{ width: 44 }} />
        </View>

        {/* Product being tried on */}
        {product && (
          <View style={s.productCard}>
            <Image source={{ uri: productImgUri }} style={s.productThumb} />
            <View style={{ flex: 1 }}>
              <Text style={s.productTitle} numberOfLines={2}>{product.title}</Text>
              <Text style={s.productMeta}>{product.metal_type} {product.category ? `• ${product.category.replace(/_/g, ' ')}` : ''}</Text>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 4 }}>
                <Ionicons name="checkmark-circle" size={14} color={Colors.pastelGreen} />
                <Text style={{ fontSize: FontSize.xs, color: Colors.pastelGreen, fontWeight: '600' }}>This exact product will be used</Text>
              </View>
            </View>
          </View>
        )}

        {/* Body area selection */}
        <View style={s.section}>
          <Text style={s.stepLabel}>PLACEMENT AREA</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false}>
            <View style={{ flexDirection: 'row', gap: 8 }}>
              {bodyAreas.map(ba => (
                <TouchableOpacity key={ba.key} style={[s.areaChip, bodyArea === ba.key && s.areaChipActive]} onPress={() => { setBodyArea(ba.key); if (userPhotoB64) generateTryOn(); }}>
                  <Text style={[s.areaChipText, bodyArea === ba.key && { color: Colors.gold }]}>{ba.label}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </ScrollView>
        </View>

        {/* Upload photo */}
        {!userPhotoB64 && (
          <View style={s.section}>
            <Text style={s.stepLabel}>UPLOAD YOUR PHOTO</Text>
            <Text style={s.hint}>{bodyHint}</Text>
            <TouchableOpacity style={s.uploadBox} onPress={pickPhoto} data-testid="tryon-upload-btn">
              <Ionicons name="camera" size={44} color={Colors.gold} />
              <Text style={s.uploadText}>Take Photo or Upload</Text>
              <Text style={s.uploadSub}>Your exact photo will be preserved — no AI replacement</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Generating state */}
        {generating && (
          <View style={s.genBox}>
            <ActivityIndicator size="large" color={Colors.gold} />
            <Text style={s.genTitle}>Creating Try-On Preview...</Text>
            <Text style={s.genSub}>Cutting out product + compositing on your photo</Text>
            <View style={s.genChecks}>
              <Text style={s.genCheck}>Using your exact uploaded photo</Text>
              <Text style={s.genCheck}>Using the exact selected product image</Text>
              <Text style={s.genCheck}>Removing product background</Text>
              <Text style={s.genCheck}>Adding realistic shadows & blending</Text>
            </View>
          </View>
        )}

        {/* Result */}
        {resultUrl && !generating && (
          <View style={s.section}>
            <Text style={s.stepLabel}>YOUR TRY-ON PREVIEW</Text>

            {/* Before / After toggle */}
            <View style={[s.previewBox, { width: PREVIEW_SIZE, height: PREVIEW_SIZE }]}>
              <Image
                source={{ uri: showOriginal ? userPhotoUri! : resultUrl }}
                style={s.previewImg}
                resizeMode="cover"
                data-testid="tryon-result"
              />
              <View style={s.previewLabel}>
                <Text style={s.previewLabelText}>{showOriginal ? 'YOUR ORIGINAL PHOTO' : 'TRY-ON PREVIEW'}</Text>
              </View>
            </View>

            {/* Before/After toggle */}
            <TouchableOpacity style={s.compareBtn} onPress={() => setShowOriginal(!showOriginal)}>
              <Ionicons name={showOriginal ? 'eye' : 'eye-off'} size={18} color={Colors.gold} />
              <Text style={s.compareBtnText}>{showOriginal ? 'Show Try-On Result' : 'Show Original Photo (Compare)'}</Text>
            </TouchableOpacity>

            {/* Size/Position adjustments */}
            <Text style={s.controlTitle}>Adjust Placement</Text>
            <View style={s.controlRow}>
              <Text style={s.controlLabel}>Size</Text>
              <TouchableOpacity style={s.ctrlBtn} onPress={() => { setScale(Math.max(0.15, scale - 0.05)); }}><Ionicons name="remove" size={20} color={Colors.text} /></TouchableOpacity>
              <Text style={s.ctrlValue}>{Math.round(scale * 100)}%</Text>
              <TouchableOpacity style={s.ctrlBtn} onPress={() => { setScale(Math.min(0.9, scale + 0.05)); }}><Ionicons name="add" size={20} color={Colors.text} /></TouchableOpacity>
            </View>
            <View style={s.controlRow}>
              <Text style={s.controlLabel}>Position</Text>
              <TouchableOpacity style={s.ctrlBtn} onPress={() => { setPosY(Math.max(0, posY - 0.05)); }}><Ionicons name="arrow-up" size={20} color={Colors.text} /></TouchableOpacity>
              <Text style={s.ctrlValue}>{Math.round(posY * 100)}%</Text>
              <TouchableOpacity style={s.ctrlBtn} onPress={() => { setPosY(Math.min(0.8, posY + 0.05)); }}><Ionicons name="arrow-down" size={20} color={Colors.text} /></TouchableOpacity>
            </View>

            {/* Regenerate with adjustments */}
            <TouchableOpacity style={s.regenBtn} onPress={generateTryOn} disabled={generating}>
              <Ionicons name="refresh" size={18} color="#000" />
              <Text style={s.regenBtnText}>Regenerate with Adjustments</Text>
            </TouchableOpacity>

            {/* Actions */}
            <View style={s.actionRow}>
              <TouchableOpacity style={s.actionBtn} onPress={pickPhoto}>
                <Ionicons name="camera" size={16} color={Colors.gold} />
                <Text style={s.actionBtnText}>New Photo</Text>
              </TouchableOpacity>
              <TouchableOpacity style={s.actionBtn} onPress={() => router.back()}>
                <Ionicons name="arrow-back" size={16} color={Colors.gold} />
                <Text style={s.actionBtnText}>Back to Product</Text>
              </TouchableOpacity>
            </View>
          </View>
        )}

        {/* Error */}
        {error ? (
          <View style={s.errorBox}>
            <Ionicons name="alert-circle" size={20} color={Colors.error} />
            <Text style={s.errorText}>{error}</Text>
            <TouchableOpacity onPress={generateTryOn} style={s.retryBtn}>
              <Text style={s.retryText}>Retry</Text>
            </TouchableOpacity>
          </View>
        ) : null}

        <View style={{ height: 40 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  loader: { flex: 1, backgroundColor: Colors.background, justifyContent: 'center', alignItems: 'center' },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: Spacing.lg, paddingVertical: Spacing.md },
  backBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: Colors.surface, alignItems: 'center', justifyContent: 'center' },
  headerTitle: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.text },
  productCard: { flexDirection: 'row', alignItems: 'center', marginHorizontal: Spacing.lg, padding: Spacing.md, backgroundColor: Colors.card, borderRadius: 14, gap: 12, borderWidth: 1, borderColor: Colors.borderGold },
  productThumb: { width: 64, height: 64, borderRadius: 10, backgroundColor: Colors.surface },
  productTitle: { fontSize: FontSize.md, fontWeight: '600', color: Colors.text },
  productMeta: { fontSize: FontSize.sm, color: Colors.textSecondary, marginTop: 2, textTransform: 'capitalize' },
  section: { marginTop: Spacing.lg, paddingHorizontal: Spacing.lg },
  stepLabel: { fontSize: FontSize.xs, fontWeight: '700', color: Colors.gold, letterSpacing: 2, marginBottom: Spacing.sm },
  hint: { fontSize: FontSize.sm, color: Colors.textMuted, marginBottom: Spacing.md },
  areaChip: { paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10, backgroundColor: Colors.surface, borderWidth: 1, borderColor: Colors.border },
  areaChipActive: { backgroundColor: Colors.gold + '15', borderColor: Colors.gold },
  areaChipText: { fontSize: FontSize.sm, color: Colors.textMuted, fontWeight: '600' },
  uploadBox: { alignItems: 'center', justifyContent: 'center', paddingVertical: 44, borderRadius: 16, borderWidth: 2, borderColor: Colors.gold + '40', borderStyle: 'dashed', backgroundColor: Colors.card },
  uploadText: { color: Colors.text, fontSize: FontSize.md, fontWeight: '700', marginTop: Spacing.sm },
  uploadSub: { color: Colors.pastelGreen, fontSize: FontSize.xs, marginTop: 4, fontWeight: '500' },
  genBox: { alignItems: 'center', paddingVertical: Spacing.xl, marginHorizontal: Spacing.lg, marginTop: Spacing.lg, backgroundColor: Colors.card, borderRadius: 16, borderWidth: 1, borderColor: Colors.borderGold },
  genTitle: { fontSize: FontSize.md, fontWeight: '700', color: Colors.gold, marginTop: Spacing.md },
  genSub: { fontSize: FontSize.sm, color: Colors.textMuted, marginTop: 4 },
  genChecks: { marginTop: Spacing.md, gap: 4 },
  genCheck: { fontSize: FontSize.xs, color: Colors.pastelGreen, fontWeight: '500' },
  previewBox: { borderRadius: 16, overflow: 'hidden', alignSelf: 'center', backgroundColor: Colors.surface },
  previewImg: { width: '100%', height: '100%' },
  previewLabel: { position: 'absolute', top: 10, left: 10, backgroundColor: 'rgba(0,0,0,0.6)', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6 },
  previewLabelText: { fontSize: 9, color: '#fff', fontWeight: '700', letterSpacing: 1 },
  compareBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, marginTop: Spacing.md, paddingVertical: 12, backgroundColor: Colors.surface, borderRadius: 10, borderWidth: 1, borderColor: Colors.borderGold },
  compareBtnText: { color: Colors.gold, fontSize: FontSize.sm, fontWeight: '600' },
  controlTitle: { fontSize: FontSize.xs, fontWeight: '700', color: Colors.textMuted, letterSpacing: 1, marginTop: Spacing.lg, marginBottom: 8 },
  controlRow: { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 8 },
  controlLabel: { fontSize: FontSize.sm, color: Colors.textSecondary, width: 60 },
  ctrlBtn: { width: 40, height: 40, borderRadius: 10, backgroundColor: Colors.surface, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: Colors.border },
  ctrlValue: { fontSize: FontSize.md, fontWeight: '700', color: Colors.gold, width: 50, textAlign: 'center' },
  regenBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: Colors.gold, paddingVertical: 14, borderRadius: 12, marginTop: Spacing.md },
  regenBtnText: { fontSize: FontSize.md, fontWeight: '700', color: '#000' },
  actionRow: { flexDirection: 'row', gap: 12, marginTop: Spacing.md },
  actionBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, backgroundColor: Colors.surface, paddingVertical: 12, borderRadius: 10, borderWidth: 1, borderColor: Colors.borderGold },
  actionBtnText: { color: Colors.gold, fontSize: FontSize.sm, fontWeight: '600' },
  errorBox: { flexDirection: 'row', alignItems: 'center', gap: 8, marginHorizontal: Spacing.lg, marginTop: Spacing.md, padding: Spacing.md, backgroundColor: Colors.error + '15', borderRadius: 12 },
  errorText: { color: Colors.error, fontSize: FontSize.sm, flex: 1 },
  retryBtn: { backgroundColor: Colors.error + '20', paddingHorizontal: 12, paddingVertical: 6, borderRadius: 6 },
  retryText: { color: Colors.error, fontSize: FontSize.sm, fontWeight: '600' },
});
