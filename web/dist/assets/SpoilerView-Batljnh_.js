import{bB as S,dz as w,bs as y,bp as s,bw as d,db as t,z as $,cZ as g,bv as n,d4 as l,dV as x,br as B,aM as T,dS as a,dT as z,dP as M,cD as U,cB as I,cx as N,bm as D,cN as f,b8 as C,ds as O,cV as E,bq as F,cY as P,F as H,b9 as j,cW as b}from"./index-DANwfCw4.js";import{P as q}from"./PageHeader-C3SwBhck.js";import{C as A}from"./CodeBlock-CIrpO5cp.js";import{V as L}from"./VChip-BF0RHZNl.js";import"./IconCopy-BQLdjwjT.js";const Q=["disabled","aria-expanded"],R={class:"spoiler__title"},W={class:"spoiler__body"},Y={class:"spoiler__content"},Z=S({__name:"Spoiler",props:N({title:{},variant:{default:"default"},disabled:{type:Boolean},color:{},activeColor:{}},{modelValue:{type:Boolean,default:!1},modelModifiers:{}}),emits:["update:modelValue"],setup(c){const e=w(c,"modelValue"),r=c,v=D(()=>({...r.color?{"--spoiler-color":r.color}:{},...r.activeColor?{"--spoiler-active-color":r.activeColor}:{}}));function _(){r.disabled||(e.value=!e.value)}return(p,u)=>(f(),y("div",{class:I(["spoiler",[`spoiler--${c.variant}`,{"spoiler--open":e.value,"spoiler--disabled":c.disabled}]]),style:U(v.value)},[s("button",{type:"button",class:"spoiler__head",disabled:c.disabled,"aria-expanded":e.value,onClick:_},[d(t($),{class:"spoiler__chevron",size:16,"stroke-width":2}),s("span",R,[g(p.$slots,"title",{},()=>[n(l(c.title),1)],!0)]),p.$slots.actions?(f(),y("span",{key:0,class:"spoiler__actions",onClick:u[0]||(u[0]=x(()=>{},["stop"]))},[g(p.$slots,"actions",{},void 0,!0)])):B("",!0)],8,Q),d(T,null,{default:a(()=>[z(s("div",W,[s("div",Y,[g(p.$slots,"default",{},void 0,!0)])],512),[[M,e.value]])]),_:3})],6))}}),m=C(Z,[["__scopeId","data-v-befa2c34"]]),G={class:"ds-page"},J={class:"ds-section"},K={class:"mb-3"},X={class:"ds-stack"},ss={class:"ds-section"},es={class:"mb-3"},ts={class:"ds-card"},os={class:"ds-tag"},ls={class:"ds-controls"},is={class:"ds-spec"},as={class:"ds-section"},ds={class:"mb-3"},ns={class:"ds-stack"},rs={class:"ds-section"},cs={class:"mb-3"},ps={class:"ds-card"},ms={class:"ds-row"},us={class:"ds-controls"},vs={class:"ds-section"},_s={class:"mb-3"},bs={class:"ds-card"},fs={class:"ds-row"},gs={class:"ds-controls"},ys={class:"ds-row"},hs={class:"ds-controls"},Vs={class:"ds-section"},Ss={class:"mb-3"},Cs=`<script setup lang="ts">
import { ref } from 'vue'
import Spoiler from '@/components/Spoiler.vue'

const open = ref(false)
<\/script>

<template>
  <!-- Title + content, default theme -->
  <Spoiler v-model="open" title="Technical details">
    Hidden content goes here.
  </Spoiler>

  <!-- Minimal theme — borderless uppercase label -->
  <Spoiler title="Quoted history" variant="minimal">
    <p>Older messages…</p>
  </Spoiler>

  <!-- Custom title + trailing actions -->
  <Spoiler variant="card">
    <template #title>Attachments</template>
    <template #actions>
      <VChip size="x-small">3</VChip>
    </template>
    <p>Files…</p>
  </Spoiler>

  <!-- Custom header colours: resting (color) + hover (active-color) -->
  <Spoiler
    variant="minimal"
    title="Danger zone"
    color="var(--text-faint)"
    active-color="var(--error)"
  >
    <p>Irreversible actions…</p>
  </Spoiler>
</template>`,ks=S({__name:"SpoilerView",setup(c){const{t:e}=O(),r=b(!1),v=b(!0),_=b(!1),p=b(!1),u=["default","minimal","card"],h=E(Object.fromEntries(u.map(V=>[V,!1])));return(V,o)=>(f(),F(j,null,{default:a(()=>[s("div",G,[d(q,{title:t(e)("design-system.page.spoiler.title"),description:t(e)("design-system.page.spoiler.description"),"back-to":"/design-system"},null,8,["title","description"]),s("section",J,[s("h6",K,l(t(e)("design-system.section.spoiler.basic")),1),s("div",X,[d(m,{modelValue:r.value,"onUpdate:modelValue":o[0]||(o[0]=i=>r.value=i),title:t(e)("design-system.section.spoiler.sample.title")},{default:a(()=>[n(l(t(e)("design-system.section.spoiler.sample.body")),1)]),_:1},8,["modelValue","title"]),d(m,{modelValue:v.value,"onUpdate:modelValue":o[1]||(o[1]=i=>v.value=i),title:t(e)("design-system.section.spoiler.sample.openTitle")},{default:a(()=>[n(l(t(e)("design-system.section.spoiler.sample.body")),1)]),_:1},8,["modelValue","title"])])]),s("section",ss,[s("h6",es,l(t(e)("design-system.section.spoiler.variants")),1),s("div",ts,[(f(),y(H,null,P(u,i=>s("div",{key:i,class:"ds-row"},[s("span",os,l(i),1),s("div",ls,[d(m,{modelValue:h[i],"onUpdate:modelValue":k=>h[i]=k,variant:i,title:t(e)(`design-system.section.spoiler.variantSample.${i}`)},{default:a(()=>[n(l(t(e)("design-system.section.spoiler.sample.body")),1)]),_:1},8,["modelValue","onUpdate:modelValue","variant","title"])]),s("span",is,'variant="'+l(i)+'"',1)])),64))])]),s("section",as,[s("h6",ds,l(t(e)("design-system.section.spoiler.slots")),1),s("div",ns,[d(m,{variant:"card"},{title:a(()=>[n(l(t(e)("design-system.section.spoiler.sample.attachments")),1)]),actions:a(()=>[d(L,{size:"x-small",variant:"tonal"},{default:a(()=>[...o[4]||(o[4]=[n("3",-1)])]),_:1})]),default:a(()=>[n(" "+l(t(e)("design-system.section.spoiler.sample.body")),1)]),_:1})])]),s("section",rs,[s("h6",cs,l(t(e)("design-system.section.spoiler.states")),1),s("div",ps,[s("div",ms,[o[5]||(o[5]=s("span",{class:"ds-tag"},"disabled",-1)),s("div",us,[d(m,{modelValue:_.value,"onUpdate:modelValue":o[2]||(o[2]=i=>_.value=i),disabled:"",title:t(e)("design-system.section.spoiler.sample.disabledTitle")},{default:a(()=>[n(l(t(e)("design-system.section.spoiler.sample.body")),1)]),_:1},8,["modelValue","title"])]),o[6]||(o[6]=s("span",{class:"ds-spec"},"disabled",-1))])])]),s("section",vs,[s("h6",_s,l(t(e)("design-system.section.spoiler.colors")),1),s("div",bs,[s("div",fs,[o[7]||(o[7]=s("span",{class:"ds-tag"},"accent",-1)),s("div",gs,[d(m,{modelValue:p.value,"onUpdate:modelValue":o[3]||(o[3]=i=>p.value=i),variant:"minimal",color:"var(--text-faint)","active-color":"var(--accent)",title:t(e)("design-system.section.spoiler.sample.colorTitle")},{default:a(()=>[n(l(t(e)("design-system.section.spoiler.sample.body")),1)]),_:1},8,["modelValue","title"])]),o[8]||(o[8]=s("span",{class:"ds-spec"},"color / active-color",-1))]),s("div",ys,[o[9]||(o[9]=s("span",{class:"ds-tag"},"error",-1)),s("div",hs,[d(m,{variant:"minimal",color:"var(--text-faint)","active-color":"var(--error)",title:t(e)("design-system.section.spoiler.sample.dangerTitle")},{default:a(()=>[n(l(t(e)("design-system.section.spoiler.sample.body")),1)]),_:1},8,["title"])]),o[10]||(o[10]=s("span",{class:"ds-spec"},'active-color="var(--error)"',-1))])])]),s("section",Vs,[s("h6",Ss,l(t(e)("design-system.section.spoiler.usage")),1),d(A,{code:Cs,lang:"vue"})])])]),_:1}))}}),zs=C(ks,[["__scopeId","data-v-dbb4df64"]]);export{zs as default};
