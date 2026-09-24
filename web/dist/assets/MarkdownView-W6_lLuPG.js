import{bj as f,c7 as g,ba as _,ci as i,b9 as e,bf as t,c1 as n,b_ as l,an as p,be as m,ap as b,a_ as v,b3 as w,bR as u,bM as y,b2 as k}from"./index-pWzGLlVE.js";import{P as x}from"./PageHeader-v4cUJ2fI.js";import{_ as c}from"./document.css_vue_type_style_index_0_src_true_lang-Ci-D60nq.js";import"./CodeBlock-mTkXuiBz.js";import"./IconCopy-D6cf29Wj.js";import"./purify.es-DxCUJf2h.js";const V={class:"ds-page"},B={class:"ds-section"},M={class:"mb-3"},R={class:"ds-card"},S={class:"ds-row"},P={class:"ds-controls"},T={class:"ds-section"},C={class:"mb-3"},D={class:"live-grid"},A={class:"live-pane"},I={class:"live-pane"},L={class:"preview-box"},K={class:"ds-section"},N={class:"mb-3"},E={class:"preview-box"},F={class:"ds-section"},Q={class:"mb-3"},U={class:"preview-box preview-box--narrow"},W=`# First-level heading

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

We offer interesting tasks, honest feedback and no bureaucracy.`,q=f({__name:"MarkdownView",setup(H){const o=u(!1),d=u(h),{t:a}=g();return(j,s)=>(y(),_(w,null,{default:i(()=>[e("div",V,[t(x,{title:n(a)("design-system.page.markdown.title"),description:n(a)("design-system.page.markdown.description"),"back-to":"/design-system"},null,8,["title","description"]),e("section",B,[e("h6",M,l(n(a)("design-system.section.markdown.props")),1),e("div",R,[e("div",S,[s[4]||(s[4]=e("span",{class:"ds-tag"},"compact",-1)),e("div",P,[t(b,{modelValue:o.value,"onUpdate:modelValue":s[0]||(s[0]=r=>o.value=r),mandatory:"",divided:"",density:"compact"},{default:i(()=>[t(p,{value:!1},{default:i(()=>[...s[2]||(s[2]=[m("false",-1)])]),_:1}),t(p,{value:!0},{default:i(()=>[...s[3]||(s[3]=[m("true",-1)])]),_:1})]),_:1},8,["modelValue"])]),s[5]||(s[5]=e("span",{class:"ds-spec"},"reduces font-size and spacing",-1))])])]),e("section",T,[e("h6",C,l(n(a)("design-system.section.markdown.liveEditor")),1),e("div",D,[e("div",A,[s[6]||(s[6]=e("span",{class:"ds-tag mb-2"},"Markdown",-1)),t(v,{modelValue:d.value,"onUpdate:modelValue":s[1]||(s[1]=r=>d.value=r),variant:"outlined",density:"compact",rows:"14","hide-details":"",style:{"font-family":"var(--font-mono)","font-size":"12px"}},null,8,["modelValue"])]),e("div",I,[s[7]||(s[7]=e("span",{class:"ds-tag mb-2"},"Result",-1)),e("div",L,[t(c,{text:d.value,compact:o.value},null,8,["text","compact"])])])])]),e("section",K,[e("h6",N,l(n(a)("design-system.section.markdown.fullDemo")),1),e("div",E,[t(c,{text:W,compact:o.value},null,8,["compact"])])]),e("section",F,[e("h6",Q,l(n(a)("design-system.section.markdown.jobContent")),1),e("div",U,[t(c,{text:h,compact:o.value},null,8,["compact"])])])])]),_:1}))}}),Y=k(q,[["__scopeId","data-v-03a7cacf"]]);export{Y as default};
