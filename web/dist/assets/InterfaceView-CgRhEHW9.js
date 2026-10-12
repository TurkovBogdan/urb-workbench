import{bH as P,cU as g,bw as D,aH as b,e0 as r,bC as i,bB as y,dd as d,aM as v,by as U,bx as A,aQ as V,d5 as j,aL as w,bd as N,dB as K,dS as Z,dk as e,bv as n,an as J,aY as Q,cJ as Y,c2 as q,bS as f,be as X,bs as x,av as ee,c as te,aw as ie,i as ae,ar as se,au as le,as as ne}from"./index-DitlXhVX.js";import{P as oe}from"./PageHeader-DPt2lRZ0.js";import{_ as F}from"./MarkdownRenderer.vue_vue_type_script_setup_true_lang-CcijycEs.js";import"./document.css_vue_type_style_index_0_src_true_lang-D_djjgWD.js";import{S as de}from"./SwitchPanel-XCsf0yCl.js";import{V as c}from"./VSelectStepper-Dm_NwJ0f.js";import{u as re}from"./useAppearanceOptions-BtOt1SW1.js";import{a as p}from"./VSelect-CV1yqoUu.js";import"./CodeBlock-B_W1LGvP.js";import"./IconCopy-BHBl3qdd.js";import"./purify.es-DxCUJf2h.js";import"./IconLayoutGrid-Rj2d4UOw.js";import"./IconListCheck-K4ZYalW5.js";import"./VSwitch-D0mQksJo.js";import"./VSelectionControl-BrthGuKH.js";import"./VChip-BV3hIx5o.js";const ce={key:0,class:"settings-group__desc"},pe=P({__name:"SettingsGroup",props:{title:{},description:{}},setup(u){return(t,s)=>(g(),D(b,{variant:"outlined",rounded:"lg"},{default:r(()=>[i(v,{class:"text-h6"},{default:r(()=>[y(d(u.title),1)]),_:1}),u.description?(g(),U("p",ce,d(u.description),1)):A("",!0),i(V),i(w,{class:"settings-columns"},{default:r(()=>[j(t.$slots,"default",{},void 0,!0)]),_:3})]),_:3}))}}),_=N(pe,[["__scopeId","data-v-f20eb0d7"]]),me={document:`# First-level heading

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
`},ue={en:me,ru:ge},he={class:"settings-list"},fe={class:"setting"},_e=["src"],be=["src"],ye={class:"setting__desc"},ve={class:"setting"},Ve={class:"setting__desc"},we={class:"setting"},Se={class:"setting__desc"},xe={class:"setting"},Fe={class:"setting__desc"},Ue={class:"setting"},Ae={class:"setting__desc"},Ee={class:"setting"},Ie={class:"setting__desc"},Pe={class:"setting"},De={class:"setting__desc"},Ne={class:"setting"},ke={class:"setting__desc"},Te={class:"setting"},Oe={class:"setting__desc"},Ce={class:"setting"},Ge={class:"setting__desc"},Re={class:"setting"},He={class:"setting__desc"},ze={class:"setting"},$e={class:"setting__desc"},Me={class:"setting"},We={class:"setting__desc"},Be={class:"setting"},Le={class:"setting__desc"},je={class:"setting"},Ke={class:"setting__desc"},Ze={class:"setting"},Je={class:"setting__desc"},Qe=P({__name:"InterfaceView",setup(u){const{t}=K(),s=Z(),{themes:k,codeVariants:T,diagramAligns:O,diagramThemes:C,interfaceFonts:G,readingFonts:R,headingFonts:H,monoFonts:z,diagramFonts:$}=re(),S=x(()=>ue[s.locale.language]);function m(o){return{subtitle:o.note,style:{fontFamily:o.stack}}}function h(o){return{subtitle:o.note}}const M=x(()=>ae.map(o=>({title:o===se?t("settings.interface.diagram.height.unlimited"):`${o} px`,value:o}))),W=ee.map(o=>({title:`${o} px`,value:o})),B=te.map(o=>({title:`${o} px`,value:o})),E=ie.map(o=>({title:String(o),value:o,props:{style:{fontWeight:o}}})),L=x(()=>le.map(o=>({title:o===ne?t("settings.interface.measure.reading.unlimited"):`${o}ch`,value:o})));return(o,l)=>(g(),D(X,null,{default:r(()=>[i(oe,{title:e(t)("settings.interface.page.title"),description:e(t)("settings.interface.page.description")},null,8,["title","description"]),n("div",he,[i(_,{title:e(t)("settings.interface.group.app.title"),description:e(t)("settings.interface.group.app.description")},{default:r(()=>[n("div",fe,[i(p,{modelValue:e(s).locale.language,"onUpdate:modelValue":l[0]||(l[0]=a=>e(s).locale.language=a),items:e(J),"item-title":"label","item-value":"code",chips:!1,label:e(t)("settings.interface.language.label"),variant:"outlined",density:"comfortable","hide-details":"auto"},{selection:r(({item:a})=>[e(f)(a.flag)?(g(),U("img",{key:0,src:e(f)(a.flag),alt:"",class:"language-flag"},null,8,_e)):A("",!0),n("span",null,d(a.label),1)]),item:r(({props:a,item:I})=>[i(Q,Y(q(a)),{prepend:r(()=>[e(f)(I.flag)?(g(),U("img",{key:0,src:e(f)(I.flag),alt:"",class:"language-flag"},null,8,be)):A("",!0)]),_:2},1040)]),_:1},8,["modelValue","items","label"]),n("p",ye,d(e(t)("settings.interface.language.description")),1)]),n("div",ve,[i(p,{modelValue:e(s).appearance.theme,"onUpdate:modelValue":l[1]||(l[1]=a=>e(s).appearance.theme=a),items:e(k),"item-title":"label","item-value":"code","item-props":h,chips:!1,label:e(t)("settings.interface.theme.label"),variant:"outlined",density:"comfortable","hide-details":"auto"},null,8,["modelValue","items","label"]),n("p",Ve,d(e(t)("settings.interface.theme.description")),1)]),n("div",we,[i(c,{modelValue:e(s).typography.interfaceFont,"onUpdate:modelValue":l[2]||(l[2]=a=>e(s).typography.interfaceFont=a),items:e(G),"item-title":"label","item-value":"code","item-props":m,chips:!1,label:e(t)("settings.interface.font.interface.label"),variant:"outlined",density:"comfortable","hide-details":"auto"},null,8,["modelValue","items","label"]),n("p",Se,d(e(t)("settings.interface.font.interface.description")),1)])]),_:1},8,["title","description"]),i(_,{title:e(t)("settings.interface.group.document.title"),description:e(t)("settings.interface.group.document.description")},{default:r(()=>[n("div",xe,[i(c,{modelValue:e(s).typography.readingFont,"onUpdate:modelValue":l[3]||(l[3]=a=>e(s).typography.readingFont=a),items:e(R),"item-title":"label","item-value":"code","item-props":m,chips:!1,label:e(t)("settings.interface.font.reading.label"),variant:"outlined",density:"comfortable","hide-details":"auto"},null,8,["modelValue","items","label"]),n("p",Fe,d(e(t)("settings.interface.font.reading.description")),1)]),n("div",Ue,[i(c,{modelValue:e(s).typography.readingSize,"onUpdate:modelValue":l[4]||(l[4]=a=>e(s).typography.readingSize=a),items:e(W),chips:!1,label:e(t)("settings.interface.size.reading.label"),variant:"outlined",density:"comfortable","hide-details":"auto"},null,8,["modelValue","items","label"]),n("p",Ae,d(e(t)("settings.interface.size.reading.description")),1)]),n("div",Ee,[i(c,{modelValue:e(s).typography.readingWeight,"onUpdate:modelValue":l[5]||(l[5]=a=>e(s).typography.readingWeight=a),items:e(E),chips:!1,label:e(t)("settings.interface.weight.reading.label"),variant:"outlined",density:"comfortable","hide-details":"auto"},null,8,["modelValue","items","label"]),n("p",Ie,d(e(t)("settings.interface.weight.reading.description")),1)]),n("div",Pe,[i(c,{modelValue:e(s).typography.headingFont,"onUpdate:modelValue":l[6]||(l[6]=a=>e(s).typography.headingFont=a),items:e(H),"item-title":"label","item-value":"code","item-props":m,chips:!1,label:e(t)("settings.interface.font.heading.label"),variant:"outlined",density:"comfortable","hide-details":"auto"},null,8,["modelValue","items","label"]),n("p",De,d(e(t)("settings.interface.font.heading.description")),1)]),n("div",Ne,[i(c,{modelValue:e(s).typography.headingWeight,"onUpdate:modelValue":l[7]||(l[7]=a=>e(s).typography.headingWeight=a),items:e(E),chips:!1,label:e(t)("settings.interface.weight.heading.label"),variant:"outlined",density:"comfortable","hide-details":"auto"},null,8,["modelValue","items","label"]),n("p",ke,d(e(t)("settings.interface.weight.heading.description")),1)]),n("div",Te,[i(c,{modelValue:e(s).typography.readingMeasure,"onUpdate:modelValue":l[8]||(l[8]=a=>e(s).typography.readingMeasure=a),items:L.value,chips:!1,label:e(t)("settings.interface.measure.reading.label"),variant:"outlined",density:"comfortable","hide-details":"auto"},null,8,["modelValue","items","label"]),n("p",Oe,d(e(t)("settings.interface.measure.reading.description")),1)])]),_:1},8,["title","description"]),i(b,{variant:"outlined",rounded:"lg"},{default:r(()=>[i(v,{class:"text-h6"},{default:r(()=>[y(d(e(t)("settings.interface.preview.title")),1)]),_:1}),i(V),i(w,null,{default:r(()=>[i(F,{text:S.value.document},null,8,["text"])]),_:1})]),_:1}),i(_,{title:e(t)("settings.interface.group.code.title"),description:e(t)("settings.interface.group.code.description")},{default:r(()=>[n("div",Ce,[i(p,{modelValue:e(s).typography.codeVariant,"onUpdate:modelValue":l[9]||(l[9]=a=>e(s).typography.codeVariant=a),items:e(T),"item-title":"label","item-value":"code","item-props":h,chips:!1,label:e(t)("settings.interface.code.variant.label"),variant:"outlined",density:"comfortable","hide-details":"auto"},null,8,["modelValue","items","label"]),n("p",Ge,d(e(t)("settings.interface.code.variant.description")),1)]),n("div",Re,[i(c,{modelValue:e(s).typography.monoFont,"onUpdate:modelValue":l[10]||(l[10]=a=>e(s).typography.monoFont=a),items:e(z),"item-title":"label","item-value":"code","item-props":m,chips:!1,label:e(t)("settings.interface.font.mono.label"),variant:"outlined",density:"comfortable","hide-details":"auto"},null,8,["modelValue","items","label"]),n("p",He,d(e(t)("settings.interface.font.mono.description")),1)]),n("div",ze,[i(c,{modelValue:e(s).typography.codeSize,"onUpdate:modelValue":l[11]||(l[11]=a=>e(s).typography.codeSize=a),items:e(B),chips:!1,label:e(t)("settings.interface.size.code.label"),variant:"outlined",density:"comfortable","hide-details":"auto"},null,8,["modelValue","items","label"]),n("p",$e,d(e(t)("settings.interface.size.code.description")),1)]),i(de,{modelValue:e(s).typography.codeLineNumbers,"onUpdate:modelValue":l[12]||(l[12]=a=>e(s).typography.codeLineNumbers=a),title:e(t)("settings.interface.code.line_numbers.label"),description:e(t)("settings.interface.code.line_numbers.description")},null,8,["modelValue","title","description"])]),_:1},8,["title","description"]),i(b,{variant:"outlined",rounded:"lg"},{default:r(()=>[i(v,{class:"text-h6"},{default:r(()=>[y(d(e(t)("settings.interface.preview.title")),1)]),_:1}),i(V),i(w,null,{default:r(()=>[i(F,{text:S.value.code},null,8,["text"])]),_:1})]),_:1}),i(_,{title:e(t)("settings.interface.group.diagram.title"),description:e(t)("settings.interface.group.diagram.description")},{default:r(()=>[n("div",Me,[i(p,{modelValue:e(s).diagrams.theme,"onUpdate:modelValue":l[13]||(l[13]=a=>e(s).diagrams.theme=a),items:e(C),"item-title":"label","item-value":"code","item-props":h,chips:!1,label:e(t)("settings.interface.diagram.theme.label"),variant:"outlined",density:"comfortable","hide-details":"auto"},null,8,["modelValue","items","label"]),n("p",We,d(e(t)("settings.interface.diagram.theme.description")),1)]),n("div",Be,[i(p,{modelValue:e(s).diagrams.font,"onUpdate:modelValue":l[14]||(l[14]=a=>e(s).diagrams.font=a),items:e($),"item-title":"label","item-value":"code","item-props":m,chips:!1,label:e(t)("settings.interface.font.diagram.label"),variant:"outlined",density:"comfortable","hide-details":"auto"},null,8,["modelValue","items","label"]),n("p",Le,d(e(t)("settings.interface.font.diagram.description")),1)]),n("div",je,[i(p,{modelValue:e(s).diagrams.align,"onUpdate:modelValue":l[15]||(l[15]=a=>e(s).diagrams.align=a),items:e(O),"item-title":"label","item-value":"code","item-props":h,chips:!1,label:e(t)("settings.interface.diagram.align.label"),variant:"outlined",density:"comfortable","hide-details":"auto"},null,8,["modelValue","items","label"]),n("p",Ke,d(e(t)("settings.interface.diagram.align.description")),1)]),n("div",Ze,[i(p,{modelValue:e(s).diagrams.maxHeight,"onUpdate:modelValue":l[16]||(l[16]=a=>e(s).diagrams.maxHeight=a),items:M.value,chips:!1,label:e(t)("settings.interface.diagram.height.label"),variant:"outlined",density:"comfortable","hide-details":"auto"},null,8,["modelValue","items","label"]),n("p",Je,d(e(t)("settings.interface.diagram.height.description")),1)])]),_:1},8,["title","description"]),i(b,{variant:"outlined",rounded:"lg"},{default:r(()=>[i(v,{class:"text-h6"},{default:r(()=>[y(d(e(t)("settings.interface.preview.title")),1)]),_:1}),i(V),i(w,null,{default:r(()=>[i(F,{text:S.value.diagram},null,8,["text"])]),_:1})]),_:1})])]),_:1}))}}),gt=N(Qe,[["__scopeId","data-v-f4461ed7"]]);export{gt as default};
