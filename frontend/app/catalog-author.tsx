import React, { useState } from 'react';
import { Platform, Text, View } from 'react-native';
import { KeyboardAwareScreen } from '../src/components/KeyboardScreen';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import * as DocumentPicker from 'expo-document-picker';
import { File as NativeFile, Paths } from 'expo-file-system';
import * as Sharing from 'expo-sharing';
import { api, authenticatedFetch, responseJson } from '../src/api';
import { useAuth } from '../src/context/AuthContext';
import ProductFields, { emptyProduct } from '../src/components/staff/ProductFields';
import PrivateImage from '../src/components/staff/PrivateImage';
import { Button, ui } from '../src/components/staff/Controls';
// Content domain (R10): administrators and Upload Executives; the server enforces the same gate on every route.
const CONTENT_ROLES = ['admin', 'upload_executive'];

export default function CatalogAuthor() {
  const router=useRouter(),{user}=useAuth();
  const [fields,setFields]=useState<any>(emptyProduct()),[photo,setPhoto]=useState<any>(null),[entries,setEntries]=useState<any[]>([]);
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
  const action=async(fn:()=>Promise<void>)=>{setBusy(true);setError('');setMessage('');try{await fn();}catch(e:any){setError(e.message);}finally{setBusy(false);}};
  const pick=()=>action(async()=>{
    const r=await DocumentPicker.getDocumentAsync({type:['image/jpeg','image/png','image/webp'],copyToCacheDirectory:true,base64:false});
    if(r.canceled)return;const f=r.assets[0];if((f.size||0)>8*1024*1024)throw new Error('Choose an image up to 8 MB');
    const body=new FormData();if(Platform.OS==='web')body.append('file',f.file!);else body.append('file',{uri:f.uri,name:f.name,type:f.mimeType} as any);
    setPhoto(await responseJson(await authenticatedFetch('/products/upload-image',{method:'POST',body})));
  });
  const exportPDF=()=>action(async()=>{
    const r=await authenticatedFetch('/pdf-template/export',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({products:entries})});
    if(!r.ok)await responseJson(r);
    if(Platform.OS==='web'){
      const url=URL.createObjectURL(await r.blob()),a=document.createElement('a');a.href=url;a.download='Yash-Catalog-v1.pdf';a.click();setTimeout(()=>URL.revokeObjectURL(url),30000);
    }else{
      const file=new NativeFile(Paths.cache,'Yash-Catalog-v1.pdf');file.create({overwrite:true});file.write(new Uint8Array(await r.arrayBuffer()));
      if(!await Sharing.isAvailableAsync())throw new Error('PDF saved in app cache; sharing is unavailable on this device');
      await Sharing.shareAsync(file.uri,{mimeType:'application/pdf',UTI:'com.adobe.pdf'});
    }
    setMessage('Version 1 PDF exported. Review it, then upload through Import PDF. No products were published.');
  });
  if(!CONTENT_ROLES.includes(user?.role||''))return <SafeAreaView style={ui.guard}><Text testID="author-access-denied" style={ui.error}>Admin or Upload Executive access required</Text></SafeAreaView>;
  return <SafeAreaView style={ui.screen}><KeyboardAwareScreen contentContainerStyle={ui.content}>
    <Button id="author-back" title="Back" onPress={()=>router.canGoBack()?router.back():router.replace('/panel')}/><Text testID="author-screen-title" style={ui.title}>Create your catalogue</Text>
    <Text testID="author-help" style={ui.muted}>Fill in a product and choose its photograph. Save a single hidden product, or collect up to 20 entries and export the exact v1 PDF. Keep this screen open until export; unsaved form entries are not durable drafts.</Text>
    {!!error&&<Text testID="author-error" style={ui.error}>{error}</Text>}{!!message&&<Text testID="author-message" style={ui.success}>{message}</Text>}
    <ProductFields id="author" fields={fields} onChange={setFields}/>
    <Button id="author-photo" title={photo?'Replace selected photograph':'Choose product photograph'} disabled={busy} onPress={pick}/>
    {photo&&<PrivateImage id="author-photo-preview" url={photo.url} style={ui.image}/>}
    <Button id="author-save-product" title="Save single hidden product" disabled={busy||!photo} onPress={()=>action(async()=>{await api.post('/products',{...fields,visibility:'hidden',images:[photo.url]});setMessage('Hidden product saved. Open Products to review and publish.');setFields(emptyProduct());setPhoto(null);})}/>
    <Button id="author-add-entry" title="Add entry to PDF" disabled={busy||!photo||entries.length>=20||!fields.product_code||!fields.title} onPress={()=>{setEntries([...entries,{...fields,photo_path:photo.storage_path}]);setFields(emptyProduct());setPhoto(null);}}/>
    <Text testID="author-entry-count" style={ui.label}>{entries.length} / 20 PDF ENTRIES</Text>
    {entries.map((e,i)=><View key={i} style={ui.card}><Text testID={`author-entry-${i}`} style={ui.text}>{e.product_code} · {e.title}</Text><Button id={`author-remove-${i}`} title="Remove from PDF" disabled={busy} onPress={()=>setEntries(entries.filter((_,n)=>n!==i))}/></View>)}
    <Button id="author-export" title={busy?'Working…':'Export version 1 PDF'} disabled={busy||!entries.length} onPress={exportPDF}/>
  </KeyboardAwareScreen></SafeAreaView>;
}