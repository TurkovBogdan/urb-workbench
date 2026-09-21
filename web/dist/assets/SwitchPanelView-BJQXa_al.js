import{bg as P,c0 as O,bL as y,b7 as U,cb as V,b6 as s,bc as l,bX as i,bV as n,bb as k,b9 as S,bO as T,F as x,b0 as D,bM as d,bH as r,a$ as C}from"./index-CtJp1Su1.js";import{P as E}from"./PageHeader-CMmgx8Sl.js";import{S as a}from"./SwitchPanel-DbLuG0cl.js";import{C as B}from"./CodeBlock-CswMfkng.js";const I={class:"ds-page"},N={class:"ds-section"},$={class:"mb-3"},j={class:"ds-card"},H={class:"ds-row"},F={class:"ds-controls"},L={class:"ds-row"},M={class:"ds-controls"},z={class:"ds-row"},X={class:"ds-controls"},q={class:"ds-section"},A={class:"mb-3"},G={class:"ds-card"},J={class:"ds-row"},K={class:"ds-controls"},Q={class:"ds-section"},R={class:"mb-3"},W={class:"ds-card"},Y={class:"ds-tag"},Z={class:"ds-controls"},ss={class:"ds-spec"},es={class:"ds-section"},ts={class:"mb-3"},os={class:"ds-card"},is={class:"ds-tag"},ns={class:"ds-controls"},ls={class:"ds-spec"},as={class:"ds-section"},ds={class:"mb-3"},cs={class:"ds-card"},ps={class:"ds-row"},rs={class:"ds-controls"},ms={class:"ds-section"},us={class:"mb-3"},hs=`<script setup lang="ts">
import { ref } from 'vue'
import SwitchPanel from '@/components/SwitchPanel.vue'

const active = ref(true)
const paused = ref(false)
<\/script>

<template>
  <!-- Common title + description -->
  <SwitchPanel
    v-model="active"
    title="Mailbox active"
    description="Email import is enabled."
  />

  <!-- Separate text for the on / off state -->
  <SwitchPanel
    v-model="paused"
    title-on="Import enabled"
    title-off="Import disabled"
    description-on="Emails are synced on schedule."
    description-off="Synchronization is paused."
  />

  <!-- Semantic tone — changes the panel background and the switch color -->
  <SwitchPanel
    v-model="active"
    tone="warning"
    title="Heads up"
    description="This action affects every mailbox."
  />

  <!-- Neutral panel, coloured switch only — switchTone overrides just the switch -->
  <SwitchPanel
    v-model="paused"
    switch-tone="error"
    title="Exclude from processing"
    description="The item won't be processed."
  />
</template>`,ws=P({__name:"SwitchPanelView",setup(fs){const{t:o}=O(),m=d(!0),u=d(!1),h=d(!0),w=d(!1),f=d(!0),_=["default","primary","info","success","warning","error","transparent"],v=y(Object.fromEntries(_.map(c=>[c,!0]))),g=["primary","info","success","warning","error"],b=y(Object.fromEntries(g.map(c=>[c,!0])));return(c,e)=>(r(),U(D,null,{default:V(()=>[s("div",I,[l(E,{title:i(o)("design-system.page.switch-panel.title"),description:i(o)("design-system.page.switch-panel.description"),"back-to":"/design-system"},null,8,["title","description"]),s("section",N,[s("h6",$,n(i(o)("design-system.section.switch-panel.basic")),1),s("div",j,[s("div",H,[e[5]||(e[5]=s("span",{class:"ds-tag"},"title + desc",-1)),s("div",F,[l(a,{modelValue:u.value,"onUpdate:modelValue":e[0]||(e[0]=t=>u.value=t),title:i(o)("design-system.section.switch-panel.sample.title"),description:i(o)("design-system.section.switch-panel.sample.desc")},null,8,["modelValue","title","description"])]),e[6]||(e[6]=s("span",{class:"ds-spec"},"v-model · title · description",-1))]),s("div",L,[e[7]||(e[7]=s("span",{class:"ds-tag"},"title only",-1)),s("div",M,[l(a,{modelValue:h.value,"onUpdate:modelValue":e[1]||(e[1]=t=>h.value=t),title:i(o)("design-system.section.switch-panel.sample.activeTitle")},null,8,["modelValue","title"])]),e[8]||(e[8]=s("span",{class:"ds-spec"},"title",-1))]),s("div",z,[e[9]||(e[9]=s("span",{class:"ds-tag"},"slot",-1)),s("div",X,[l(a,{modelValue:m.value,"onUpdate:modelValue":e[2]||(e[2]=t=>m.value=t)},{default:V(()=>[k(n(i(o)("design-system.section.switch-panel.sample.slot")),1)]),_:1},8,["modelValue"])]),e[10]||(e[10]=s("span",{class:"ds-spec"},"default slot — rich text",-1))])])]),s("section",q,[s("h6",A,n(i(o)("design-system.section.switch-panel.stateText")),1),s("div",G,[s("div",J,[e[11]||(e[11]=s("span",{class:"ds-tag"},"on / off",-1)),s("div",K,[l(a,{modelValue:w.value,"onUpdate:modelValue":e[3]||(e[3]=t=>w.value=t),"title-on":i(o)("design-system.section.switch-panel.sample.onTitle"),"title-off":i(o)("design-system.section.switch-panel.sample.offTitle"),"description-on":i(o)("design-system.section.switch-panel.sample.onDesc"),"description-off":i(o)("design-system.section.switch-panel.sample.offDesc")},null,8,["modelValue","title-on","title-off","description-on","description-off"])]),e[12]||(e[12]=s("span",{class:"ds-spec"},"titleOn/Off · descriptionOn/Off",-1))])])]),s("section",Q,[s("h6",R,n(i(o)("design-system.section.switch-panel.tones")),1),s("div",W,[(r(),S(x,null,T(_,t=>s("div",{key:t,class:"ds-row"},[s("span",Y,n(t),1),s("div",Z,[l(a,{modelValue:v[t],"onUpdate:modelValue":p=>v[t]=p,tone:t,title:i(o)(`design-system.section.switch-panel.toneSample.${t}`),description:i(o)("design-system.section.switch-panel.toneDesc")},null,8,["modelValue","onUpdate:modelValue","tone","title","description"])]),s("span",ss,'tone="'+n(t)+'"',1)])),64))])]),s("section",es,[s("h6",ts,n(i(o)("design-system.section.switch-panel.switchTone")),1),s("div",os,[(r(),S(x,null,T(g,t=>s("div",{key:t,class:"ds-row"},[s("span",is,n(t),1),s("div",ns,[l(a,{modelValue:b[t],"onUpdate:modelValue":p=>b[t]=p,"switch-tone":t,title:i(o)(`design-system.section.switch-panel.toneSample.${t}`),description:i(o)("design-system.section.switch-panel.switchToneDesc")},null,8,["modelValue","onUpdate:modelValue","switch-tone","title","description"])]),s("span",ls,'switch-tone="'+n(t)+'"',1)])),64))])]),s("section",as,[s("h6",ds,n(i(o)("design-system.section.switch-panel.states")),1),s("div",cs,[s("div",ps,[e[13]||(e[13]=s("span",{class:"ds-tag"},"disabled",-1)),s("div",rs,[l(a,{modelValue:f.value,"onUpdate:modelValue":e[4]||(e[4]=t=>f.value=t),disabled:"",title:i(o)("design-system.section.switch-panel.sample.disabledTitle"),description:i(o)("design-system.section.switch-panel.sample.disabledDesc")},null,8,["modelValue","title","description"])]),e[14]||(e[14]=s("span",{class:"ds-spec"},"disabled",-1))])])]),s("section",ms,[s("h6",us,n(i(o)("design-system.section.switch-panel.usage")),1),l(B,{code:hs,lang:"vue"})])])]),_:1}))}}),ys=C(ws,[["__scopeId","data-v-a51b5593"]]);export{ys as default};
