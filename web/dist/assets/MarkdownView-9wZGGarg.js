import{bM as f,dR as g,bA as _,ei as i,bz as e,bH as s,dA as o,dt as r,aH as p,bF as m,aJ as v,bc as w,bh as b,dd as u,d1 as y,bg as k}from"./index-BZBeLbdV.js";import{P as x}from"./PageHeader-xUi9dSf5.js";import{_ as c}from"./MarkdownRenderer.vue_vue_type_script_setup_true_lang-D08jrR18.js";import"./document.css_vue_type_style_index_0_src_true_lang-Dc1qaQ3r.js";import"./VSkeletonLoader-BlhhTmPr.js";import"./CodeBlock-DycGxIcn.js";import"./IconCopy-CZwMt5Ec.js";import"./useClipboard-BlzvheNH.js";import"./purify.es-DxCUJf2h.js";import"./ImageLightbox-rq3P4PGV.js";import"./IconDownload-CgHAzQLj.js";import"./file-icon-CiH-X-Qo.js";import"./IconMarkdown-DK2ytRy4.js";import"./IconLayoutGrid-CGmZXOwp.js";import"./IconListCheck-BTZXdaJQ.js";import"./IconTrash-X1YvxKkn.js";import"./ActionMenu-OjbAs1Ov.js";import"./IconDotsVertical-D8p8tBm9.js";import"./ConfirmDialog-BX3O2pIO.js";const V={class:"ds-page"},B={class:"ds-section"},M={class:"mb-3"},R={class:"ds-card"},S={class:"ds-row"},P={class:"ds-controls"},A={class:"ds-section"},T={class:"mb-3"},C={class:"live-grid"},D={class:"live-pane"},I={class:"live-pane"},L={class:"preview-box"},F={class:"ds-section"},H={class:"mb-3"},K={class:"preview-box"},N={class:"ds-section"},E={class:"mb-3"},Q={class:"preview-box preview-box--narrow"},U=`# First-level heading

A regular paragraph with **bold text**, *italic* and \`inline code\`.

## Unordered list

- Develop and maintain backend services in Python
- Design REST APIs and integrate with external systems
- Review code, take part in architectural decisions
- Nested item:
  - Sub-item A
  - Sub-item B

## Ordered list

1. Write tests
2. Run CI
3. Ship to production

## Requirements

### Must have

- 3+ years of experience with Python 3.10+
- FastAPI / SQLAlchemy / PostgreSQL
- Understanding of asyncio and the event loop

### Nice to have

- Experience with queues (Celery, RabbitMQ, Redis)
- Knowledge of Docker and Kubernetes

## Code block

\`\`\`python
async def list_vacancies(status: str, limit: int = 50) -> list[Vacancy]:
    async with session_scope() as s:
        result = await s.execute(
            select(Vacancy).where(Vacancy.status == status).limit(limit)
        )
        return list(result.scalars())
\`\`\`

## Table

| Engine | Bundle (gzip) | Raw HTML by default | Notes |
|---|---:|:---:|---|
| markdown-it | 52.7 KB | off | plugin rules, GFM tables |
| marked | 12.5 KB | on | smallest, narrow extension model |
| unified | 36.8 KB | pipeline choice | full AST, largest ecosystem |

## Quote

> We are looking for a specialist ready to work in a fast-changing environment
> and not afraid of technical challenges.

## Task list

- [x] Migrate the renderer to markdown-it
- [ ] Wire syntax highlighting into body code blocks

---

Small text at the end of the paragraph with ~~a struck-out phrase~~, an [external link](https://example.com)
that opens in a new tab, and raw HTML like <b>this</b> which the parser escapes instead of rendering.`,h=`Requirements:
- 2+ years of experience as a Python Backend Developer
- Knowledge of Django or FastAPI
- Understanding of SOLID principles and clean code
- Experience with relational databases (PostgreSQL preferred)

What we offer:
- Remote work, 5/2 schedule
- Health insurance from the first month
- Corporate training and conferences at the company's expense
- Choice of equipment (Mac/Linux)

We offer interesting tasks, honest feedback and no bureaucracy.`,W=f({__name:"MarkdownView",setup(q){const n=u(!1),d=u(h),{t:a}=g();return(z,t)=>(y(),_(b,null,{default:i(()=>[e("div",V,[s(x,{title:o(a)("design-system.page.markdown.title"),description:o(a)("design-system.page.markdown.description"),"back-to":"/design-system"},null,8,["title","description"]),e("section",B,[e("h6",M,r(o(a)("design-system.section.markdown.props")),1),e("div",R,[e("div",S,[t[4]||(t[4]=e("span",{class:"ds-tag"},"compact",-1)),e("div",P,[s(v,{modelValue:n.value,"onUpdate:modelValue":t[0]||(t[0]=l=>n.value=l),mandatory:"",divided:"",density:"compact"},{default:i(()=>[s(p,{value:!1},{default:i(()=>[...t[2]||(t[2]=[m("false",-1)])]),_:1}),s(p,{value:!0},{default:i(()=>[...t[3]||(t[3]=[m("true",-1)])]),_:1})]),_:1},8,["modelValue"])]),t[5]||(t[5]=e("span",{class:"ds-spec"},"reduces font-size and spacing",-1))])])]),e("section",A,[e("h6",T,r(o(a)("design-system.section.markdown.liveEditor")),1),e("div",C,[e("div",D,[t[6]||(t[6]=e("span",{class:"ds-tag mb-2"},"Markdown",-1)),s(w,{modelValue:d.value,"onUpdate:modelValue":t[1]||(t[1]=l=>d.value=l),variant:"outlined",density:"compact",rows:"14","hide-details":"",style:{"font-family":"var(--font-mono)","font-size":"12px"}},null,8,["modelValue"])]),e("div",I,[t[7]||(t[7]=e("span",{class:"ds-tag mb-2"},"Result",-1)),e("div",L,[s(c,{text:d.value,compact:n.value},null,8,["text","compact"])])])])]),e("section",F,[e("h6",H,r(o(a)("design-system.section.markdown.fullDemo")),1),e("div",K,[s(c,{text:U,compact:n.value},null,8,["compact"])])]),e("section",N,[e("h6",E,r(o(a)("design-system.section.markdown.jobContent")),1),e("div",Q,[s(c,{text:h,compact:n.value},null,8,["compact"])])])])]),_:1}))}}),pe=k(W,[["__scopeId","data-v-03a7cacf"]]);export{pe as default};
