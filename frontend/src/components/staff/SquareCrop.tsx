import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { PanResponder, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { api } from '../../api';
import { Button, ui } from './Controls';
import PrivateImage from './PrivateImage';

const clamp=(v:number,min:number,max:number)=>Math.max(min,Math.min(v,max));
export default function SquareCrop({id,jobId,page,initial,onSave,disabled}:{id:string;jobId:string;page:number;initial:number[]|null;onSave:(v:number[])=>void;disabled:boolean}) {
  const [geometry,setGeometry]=useState<any>(null),[error,setError]=useState(''),[width,setWidth]=useState(0);
  const [box,setBox]=useState(initial||[50,100,250,300]);
  const current=useRef(box),start=useRef(box);current.current=box;
  useEffect(()=>{api.get(`/pdf-upload/${jobId}/pages/${page}/image?metadata=true`).then(setGeometry).catch(e=>setError(e.message));},[jobId,page]);
  const scale=width/(geometry?.width_points||595.276);
  const gesture=useCallback((resize:boolean)=>PanResponder.create({
    onStartShouldSetPanResponder:()=>!disabled,onMoveShouldSetPanResponder:()=>!disabled,
    onPanResponderGrant:()=>{start.current=[...current.current];},
    onPanResponderTerminationRequest:()=>false,
    onPanResponderMove:(_,g)=>{
      const [x,y,x1,y1]=start.current,size=x1-x;
      if(resize){const side=clamp(size+Math.max(g.dx,g.dy)/scale,24,Math.min(geometry.width_points-x,geometry.height_points-y));setBox([x,y,x+side,y+side]);}
      else{const nx=clamp(x+g.dx/scale,0,geometry.width_points-size),ny=clamp(y+g.dy/scale,0,geometry.height_points-(y1-y));setBox([nx,ny,nx+size,ny+size]);}
    },
  }),[disabled,scale,geometry]);
  // Recreate only when the page layout changes; gesture start comes from the live ref.
  const move=useMemo(()=>gesture(false),[gesture]);
  const resize=useMemo(()=>gesture(true),[gesture]);
  return <View style={ui.card}><Text testID={`${id}-instructions`} style={ui.muted}>Drag inside the square to move. Drag the corner to resize. Keep only the photograph, without labels. The page is shown upright.</Text>
    {!!error&&<Text testID={`${id}-error`} style={ui.error}>{error}</Text>}
    {geometry&&<View testID={`${id}-page`} onLayout={e=>setWidth(e.nativeEvent.layout.width)} style={[styles.page,{aspectRatio:geometry.width_points/geometry.height_points}]}>
      <PrivateImage id={`${id}-source`} url={`/api/pdf-upload/${jobId}/pages/${page}/image`} style={StyleSheet.absoluteFillObject}/>
      {width>0&&<View testID={`${id}-square`} accessibilityLabel="Move square crop" {...move.panHandlers} style={[styles.square,{left:box[0]*scale,top:box[1]*scale,width:(box[2]-box[0])*scale,height:(box[3]-box[1])*scale}]}>
        <View testID={`${id}-resize`} accessibilityLabel="Resize square crop" {...resize.panHandlers} style={styles.handle}><Ionicons name="resize" color="#111" size={22}/></View>
      </View>}
    </View>}
    <View style={ui.row}><Button id={`${id}-smaller`} title="Smaller" disabled={!geometry||disabled} onPress={()=>{const side=Math.max(24,(box[2]-box[0])*0.9);setBox([box[0],box[1],box[0]+side,box[1]+side]);}}/><Button id={`${id}-reset`} title="Reset crop" onPress={()=>setBox(initial||[50,100,250,300])}/></View>
    <Button id={`pdf-save-crop-${id}`} title="Apply square crop" disabled={disabled||!geometry} onPress={()=>onSave(box.map(v=>Math.round(v*1000)/1000))}/>
  </View>;
}
const styles=StyleSheet.create({page:{width:'100%',backgroundColor:'#fff',overflow:'hidden'},square:{position:'absolute',borderWidth:2,borderColor:'#e9b74e',backgroundColor:'rgba(233,183,78,0.08)'},handle:{position:'absolute',right:0,bottom:0,width:44,height:44,backgroundColor:'#e9b74e',alignItems:'center',justifyContent:'center'}});