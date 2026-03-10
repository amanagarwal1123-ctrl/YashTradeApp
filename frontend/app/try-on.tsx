import React, { useState, useEffect } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, Image, ActivityIndicator, ScrollView, Platform, Alert } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, FontSize } from '../src/theme';
import { api, getImageUrl } from '../src/api';

const WEARABLE_CATEGORIES = ['payal', 'chain', 'necklace', 'bracelet', 'bangles', 'kadaa', 'ring', 'earrings', 'pendant', 'nose_ring', 'toe_rings'];

export default function TryOnScreen() {
  const { productId } = useLocalSearchParams<{ productId?: string }>();
  const router = useRouter();
  const [product, setProduct] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [userPhoto, setUserPhoto] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState('');
  const [bodyArea, setBodyArea] = useState('auto');

  useEffect(() => {
    if (productId) {
      (async () => {
        try {
          const p = await api.get(`/products/${productId}`);
          setProduct(p);
          // Auto-detect body area
          const cat = (p.category || '').toLowerCase();
          if (['necklace', 'chain', 'pendant'].includes(cat)) setBodyArea('neck');
          else if (['bracelet', 'kadaa', 'bangles'].includes(cat)) setBodyArea('wrist');
          else if (['earrings', 'nose_ring'].includes(cat)) setBodyArea('ear');
          else if (['ring', 'toe_rings'].includes(cat)) setBodyArea('finger');
          else if (cat === 'payal') setBodyArea('ankle');
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
            const base64 = (reader.result as string).split(',')[1];
            setUserPhoto(base64);
            setResult(null);
            setError('');
          };
          reader.readAsDataURL(file);
        }
      };
      input.click();
    }
  };

  const generateTryOn = async () => {
    if (!product || !userPhoto) return;
    setGenerating(true);
    setError('');
    setResult(null);
    try {
      const res = await api.post('/ai/try-on', {
        product_id: product.id,
        user_photo_base64: userPhoto,
        body_area: bodyArea,
      });
      setResult(res);
    } catch (e: any) {
      setError(e.message || 'Failed to generate try-on preview');
    } finally {
      setGenerating(false);
    }
  };

  if (loading) return <View style={s.loader}><ActivityIndicator size="large" color={Colors.gold} /></View>;

  const productImageUri = product ? getImageUrl(product, false) : '';
  const bodyAreas = [
    { key: 'neck', label: 'Neck', icon: 'body' },
    { key: 'wrist', label: 'Wrist', icon: 'hand-left' },
    { key: 'ear', label: 'Ear', icon: 'ear' },
    { key: 'finger', label: 'Finger', icon: 'finger-print' },
    { key: 'ankle', label: 'Ankle', icon: 'footsteps' },
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

        {/* Product Card */}
        {product && (
          <View style={s.productCard}>
            <Image source={{ uri: productImageUri }} style={s.productThumb} />
            <View style={s.productInfo}>
              <Text style={s.productTitle} numberOfLines={2}>{product.title}</Text>
              <Text style={s.productMeta}>{product.metal_type} {product.category ? `• ${product.category.replace(/_/g, ' ')}` : ''}</Text>
            </View>
          </View>
        )}

        {/* Step 1: Body Area Selection */}
        <View style={s.section}>
          <Text style={s.stepLabel}>STEP 1: Where to try on?</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false}>
            <View style={{ flexDirection: 'row', gap: 8 }}>
              {bodyAreas.map(ba => (
                <TouchableOpacity key={ba.key} style={[s.areaChip, bodyArea === ba.key && s.areaChipActive]} onPress={() => setBodyArea(ba.key)}>
                  <Ionicons name={ba.icon as any} size={18} color={bodyArea === ba.key ? Colors.gold : Colors.textMuted} />
                  <Text style={[s.areaChipText, bodyArea === ba.key && { color: Colors.gold }]}>{ba.label}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </ScrollView>
        </View>

        {/* Step 2: Upload Photo */}
        <View style={s.section}>
          <Text style={s.stepLabel}>STEP 2: Upload your photo</Text>
          <Text style={s.hint}>Take or upload a photo of yourself to see how the jewellery looks on you</Text>

          {!userPhoto ? (
            <TouchableOpacity style={s.uploadBox} onPress={pickPhoto} data-testid="tryon-upload-btn">
              <Ionicons name="camera" size={40} color={Colors.gold} />
              <Text style={s.uploadText}>Tap to take photo or upload</Text>
              <Text style={s.uploadHint}>Camera / Gallery</Text>
            </TouchableOpacity>
          ) : (
            <View style={s.photoPreview}>
              <Image source={{ uri: `data:image/jpeg;base64,${userPhoto}` }} style={s.photoImage} />
              <TouchableOpacity style={s.changePhotoBtn} onPress={pickPhoto}>
                <Ionicons name="camera" size={16} color="#fff" />
                <Text style={s.changePhotoText}>Change Photo</Text>
              </TouchableOpacity>
            </View>
          )}
        </View>

        {/* Step 3: Generate */}
        <View style={s.section}>
          <Text style={s.stepLabel}>STEP 3: Generate Preview</Text>
          <TouchableOpacity
            style={[s.generateBtn, (!userPhoto || !product || generating) && { opacity: 0.5 }]}
            onPress={generateTryOn}
            disabled={!userPhoto || !product || generating}
            data-testid="tryon-generate-btn"
          >
            {generating ? (
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                <ActivityIndicator color="#000" />
                <Text style={s.generateBtnText}>Creating AI Preview...</Text>
              </View>
            ) : (
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <Ionicons name="sparkles" size={20} color="#000" />
                <Text style={s.generateBtnText}>Generate AI Try-On Preview</Text>
              </View>
            )}
          </TouchableOpacity>
          {generating && (
            <Text style={s.generatingHint}>AI is creating your personalized try-on preview. This may take up to 60 seconds...</Text>
          )}
        </View>

        {/* Result */}
        {result && (
          <View style={s.resultSection}>
            <Text style={s.resultTitle}>Your AI Try-On Preview</Text>
            <Image
              source={{ uri: result.image_url ? `${process.env.EXPO_PUBLIC_BACKEND_URL}${result.image_url}` : `data:image/png;base64,${result.image_base64}` }}
              style={s.resultImage}
              resizeMode="contain"
              data-testid="tryon-result-image"
            />
            <View style={s.resultActions}>
              <TouchableOpacity style={s.resultActionBtn} onPress={generateTryOn}>
                <Ionicons name="refresh" size={18} color={Colors.gold} />
                <Text style={s.resultActionText}>Try Again</Text>
              </TouchableOpacity>
              <TouchableOpacity style={s.resultActionBtn} onPress={pickPhoto}>
                <Ionicons name="camera" size={18} color={Colors.gold} />
                <Text style={s.resultActionText}>New Photo</Text>
              </TouchableOpacity>
            </View>
          </View>
        )}

        {/* Error */}
        {error ? (
          <View style={s.errorBox}>
            <Ionicons name="alert-circle" size={20} color={Colors.error} />
            <Text style={s.errorText}>{error}</Text>
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
  productThumb: { width: 60, height: 60, borderRadius: 10, backgroundColor: Colors.surface },
  productInfo: { flex: 1 },
  productTitle: { fontSize: FontSize.md, fontWeight: '600', color: Colors.text },
  productMeta: { fontSize: FontSize.sm, color: Colors.textSecondary, marginTop: 2, textTransform: 'capitalize' },
  section: { marginTop: Spacing.lg, paddingHorizontal: Spacing.lg },
  stepLabel: { fontSize: FontSize.xs, fontWeight: '700', color: Colors.gold, letterSpacing: 2, marginBottom: Spacing.sm },
  hint: { fontSize: FontSize.sm, color: Colors.textMuted, marginBottom: Spacing.md },
  areaChip: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 10, borderRadius: 10, backgroundColor: Colors.surface, borderWidth: 1, borderColor: Colors.border },
  areaChipActive: { backgroundColor: Colors.gold + '15', borderColor: Colors.gold },
  areaChipText: { fontSize: FontSize.sm, color: Colors.textMuted, fontWeight: '600' },
  uploadBox: { alignItems: 'center', justifyContent: 'center', paddingVertical: 40, borderRadius: 16, borderWidth: 2, borderColor: Colors.gold + '40', borderStyle: 'dashed', backgroundColor: Colors.card },
  uploadText: { color: Colors.text, fontSize: FontSize.md, fontWeight: '600', marginTop: Spacing.sm },
  uploadHint: { color: Colors.textMuted, fontSize: FontSize.xs, marginTop: 4 },
  photoPreview: { alignItems: 'center' },
  photoImage: { width: 200, height: 200, borderRadius: 16, backgroundColor: Colors.surface },
  changePhotoBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: Spacing.sm, backgroundColor: Colors.surface, paddingHorizontal: 16, paddingVertical: 8, borderRadius: 8 },
  changePhotoText: { color: Colors.text, fontSize: FontSize.sm, fontWeight: '600' },
  generateBtn: { backgroundColor: Colors.gold, paddingVertical: 16, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  generateBtnText: { fontSize: FontSize.md, fontWeight: '700', color: '#000' },
  generatingHint: { color: Colors.gold, fontSize: FontSize.xs, textAlign: 'center', marginTop: Spacing.sm },
  resultSection: { marginTop: Spacing.xl, paddingHorizontal: Spacing.lg, alignItems: 'center' },
  resultTitle: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.success, marginBottom: Spacing.md },
  resultImage: { width: '100%', aspectRatio: 1, borderRadius: 16, backgroundColor: Colors.surface },
  resultActions: { flexDirection: 'row', gap: 16, marginTop: Spacing.md },
  resultActionBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: Colors.surface, paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10, borderWidth: 1, borderColor: Colors.borderGold },
  resultActionText: { color: Colors.gold, fontSize: FontSize.sm, fontWeight: '600' },
  errorBox: { flexDirection: 'row', alignItems: 'center', gap: 8, marginHorizontal: Spacing.lg, marginTop: Spacing.md, padding: Spacing.md, backgroundColor: Colors.error + '15', borderRadius: 12 },
  errorText: { color: Colors.error, fontSize: FontSize.sm, flex: 1 },
});
