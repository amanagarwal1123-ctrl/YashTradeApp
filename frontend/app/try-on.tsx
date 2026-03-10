import React, { useState, useEffect, useRef } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, Image, ActivityIndicator, ScrollView, Platform, Dimensions } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../src/theme';
import { api, getImageUrl } from '../src/api';

const { width: SW } = Dimensions.get('window');
const CANVAS_SIZE = SW - 48;

export default function TryOnScreen() {
  const { productId } = useLocalSearchParams<{ productId?: string }>();
  const router = useRouter();
  const [product, setProduct] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [userPhotoUri, setUserPhotoUri] = useState<string | null>(null);
  const [productImageUri, setProductImageUri] = useState<string | null>(null);
  const [step, setStep] = useState<'photo' | 'position' | 'result'>('photo');
  const [showOverlay, setShowOverlay] = useState(true);

  // Overlay position/size controls
  const [overlayX, setOverlayX] = useState(0.25); // 0-1 fraction of canvas
  const [overlayY, setOverlayY] = useState(0.15);
  const [overlayScale, setOverlayScale] = useState(0.5); // 0.1 - 1.0
  const [savedComposite, setSavedComposite] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (productId) {
      (async () => {
        try {
          const p = await api.get(`/products/${productId}`);
          setProduct(p);
          setProductImageUri(getImageUrl(p, false));
        } catch {} finally { setLoading(false); }
      })();
    } else { setLoading(false); }
  }, [productId]);

  const pickPhoto = () => {
    if (Platform.OS === 'web') {
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = 'image/*';
      input.capture = 'user';
      input.onchange = (e: any) => {
        const file = e.target.files?.[0];
        if (file) {
          const reader = new FileReader();
          reader.onload = () => {
            setUserPhotoUri(reader.result as string);
            setStep('position');
          };
          reader.readAsDataURL(file);
        }
      };
      input.click();
    }
  };

  // Compose on web canvas
  const saveComposite = async () => {
    if (Platform.OS !== 'web' || !userPhotoUri || !productImageUri) return;
    setSaving(true);
    try {
      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      const size = 800;
      canvas.width = size;
      canvas.height = size;

      // Draw user photo
      const userImg = new window.Image();
      userImg.crossOrigin = 'anonymous';
      await new Promise<void>((resolve, reject) => {
        userImg.onload = () => resolve();
        userImg.onerror = reject;
        userImg.src = userPhotoUri;
      });
      // Cover fill
      const ur = userImg.width / userImg.height;
      let sx = 0, sy = 0, sw = userImg.width, sh = userImg.height;
      if (ur > 1) { sx = (userImg.width - userImg.height) / 2; sw = userImg.height; }
      else { sy = (userImg.height - userImg.width) / 2; sh = userImg.width; }
      ctx.drawImage(userImg, sx, sy, sw, sh, 0, 0, size, size);

      // Draw product overlay
      const prodImg = new window.Image();
      prodImg.crossOrigin = 'anonymous';
      await new Promise<void>((resolve, reject) => {
        prodImg.onload = () => resolve();
        prodImg.onerror = reject;
        prodImg.src = productImageUri;
      });
      const prodW = size * overlayScale;
      const prodH = (prodImg.height / prodImg.width) * prodW;
      const px = overlayX * size;
      const py = overlayY * size;
      ctx.drawImage(prodImg, px, py, prodW, prodH);

      const dataUrl = canvas.toDataURL('image/jpeg', 0.9);
      setSavedComposite(dataUrl);
      setStep('result');
    } catch (e) {
      console.error('Composite error:', e);
    } finally {
      setSaving(false);
    }
  };

  const bodyHint = (() => {
    const cat = (product?.category || '').toLowerCase();
    if (['necklace', 'chain', 'pendant'].includes(cat)) return 'Take a photo of your neck/chest area';
    if (['earrings', 'nose_ring'].includes(cat)) return 'Take a photo of your face showing ears';
    if (['bracelet', 'kadaa', 'bangles'].includes(cat)) return 'Take a photo of your wrist/hand';
    if (cat === 'payal') return 'Take a photo of your ankle';
    if (['ring', 'toe_rings'].includes(cat)) return 'Take a photo of your finger/hand';
    return 'Take a photo where you want to see this jewellery';
  })();

  if (loading) return <View style={s.loader}><ActivityIndicator size="large" color={Colors.gold} /></View>;

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

        {/* Product info */}
        {product && (
          <View style={s.productCard}>
            <Image source={{ uri: productImageUri || '' }} style={s.productThumb} />
            <View style={s.productInfo}>
              <Text style={s.productTitle} numberOfLines={2}>{product.title}</Text>
              <Text style={s.productMeta}>{product.metal_type} {product.category ? `• ${product.category.replace(/_/g, ' ')}` : ''}</Text>
              <Text style={s.productHint}>This exact product will be placed on your photo</Text>
            </View>
          </View>
        )}

        {/* STEP 1: Upload Photo */}
        {step === 'photo' && (
          <View style={s.section}>
            <Text style={s.stepLabel}>STEP 1: Upload Your Photo</Text>
            <Text style={s.hint}>{bodyHint}</Text>
            <TouchableOpacity style={s.uploadBox} onPress={pickPhoto} data-testid="tryon-upload-btn">
              <Ionicons name="camera" size={44} color={Colors.gold} />
              <Text style={s.uploadText}>Tap to take photo or upload</Text>
              <Text style={s.uploadSubtext}>Your exact photo will be used — no AI replacement</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* STEP 2: Position the jewellery */}
        {step === 'position' && userPhotoUri && productImageUri && (
          <View style={s.section}>
            <Text style={s.stepLabel}>STEP 2: Position the Jewellery</Text>
            <Text style={s.hint}>Use controls below to place the exact product on your photo</Text>

            {/* Preview canvas */}
            <View style={[s.canvasBox, { width: CANVAS_SIZE, height: CANVAS_SIZE }]}>
              {/* User photo as background */}
              <Image source={{ uri: userPhotoUri }} style={s.canvasBackground} />
              {/* Product overlay */}
              {showOverlay && (
                <Image
                  source={{ uri: productImageUri }}
                  style={{
                    position: 'absolute',
                    left: overlayX * CANVAS_SIZE,
                    top: overlayY * CANVAS_SIZE,
                    width: CANVAS_SIZE * overlayScale,
                    height: CANVAS_SIZE * overlayScale,
                    resizeMode: 'contain',
                  }}
                  data-testid="tryon-overlay"
                />
              )}
            </View>

            {/* Toggle overlay */}
            <TouchableOpacity style={s.toggleBtn} onPress={() => setShowOverlay(!showOverlay)}>
              <Ionicons name={showOverlay ? 'eye' : 'eye-off'} size={18} color={Colors.gold} />
              <Text style={s.toggleText}>{showOverlay ? 'Hide jewellery (compare)' : 'Show jewellery'}</Text>
            </TouchableOpacity>

            {/* Position controls */}
            <Text style={s.controlLabel}>Move Position</Text>
            <View style={s.controlRow}>
              <TouchableOpacity style={s.ctrlBtn} onPress={() => setOverlayY(Math.max(0, overlayY - 0.03))}><Ionicons name="arrow-up" size={22} color={Colors.text} /></TouchableOpacity>
              <TouchableOpacity style={s.ctrlBtn} onPress={() => setOverlayY(Math.min(0.8, overlayY + 0.03))}><Ionicons name="arrow-down" size={22} color={Colors.text} /></TouchableOpacity>
              <TouchableOpacity style={s.ctrlBtn} onPress={() => setOverlayX(Math.max(0, overlayX - 0.03))}><Ionicons name="arrow-back" size={22} color={Colors.text} /></TouchableOpacity>
              <TouchableOpacity style={s.ctrlBtn} onPress={() => setOverlayX(Math.min(0.8, overlayX + 0.03))}><Ionicons name="arrow-forward" size={22} color={Colors.text} /></TouchableOpacity>
            </View>

            <Text style={s.controlLabel}>Resize</Text>
            <View style={s.controlRow}>
              <TouchableOpacity style={s.ctrlBtn} onPress={() => setOverlayScale(Math.max(0.1, overlayScale - 0.05))}>
                <Ionicons name="remove" size={22} color={Colors.text} />
              </TouchableOpacity>
              <Text style={s.sizeText}>{Math.round(overlayScale * 100)}%</Text>
              <TouchableOpacity style={s.ctrlBtn} onPress={() => setOverlayScale(Math.min(1.0, overlayScale + 0.05))}>
                <Ionicons name="add" size={22} color={Colors.text} />
              </TouchableOpacity>
            </View>

            {/* Actions */}
            <View style={s.actionRow}>
              <TouchableOpacity style={s.secondaryBtn} onPress={() => { setUserPhotoUri(null); setStep('photo'); }}>
                <Ionicons name="camera" size={16} color={Colors.gold} />
                <Text style={s.secondaryBtnText}>Change Photo</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[s.primaryBtn, saving && { opacity: 0.5 }]} onPress={saveComposite} disabled={saving}>
                {saving ? <ActivityIndicator color="#000" size="small" /> : (
                  <>
                    <Ionicons name="checkmark-circle" size={18} color="#000" />
                    <Text style={s.primaryBtnText}>Save Preview</Text>
                  </>
                )}
              </TouchableOpacity>
            </View>
          </View>
        )}

        {/* STEP 3: Result */}
        {step === 'result' && savedComposite && (
          <View style={s.section}>
            <Text style={s.stepLabel}>YOUR TRY-ON PREVIEW</Text>

            <View style={[s.canvasBox, { width: CANVAS_SIZE, height: CANVAS_SIZE }]}>
              <Image source={{ uri: savedComposite }} style={s.canvasBackground} />
            </View>

            <View style={[s.actionRow, { marginTop: Spacing.lg }]}>
              <TouchableOpacity style={s.secondaryBtn} onPress={() => setStep('position')}>
                <Ionicons name="create" size={16} color={Colors.gold} />
                <Text style={s.secondaryBtnText}>Adjust</Text>
              </TouchableOpacity>
              <TouchableOpacity style={s.secondaryBtn} onPress={() => { setUserPhotoUri(null); setSavedComposite(null); setStep('photo'); }}>
                <Ionicons name="camera" size={16} color={Colors.gold} />
                <Text style={s.secondaryBtnText}>New Photo</Text>
              </TouchableOpacity>
            </View>

            <View style={s.successBanner}>
              <Ionicons name="checkmark-circle" size={20} color={Colors.success} />
              <Text style={s.successText}>Preview saved! Your exact photo + exact product.</Text>
            </View>
          </View>
        )}

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
  productThumb: { width: 60, height: 60, borderRadius: 10, backgroundColor: Colors.surface },
  productInfo: { flex: 1 },
  productTitle: { fontSize: FontSize.md, fontWeight: '600', color: Colors.text },
  productMeta: { fontSize: FontSize.sm, color: Colors.textSecondary, marginTop: 2, textTransform: 'capitalize' },
  productHint: { fontSize: FontSize.xs, color: Colors.pastelGreen, marginTop: 4, fontWeight: '600' },
  section: { marginTop: Spacing.lg, paddingHorizontal: Spacing.lg },
  stepLabel: { fontSize: FontSize.xs, fontWeight: '700', color: Colors.gold, letterSpacing: 2, marginBottom: Spacing.sm },
  hint: { fontSize: FontSize.sm, color: Colors.textMuted, marginBottom: Spacing.md, lineHeight: 20 },
  uploadBox: { alignItems: 'center', justifyContent: 'center', paddingVertical: 44, borderRadius: 16, borderWidth: 2, borderColor: Colors.gold + '40', borderStyle: 'dashed', backgroundColor: Colors.card },
  uploadText: { color: Colors.text, fontSize: FontSize.md, fontWeight: '600', marginTop: Spacing.sm },
  uploadSubtext: { color: Colors.pastelGreen, fontSize: FontSize.xs, marginTop: 4, fontWeight: '500' },
  canvasBox: { borderRadius: 16, overflow: 'hidden', backgroundColor: Colors.surface, alignSelf: 'center' },
  canvasBackground: { width: '100%', height: '100%', resizeMode: 'cover' },
  toggleBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, marginTop: Spacing.md, paddingVertical: 10, backgroundColor: Colors.surface, borderRadius: 10, borderWidth: 1, borderColor: Colors.borderGold },
  toggleText: { color: Colors.gold, fontSize: FontSize.sm, fontWeight: '600' },
  controlLabel: { fontSize: FontSize.xs, color: Colors.textMuted, fontWeight: '700', letterSpacing: 1, marginTop: Spacing.md, marginBottom: 6 },
  controlRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 12 },
  ctrlBtn: { width: 44, height: 44, borderRadius: 10, backgroundColor: Colors.surface, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: Colors.border },
  sizeText: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.gold, minWidth: 60, textAlign: 'center' },
  actionRow: { flexDirection: 'row', gap: 12, marginTop: Spacing.lg },
  primaryBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: Colors.gold, paddingVertical: 14, borderRadius: 12 },
  primaryBtnText: { fontSize: FontSize.md, fontWeight: '700', color: '#000' },
  secondaryBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, backgroundColor: Colors.surface, paddingVertical: 14, borderRadius: 12, borderWidth: 1, borderColor: Colors.borderGold },
  secondaryBtnText: { fontSize: FontSize.sm, fontWeight: '600', color: Colors.gold },
  successBanner: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, marginTop: Spacing.lg, paddingVertical: 12, backgroundColor: Colors.success + '15', borderRadius: 12 },
  successText: { color: Colors.success, fontSize: FontSize.sm, fontWeight: '600' },
});
