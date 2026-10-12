import{bH as _,dB as g,bw as f,e0 as h,bv as t,bC as m,dk as n,dd as s,cI as b,bB as v,be as k,d2 as d,bs as w,cU as A,a3 as I,r as C,p as x,bd as M}from"./index-DitlXhVX.js";import{I as T}from"./IconTrash-BnY9pMm_.js";import{P as B}from"./PageHeader-DPt2lRZ0.js";import{A as D}from"./ActionMenu-vK9oBZp5.js";import{C as E}from"./CodeBlock-B_W1LGvP.js";import"./IconCopy-BHBl3qdd.js";import"./IconDotsVertical-CO__VPk0.js";import"./KeyCap-DYsS8UBm.js";/* empty css                                                               */import"./useClipboard-CV2F9Mz9.js";const P={class:"ds-page"},V={class:"ds-section"},O={class:"mb-1"},N={class:"ds-note"},S={class:"ds-card"},U={class:"ds-sample__title"},H={class:"ds-last"},$={class:"ds-section"},z={class:"mb-3"},F=`<script setup lang="ts">
import { computed, ref } from 'vue'
import { IconPencil, IconTrash } from '@tabler/icons-vue'
import ActionMenu, { type ActionMenuItem } from '@/components/ActionMenu.vue'

const menu = ref<InstanceType<typeof ActionMenu>>()
const menuOpen = ref(false)

// The key is a field of the item: the menu draws it and runs the item on it.
// Letters by meaning — E edit, D delete; C is the menu's own "Copy code"; a digit only where one was asked for
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
</template>`,K=_({__name:"ActionMenuView",setup(L){const{t:e}=g(),l=d(),c=d(!1),r=d("");function o(u){r.value=u}const y=w(()=>[{key:"edit",icon:I,label:e("design-system.section.action-menu.edit"),hotkey:"E",run:()=>o(e("design-system.section.action-menu.edit"))},{key:"delete",icon:T,label:e("design-system.section.action-menu.delete"),danger:!0,hotkey:"D",run:()=>o(e("design-system.section.action-menu.delete"))},{key:"up",icon:C,label:e("design-system.section.action-menu.up"),disabled:!0,divider:!0,hotkey:"W",run:()=>o(e("design-system.section.action-menu.up"))},{key:"down",icon:x,label:e("design-system.section.action-menu.down"),hotkey:"S",run:()=>o(e("design-system.section.action-menu.down"))}]);return(u,i)=>(A(),f(k,null,{default:h(()=>[t("div",P,[m(B,{title:n(e)("design-system.page.action-menu.title"),description:n(e)("design-system.page.action-menu.description"),"back-to":"/design-system"},null,8,["title","description"]),t("section",V,[t("h6",O,s(n(e)("design-system.section.action-menu.in_context")),1),t("p",N,s(n(e)("design-system.section.action-menu.in_context_note")),1),t("div",S,[t("div",{class:b(["ds-sample",{"ds-sample--menu":c.value}]),onContextmenu:i[1]||(i[1]=a=>{var p;return(p=l.value)==null?void 0:p.openAt(a)})},[t("span",U,s(n(e)("design-system.section.action-menu.row_title")),1),m(D,{ref_key:"menu",ref:l,open:c.value,"onUpdate:open":i[0]||(i[0]=a=>c.value=a),items:y.value,code:"TASK@F3CE1C4436",label:n(e)("design-system.section.action-menu.actions")},null,8,["open","items","label"])],34),t("p",H,[v(s(n(e)("design-system.section.action-menu.last_action"))+": ",1),t("strong",null,s(r.value||n(e)("design-system.section.action-menu.none")),1)])])]),t("section",$,[t("h6",z,s(n(e)("design-system.section.action-menu.usage")),1),m(E,{code:F,lang:"vue"})])])]),_:1}))}}),ee=M(K,[["__scopeId","data-v-ae201549"]]);export{ee as default};
