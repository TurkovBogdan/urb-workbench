import{bM as _,dR as g,bA as h,ei as f,bz as t,bH as d,dA as n,dt as s,cR as b,bF as v,bh as k,dd as m,bw as A,d1 as w,a6 as I,t as C,r as M,bg as x}from"./index-Cs8WGrv5.js";import{I as T}from"./IconTrash-DzQUOhwX.js";import{P as D}from"./PageHeader-DnMh1lOM.js";import{A as E}from"./ActionMenu-C4aww2oq.js";import{C as P}from"./CodeBlock-DTQ_OY4m.js";import"./IconCopy-Dg_K4k6G.js";import"./IconDotsVertical-BIXjb_x7.js";import"./useClipboard-iUQtFwpO.js";const V={class:"ds-page"},B={class:"ds-section"},O={class:"mb-1"},N={class:"ds-note"},S={class:"ds-card"},z={class:"ds-sample__title"},F={class:"ds-last"},H={class:"ds-section"},R={class:"mb-3"},U=`<script setup lang="ts">
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
</template>`,$=_({__name:"ActionMenuView",setup(K){const{t:e}=g(),l=m(),c=m(!1),u=m("");function o(r){u.value=r}const y=A(()=>[{key:"edit",icon:I,label:e("design-system.section.action-menu.edit"),hotkey:"E",run:()=>o(e("design-system.section.action-menu.edit"))},{key:"delete",icon:T,label:e("design-system.section.action-menu.delete"),danger:!0,hotkey:"D",run:()=>o(e("design-system.section.action-menu.delete"))},{key:"up",icon:C,label:e("design-system.section.action-menu.up"),disabled:!0,divider:!0,hotkey:"W",run:()=>o(e("design-system.section.action-menu.up"))},{key:"down",icon:M,label:e("design-system.section.action-menu.down"),hotkey:"S",run:()=>o(e("design-system.section.action-menu.down"))}]);return(r,i)=>(w(),h(k,null,{default:f(()=>[t("div",V,[d(D,{title:n(e)("design-system.page.action-menu.title"),description:n(e)("design-system.page.action-menu.description"),"back-to":"/design-system"},null,8,["title","description"]),t("section",B,[t("h6",O,s(n(e)("design-system.section.action-menu.in_context")),1),t("p",N,s(n(e)("design-system.section.action-menu.in_context_note")),1),t("div",S,[t("div",{class:b(["ds-sample",{"ds-sample--menu":c.value}]),onContextmenu:i[1]||(i[1]=a=>{var p;return(p=l.value)==null?void 0:p.openAt(a)})},[t("span",z,s(n(e)("design-system.section.action-menu.row_title")),1),d(E,{ref_key:"menu",ref:l,open:c.value,"onUpdate:open":i[0]||(i[0]=a=>c.value=a),items:y.value,code:"TASK@F3CE1C4436",label:n(e)("design-system.section.action-menu.actions")},null,8,["open","items","label"])],34),t("p",F,[v(s(n(e)("design-system.section.action-menu.last_action"))+": ",1),t("strong",null,s(u.value||n(e)("design-system.section.action-menu.none")),1)])])]),t("section",H,[t("h6",R,s(n(e)("design-system.section.action-menu.usage")),1),d(P,{code:U,lang:"vue"})])])]),_:1}))}}),Y=x($,[["__scopeId","data-v-ae201549"]]);export{Y as default};
