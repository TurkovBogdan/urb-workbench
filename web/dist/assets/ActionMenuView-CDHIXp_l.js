import{bB as _,ds as g,bq as f,dT as h,bp as t,bw as m,db as n,d4 as s,cB as b,bv as v,b9 as k,cW as d,bm as w,cN as A,$ as I,p as C,n as x,b8 as M}from"./index-TGoARfiN.js";import{I as T}from"./IconTrash-Bal_RUpZ.js";import{P as B}from"./PageHeader-CobsaQM5.js";import{A as D}from"./ActionMenu-Ch-rkjWw.js";import{C as E}from"./CodeBlock-Daw53JCA.js";import"./IconCopy-CbcSVm1N.js";import"./IconDotsVertical-C-zD6G46.js";import"./KeyCap-DogGLC3f.js";import"./useClipboard-DrULfouC.js";const P={class:"ds-page"},V={class:"ds-section"},N={class:"mb-1"},O={class:"ds-note"},S={class:"ds-card"},$={class:"ds-sample__title"},U={class:"ds-last"},W={class:"ds-section"},q={class:"mb-3"},z=`<script setup lang="ts">
import { computed, ref } from 'vue'
import { IconPencil, IconTrash } from '@tabler/icons-vue'
import ActionMenu, { type ActionMenuItem } from '@/components/ActionMenu.vue'

const menu = ref<InstanceType<typeof ActionMenu>>()
const menuOpen = ref(false)

// The key is a field of the item: the menu draws it and runs the item on it.
// Letters by meaning — E edit, D delete, C cancel; a digit only where one was asked for
const items = computed<ActionMenuItem[]>(() => [
  { key: 'edit', icon: IconPencil, label: 'Edit', hotkey: 'E', run: edit },
  { key: 'delete', icon: IconTrash, label: 'Delete', danger: true, hotkey: 'D', run: remove },
])
<\/script>

<template>
  <!-- A right click anywhere on the row opens the same menu at the pointer -->
  <div class="row" :class="{ 'row--menu': menuOpen }" @contextmenu="menu?.openAt($event)">
    {{ entity.title }}
    <ActionMenu
      ref="menu"
      v-model:open="menuOpen"
      :items="items"
      :code="entity.code"
      label="Actions"
    />
  </div>
</template>`,F=_({__name:"ActionMenuView",setup(H){const{t:e}=g(),l=d(),c=d(!1),u=d("");function o(r){u.value=r}const y=w(()=>[{key:"edit",icon:I,label:e("design-system.section.action-menu.edit"),hotkey:"E",run:()=>o(e("design-system.section.action-menu.edit"))},{key:"delete",icon:T,label:e("design-system.section.action-menu.delete"),danger:!0,hotkey:"D",run:()=>o(e("design-system.section.action-menu.delete"))},{key:"up",icon:C,label:e("design-system.section.action-menu.up"),disabled:!0,divider:!0,hotkey:"W",run:()=>o(e("design-system.section.action-menu.up"))},{key:"down",icon:x,label:e("design-system.section.action-menu.down"),hotkey:"S",run:()=>o(e("design-system.section.action-menu.down"))}]);return(r,i)=>(A(),f(k,null,{default:h(()=>[t("div",P,[m(B,{title:n(e)("design-system.page.action-menu.title"),description:n(e)("design-system.page.action-menu.description"),"back-to":"/design-system"},null,8,["title","description"]),t("section",V,[t("h6",N,s(n(e)("design-system.section.action-menu.in_context")),1),t("p",O,s(n(e)("design-system.section.action-menu.in_context_note")),1),t("div",S,[t("div",{class:b(["ds-sample",{"ds-sample--menu":c.value}]),onContextmenu:i[1]||(i[1]=a=>{var p;return(p=l.value)==null?void 0:p.openAt(a)})},[t("span",$,s(n(e)("design-system.section.action-menu.row_title")),1),m(D,{ref_key:"menu",ref:l,open:c.value,"onUpdate:open":i[0]||(i[0]=a=>c.value=a),items:y.value,code:"TASK@F3CE1C4436",label:n(e)("design-system.section.action-menu.actions")},null,8,["open","items","label"])],34),t("p",U,[v(s(n(e)("design-system.section.action-menu.last_action"))+": ",1),t("strong",null,s(u.value||n(e)("design-system.section.action-menu.none")),1)])])]),t("section",W,[t("h6",q,s(n(e)("design-system.section.action-menu.usage")),1),m(E,{code:z,lang:"vue"})])])]),_:1}))}}),Z=M(F,[["__scopeId","data-v-38a69e23"]]);export{Z as default};
