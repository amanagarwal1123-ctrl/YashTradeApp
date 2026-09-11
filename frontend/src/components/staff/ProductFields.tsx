import React from 'react';
import { Text, View } from 'react-native';
import { Button, Input, ui } from './Controls';

export const emptyProduct = () => ({ product_code: '', title: '', metal_type: 'silver', category: 'payal', stock_status: 'in_stock', visibility: 'hidden', tags: [], is_new_arrival: true, is_trending: false, is_pinned: false });
export const categories = ['payal','chain','articles','necklace','ring','bangles','bracelet','gifting','coins','kadaa','pendant','kids','toe_rings','earrings','mens','nose_ring','waist_belt'];

export function Choices({id,label,value,options,onChange}:{id:string;label:string;value:string;options:string[];onChange:(v:string)=>void}) {
  return <View><Text testID={`${id}-label`} style={ui.muted}>{label}</Text><View style={ui.row}>{options.map(v=><Button key={v} id={`${id}-${v||'all'}`} title={v.replace(/_/g,' ')||'All'} active={v===value} onPress={()=>onChange(v)}/>)}</View></View>;
}

export default function ProductFields({id,fields,onChange}:{id:string;fields:any;onChange:(v:any)=>void}) {
  const set=(key:string,value:any)=>onChange({...fields,[key]:value});
  return <View style={ui.card}>
    {[['product_code','Product code / SKU'],['title','Product name'],['description','Description'],['subcategory','Subcategory']].map(([k,l])=><Input key={k} id={`${id}-${k}`} label={l} value={String(fields[k]||'')} onChange={v=>set(k,v)} multiline={k==='description'}/>)}
    <Choices id={`${id}-metal_type`} label="Product type" value={fields.metal_type||''} options={['silver','gold','diamond']} onChange={v=>set('metal_type',v)}/>
    <Choices id={`${id}-category`} label="Category" value={fields.category||''} options={categories} onChange={v=>set('category',v)}/>
    <Input id={`${id}-category-custom`} label="Category (or enter existing category)" value={fields.category||''} onChange={v=>set('category',v)}/>
    <Input id={`${id}-approx_weight`} label="Metal weight · grams (e.g. 25-35 g per pair)" value={fields.approx_weight||''} onChange={v=>set('approx_weight',v)}/>
    <Input id={`${id}-purity`} label="Purity · silver fineness (925), gold karats (22K)" value={String(fields.purity||'')} onChange={v=>set('purity',v)}/>
    {fields.metal_type==='diamond'&&<><Choices id={`${id}-base_metal`} label="Setting / base metal" value={fields.base_metal||''} options={['','gold','silver','platinum']} onChange={v=>set('base_metal',v)}/><Input id={`${id}-stone_weight_ct`} label="Stone weight · carats" value={String(fields.stone_weight_ct||'')} onChange={v=>set('stone_weight_ct',v)} numeric/></>}
    <Input id={`${id}-selling_touch`} label="Selling touch · numeric % (optional)" value={String(fields.selling_touch||'')} onChange={v=>set('selling_touch',v)} numeric/>
    <Input id={`${id}-selling_label`} label="Selling label (optional)" value={fields.selling_label||''} onChange={v=>set('selling_label',v)}/>
    <Choices id={`${id}-stock_status`} label="Stock" value={fields.stock_status||'in_stock'} options={['in_stock','limited','out_of_stock']} onChange={v=>set('stock_status',v)}/>
    <Input id={`${id}-tags`} label="Tags · comma separated" value={(fields.tags||[]).join(', ')} onChange={v=>set('tags',v.split(',').map(t=>t.trim()))}/>
    <Input id={`${id}-video_url`} label="Video · HTTPS YouTube/Vimeo (optional)" value={fields.video_url||''} onChange={v=>set('video_url',v)}/>
    <Text testID={`${id}-visibility-notice`} style={ui.muted}>Saved hidden by default. Import publication requires separate confirmation.</Text>
    <View style={ui.row}>{['is_new_arrival','is_trending','is_pinned'].map(k=><Button key={k} id={`${id}-${k}`} title={`${k.replace('is_','').replace(/_/g,' ')}: ${fields[k]?'Yes':'No'}`} active={!!fields[k]} onPress={()=>set(k,!fields[k])}/>)}</View>
  </View>;
}