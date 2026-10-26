import{bM as v,dR as h,bA as y,ei as u,bz as e,bH as i,dA as a,dt as o,bb as _,ac as w,aT as C,aK as V,bh as S,dd as g,bw as T,d1 as k,bg as x}from"./index-Cs8WGrv5.js";import{P as R}from"./PageHeader-DnMh1lOM.js";import{T as z}from"./TablePaginationBar-BsdBD7xP.js";import{C as b}from"./CodeBlock-DTQ_OY4m.js";import{V as E}from"./VDataTable-CDotOjN1.js";import"./pagination-g1p9OMKG.js";import"./VSelect-D1JMjLU5.js";import"./VSelectionControl-BjxoiLWG.js";import"./VChip-BJmEj44S.js";import"./VPagination-D-1fZIUv.js";import"./IconCopy-Dg_K4k6G.js";import"./VTable-BaKv5va3.js";const P={class:"ds-page"},B={class:"ds-section"},H={class:"mb-3"},A={class:"ds-note"},D={class:"filter-panel"},I={class:"ds-section"},M={class:"mb-3"},N={class:"ds-card"},U={class:"ds-row"},L={class:"ds-part"},O={class:"ds-row"},W={class:"ds-part"},q={class:"ds-row"},F={class:"ds-part"},G={class:"ds-row"},K={class:"ds-part"},$={class:"ds-section"},j={class:"mb-3"},J={class:"ds-note"},Q=`<!-- The filter panel sits INSIDE the table card: rows have no frame of their own,
     so the panel and the rows live in one card, separated by a divider. -->
<VCard variant="outlined" rounded="lg">
  <div class="filter-panel">…filter fields…</div>
  <VDivider />

  <VDataTable
    :headers="headers"
    :items="store.items"
    :loading="store.loading"
    :items-per-page="store.pageSize"
    item-value="code"
    density="comfortable"
    hover
    hide-default-footer
    :no-data-text="emptyText"
    @click:row="open"
  />

  <TablePaginationBar
    :page="store.page"
    :page-size="store.pageSize"
    :total="store.total"
    :page-count="store.pageCount"
    @update:page="onPageChange"
    @update:page-size="onPageSizeChange"
  />
</VCard>`,X=`<!-- Tiles: each card is its own frame, and a wrapping card would give a frame inside a frame.
     So the panel and the pagination get THEIR OWN cards, and the grid sits on bare canvas. -->
<VCard variant="outlined" rounded="lg" class="filter-panel mb-3">…filter fields…</VCard>

<div class="cards__grid">…tiles…</div>

<VCard variant="outlined" rounded="lg" class="mt-3">
  <TablePaginationBar … :divider="false" />
</VCard>`,Y=v({__name:"TablePageView",setup(Z){const{t}=h(),m=[{code:"RESEARCH@8c1f…",title:"Ubuntu 26.04 LTS: initial setup",areas:6,sources:27,updated:"27.08.2026 23:48"},{code:"RESEARCH@2a0d…",title:"Typography and the spacing system",areas:8,sources:11,updated:"27.08.2026 08:22"},{code:"RESEARCH@8913…",title:"Markdown render engine for the frontend",areas:7,sources:9,updated:"27.08.2026 08:22"},{code:"RESEARCH@c176…",title:"Global error screens for the portal",areas:4,sources:0,updated:"27.08.2026 08:21"}],f=[{title:t("design-system.section.table-page.column.title"),key:"title"},{title:t("design-system.section.table-page.column.areas"),key:"areas",width:90,align:"end"},{title:t("design-system.section.table-page.column.sources"),key:"sources",width:110,align:"end"},{title:t("design-system.section.table-page.column.updated"),key:"updated",width:190}],l=g(""),r=g(1),d=g(25),p=T(()=>{const c=l.value.trim().toLowerCase();return c?m.filter(s=>s.title.toLowerCase().includes(c)):m});return(c,s)=>(k(),y(S,null,{default:u(()=>[e("div",P,[i(R,{title:a(t)("design-system.page.table-page.title"),description:a(t)("design-system.page.table-page.description"),"back-to":"/design-system"},null,8,["title","description"]),e("section",B,[e("h6",H,o(a(t)("design-system.section.table-page.assembled")),1),e("p",A,o(a(t)("design-system.section.table-page.assembled_note")),1),i(V,{variant:"outlined",rounded:"lg"},{default:u(()=>[e("div",D,[i(_,{modelValue:l.value,"onUpdate:modelValue":s[0]||(s[0]=n=>l.value=n),label:a(t)("design-system.section.table-page.filter"),"prepend-inner-icon":a(w),variant:"outlined",density:"comfortable","hide-details":"",clearable:""},null,8,["modelValue","label","prepend-inner-icon"])]),i(C),i(E,{headers:f,items:p.value,"items-per-page":d.value,"item-value":"code",density:"comfortable",hover:"","hide-default-footer":"","no-data-text":a(t)("design-system.section.table-page.empty")},null,8,["items","items-per-page","no-data-text"]),i(z,{page:r.value,"page-size":d.value,total:p.value.length,"page-count":Math.max(1,Math.ceil(p.value.length/d.value)),"onUpdate:page":s[1]||(s[1]=n=>r.value=n),"onUpdate:pageSize":s[2]||(s[2]=n=>{d.value=n,r.value=1})},null,8,["page","page-size","total","page-count"])]),_:1})]),e("section",I,[e("h6",M,o(a(t)("design-system.section.table-page.parts")),1),e("div",N,[e("div",U,[s[3]||(s[3]=e("span",{class:"ds-tag"},"filters",-1)),e("p",L,o(a(t)("design-system.section.table-page.part.filters")),1),s[4]||(s[4]=e("span",{class:"ds-spec"},"VCard > .filter-panel",-1))]),e("div",O,[s[5]||(s[5]=e("span",{class:"ds-tag"},"head",-1)),e("p",W,o(a(t)("design-system.section.table-page.part.head")),1),s[6]||(s[6]=e("span",{class:"ds-spec"},"11px / uppercase",-1))]),e("div",q,[s[7]||(s[7]=e("span",{class:"ds-tag"},"rows",-1)),e("p",F,o(a(t)("design-system.section.table-page.part.rows")),1),s[8]||(s[8]=e("span",{class:"ds-spec"},"hover, @click:row",-1))]),e("div",G,[s[9]||(s[9]=e("span",{class:"ds-tag"},"footer",-1)),e("p",K,o(a(t)("design-system.section.table-page.part.footer")),1),s[10]||(s[10]=e("span",{class:"ds-spec"},"TablePaginationBar",-1))])])]),e("section",$,[e("h6",j,o(a(t)("design-system.section.table-page.placement")),1),e("p",J,o(a(t)("design-system.section.table-page.placement_note")),1),i(b,{code:Q,lang:"vue"}),s[11]||(s[11]=e("div",{class:"ds-gap"},null,-1)),i(b,{code:X,lang:"vue"})])])]),_:1}))}}),ge=x(Y,[["__scopeId","data-v-0e2915e0"]]);export{ge as default};
