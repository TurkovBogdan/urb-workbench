import{bL as C,dV as w,bC as y,bz as s,bG as d,dx as t,L as $,dd as b,ei as x,bB as T,aT as B,ef as a,eg as z,ec as O,cQ as U,cO as I,cK as M,bw as F,c_ as g,bF as n,dq as l,bf as S,dO as N,d9 as D,bA as E,dc as L,F as A,bg as H,da as f}from"./index-p2dGIhHa.js";import{P}from"./PageHeader-DvpoqMhr.js";import{C as Q}from"./CodeBlock-DF78K-pO.js";import{V as j}from"./VChip-Cg71oGbz.js";import"./IconCopy-CEZ0ci6b.js";const q=["disabled","aria-expanded"],G={class:"spoiler__title"},K={class:"spoiler__body"},R={class:"spoiler__content"},J=C({__name:"Spoiler",props:M({title:{},variant:{default:"default"},disabled:{type:Boolean},color:{},activeColor:{}},{modelValue:{type:Boolean,default:!1},modelModifiers:{}}),emits:["update:modelValue"],setup(c){const e=w(c,"modelValue"),r=c,v=F(()=>({...r.color?{"--spoiler-color":r.color}:{},...r.activeColor?{"--spoiler-active-color":r.activeColor}:{}}));function _(){r.disabled||(e.value=!e.value)}return(p,u)=>(g(),y("div",{class:I(["spoiler",[`spoiler--${c.variant}`,{"spoiler--open":e.value,"spoiler--disabled":c.disabled}]]),style:U(v.value)},[s("button",{type:"button",class:"spoiler__head",disabled:c.disabled,"aria-expanded":e.value,onClick:_},[d(t($),{class:"spoiler__chevron",size:16,"stroke-width":2}),s("span",G,[b(p.$slots,"title",{},()=>[n(l(c.title),1)],!0)]),p.$slots.actions?(g(),y("span",{key:0,class:"spoiler__actions",onClick:u[0]||(u[0]=x(()=>{},["stop"]))},[b(p.$slots,"actions",{},void 0,!0)])):T("",!0)],8,q),d(B,null,{default:a(()=>[z(s("div",K,[s("div",R,[b(p.$slots,"default",{},void 0,!0)])],512),[[O,e.value]])]),_:3})],6))}}),m=S(J,[["__scopeId","data-v-befa2c34"]]),W={class:"ds-page"},X={class:"ds-section"},Y={class:"mb-3"},Z={class:"ds-stack"},ss={class:"ds-section"},es={class:"mb-3"},ts={class:"ds-card"},os={class:"ds-tag"},ls={class:"ds-controls"},is={class:"ds-spec"},as={class:"ds-section"},ds={class:"mb-3"},ns={class:"ds-stack"},rs={class:"ds-section"},cs={class:"mb-3"},ps={class:"ds-card"},ms={class:"ds-row"},us={class:"ds-controls"},vs={class:"ds-section"},_s={class:"mb-3"},fs={class:"ds-card"},gs={class:"ds-row"},bs={class:"ds-controls"},ys={class:"ds-row"},hs={class:"ds-controls"},Vs={class:"ds-section"},Cs={class:"mb-3"},Ss=`<script setup lang="ts">
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
</template>`,ks=C({__name:"SpoilerView",setup(c){const{t:e}=N(),r=f(!1),v=f(!0),_=f(!1),p=f(!1),u=["default","minimal","card"],h=D(Object.fromEntries(u.map(V=>[V,!1])));return(V,o)=>(g(),E(H,null,{default:a(()=>[s("div",W,[d(P,{title:t(e)("design-system.page.spoiler.title"),description:t(e)("design-system.page.spoiler.description"),"back-to":"/design-system"},null,8,["title","description"]),s("section",X,[s("h6",Y,l(t(e)("design-system.section.spoiler.basic")),1),s("div",Z,[d(m,{modelValue:r.value,"onUpdate:modelValue":o[0]||(o[0]=i=>r.value=i),title:t(e)("design-system.section.spoiler.sample.title")},{default:a(()=>[n(l(t(e)("design-system.section.spoiler.sample.body")),1)]),_:1},8,["modelValue","title"]),d(m,{modelValue:v.value,"onUpdate:modelValue":o[1]||(o[1]=i=>v.value=i),title:t(e)("design-system.section.spoiler.sample.openTitle")},{default:a(()=>[n(l(t(e)("design-system.section.spoiler.sample.body")),1)]),_:1},8,["modelValue","title"])])]),s("section",ss,[s("h6",es,l(t(e)("design-system.section.spoiler.variants")),1),s("div",ts,[(g(),y(A,null,L(u,i=>s("div",{key:i,class:"ds-row"},[s("span",os,l(i),1),s("div",ls,[d(m,{modelValue:h[i],"onUpdate:modelValue":k=>h[i]=k,variant:i,title:t(e)(`design-system.section.spoiler.variantSample.${i}`)},{default:a(()=>[n(l(t(e)("design-system.section.spoiler.sample.body")),1)]),_:1},8,["modelValue","onUpdate:modelValue","variant","title"])]),s("span",is,'variant="'+l(i)+'"',1)])),64))])]),s("section",as,[s("h6",ds,l(t(e)("design-system.section.spoiler.slots")),1),s("div",ns,[d(m,{variant:"card"},{title:a(()=>[n(l(t(e)("design-system.section.spoiler.sample.attachments")),1)]),actions:a(()=>[d(j,{size:"x-small",variant:"tonal"},{default:a(()=>[...o[4]||(o[4]=[n("3",-1)])]),_:1})]),default:a(()=>[n(" "+l(t(e)("design-system.section.spoiler.sample.body")),1)]),_:1})])]),s("section",rs,[s("h6",cs,l(t(e)("design-system.section.spoiler.states")),1),s("div",ps,[s("div",ms,[o[5]||(o[5]=s("span",{class:"ds-tag"},"disabled",-1)),s("div",us,[d(m,{modelValue:_.value,"onUpdate:modelValue":o[2]||(o[2]=i=>_.value=i),disabled:"",title:t(e)("design-system.section.spoiler.sample.disabledTitle")},{default:a(()=>[n(l(t(e)("design-system.section.spoiler.sample.body")),1)]),_:1},8,["modelValue","title"])]),o[6]||(o[6]=s("span",{class:"ds-spec"},"disabled",-1))])])]),s("section",vs,[s("h6",_s,l(t(e)("design-system.section.spoiler.colors")),1),s("div",fs,[s("div",gs,[o[7]||(o[7]=s("span",{class:"ds-tag"},"accent",-1)),s("div",bs,[d(m,{modelValue:p.value,"onUpdate:modelValue":o[3]||(o[3]=i=>p.value=i),variant:"minimal",color:"var(--text-faint)","active-color":"var(--accent)",title:t(e)("design-system.section.spoiler.sample.colorTitle")},{default:a(()=>[n(l(t(e)("design-system.section.spoiler.sample.body")),1)]),_:1},8,["modelValue","title"])]),o[8]||(o[8]=s("span",{class:"ds-spec"},"color / active-color",-1))]),s("div",ys,[o[9]||(o[9]=s("span",{class:"ds-tag"},"error",-1)),s("div",hs,[d(m,{variant:"minimal",color:"var(--text-faint)","active-color":"var(--error)",title:t(e)("design-system.section.spoiler.sample.dangerTitle")},{default:a(()=>[n(l(t(e)("design-system.section.spoiler.sample.body")),1)]),_:1},8,["title"])]),o[10]||(o[10]=s("span",{class:"ds-spec"},'active-color="var(--error)"',-1))])])]),s("section",Vs,[s("h6",Cs,l(t(e)("design-system.section.spoiler.usage")),1),d(Q,{code:Ss,lang:"vue"})])])]),_:1}))}}),zs=S(ks,[["__scopeId","data-v-dbb4df64"]]);export{zs as default};
