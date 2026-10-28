import{bM as h,dR as V,bA as k,ei as a,bz as e,bH as t,dA as o,dt as r,aJ as f,aH as d,bF as i,aK as u,bC as w,df as B,F as C,bh as x,dd as g,d1 as y,bg as I}from"./index-BZBeLbdV.js";import{P as N}from"./PageHeader-xUi9dSf5.js";import{C as l}from"./CodeBlock-DycGxIcn.js";import"./VSkeletonLoader-BlhhTmPr.js";import"./IconCopy-CZwMt5Ec.js";const E={class:"ds-page"},R={class:"ds-card__title"},A={class:"ds-props"},D={class:"ds-row"},M={class:"ds-controls"},O={class:"ds-row ds-row--border"},S={class:"ds-controls"},T={class:"ds-card__title"},F={class:"ds-card__title"},H={class:"variants"},L={class:"variant-item"},P={class:"variant-item"},U={class:"variant-item"},q={class:"variant-item"},J={class:"ds-card__title"},$={class:"lang-grid"},m=`def fetch_vacancies(status: str, limit: int = 50) -> list[Vacancy]:
    with session_scope() as session:
        return (
            session.query(Vacancy)
            .filter(Vacancy.status == status)
            .order_by(Vacancy.published_at.desc())
            .limit(limit)
            .all()
        )`,j=h({__name:"CodeBlockView",setup(z){const p=g("icon"),v=g(!1),{t:n}=V(),b={json:`{
  "id": "hh-1234567",
  "title": "Python Backend Developer",
  "salary": { "from": 180000, "to": 250000, "currency": "RUR" },
  "experience": "between3And6",
  "schedule": "remote",
  "published_at": "2026-05-17T09:00:00+05:00"
}`,typescript:`interface BlockMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

async function completeSession(sessionId: number, text: string) {
  const { data } = await api.post<BlockMessage>(\`/sessions/\${sessionId}/complete\`, { text })
  return data
}`,bash:`#!/usr/bin/env bash
set -euo pipefail
pnpm --filter web build
python build.py --clean
echo "Done: dist/release/urb-research"`,sql:`SELECT v.id, v.title, v.salary_from, c.name AS company_name
FROM hh_vacancy v
JOIN hh_company c ON c.id = v.company_id
WHERE v.status = 'active' AND v.salary_from >= 150000
ORDER BY v.published_at DESC
LIMIT 20;`};return(K,s)=>(y(),k(x,null,{default:a(()=>[e("div",E,[t(N,{title:o(n)("design-system.page.code-block.title"),description:o(n)("design-system.page.code-block.description"),"back-to":"/design-system"},null,8,["title","description"]),t(u,{class:"ds-card"},{default:a(()=>[e("h6",R,r(o(n)("design-system.section.code-block.props")),1),e("div",A,[e("div",D,[s[6]||(s[6]=e("span",{class:"ds-tag"},"variant",-1)),e("div",M,[t(f,{modelValue:p.value,"onUpdate:modelValue":s[0]||(s[0]=c=>p.value=c),mandatory:"",divided:"",density:"compact"},{default:a(()=>[t(d,{value:"minimal"},{default:a(()=>[...s[2]||(s[2]=[i("Minimal",-1)])]),_:1}),t(d,{value:"icon"},{default:a(()=>[...s[3]||(s[3]=[i("Icon",-1)])]),_:1}),t(d,{value:"accent"},{default:a(()=>[...s[4]||(s[4]=[i("Accent",-1)])]),_:1}),t(d,{value:"compact"},{default:a(()=>[...s[5]||(s[5]=[i("Compact",-1)])]),_:1})]),_:1},8,["modelValue"])]),s[7]||(s[7]=e("span",{class:"ds-spec"},"header template",-1))]),e("div",O,[s[10]||(s[10]=e("span",{class:"ds-tag"},"showLineNumbers",-1)),e("div",S,[t(f,{modelValue:v.value,"onUpdate:modelValue":s[1]||(s[1]=c=>v.value=c),mandatory:"",divided:"",density:"compact"},{default:a(()=>[t(d,{value:!1},{default:a(()=>[...s[8]||(s[8]=[i("Off",-1)])]),_:1}),t(d,{value:!0},{default:a(()=>[...s[9]||(s[9]=[i("On",-1)])]),_:1})]),_:1},8,["modelValue"])]),s[11]||(s[11]=e("span",{class:"ds-spec"},"default numbering",-1))])])]),_:1}),t(u,{class:"ds-card"},{default:a(()=>[e("h6",T,r(o(n)("design-system.section.code-block.demo")),1),t(l,{code:m,lang:"python",variant:p.value,"show-line-numbers":v.value},null,8,["variant","show-line-numbers"])]),_:1}),t(u,{class:"ds-card"},{default:a(()=>[e("h6",F,r(o(n)("design-system.section.code-block.allVariants")),1),e("div",H,[e("div",L,[s[12]||(s[12]=e("span",{class:"ds-tag"},"minimal",-1)),t(l,{code:m,lang:"python",variant:"minimal"})]),e("div",P,[s[13]||(s[13]=e("span",{class:"ds-tag"},"icon",-1)),t(l,{code:m,lang:"python",variant:"icon"})]),e("div",U,[s[14]||(s[14]=e("span",{class:"ds-tag"},"accent",-1)),t(l,{code:m,lang:"python",variant:"accent"})]),e("div",q,[s[15]||(s[15]=e("span",{class:"ds-tag"},"compact — single-line code, copy on hover",-1)),t(l,{code:"uv run pytest --core",lang:"bash",variant:"compact"})])])]),_:1}),t(u,{class:"ds-card"},{default:a(()=>[e("h6",J,r(o(n)("design-system.section.code-block.languages")),1),e("div",$,[(y(),w(C,null,B(b,(c,_)=>e("div",{key:_,class:"lang-item"},[t(l,{code:c,lang:_,variant:"icon"},null,8,["code","lang"])])),64))])]),_:1})])]),_:1}))}}),Z=I(j,[["__scopeId","data-v-96c9f1a9"]]);export{Z as default};
