import React, { useCallback, useState } from 'react';
import { KeyboardAvoidingView, Platform, RefreshControl, ScrollView, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, useRouter } from 'expo-router';
import { api } from '../src/api';
import { useAuth } from '../src/context/AuthContext';
import { Button, dateText, Input, ui } from '../src/components/staff/Controls';

export default function StaffRates() {
  const router = useRouter(); const { user } = useAuth();
  const [rates, setRates] = useState<any>(null), [slabs, setSlabs] = useState<any[]>([]);
  const [metal, setMetal] = useState('silver'), [value, setValue] = useState(''), [purity, setPurity] = useState('999');
  const [error, setError] = useState(''), [message, setMessage] = useState(''), [busy, setBusy] = useState(false);
  const [item, setItem] = useState(''), [wastage, setWastage] = useState(''), [labour, setLabour] = useState(''), [editing, setEditing] = useState<any>(null);
  const load = useCallback(async () => { try { const [r,s] = await Promise.all([api.get('/rates/latest'), api.get('/rate-list')]); setRates(r); setSlabs(s.slabs || []); setError(''); } catch(e: any) { setError(`Data may be stale. ${e.message}`); } }, []);
  useFocusEffect(useCallback(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t); }, [load]));
  const save = async () => {
    if (!value.trim() || !Number.isFinite(Number(value)) || Number(value) <= 0) { setError('Enter a positive INR per gram value'); return; }
    setBusy(true); setMessage('');
    try { await api.post('/rates', { version: rates.version, [`${metal}_physical_rate`]: Number(value), [`${metal}_physical_mode`]: 'manual', [`${metal}_purity`]: purity }); await load(); setMessage(`${metal} rate committed. The other metal was preserved.`); }
    catch(e: any) { setError(e.message); } finally { setBusy(false); }
  };
  if (!user || !['admin','billing_executive'].includes(user.role)) return <SafeAreaView style={ui.guard}><Text testID="rates-access-denied" style={ui.error}>Admin or billing access required</Text></SafeAreaView>;
  return <SafeAreaView style={ui.screen}><KeyboardAvoidingView style={ui.screen} behavior={Platform.OS==='ios'?'padding':undefined}><ScrollView contentContainerStyle={ui.content} refreshControl={<RefreshControl refreshing={busy} onRefresh={load}/>} keyboardShouldPersistTaps="handled">
    <Button id="rates-back" title="Back to panel" onPress={() => router.replace('/panel')}/><Text testID="staff-rates-title" style={ui.title}>Rates & rate list</Text>
    {!!error && <Text testID="rates-error" style={ui.error}>{error}</Text>}{!!message && <Text testID="rates-confirmation" style={[ui.text,ui.success]}>{message}</Text>}
    {['silver','gold'].map(m => <View key={m} testID={`current-rate-${m}`} style={ui.card}><Text style={ui.label}>{m.toUpperCase()} · INR / gram</Text><Text style={ui.title}>{rates?.[`${m}_physical_rate`] ?? '—'}</Text><Text style={ui.muted}>Purity {rates?.[`${m}_purity`] || 'Legacy purity not recorded'} · Effective {dateText(rates?.effective_at || rates?.created_at)}</Text></View>)}
    <View style={ui.card}><View style={ui.row}>{['silver','gold'].map(m => <Button id={`edit-rate-${m}`} key={m} title={m} active={metal===m} onPress={() => { setMetal(m); setValue(String(rates?.[`${m}_physical_rate`] || '')); setPurity(m === 'silver' ? '999' : '24K'); }}/>)}</View>
      <Input id="rate-value" label="Physical rate · INR per gram" value={value} onChange={setValue}/><Input id="rate-purity" label="Purity (silver fineness or gold karats)" value={purity} onChange={setPurity}/><Button id="rate-save" title="Save this metal" onPress={save} disabled={busy || !rates}/>
    </View>
    <View style={ui.card}><Text style={ui.label}>{editing ? 'EDIT RATE-LIST ITEM' : 'ADD RATE-LIST ITEM'}</Text><Text style={ui.muted}>For {metal}. Labour is INR per kg; purity and wastage use existing rate-list formats.</Text>
      <Input id="slab-item" label="Item name" value={item} onChange={setItem}/><Input id="slab-wastage" label="Wastage" value={wastage} onChange={setWastage}/><Input id="slab-labour" label="Labour · INR/kg" value={labour} onChange={setLabour}/>
      <Button id="slab-save" title={editing ? 'Update item' : 'Add item'} disabled={busy || !item.trim()} onPress={async () => { setBusy(true); try { const body = { metal_type: metal, item_name: item, purity, wastage, labour_kg: labour }; if(editing) await api.put(`/rate-list/${editing.id}`, { ...body, version: editing.version || 0 }); else await api.post('/rate-list',body); setEditing(null); setItem(''); await load(); } catch(e:any){setError(e.message);} finally{setBusy(false);} }}/>
    </View>
    {slabs.filter(s=>s.metal_type===metal).map(s=><View key={s.id} testID={`slab-${s.id}`} style={ui.card}><Text style={ui.text}>{s.item_name || s.slab_name}</Text><Text style={ui.muted}>Purity {s.purity || '—'} · Wastage {s.wastage || '—'} · Labour {s.labour_kg || '—'} INR/kg</Text><View style={ui.row}><Button id={`slab-edit-${s.id}`} title="Edit" onPress={()=>{setEditing(s);setItem(s.item_name||'');setWastage(s.wastage||'');setLabour(s.labour_kg||'');}}/><Button id={`slab-remove-${s.id}`} title="Remove" onPress={async()=>{try{await api.delete(`/rate-list/${s.id}?version=${s.version||0}`);await load();}catch(e:any){setError(e.message);}}}/></View></View>)}
  </ScrollView></KeyboardAvoidingView></SafeAreaView>;
}