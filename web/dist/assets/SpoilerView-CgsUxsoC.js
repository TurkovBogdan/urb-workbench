import{bH as C,dI as w,by as y,bv as s,bC as d,dk as t,J as $,d5 as g,bB as n,dd as l,e3 as x,bx as B,aR as T,e0 as a,e1 as I,dZ as U,cK as z,cI as M,cE as E,bs as N,cU as b,bd as S,dB as O,d1 as D,bw as F,d4 as H,F as P,be as R,d2 as f}from"./index-DitlXhVX.js";import{P as j}from"./PageHeader-DPt2lRZ0.js";import{C as A}from"./CodeBlock-B_W1LGvP.js";import{V as J}from"./VChip-BV3hIx5o.js";import"./IconCopy-BHBl3qdd.js";const K=["disabled","aria-expanded"],L={class:"spoiler__title"},Q={class:"spoiler__body"},Z={class:"spoiler__content"},q=C({__name:"Spoiler",props:E({title:{},variant:{default:"default"},disabled:{type:Boolean},color:{},activeColor:{}},{modelValue:{type:Boolean,default:!1},modelModifiers:{}}),emits:["update:modelValue"],setup(c){const e=w(c,"modelValue"),r=c,v=N(()=>({...r.color?{"--spoiler-color":r.color}:{},...r.activeColor?{"--spoiler-active-color":r.activeColor}:{}}));function _(){r.disabled||(e.value=!e.value)}return(p,u)=>(b(),y("div",{class:M(["spoiler",[`spoiler--${c.variant}`,{"spoiler--open":e.value,"spoiler--disabled":c.disabled}]]),style:z(v.value)},[s("button",{type:"button",class:"spoiler__head",disabled:c.disabled,"aria-expanded":e.value,onClick:_},[d(t($),{class:"spoiler__chevron",size:16,"stroke-width":2}),s("span",L,[g(p.$slots,"title",{},()=>[n(l(c.title),1)],!0)]),p.$slots.actions?(b(),y("span",{key:0,class:"spoiler__actions",onClick:u[0]||(u[0]=x(()=>{},["stop"]))},[g(p.$slots,"actions",{},void 0,!0)])):B("",!0)],8,K),d(T,null,{default:a(()=>[I(s("div",Q,[s("div",Z,[g(p.$slots,"default",{},void 0,!0)])],512),[[U,e.value]])]),_:3})],6))}}),m=S(q,[["__scopeId","data-v-befa2c34"]]),G={class:"ds-page"},W={class:"ds-section"},X={class:"mb-3"},Y={class:"ds-stack"},ss={class:"ds-section"},es={class:"mb-3"},ts={class:"ds-card"},os={class:"ds-tag"},ls={class:"ds-controls"},is={class:"ds-spec"},as={class:"ds-section"},ds={class:"mb-3"},ns={class:"ds-stack"},rs={class:"ds-section"},cs={class:"mb-3"},ps={class:"ds-card"},ms={class:"ds-row"},us={class:"ds-controls"},vs={class:"ds-section"},_s={class:"mb-3"},fs={class:"ds-card"},bs={class:"ds-row"},gs={class:"ds-controls"},ys={class:"ds-row"},hs={class:"ds-controls"},Vs={class:"ds-section"},Cs={class:"mb-3"},Ss=`<script setup lang="ts">
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
</template>`,ks=C({__name:"SpoilerView",setup(c){const{t:e}=O(),r=f(!1),v=f(!0),_=f(!1),p=f(!1),u=["default","minimal","card"],h=D(Object.fromEntries(u.map(V=>[V,!1])));return(V,o)=>(b(),F(R,null,{default:a(()=>[s("div",G,[d(j,{title:t(e)("design-system.page.spoiler.title"),description:t(e)("design-system.page.spoiler.description"),"back-to":"/design-system"},null,8,["title","description"]),s("section",W,[s("h6",X,l(t(e)("design-system.section.spoiler.basic")),1),s("div",Y,[d(m,{modelValue:r.value,"onUpdate:modelValue":o[0]||(o[0]=i=>r.value=i),title:t(e)("design-system.section.spoiler.sample.title")},{default:a(()=>[n(l(t(e)("design-system.section.spoiler.sample.body")),1)]),_:1},8,["modelValue","title"]),d(m,{modelValue:v.value,"onUpdate:modelValue":o[1]||(o[1]=i=>v.value=i),title:t(e)("design-system.section.spoiler.sample.openTitle")},{default:a(()=>[n(l(t(e)("design-system.section.spoiler.sample.body")),1)]),_:1},8,["modelValue","title"])])]),s("section",ss,[s("h6",es,l(t(e)("design-system.section.spoiler.variants")),1),s("div",ts,[(b(),y(P,null,H(u,i=>s("div",{key:i,class:"ds-row"},[s("span",os,l(i),1),s("div",ls,[d(m,{modelValue:h[i],"onUpdate:modelValue":k=>h[i]=k,variant:i,title:t(e)(`design-system.section.spoiler.variantSample.${i}`)},{default:a(()=>[n(l(t(e)("design-system.section.spoiler.sample.body")),1)]),_:1},8,["modelValue","onUpdate:modelValue","variant","title"])]),s("span",is,'variant="'+l(i)+'"',1)])),64))])]),s("section",as,[s("h6",ds,l(t(e)("design-system.section.spoiler.slots")),1),s("div",ns,[d(m,{variant:"card"},{title:a(()=>[n(l(t(e)("design-system.section.spoiler.sample.attachments")),1)]),actions:a(()=>[d(J,{size:"x-small",variant:"tonal"},{default:a(()=>[...o[4]||(o[4]=[n("3",-1)])]),_:1})]),default:a(()=>[n(" "+l(t(e)("design-system.section.spoiler.sample.body")),1)]),_:1})])]),s("section",rs,[s("h6",cs,l(t(e)("design-system.section.spoiler.states")),1),s("div",ps,[s("div",ms,[o[5]||(o[5]=s("span",{class:"ds-tag"},"disabled",-1)),s("div",us,[d(m,{modelValue:_.value,"onUpdate:modelValue":o[2]||(o[2]=i=>_.value=i),disabled:"",title:t(e)("design-system.section.spoiler.sample.disabledTitle")},{default:a(()=>[n(l(t(e)("design-system.section.spoiler.sample.body")),1)]),_:1},8,["modelValue","title"])]),o[6]||(o[6]=s("span",{class:"ds-spec"},"disabled",-1))])])]),s("section",vs,[s("h6",_s,l(t(e)("design-system.section.spoiler.colors")),1),s("div",fs,[s("div",bs,[o[7]||(o[7]=s("span",{class:"ds-tag"},"accent",-1)),s("div",gs,[d(m,{modelValue:p.value,"onUpdate:modelValue":o[3]||(o[3]=i=>p.value=i),variant:"minimal",color:"var(--text-faint)","active-color":"var(--accent)",title:t(e)("design-system.section.spoiler.sample.colorTitle")},{default:a(()=>[n(l(t(e)("design-system.section.spoiler.sample.body")),1)]),_:1},8,["modelValue","title"])]),o[8]||(o[8]=s("span",{class:"ds-spec"},"color / active-color",-1))]),s("div",ys,[o[9]||(o[9]=s("span",{class:"ds-tag"},"error",-1)),s("div",hs,[d(m,{variant:"minimal",color:"var(--text-faint)","active-color":"var(--error)",title:t(e)("design-system.section.spoiler.sample.dangerTitle")},{default:a(()=>[n(l(t(e)("design-system.section.spoiler.sample.body")),1)]),_:1},8,["title"])]),o[10]||(o[10]=s("span",{class:"ds-spec"},'active-color="var(--error)"',-1))])])]),s("section",Vs,[s("h6",Cs,l(t(e)("design-system.section.spoiler.usage")),1),d(A,{code:Ss,lang:"vue"})])])]),_:1}))}}),Is=S(ks,[["__scopeId","data-v-dbb4df64"]]);export{Is as default};
