import React, { useCallback, useEffect, useRef, useState } from 'react';
import { FlatList, KeyboardAvoidingView, Platform, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, useRouter } from 'expo-router';
import { api, getImageUrl, API_BASE } from '../src/api';
import { useAuth } from '../src/context/AuthContext';
import { Button, Input, ui } from '../src/components/staff/Controls';
import { Choices } from '../src/components/staff/ProductFields';
import PrivateImage from '../src/components/staff/PrivateImage';
import { confirmAlert } from '../src/utils/alert';

export default function ProductCatalog() {
  const {user}=useAuth(),router=useRouter(),generation=useRef(0),list=useRef<FlatList>(null);
  const [data,setData]=useState<any>(null),[page,setPage]=useState(1),[search,setSearch]=useState(''),[term,setTerm]=useState('');
  const [metal,setMetal]=useState(''),[category,setCategory]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const [searchMode,setSearchMode]=useState('words');
  const load=useCallback(async()=>{const seq=++generation.current;setBusy(true);try{const r=await api.get(`/products?${new URLSearchParams({page:String(page),limit:'40',include_hidden:'true',search:searchMode==='words'?term:'',product_code:searchMode==='exact_sku'?term:'',metal_type:metal,category})}`);if(seq===generation.current){setData(r);setError('');list.current?.scrollToOffset({offset:0});}}catch(e:any){if(seq===generation.current)setError(e.message);}finally{if(seq===generation.current)setBusy(false);}},[page,term,metal,category,searchMode]);
  useFocusEffect(useCallback(()=>{if(user?.role==='admin')load();return()=>{generation.current++;};},[user,load]));
  useEffect(()=>{const t=setTimeout(()=>{setPage(1);setTerm(search);},350);return()=>clearTimeout(t);},[search]);
  if(user?.role!=='admin')return <SafeAreaView style={ui.guard}><Text testID="catalog-access-denied" style={ui.error}>Admin access required</Text></SafeAreaView>;
  return <SafeAreaView style={ui.screen}><KeyboardAvoidingView style={ui.screen} behavior={Platform.OS==='ios'?'padding':undefined}>
    <View style={styles.header}><Button id="catalog-back" title="Back" onPress={()=>router.canGoBack()?router.back():router.replace('/panel')}/><Text testID="catalog-title" style={ui.title}>Products</Text><Button id="catalog-create" title="Add" onPress={()=>router.push('/catalog-author')}/></View>
    <View style={styles.filters}><View style={ui.row}><Button id="catalog-search-words" title="Words" active={searchMode==='words'} onPress={()=>{setPage(1);setSearchMode('words');}}/><Button id="catalog-search-sku" title="Exact SKU" active={searchMode==='exact_sku'} onPress={()=>{setPage(1);setSearchMode('exact_sku');}}/></View><Input id="catalog-search" label={searchMode==='words'?'Search indexed words · title, tags (not substrings)':'Exact product code · case sensitive'} value={search} onChange={setSearch}/><Choices id="catalog-metal" label="Type" value={metal} options={['','silver','gold','diamond']} onChange={v=>{setPage(1);setMetal(v);}}/><Input id="catalog-category" label="Exact category (optional)" value={category} onChange={v=>{setPage(1);setCategory(v);}}/>
      {!!error&&<Text testID="catalog-error" style={ui.error}>{error}</Text>}<Text testID="catalog-total" style={ui.muted}>{data?.total??'—'} products · at most 40 held per page</Text></View>
    <FlatList testID="catalog-list" ref={list} data={data?.products||[]} keyExtractor={p=>p.id} initialNumToRender={6} maxToRenderPerBatch={6} windowSize={5} refreshing={busy} onRefresh={load} contentContainerStyle={styles.list} renderItem={({item:p})=><View testID={`catalog-product-${p.id}`} style={ui.card}>
      {getImageUrl(p)&&<PrivateImage id={`catalog-photo-${p.id}`} url={getImageUrl(p).replace(API_BASE,'/api')} style={styles.photo}/>}
      <Text testID={`catalog-title-${p.id}`} style={ui.text}>{p.title}</Text><Text testID={`catalog-meta-${p.id}`} style={ui.muted}>{p.product_code} · {p.metal_type} · {p.category} · {p.visibility||'all'}</Text>
      <View style={ui.row}><Button id={`catalog-edit-${p.id}`} title="Photos & details" onPress={()=>router.push({pathname:'/product-photos',params:{id:p.id}})}/><Button id={`catalog-publish-${p.id}`} title={p.visibility==='hidden'?'Publish':'Hide'} disabled={busy} onPress={async()=>{try{await api.put(`/products/${p.id}`,{version:p.version,visibility:p.visibility==='hidden'?'all':'hidden'});await load();}catch(e:any){setError(e.message);}}}/><Button id={`catalog-delete-${p.id}`} title="Delete" disabled={busy} onPress={()=>confirmAlert('Delete product?','The product will be hidden; retained media is not erased.',async()=>{try{await api.delete(`/products/${p.id}`);await load();}catch(e:any){setError(e.message);}})}/></View>
    </View>}/>
    <View style={styles.footer}><Button id="catalog-prev" title="Previous" disabled={busy||page<=1} onPress={()=>setPage(page-1)}/><Text testID="catalog-page" style={ui.text}>{page} / {Math.max(data?.pages||1,1)}</Text><Button id="catalog-next" title="Next" disabled={busy||!data||page>=data.pages} onPress={()=>setPage(page+1)}/></View><Button id="catalog-media-usage" title="Storage accounting & alerts" onPress={()=>router.push('/media-usage')}/>
  </KeyboardAvoidingView></SafeAreaView>;
}
const styles=StyleSheet.create({header:{padding:16,flexDirection:'row',gap:12},filters:{paddingHorizontal:16,gap:8},list:{padding:16,gap:16},photo:{height:100,width:'100%'},footer:{flexDirection:'row',justifyContent:'space-between',alignItems:'center',padding:16}});