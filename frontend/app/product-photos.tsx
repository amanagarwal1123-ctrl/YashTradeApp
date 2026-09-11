import React, { useCallback, useState } from 'react';
import { Platform, ScrollView, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, useLocalSearchParams, useRouter } from 'expo-router';
import * as DocumentPicker from 'expo-document-picker';
import { api, authenticatedFetch, getProductGallery, resolveFileUrl, responseJson } from '../src/api';
import { useAuth } from '../src/context/AuthContext';
import { Button, ui } from '../src/components/staff/Controls';
import ProtectedMedia from '../src/components/staff/ProtectedMedia';

export default function ProductPhotos(){
  const {id}=useLocalSearchParams<{id:string}>();const {user}=useAuth();const router=useRouter();
  const [product,setProduct]=useState<any>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const load=useCallback(async()=>{try{setProduct(await api.get(`/products/${id}`));}catch(e:any){setError(e.message);}},[id]);
  useFocusEffect(useCallback(()=>{if(user?.role==='admin')load();},[user,load]));
  const update=async(images:string[])=>{await api.put(`/products/${id}`,{images,version:product.version||0});await load();};
  const select=async()=>{setBusy(true);setError('');try{
    const picked=await DocumentPicker.getDocumentAsync({type:['image/jpeg','image/png','image/webp','image/gif'],copyToCacheDirectory:true,base64:false});
    if(picked.canceled)return;const file=picked.assets[0];if((file.size||0)>8*1024*1024)throw new Error('Choose an image up to 8 MB');
    const data=new FormData();if(Platform.OS==='web')data.append('file',file.file!);else data.append('file',{uri:file.uri,name:file.name,type:file.mimeType||'application/octet-stream'} as any);
    const upload=await responseJson(await authenticatedFetch('/products/upload-image',{method:'POST',body:data}));
    await update([...(product.images||[]),upload.url]);
  }catch(e:any){setError(e.message);}finally{setBusy(false);}};
  if(user?.role!=='admin')return <SafeAreaView style={ui.guard}><Text testID="product-photos-denied" style={ui.error}>Admin access required</Text></SafeAreaView>;
  return <SafeAreaView style={ui.screen}><ScrollView contentContainerStyle={ui.content}><Button id="product-photos-back" title="Back" onPress={()=>router.back()}/><Text testID="product-photos-title" style={ui.title}>Product photographs</Text>{!!error&&<Text testID="product-photos-error" style={ui.error}>{error}</Text>}
    <Text style={ui.muted}>Permanent photos, up to 8 MB each. The original catalog scan cannot be removed here. Concurrent changes require a refresh.</Text>
    {product&&<><Text style={ui.text}>{product.title}</Text><Button id="product-photo-upload" title="Add permanent photograph" icon="image-outline" disabled={busy} onPress={select}/><Button id="product-photo-refresh" title="Refresh product" onPress={load}/>
      <Text style={ui.label}>ORIGINAL / CANONICAL SCAN (PRESERVED)</Text><ProtectedMedia id="product-original-photo" uri={getProductGallery({...product,images:[]})[0]} style={ui.image}/>
      {(product.images||[]).map((url:string,index:number)=><View key={`${url}-${index}`} style={ui.card}><ProtectedMedia id={`added-photo-${index}`} uri={resolveFileUrl(url)} style={ui.image}/><Button id={`remove-added-photo-${index}`} title="Remove only this added photo" disabled={busy} onPress={async()=>{setBusy(true);try{await update(product.images.filter((_:string,i:number)=>i!==index));}catch(e:any){setError(e.message);}finally{setBusy(false);}}}/></View>)}
    </>}
  </ScrollView></SafeAreaView>;
}