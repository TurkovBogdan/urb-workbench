import{bj as m,c6 as g,ba as v,ch as b,b9 as s,bf as y,c0 as o,b_ as l,be as f,bc as n,bT as i,F as c,b3 as _,bM as d,bD as r,b2 as h}from"./index-CbGvUGSv.js";import{P as x}from"./PageHeader-B7gvm_nR.js";const w={class:"ds-page"},k={class:"ds-section"},V={class:"mb-4"},L={class:"ds-section"},P={class:"ds-card"},T={class:"ds-code"},C={class:"ds-row-body"},B={class:"ds-section"},D={class:"ds-card"},E={class:"ds-code"},F={class:"ds-row-body"},H={class:"ds-section"},M={class:"mb-4"},N=`// routes.ts
{
  path: '/tasks/:module/:code',
  component: () => import('./views/TaskRunsView.vue'),
  props: true,
  meta: { scroll: 'none', padding: false },
}`,S=`// TaskRunsView.vue — scroll: none, padding: false
<template>
  <PageLayout>
    <div class="d-flex flex-column h-100 pa-6">
      <PageHeader ... />
      <VCard class="flex-grow-1 min-h-0">
        <VDataTable fixed-header height="100%" ... />
      </VCard>
      <div class="pagination-row">...</div>
    </div>
  </PageLayout>
</template>`,z=`// routes.ts — standard page
{
  path: '/tasks',
  component: () => import('./views/TasksView.vue'),
  meta: { scroll: 'y' },   // padding: true — by default
}`,A=`// PageLayout.vue — what it does
const contentClass = computed(() => [
  'page-layout__content',
  scrollClass(route.meta.scroll),   // 'scroll-y' | 'scroll-x' | ...
  // .page-layout__content--padded — padding via --page-layout-pad
  // (24px, 16px below md); see styles/layout.scss
  route.meta.padding !== false ? 'page-layout__content--padded' : '',
])`,I=m({__name:"LayoutView",setup(R){const{t}=g(),u=[{value:"y",label:"scroll: y",desc:"Vertical scrolling. Default for most pages.",use:"Tasks, lists, forms"},{value:"x",label:"scroll: x",desc:"Horizontal scrolling. Fixed-height content wider than the screen.",use:"Wide tables, kanban"},{value:"both",label:"scroll: both",desc:"Scrolling in both directions.",use:"Editors, diagrams, maps"},{value:"none",label:"scroll: none",desc:"No scrolling. Content manages overflow on its own.",use:"Tables with fixed-header, split-view"}],p=[{value:"true",label:"padding: true",desc:"Default. PageLayout adds pa-6 to the content area.",use:"Any standard pages"},{value:"false",label:"padding: false",desc:"Content flush to the edges. The page manages spacing itself.",use:"Full-bleed tables, custom layout"}];return($,e)=>(d(),v(_,null,{default:b(()=>[s("div",w,[y(x,{title:o(t)("design-system.page.layout.title"),description:o(t)("design-system.page.layout.description"),"back-to":"/design-system"},null,8,["title","description"]),s("section",k,[s("h6",V,l(o(t)("design-system.section.layout.structure")),1),e[0]||(e[0]=s("div",{class:"ds-card"},[s("div",{class:"layout-diagram"},[s("div",{class:"ld-app"},[s("div",{class:"ld-label"},"App.vue — VMain"),s("div",{class:"ld-page-layout"},[s("div",{class:"ld-label"},"PageLayout"),s("div",{class:"ld-toolbar"},[s("span",{class:"ld-slot"},"#toolbar"),s("small",null,"flex-shrink-0 · visibility via layout.showTopBar")]),s("div",{class:"ld-content"},[s("span",{class:"ld-slot"},"#default"),s("small",null,[f("flex-grow-1 · "),s("strong",null,"scroll + padding from route.meta")])]),s("div",{class:"ld-footer"},[s("span",{class:"ld-slot"},"#footer"),s("small",null,"flex-shrink-0 · visibility via layout.showBottomBar")])])])])],-1))]),s("section",L,[e[2]||(e[2]=s("h6",{class:"mb-4"},"meta.scroll",-1)),s("div",P,[(d(),n(c,null,i(u,a=>s("div",{key:a.value,class:"ds-row"},[s("code",T,l(a.label),1),s("div",C,[s("p",null,l(a.desc),1),s("small",null,l(a.use),1)]),s("div",{class:r(["scroll-demo",`scroll-demo--${a.value}`])},[...e[1]||(e[1]=[s("div",{class:"scroll-demo__inner"},null,-1)])],2)])),64))])]),s("section",B,[e[4]||(e[4]=s("h6",{class:"mb-4"},"meta.padding",-1)),s("div",D,[(d(),n(c,null,i(p,a=>s("div",{key:a.value,class:"ds-row"},[s("code",E,l(a.label),1),s("div",F,[s("p",null,l(a.desc),1),s("small",null,l(a.use),1)]),s("div",{class:r(["padding-demo",a.value==="true"?"padding-demo--on":"padding-demo--off"])},[...e[3]||(e[3]=[s("div",{class:"padding-demo__inner"},null,-1)])],2)])),64))])]),s("section",H,[s("h6",M,l(o(t)("design-system.section.layout.examples")),1),s("div",{class:"ds-card ds-card--examples"},[s("div",{class:"example-block"},[e[5]||(e[5]=s("div",{class:"example-label"},"Standard page",-1)),s("pre",null,l(z))]),s("div",{class:"example-block"},[e[6]||(e[6]=s("div",{class:"example-label"},"Page with a full-height table",-1)),s("pre",null,l(N)),s("pre",null,l(S))]),s("div",{class:"example-block"},[e[7]||(e[7]=s("div",{class:"example-label"},"How PageLayout applies the parameters",-1)),s("pre",null,l(A))])])])])]),_:1}))}}),q=h(I,[["__scopeId","data-v-adcd5f01"]]);export{q as default};
