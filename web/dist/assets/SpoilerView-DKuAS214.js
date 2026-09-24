import{bj as C,c7 as $,bc as y,b9 as s,bf as n,c0 as t,u as w,bU as g,be as d,b_ as l,ck as x,bb as T,aE as B,ch as a,ci as U,ce as z,bF as M,bD as I,bA as D,b8 as E,bM as f,b2 as S,c6 as F,bQ as N,ba as O,bT as j,F as A,ay as H,b3 as P,bR as b}from"./index-Cf-SeS3Z.js";import{P as Q}from"./PageHeader-DpjZaKE7.js";import{C as R}from"./CodeBlock-FAAA5P2s.js";import"./IconCopy-CMefTlxJ.js";const L=["disabled","aria-expanded"],q={class:"spoiler__title"},G={class:"spoiler__body"},J={class:"spoiler__content"},K=C({__name:"Spoiler",props:D({title:{},variant:{default:"default"},disabled:{type:Boolean},color:{},activeColor:{}},{modelValue:{type:Boolean,default:!1},modelModifiers:{}}),emits:["update:modelValue"],setup(c){const e=$(c,"modelValue"),r=c,v=E(()=>({...r.color?{"--spoiler-color":r.color}:{},...r.activeColor?{"--spoiler-active-color":r.activeColor}:{}}));function _(){r.disabled||(e.value=!e.value)}return(p,u)=>(f(),y("div",{class:I(["spoiler",[`spoiler--${c.variant}`,{"spoiler--open":e.value,"spoiler--disabled":c.disabled}]]),style:M(v.value)},[s("button",{type:"button",class:"spoiler__head",disabled:c.disabled,"aria-expanded":e.value,onClick:_},[n(t(w),{class:"spoiler__chevron",size:16,"stroke-width":2}),s("span",q,[g(p.$slots,"title",{},()=>[d(l(c.title),1)],!0)]),p.$slots.actions?(f(),y("span",{key:0,class:"spoiler__actions",onClick:u[0]||(u[0]=x(()=>{},["stop"]))},[g(p.$slots,"actions",{},void 0,!0)])):T("",!0)],8,L),n(B,null,{default:a(()=>[U(s("div",G,[s("div",J,[g(p.$slots,"default",{},void 0,!0)])],512),[[z,e.value]])]),_:3})],6))}}),m=S(K,[["__scopeId","data-v-4b733c22"]]),W={class:"ds-page"},X={class:"ds-section"},Y={class:"mb-3"},Z={class:"ds-stack"},ss={class:"ds-section"},es={class:"mb-3"},ts={class:"ds-card"},os={class:"ds-tag"},ls={class:"ds-controls"},is={class:"ds-spec"},as={class:"ds-section"},ns={class:"mb-3"},ds={class:"ds-stack"},rs={class:"ds-section"},cs={class:"mb-3"},ps={class:"ds-card"},ms={class:"ds-row"},us={class:"ds-controls"},vs={class:"ds-section"},_s={class:"mb-3"},bs={class:"ds-card"},fs={class:"ds-row"},gs={class:"ds-controls"},ys={class:"ds-row"},hs={class:"ds-controls"},Vs={class:"ds-section"},Cs={class:"mb-3"},Ss=`<script setup lang="ts">
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
</template>`,ks=C({__name:"SpoilerView",setup(c){const{t:e}=F(),r=b(!1),v=b(!0),_=b(!1),p=b(!1),u=["default","minimal","card"],h=N(Object.fromEntries(u.map(V=>[V,!1])));return(V,o)=>(f(),O(P,null,{default:a(()=>[s("div",W,[n(Q,{title:t(e)("design-system.page.spoiler.title"),description:t(e)("design-system.page.spoiler.description"),"back-to":"/design-system"},null,8,["title","description"]),s("section",X,[s("h6",Y,l(t(e)("design-system.section.spoiler.basic")),1),s("div",Z,[n(m,{modelValue:r.value,"onUpdate:modelValue":o[0]||(o[0]=i=>r.value=i),title:t(e)("design-system.section.spoiler.sample.title")},{default:a(()=>[d(l(t(e)("design-system.section.spoiler.sample.body")),1)]),_:1},8,["modelValue","title"]),n(m,{modelValue:v.value,"onUpdate:modelValue":o[1]||(o[1]=i=>v.value=i),title:t(e)("design-system.section.spoiler.sample.openTitle")},{default:a(()=>[d(l(t(e)("design-system.section.spoiler.sample.body")),1)]),_:1},8,["modelValue","title"])])]),s("section",ss,[s("h6",es,l(t(e)("design-system.section.spoiler.variants")),1),s("div",ts,[(f(),y(A,null,j(u,i=>s("div",{key:i,class:"ds-row"},[s("span",os,l(i),1),s("div",ls,[n(m,{modelValue:h[i],"onUpdate:modelValue":k=>h[i]=k,variant:i,title:t(e)(`design-system.section.spoiler.variantSample.${i}`)},{default:a(()=>[d(l(t(e)("design-system.section.spoiler.sample.body")),1)]),_:1},8,["modelValue","onUpdate:modelValue","variant","title"])]),s("span",is,'variant="'+l(i)+'"',1)])),64))])]),s("section",as,[s("h6",ns,l(t(e)("design-system.section.spoiler.slots")),1),s("div",ds,[n(m,{variant:"card"},{title:a(()=>[d(l(t(e)("design-system.section.spoiler.sample.attachments")),1)]),actions:a(()=>[n(H,{size:"x-small",variant:"tonal"},{default:a(()=>[...o[4]||(o[4]=[d("3",-1)])]),_:1})]),default:a(()=>[d(" "+l(t(e)("design-system.section.spoiler.sample.body")),1)]),_:1})])]),s("section",rs,[s("h6",cs,l(t(e)("design-system.section.spoiler.states")),1),s("div",ps,[s("div",ms,[o[5]||(o[5]=s("span",{class:"ds-tag"},"disabled",-1)),s("div",us,[n(m,{modelValue:_.value,"onUpdate:modelValue":o[2]||(o[2]=i=>_.value=i),disabled:"",title:t(e)("design-system.section.spoiler.sample.disabledTitle")},{default:a(()=>[d(l(t(e)("design-system.section.spoiler.sample.body")),1)]),_:1},8,["modelValue","title"])]),o[6]||(o[6]=s("span",{class:"ds-spec"},"disabled",-1))])])]),s("section",vs,[s("h6",_s,l(t(e)("design-system.section.spoiler.colors")),1),s("div",bs,[s("div",fs,[o[7]||(o[7]=s("span",{class:"ds-tag"},"accent",-1)),s("div",gs,[n(m,{modelValue:p.value,"onUpdate:modelValue":o[3]||(o[3]=i=>p.value=i),variant:"minimal",color:"var(--text-faint)","active-color":"var(--accent)",title:t(e)("design-system.section.spoiler.sample.colorTitle")},{default:a(()=>[d(l(t(e)("design-system.section.spoiler.sample.body")),1)]),_:1},8,["modelValue","title"])]),o[8]||(o[8]=s("span",{class:"ds-spec"},"color / active-color",-1))]),s("div",ys,[o[9]||(o[9]=s("span",{class:"ds-tag"},"error",-1)),s("div",hs,[n(m,{variant:"minimal",color:"var(--text-faint)","active-color":"var(--error)",title:t(e)("design-system.section.spoiler.sample.dangerTitle")},{default:a(()=>[d(l(t(e)("design-system.section.spoiler.sample.body")),1)]),_:1},8,["title"])]),o[10]||(o[10]=s("span",{class:"ds-spec"},'active-color="var(--error)"',-1))])])]),s("section",Vs,[s("h6",Cs,l(t(e)("design-system.section.spoiler.usage")),1),n(R,{code:Ss,lang:"vue"})])])]),_:1}))}}),Bs=S(ks,[["__scopeId","data-v-dbb4df64"]]);export{Bs as default};
