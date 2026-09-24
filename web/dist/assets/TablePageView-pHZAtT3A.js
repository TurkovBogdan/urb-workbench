import{bj as v,c7 as _,ba as h,ci as m,b9 as e,bf as i,c1 as a,b_ as o,aZ as y,_ as w,aD as C,aB as V,aq as S,b3 as T,bR as g,b8 as k,bM as x,b2 as R}from"./index-pWzGLlVE.js";import{P as E}from"./PageHeader-v4cUJ2fI.js";import{T as P}from"./TablePaginationBar-fVg0AmTP.js";import{C as b}from"./CodeBlock-mTkXuiBz.js";import"./pagination-g1p9OMKG.js";import"./IconCopy-D6cf29Wj.js";const z={class:"ds-page"},B={class:"ds-section"},D={class:"mb-3"},H={class:"ds-note"},I={class:"filter-panel"},A={class:"ds-section"},M={class:"mb-3"},N={class:"ds-card"},U={class:"ds-row"},L={class:"ds-part"},q={class:"ds-row"},O={class:"ds-part"},W={class:"ds-row"},j={class:"ds-part"},F={class:"ds-row"},G={class:"ds-part"},Z={class:"ds-section"},$={class:"mb-3"},J={class:"ds-note"},K=`<!-- The filter panel sits INSIDE the table card: rows have no frame of their own,
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
</VCard>`,Q=`<!-- Tiles: each card is its own frame, and a wrapping card would give a frame inside a frame.
     So the panel and the pagination get THEIR OWN cards, and the grid sits on bare canvas. -->
<VCard variant="outlined" rounded="lg" class="filter-panel mb-3">…filter fields…</VCard>

<div class="cards__grid">…tiles…</div>

<VCard variant="outlined" rounded="lg" class="mt-3">
  <TablePaginationBar … :divider="false" />
</VCard>`,X=v({__name:"TablePageView",setup(Y){const{t}=_(),u=[{code:"RESEARCH@8c1f…",title:"Ubuntu 26.04 LTS: initial setup",areas:6,sources:27,updated:"27.08.2026 23:48"},{code:"RESEARCH@2a0d…",title:"Typography and the spacing system",areas:8,sources:11,updated:"27.08.2026 08:22"},{code:"RESEARCH@8913…",title:"Markdown render engine for the frontend",areas:7,sources:9,updated:"27.08.2026 08:22"},{code:"RESEARCH@c176…",title:"Global error screens for the portal",areas:4,sources:0,updated:"27.08.2026 08:21"}],f=[{title:t("design-system.section.table-page.column.title"),key:"title"},{title:t("design-system.section.table-page.column.areas"),key:"areas",width:90,align:"end"},{title:t("design-system.section.table-page.column.sources"),key:"sources",width:110,align:"end"},{title:t("design-system.section.table-page.column.updated"),key:"updated",width:190}],l=g(""),r=g(1),d=g(25),p=k(()=>{const c=l.value.trim().toLowerCase();return c?u.filter(s=>s.title.toLowerCase().includes(c)):u});return(c,s)=>(x(),h(T,null,{default:m(()=>[e("div",z,[i(E,{title:a(t)("design-system.page.table-page.title"),description:a(t)("design-system.page.table-page.description"),"back-to":"/design-system"},null,8,["title","description"]),e("section",B,[e("h6",D,o(a(t)("design-system.section.table-page.assembled")),1),e("p",H,o(a(t)("design-system.section.table-page.assembled_note")),1),i(S,{variant:"outlined",rounded:"lg"},{default:m(()=>[e("div",I,[i(y,{modelValue:l.value,"onUpdate:modelValue":s[0]||(s[0]=n=>l.value=n),label:a(t)("design-system.section.table-page.filter"),"prepend-inner-icon":a(w),variant:"outlined",density:"comfortable","hide-details":"",clearable:""},null,8,["modelValue","label","prepend-inner-icon"])]),i(C),i(V,{headers:f,items:p.value,"items-per-page":d.value,"item-value":"code",density:"comfortable",hover:"","hide-default-footer":"","no-data-text":a(t)("design-system.section.table-page.empty")},null,8,["items","items-per-page","no-data-text"]),i(P,{page:r.value,"page-size":d.value,total:p.value.length,"page-count":Math.max(1,Math.ceil(p.value.length/d.value)),"onUpdate:page":s[1]||(s[1]=n=>r.value=n),"onUpdate:pageSize":s[2]||(s[2]=n=>{d.value=n,r.value=1})},null,8,["page","page-size","total","page-count"])]),_:1})]),e("section",A,[e("h6",M,o(a(t)("design-system.section.table-page.parts")),1),e("div",N,[e("div",U,[s[3]||(s[3]=e("span",{class:"ds-tag"},"filters",-1)),e("p",L,o(a(t)("design-system.section.table-page.part.filters")),1),s[4]||(s[4]=e("span",{class:"ds-spec"},"VCard > .filter-panel",-1))]),e("div",q,[s[5]||(s[5]=e("span",{class:"ds-tag"},"head",-1)),e("p",O,o(a(t)("design-system.section.table-page.part.head")),1),s[6]||(s[6]=e("span",{class:"ds-spec"},"11px / uppercase",-1))]),e("div",W,[s[7]||(s[7]=e("span",{class:"ds-tag"},"rows",-1)),e("p",j,o(a(t)("design-system.section.table-page.part.rows")),1),s[8]||(s[8]=e("span",{class:"ds-spec"},"hover, @click:row",-1))]),e("div",F,[s[9]||(s[9]=e("span",{class:"ds-tag"},"footer",-1)),e("p",G,o(a(t)("design-system.section.table-page.part.footer")),1),s[10]||(s[10]=e("span",{class:"ds-spec"},"TablePaginationBar",-1))])])]),e("section",Z,[e("h6",$,o(a(t)("design-system.section.table-page.placement")),1),e("p",J,o(a(t)("design-system.section.table-page.placement_note")),1),i(b,{code:K,lang:"vue"}),s[11]||(s[11]=e("div",{class:"ds-gap"},null,-1)),i(b,{code:Q,lang:"vue"})])])]),_:1}))}}),ne=R(X,[["__scopeId","data-v-074e3500"]]);export{ne as default};
