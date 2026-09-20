import React, { useCallback, useEffect, useRef, useState } from 'react';
import { RefreshControl, Text, View } from 'react-native';
import { KeyboardAwareScreen } from '../src/components/KeyboardScreen';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, useRouter } from 'expo-router';
import { api } from '../src/api';
import { useAuth } from '../src/context/AuthContext';
import { Button, dateText, Input, ui } from '../src/components/staff/Controls';

export default function StaffRates() {
  const router = useRouter(); const { user } = useAuth();
  const [rates, setRates] = useState<any>(null), [slabs, setSlabs] = useState<any[]>([]);
  const [metal, setMetal] = useState('silver'), [value, setValue] = useState(''), [purity, setPurity] = useState('999');
  // MCX is edited in MARKET units (silver INR/kg, gold INR/10 g); the server converts to its canonical INR/g basis.
  const [mcxDisplay, setMcxDisplay] = useState(''), [mode, setMode] = useState<'manual' | 'calculated'>('manual'), [premium, setPremium] = useState('');
  const mcxUnit = (m: string) => rates?.units?.mcx_display?.[m] || (m === 'silver' ? 'INR/kg' : 'INR/10g');
  const pick = (m: string, r: any = rates) => { setMetal(m); setValue(String(r?.[`${m}_physical_rate`] || '')); setPurity(r?.[`${m}_purity`] || (m === 'silver' ? '999' : '24K')); setMcxDisplay(r?.[`${m}_mcx_display_rate`] ? String(r[`${m}_mcx_display_rate`]) : ''); setMode(r?.[`${m}_physical_mode`] === 'calculated' ? 'calculated' : 'manual'); setPremium(String(r?.[`${m}_physical_premium`] ?? '')); };
  const [error, setError] = useState(''), [message, setMessage] = useState(''), [busy, setBusy] = useState(false);
  const [item, setItem] = useState(''), [wastage, setWastage] = useState(''), [labour, setLabour] = useState(''), [editing, setEditing] = useState<any>(null);
  const load = useCallback(async () => { try { const [r,s] = await Promise.all([api.get('/rates/latest'), api.get('/rate-list')]); setRates(r); setSlabs(s.slabs || []); setError(''); } catch(e: any) { setError(`Data may be stale. ${e.message}`); } }, []);
  useFocusEffect(useCallback(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t); }, [load]));
  const primed = useRef(false);
  useEffect(() => { if (rates && !primed.current) { primed.current = true; pick(metal, rates); } }, [rates]);
  const save = async () => {
    const num = (v: string) => Number(v.trim());
    const body: Record<string, any> = { version: rates.version, [`${metal}_physical_mode`]: mode, [`${metal}_purity`]: purity };
    if (mcxDisplay.trim()) {
      if (!Number.isFinite(num(mcxDisplay)) || num(mcxDisplay) < 0) { setError(`Enter the MCX quote as a number in ${mcxUnit(metal)}`); return; }
      body[`${metal}_mcx_display_rate`] = num(mcxDisplay);
    }
    if (mode === 'calculated') {
      if (!mcxDisplay.trim() && !rates?.[`${metal}_mcx_rate`]) { setError('Calculated mode needs an MCX quote'); return; }
      if (!Number.isFinite(num(premium || '0')) || num(premium || '0') < 0) { setError('Enter the premium in INR per gram'); return; }
      body[`${metal}_physical_premium`] = num(premium || '0');
    } else {
      if (!value.trim() || !Number.isFinite(num(value)) || num(value) <= 0) { setError('Enter a positive INR per gram value'); return; }
      body[`${metal}_physical_rate`] = num(value);
    }
    setBusy(true); setMessage(''); setError('');
    try { const saved = await api.post('/rates', body); setRates(saved); pick(metal, saved); await load(); setMessage(`${metal} committed: physical ${saved[`${metal}_physical_rate`]} INR/g${mcxDisplay.trim() ? ` · MCX ${saved[`${metal}_mcx_display_rate`]} ${mcxUnit(metal)} (= ${saved[`${metal}_mcx_rate`]} INR/g)` : ''}. The other metal was preserved.`); }
    catch(e: any) { setError(e.message); } finally { setBusy(false); }
  };
  if (!user || !['admin','billing_executive'].includes(user.role)) return <SafeAreaView style={ui.guard}><Text testID="rates-access-denied" style={ui.error}>Admin or billing access required</Text></SafeAreaView>;
  return <SafeAreaView style={ui.screen}><KeyboardAwareScreen contentContainerStyle={ui.content} refreshControl={<RefreshControl refreshing={busy} onRefresh={load}/>}>
    <Button id="rates-back" title="Back to panel" onPress={() => router.replace('/panel')}/><Text testID="staff-rates-title" style={ui.title}>Rates & rate list</Text>
    {!!error && <Text testID="rates-error" style={ui.error}>{error}</Text>}{!!message && <Text testID="rates-confirmation" style={[ui.text,ui.success]}>{message}</Text>}
    {['silver','gold'].map(m => <View key={m} testID={`current-rate-${m}`} style={ui.card}><Text style={ui.label}>{m.toUpperCase()} · PHYSICAL INR / gram</Text><Text style={ui.title}>{rates?.[`${m}_physical_rate`] ?? '—'}</Text>
      <Text testID={`current-mcx-${m}`} style={ui.text}>MCX {rates?.[`${m}_mcx_display_rate`] ?? '—'} {mcxUnit(m)}{rates?.[`${m}_mcx_rate`] ? ` (= ${rates[`${m}_mcx_rate`]} INR/g)` : ''}{rates?.[`${m}_physical_mode`] === 'calculated' ? ` · physical = MCX + ${rates?.[`${m}_physical_premium`] ?? 0} INR/g premium` : ' · physical entered manually'}</Text>
      {rates && !rates.mcx_units_verified && !!rates[`${m}_mcx_rate`] && <Text testID={`mcx-unverified-${m}`} style={[ui.muted, { color: '#F59E0B' }]}>MCX basis not yet confirmed by a unit-aware save: the stored number was entered against an INR/g label. Re-enter the quote in {mcxUnit(m)} to confirm.</Text>}
      <Text style={ui.muted}>Purity {rates?.[`${m}_purity`] || 'Legacy purity not recorded'} · Effective {dateText(rates?.effective_at || rates?.created_at)}</Text></View>)}
    <View style={ui.card}><View style={ui.row}>{['silver','gold'].map(m => <Button id={`edit-rate-${m}`} key={m} title={m} active={metal===m} onPress={() => pick(m)}/>)}</View>
      <Input id="rate-mcx" label={`MCX quote · ${mcxUnit(metal)} (${metal === 'silver' ? 'e.g. 100000 = 100 INR/g' : 'e.g. 75000 = 7500 INR/g'}; leave blank to keep)`} value={mcxDisplay} onChange={setMcxDisplay} numeric/>
      <View style={ui.row}><Button id="rate-mode-manual" title="Physical: enter manually" active={mode==='manual'} onPress={() => setMode('manual')}/><Button id="rate-mode-calculated" title="Physical: MCX + premium" active={mode==='calculated'} onPress={() => setMode('calculated')}/></View>
      {mode === 'manual' ? <Input id="rate-value" label="Physical rate · INR per gram" value={value} onChange={setValue} numeric/> : <Input id="rate-premium" label="Premium over MCX · INR per gram (MCX is normalised to INR/g first)" value={premium} onChange={setPremium} numeric/>}
      <Input id="rate-purity" label="Purity (silver fineness or gold karats)" value={purity} onChange={setPurity}/><Button id="rate-save" title="Save this metal" onPress={save} disabled={busy || !rates}/>
    </View>
    <View style={ui.card}><Text style={ui.label}>{editing ? 'EDIT RATE-LIST ITEM' : 'ADD RATE-LIST ITEM'}</Text><Text style={ui.muted}>For {metal}. Keep the original labour basis. Examples: INR 850/kg, INR 50/10g, INR 20/piece. Bare numbers mean INR/kg.</Text>
      <Input id="slab-item" label="Item name" value={item} onChange={setItem}/><Input id="slab-wastage" label="Wastage" value={wastage} onChange={setWastage}/><Input id="slab-labour" label="Labour · amount and basis" value={labour} onChange={setLabour}/>
      <Button id="slab-save" title={editing ? 'Update item' : 'Add item'} disabled={busy || !item.trim()} onPress={async () => { setBusy(true); try { const body = { metal_type: metal, item_name: item, purity, wastage, labour_kg: labour }; if(editing) await api.put(`/rate-list/${editing.id}`, { ...body, version: editing.version || 0 }); else await api.post('/rate-list',body); setEditing(null); setItem(''); await load(); } catch(e:any){setError(e.message);} finally{setBusy(false);} }}/>
    </View>
    {slabs.filter(s=>s.metal_type===metal).map(s=><View key={s.id} testID={`slab-${s.id}`} style={ui.card}><Text style={ui.text}>{s.item_name || s.slab_name}</Text><Text testID={`slab-units-${s.id}`} style={ui.muted}>Purity {s.purity || '—'} · Wastage {s.wastage || '—'} · Labour {s.labour_display || s.labour_kg || '—'}{s.unit_review_required?' · Units need review':''}</Text><View style={ui.row}><Button id={`slab-edit-${s.id}`} title="Edit" onPress={()=>{setEditing(s);setItem(s.item_name||'');setPurity(s.purity||'');setWastage(String(s.wastage||''));setLabour(s.labour_display==='—'?'':String(s.labour_display||s.labour_kg||''));}}/><Button id={`slab-remove-${s.id}`} title="Remove" onPress={async()=>{try{await api.delete(`/rate-list/${s.id}?version=${s.version||0}`);await load();}catch(e:any){setError(e.message);}}}/></View></View>)}
  </KeyboardAwareScreen></SafeAreaView>;
}