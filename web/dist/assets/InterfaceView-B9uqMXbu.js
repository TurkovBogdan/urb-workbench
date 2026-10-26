import{bL as I,c_ as g,bA as N,aJ as b,ef as r,bG as i,bF as y,dq as d,aO as v,bC as U,bB as A,aS as V,dd as j,aN as w,bf as D,dO as K,e4 as Z,dx as e,bz as n,ap as q,a_ as J,cP as Y,c8 as Q,bY as f,bg as X,bw as S,ax as ee,e as te,ay as ie,k as ae,at as se,aw as le,au as ne}from"./index-p2dGIhHa.js";import{P as oe}from"./PageHeader-DvpoqMhr.js";import{_ as F}from"./MarkdownRenderer.vue_vue_type_script_setup_true_lang-B44iVbFk.js";import"./document.css_vue_type_style_index_0_src_true_lang-CAKj4ebF.js";import{S as de}from"./SwitchPanel-Ct22P28a.js";import{V as c}from"./VSelectStepper-DbjaO-wj.js";import{u as re}from"./useAppearanceOptions-B5ndStIB.js";import{a as p}from"./VSelect-_La-UFae.js";import"./CodeBlock-DF78K-pO.js";import"./IconCopy-CEZ0ci6b.js";import"./useClipboard-DqyoqLrI.js";import"./purify.es-DxCUJf2h.js";import"./ImageLightbox-56gGmE4Z.js";import"./IconDownload-cMMhogUY.js";import"./file-icon-DMfb7xOm.js";import"./IconMarkdown-BTwcsIbi.js";import"./IconLayoutGrid-BuoKQ8Y9.js";import"./IconListCheck-D5PLa4Xy.js";import"./IconTrash-CSGTvkWS.js";import"./ActionMenu-DDLWiSt0.js";import"./IconDotsVertical-DL_W92eQ.js";import"./ConfirmDialog-Cju6V7if.js";import"./VSwitch-Co__HMuY.js";import"./VSelectionControl-D659pbdl.js";import"./VChip-Cg71oGbz.js";const ce={key:0,class:"settings-group__desc"},pe=I({__name:"SettingsGroup",props:{title:{},description:{}},setup(u){return(t,s)=>(g(),N(b,{variant:"outlined",rounded:"lg"},{default:r(()=>[i(v,{class:"text-h6"},{default:r(()=>[y(d(u.title),1)]),_:1}),u.description?(g(),U("p",ce,d(u.description),1)):A("",!0),i(V),i(w,{class:"settings-columns"},{default:r(()=>[j(t.$slots,"default",{},void 0,!0)]),_:3})]),_:3}))}}),_=D(pe,[["__scopeId","data-v-f20eb0d7"]]),me={document:`# First-level heading

The first paragraph comes right under the heading — it shows the shape of the lowercase, the
leading and, above all, the line length at which the eye still finds the start of the next line
with confidence. Line length affects reading speed more than type size does, so the column is
limited in width, while tables and code blocks are exempt — they are scanned, not read through.

## Second-level heading

The second paragraph shows the distance between sections and that the space above a heading is
noticeably larger than below it: a heading belongs to the text that follows. Inside the line
there is \`inline code\`, **bold emphasis**, *italics* and an [external link](https://example.com),
and also an entity link pill — TASK@ef8a7d2f25.

### Third-level heading

- bulleted list: the first item
- the second item, noticeably longer than the first, to show how a line wraps inside an item
  - a nested item
`,code:`A short paragraph before the block: it shows how monospace sits next to the text — whether it
fights it in letter height and weight. There is \`inline code\` inside the line too, set in the
same face as the block below.

\`\`\`python
def read(path: Path) -> str:
    """Code block: highlighting, line numbers and copying."""
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"empty file: {path}")
    lines = [line.rstrip() for line in text.splitlines()]
    return "\\n".join(lines)
\`\`\`

A paragraph between the blocks — the same text as in a document body: it shows how much air is
left around the listing and whether the block eats into the spacing of neighbouring paragraphs.

\`\`\`bash
uv run pytest --module=core_interface
\`\`\`
`,diagram:`\`\`\`mermaid
flowchart TD
  Status{Order status} -->|paid, completed, needs_review| Paid([Paid])
  Status -->|canceled| Canceled([Canceled])
  Status -->|awaiting_payment| Due{Due date passed?}
  Status -->|draft| Failed{Payment failed?}
  Due -->|yes| Overdue([Overdue])
  Due -->|no| Awaiting([AwaitingPayment])
  Failed -->|yes| PaymentFailed([PaymentFailed])
  Failed -->|no| NoRow([No row in history])
\`\`\`
`},ge={document:`# Заголовок первого уровня

Первый абзац идёт сразу под заголовком — по нему видно рисунок строчных, интерлиньяж и,
главное, длину строки, на которой глаз ещё уверенно находит начало следующей. Длина строки
влияет на скорость чтения сильнее, чем кегль, поэтому колонка ограничена по ширине, а
таблицы и блоки кода из этого ограничения выведены — их просматривают, а не читают подряд.

## Заголовок второго уровня

Второй абзац — чтобы стало видно расстояние между разделами и то, что отступ над заголовком
заметно больше отступа под ним: заголовок принадлежит тексту, который идёт следом. Внутри
строки встречаются \`inline-код\`, **жирное выделение**, *курсив* и [внешняя ссылка](https://example.com),
а ещё пилюля ссылки на сущность — TASK@ef8a7d2f25.

### Заголовок третьего уровня

- маркированный список: первый пункт
- второй пункт, заметно длиннее первого, чтобы стало видно, как ложится перенос внутри пункта
  - вложенный пункт
`,code:`Короткий абзац перед блоком: по нему видно, как моноширинный набор стоит
рядом с текстом — не спорит ли он с ним по росту знака и насыщенности. Внутри строки тоже
встречается \`inline-код\`, и он набран той же гарнитурой, что и блок ниже.

\`\`\`python
def read(path: Path) -> str:
    """Блок кода: подсветка, номера строк и копирование."""
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"пустой файл: {path}")
    lines = [line.rstrip() for line in text.splitlines()]
    return "\\n".join(lines)
\`\`\`

Абзац между блоками — тот же текст, что и в теле документа: по нему видно, сколько воздуха
остаётся вокруг листинга и не съедает ли блок отбивку соседних абзацев.

\`\`\`bash
uv run pytest --module=core_interface
\`\`\`
`,diagram:`\`\`\`mermaid
flowchart TD
  Status{Статус заказа} -->|paid, completed, needs_review| Paid([Оплачен])
  Status -->|canceled| Canceled([Отменён])
  Status -->|awaiting_payment| Due{Срок оплаты прошёл?}
  Status -->|draft| Failed{Оплата не прошла?}
  Due -->|да| Overdue([Просрочен])
  Due -->|нет| Awaiting([Ждёт оплаты])
  Failed -->|да| PaymentFailed([Ошибка оплаты])
  Failed -->|нет| NoRow([Нет записи в истории])
\`\`\`
`},ue={en:me,ru:ge},he={class:"settings-list"},fe={class:"setting"},_e=["src"],be=["src"],ye={class:"setting__desc"},ve={class:"setting"},Ve={class:"setting__desc"},we={class:"setting"},xe={class:"setting__desc"},Se={class:"setting"},Fe={class:"setting__desc"},Ue={class:"setting"},Ae={class:"setting__desc"},Ee={class:"setting"},Pe={class:"setting__desc"},Ie={class:"setting"},Ne={class:"setting__desc"},De={class:"setting"},Oe={class:"setting__desc"},ke={class:"setting"},Te={class:"setting__desc"},Ge={class:"setting"},Ce={class:"setting__desc"},Re={class:"setting"},ze={class:"setting__desc"},He={class:"setting"},$e={class:"setting__desc"},We={class:"setting"},Le={class:"setting__desc"},Me={class:"setting"},Be={class:"setting__desc"},je={class:"setting"},Ke={class:"setting__desc"},Ze={class:"setting"},qe={class:"setting__desc"},Je=I({__name:"InterfaceView",setup(u){const{t}=K(),s=Z(),{themes:O,codeVariants:k,diagramAligns:T,diagramThemes:G,interfaceFonts:C,readingFonts:R,headingFonts:z,monoFonts:H,diagramFonts:$}=re(),x=S(()=>ue[s.locale.language]);function m(o){return{subtitle:o.note,style:{fontFamily:o.stack}}}function h(o){return{subtitle:o.note}}const W=S(()=>ae.map(o=>({title:o===se?t("settings.interface.diagram.height.unlimited"):`${o} px`,value:o}))),L=ee.map(o=>({title:`${o} px`,value:o})),M=te.map(o=>({title:`${o} px`,value:o})),E=ie.map(o=>({title:String(o),value:o,props:{style:{fontWeight:o}}})),B=S(()=>le.map(o=>({title:o===ne?t("settings.interface.measure.reading.unlimited"):`${o}ch`,value:o})));return(o,l)=>(g(),N(X,null,{default:r(()=>[i(oe,{title:e(t)("settings.interface.page.title"),description:e(t)("settings.interface.page.description")},null,8,["title","description"]),n("div",he,[i(_,{title:e(t)("settings.interface.group.app.title"),description:e(t)("settings.interface.group.app.description")},{default:r(()=>[n("div",fe,[i(p,{modelValue:e(s).locale.language,"onUpdate:modelValue":l[0]||(l[0]=a=>e(s).locale.language=a),items:e(q),"item-title":"label","item-value":"code",chips:!1,label:e(t)("settings.interface.language.label"),variant:"outlined",density:"comfortable","hide-details":"auto"},{selection:r(({item:a})=>[e(f)(a.flag)?(g(),U("img",{key:0,src:e(f)(a.flag),alt:"",class:"language-flag"},null,8,_e)):A("",!0),n("span",null,d(a.label),1)]),item:r(({props:a,item:P})=>[i(J,Y(Q(a)),{prepend:r(()=>[e(f)(P.flag)?(g(),U("img",{key:0,src:e(f)(P.flag),alt:"",class:"language-flag"},null,8,be)):A("",!0)]),_:2},1040)]),_:1},8,["modelValue","items","label"]),n("p",ye,d(e(t)("settings.interface.language.description")),1)]),n("div",ve,[i(p,{modelValue:e(s).appearance.theme,"onUpdate:modelValue":l[1]||(l[1]=a=>e(s).appearance.theme=a),items:e(O),"item-title":"label","item-value":"code","item-props":h,chips:!1,label:e(t)("settings.interface.theme.label"),variant:"outlined",density:"comfortable","hide-details":"auto"},null,8,["modelValue","items","label"]),n("p",Ve,d(e(t)("settings.interface.theme.description")),1)]),n("div",we,[i(c,{modelValue:e(s).typography.interfaceFont,"onUpdate:modelValue":l[2]||(l[2]=a=>e(s).typography.interfaceFont=a),items:e(C),"item-title":"label","item-value":"code","item-props":m,chips:!1,label:e(t)("settings.interface.font.interface.label"),variant:"outlined",density:"comfortable","hide-details":"auto"},null,8,["modelValue","items","label"]),n("p",xe,d(e(t)("settings.interface.font.interface.description")),1)])]),_:1},8,["title","description"]),i(_,{title:e(t)("settings.interface.group.document.title"),description:e(t)("settings.interface.group.document.description")},{default:r(()=>[n("div",Se,[i(c,{modelValue:e(s).typography.readingFont,"onUpdate:modelValue":l[3]||(l[3]=a=>e(s).typography.readingFont=a),items:e(R),"item-title":"label","item-value":"code","item-props":m,chips:!1,label:e(t)("settings.interface.font.reading.label"),variant:"outlined",density:"comfortable","hide-details":"auto"},null,8,["modelValue","items","label"]),n("p",Fe,d(e(t)("settings.interface.font.reading.description")),1)]),n("div",Ue,[i(c,{modelValue:e(s).typography.readingSize,"onUpdate:modelValue":l[4]||(l[4]=a=>e(s).typography.readingSize=a),items:e(L),chips:!1,label:e(t)("settings.interface.size.reading.label"),variant:"outlined",density:"comfortable","hide-details":"auto"},null,8,["modelValue","items","label"]),n("p",Ae,d(e(t)("settings.interface.size.reading.description")),1)]),n("div",Ee,[i(c,{modelValue:e(s).typography.readingWeight,"onUpdate:modelValue":l[5]||(l[5]=a=>e(s).typography.readingWeight=a),items:e(E),chips:!1,label:e(t)("settings.interface.weight.reading.label"),variant:"outlined",density:"comfortable","hide-details":"auto"},null,8,["modelValue","items","label"]),n("p",Pe,d(e(t)("settings.interface.weight.reading.description")),1)]),n("div",Ie,[i(c,{modelValue:e(s).typography.headingFont,"onUpdate:modelValue":l[6]||(l[6]=a=>e(s).typography.headingFont=a),items:e(z),"item-title":"label","item-value":"code","item-props":m,chips:!1,label:e(t)("settings.interface.font.heading.label"),variant:"outlined",density:"comfortable","hide-details":"auto"},null,8,["modelValue","items","label"]),n("p",Ne,d(e(t)("settings.interface.font.heading.description")),1)]),n("div",De,[i(c,{modelValue:e(s).typography.headingWeight,"onUpdate:modelValue":l[7]||(l[7]=a=>e(s).typography.headingWeight=a),items:e(E),chips:!1,label:e(t)("settings.interface.weight.heading.label"),variant:"outlined",density:"comfortable","hide-details":"auto"},null,8,["modelValue","items","label"]),n("p",Oe,d(e(t)("settings.interface.weight.heading.description")),1)]),n("div",ke,[i(c,{modelValue:e(s).typography.readingMeasure,"onUpdate:modelValue":l[8]||(l[8]=a=>e(s).typography.readingMeasure=a),items:B.value,chips:!1,label:e(t)("settings.interface.measure.reading.label"),variant:"outlined",density:"comfortable","hide-details":"auto"},null,8,["modelValue","items","label"]),n("p",Te,d(e(t)("settings.interface.measure.reading.description")),1)])]),_:1},8,["title","description"]),i(b,{variant:"outlined",rounded:"lg"},{default:r(()=>[i(v,{class:"text-h6"},{default:r(()=>[y(d(e(t)("settings.interface.preview.title")),1)]),_:1}),i(V),i(w,null,{default:r(()=>[i(F,{text:x.value.document},null,8,["text"])]),_:1})]),_:1}),i(_,{title:e(t)("settings.interface.group.code.title"),description:e(t)("settings.interface.group.code.description")},{default:r(()=>[n("div",Ge,[i(p,{modelValue:e(s).typography.codeVariant,"onUpdate:modelValue":l[9]||(l[9]=a=>e(s).typography.codeVariant=a),items:e(k),"item-title":"label","item-value":"code","item-props":h,chips:!1,label:e(t)("settings.interface.code.variant.label"),variant:"outlined",density:"comfortable","hide-details":"auto"},null,8,["modelValue","items","label"]),n("p",Ce,d(e(t)("settings.interface.code.variant.description")),1)]),n("div",Re,[i(c,{modelValue:e(s).typography.monoFont,"onUpdate:modelValue":l[10]||(l[10]=a=>e(s).typography.monoFont=a),items:e(H),"item-title":"label","item-value":"code","item-props":m,chips:!1,label:e(t)("settings.interface.font.mono.label"),variant:"outlined",density:"comfortable","hide-details":"auto"},null,8,["modelValue","items","label"]),n("p",ze,d(e(t)("settings.interface.font.mono.description")),1)]),n("div",He,[i(c,{modelValue:e(s).typography.codeSize,"onUpdate:modelValue":l[11]||(l[11]=a=>e(s).typography.codeSize=a),items:e(M),chips:!1,label:e(t)("settings.interface.size.code.label"),variant:"outlined",density:"comfortable","hide-details":"auto"},null,8,["modelValue","items","label"]),n("p",$e,d(e(t)("settings.interface.size.code.description")),1)]),i(de,{modelValue:e(s).typography.codeLineNumbers,"onUpdate:modelValue":l[12]||(l[12]=a=>e(s).typography.codeLineNumbers=a),title:e(t)("settings.interface.code.line_numbers.label"),description:e(t)("settings.interface.code.line_numbers.description")},null,8,["modelValue","title","description"])]),_:1},8,["title","description"]),i(b,{variant:"outlined",rounded:"lg"},{default:r(()=>[i(v,{class:"text-h6"},{default:r(()=>[y(d(e(t)("settings.interface.preview.title")),1)]),_:1}),i(V),i(w,null,{default:r(()=>[i(F,{text:x.value.code},null,8,["text"])]),_:1})]),_:1}),i(_,{title:e(t)("settings.interface.group.diagram.title"),description:e(t)("settings.interface.group.diagram.description")},{default:r(()=>[n("div",We,[i(p,{modelValue:e(s).diagrams.theme,"onUpdate:modelValue":l[13]||(l[13]=a=>e(s).diagrams.theme=a),items:e(G),"item-title":"label","item-value":"code","item-props":h,chips:!1,label:e(t)("settings.interface.diagram.theme.label"),variant:"outlined",density:"comfortable","hide-details":"auto"},null,8,["modelValue","items","label"]),n("p",Le,d(e(t)("settings.interface.diagram.theme.description")),1)]),n("div",Me,[i(p,{modelValue:e(s).diagrams.font,"onUpdate:modelValue":l[14]||(l[14]=a=>e(s).diagrams.font=a),items:e($),"item-title":"label","item-value":"code","item-props":m,chips:!1,label:e(t)("settings.interface.font.diagram.label"),variant:"outlined",density:"comfortable","hide-details":"auto"},null,8,["modelValue","items","label"]),n("p",Be,d(e(t)("settings.interface.font.diagram.description")),1)]),n("div",je,[i(p,{modelValue:e(s).diagrams.align,"onUpdate:modelValue":l[15]||(l[15]=a=>e(s).diagrams.align=a),items:e(T),"item-title":"label","item-value":"code","item-props":h,chips:!1,label:e(t)("settings.interface.diagram.align.label"),variant:"outlined",density:"comfortable","hide-details":"auto"},null,8,["modelValue","items","label"]),n("p",Ke,d(e(t)("settings.interface.diagram.align.description")),1)]),n("div",Ze,[i(p,{modelValue:e(s).diagrams.maxHeight,"onUpdate:modelValue":l[16]||(l[16]=a=>e(s).diagrams.maxHeight=a),items:W.value,chips:!1,label:e(t)("settings.interface.diagram.height.label"),variant:"outlined",density:"comfortable","hide-details":"auto"},null,8,["modelValue","items","label"]),n("p",qe,d(e(t)("settings.interface.diagram.height.description")),1)])]),_:1},8,["title","description"]),i(b,{variant:"outlined",rounded:"lg"},{default:r(()=>[i(v,{class:"text-h6"},{default:r(()=>[y(d(e(t)("settings.interface.preview.title")),1)]),_:1}),i(V),i(w,null,{default:r(()=>[i(F,{text:x.value.diagram},null,8,["text"])]),_:1})]),_:1})])]),_:1}))}}),wt=D(Je,[["__scopeId","data-v-f4461ed7"]]);export{wt as default};
