import{bM as h,dR as V,dc as S,bA as C,ei as a,bz as s,bH as n,dA as o,dt as i,bF as d,bC as x,df as k,F as w,bh as T,dd as c,d1 as b,bg as U}from"./index-Cs8WGrv5.js";import{P as B}from"./PageHeader-DnMh1lOM.js";import{S as r}from"./Spoiler-Dgfj2dea.js";import{C as z}from"./CodeBlock-DTQ_OY4m.js";import{V as F}from"./VChip-BJmEj44S.js";import"./IconCopy-Dg_K4k6G.js";const O={class:"ds-page"},A={class:"ds-section"},H={class:"mb-3"},I={class:"ds-stack"},N={class:"ds-section"},D={class:"mb-3"},E={class:"ds-card"},M={class:"ds-tag"},P={class:"ds-controls"},$={class:"ds-spec"},j={class:"ds-section"},L={class:"mb-3"},Q={class:"ds-stack"},R={class:"ds-section"},q={class:"mb-3"},G={class:"ds-card"},J={class:"ds-row"},K={class:"ds-controls"},W={class:"ds-section"},X={class:"mb-3"},Y={class:"ds-card"},Z={class:"ds-row"},ss={class:"ds-controls"},es={class:"ds-row"},ts={class:"ds-controls"},os={class:"ds-section"},is={class:"mb-3"},ls=`<script setup lang="ts">
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
</template>`,as=h({__name:"SpoilerView",setup(ns){const{t:e}=V(),p=c(!1),m=c(!0),u=c(!1),_=c(!1),v=["default","minimal","card"],g=S(Object.fromEntries(v.map(f=>[f,!1])));return(f,t)=>(b(),C(T,null,{default:a(()=>[s("div",O,[n(B,{title:o(e)("design-system.page.spoiler.title"),description:o(e)("design-system.page.spoiler.description"),"back-to":"/design-system"},null,8,["title","description"]),s("section",A,[s("h6",H,i(o(e)("design-system.section.spoiler.basic")),1),s("div",I,[n(r,{modelValue:p.value,"onUpdate:modelValue":t[0]||(t[0]=l=>p.value=l),title:o(e)("design-system.section.spoiler.sample.title")},{default:a(()=>[d(i(o(e)("design-system.section.spoiler.sample.body")),1)]),_:1},8,["modelValue","title"]),n(r,{modelValue:m.value,"onUpdate:modelValue":t[1]||(t[1]=l=>m.value=l),title:o(e)("design-system.section.spoiler.sample.openTitle")},{default:a(()=>[d(i(o(e)("design-system.section.spoiler.sample.body")),1)]),_:1},8,["modelValue","title"])])]),s("section",N,[s("h6",D,i(o(e)("design-system.section.spoiler.variants")),1),s("div",E,[(b(),x(w,null,k(v,l=>s("div",{key:l,class:"ds-row"},[s("span",M,i(l),1),s("div",P,[n(r,{modelValue:g[l],"onUpdate:modelValue":y=>g[l]=y,variant:l,title:o(e)(`design-system.section.spoiler.variantSample.${l}`)},{default:a(()=>[d(i(o(e)("design-system.section.spoiler.sample.body")),1)]),_:1},8,["modelValue","onUpdate:modelValue","variant","title"])]),s("span",$,'variant="'+i(l)+'"',1)])),64))])]),s("section",j,[s("h6",L,i(o(e)("design-system.section.spoiler.slots")),1),s("div",Q,[n(r,{variant:"card"},{title:a(()=>[d(i(o(e)("design-system.section.spoiler.sample.attachments")),1)]),actions:a(()=>[n(F,{size:"x-small",variant:"tonal"},{default:a(()=>[...t[4]||(t[4]=[d("3",-1)])]),_:1})]),default:a(()=>[d(" "+i(o(e)("design-system.section.spoiler.sample.body")),1)]),_:1})])]),s("section",R,[s("h6",q,i(o(e)("design-system.section.spoiler.states")),1),s("div",G,[s("div",J,[t[5]||(t[5]=s("span",{class:"ds-tag"},"disabled",-1)),s("div",K,[n(r,{modelValue:u.value,"onUpdate:modelValue":t[2]||(t[2]=l=>u.value=l),disabled:"",title:o(e)("design-system.section.spoiler.sample.disabledTitle")},{default:a(()=>[d(i(o(e)("design-system.section.spoiler.sample.body")),1)]),_:1},8,["modelValue","title"])]),t[6]||(t[6]=s("span",{class:"ds-spec"},"disabled",-1))])])]),s("section",W,[s("h6",X,i(o(e)("design-system.section.spoiler.colors")),1),s("div",Y,[s("div",Z,[t[7]||(t[7]=s("span",{class:"ds-tag"},"accent",-1)),s("div",ss,[n(r,{modelValue:_.value,"onUpdate:modelValue":t[3]||(t[3]=l=>_.value=l),variant:"minimal",color:"var(--text-faint)","active-color":"var(--accent)",title:o(e)("design-system.section.spoiler.sample.colorTitle")},{default:a(()=>[d(i(o(e)("design-system.section.spoiler.sample.body")),1)]),_:1},8,["modelValue","title"])]),t[8]||(t[8]=s("span",{class:"ds-spec"},"color / active-color",-1))]),s("div",es,[t[9]||(t[9]=s("span",{class:"ds-tag"},"error",-1)),s("div",ts,[n(r,{variant:"minimal",color:"var(--text-faint)","active-color":"var(--error)",title:o(e)("design-system.section.spoiler.sample.dangerTitle")},{default:a(()=>[d(i(o(e)("design-system.section.spoiler.sample.body")),1)]),_:1},8,["title"])]),t[10]||(t[10]=s("span",{class:"ds-spec"},'active-color="var(--error)"',-1))])])]),s("section",os,[s("h6",is,i(o(e)("design-system.section.spoiler.usage")),1),n(z,{code:ls,lang:"vue"})])])]),_:1}))}}),_s=U(as,[["__scopeId","data-v-dbb4df64"]]);export{_s as default};
