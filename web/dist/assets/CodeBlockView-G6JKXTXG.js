import{bL as h,dO as V,bA as k,ef as a,bz as e,bG as t,dx as o,dq as r,aI as f,aG as d,bF as i,aJ as u,bC as w,dc as B,F as C,bg as x,da as g,c_ as y,bf as I}from"./index-p2dGIhHa.js";import{P as N}from"./PageHeader-DvpoqMhr.js";import{C as l}from"./CodeBlock-DF78K-pO.js";import"./IconCopy-CEZ0ci6b.js";const E={class:"ds-page"},O={class:"ds-card__title"},D={class:"ds-props"},R={class:"ds-row"},A={class:"ds-controls"},L={class:"ds-row ds-row--border"},M={class:"ds-controls"},S={class:"ds-card__title"},T={class:"ds-card__title"},F={class:"variants"},q={class:"variant-item"},P={class:"variant-item"},U={class:"variant-item"},G={class:"variant-item"},H={class:"ds-card__title"},J={class:"lang-grid"},m=`def fetch_vacancies(status: str, limit: int = 50) -> list[Vacancy]:
    with session_scope() as session:
        return (
            session.query(Vacancy)
            .filter(Vacancy.status == status)
            .order_by(Vacancy.published_at.desc())
            .limit(limit)
            .all()
        )`,$=h({__name:"CodeBlockView",setup(j){const p=g("icon"),v=g(!1),{t:n}=V(),b={json:`{
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
LIMIT 20;`};return(z,s)=>(y(),k(x,null,{default:a(()=>[e("div",E,[t(N,{title:o(n)("design-system.page.code-block.title"),description:o(n)("design-system.page.code-block.description"),"back-to":"/design-system"},null,8,["title","description"]),t(u,{class:"ds-card"},{default:a(()=>[e("h6",O,r(o(n)("design-system.section.code-block.props")),1),e("div",D,[e("div",R,[s[6]||(s[6]=e("span",{class:"ds-tag"},"variant",-1)),e("div",A,[t(f,{modelValue:p.value,"onUpdate:modelValue":s[0]||(s[0]=c=>p.value=c),mandatory:"",divided:"",density:"compact"},{default:a(()=>[t(d,{value:"minimal"},{default:a(()=>[...s[2]||(s[2]=[i("Minimal",-1)])]),_:1}),t(d,{value:"icon"},{default:a(()=>[...s[3]||(s[3]=[i("Icon",-1)])]),_:1}),t(d,{value:"accent"},{default:a(()=>[...s[4]||(s[4]=[i("Accent",-1)])]),_:1}),t(d,{value:"compact"},{default:a(()=>[...s[5]||(s[5]=[i("Compact",-1)])]),_:1})]),_:1},8,["modelValue"])]),s[7]||(s[7]=e("span",{class:"ds-spec"},"header template",-1))]),e("div",L,[s[10]||(s[10]=e("span",{class:"ds-tag"},"showLineNumbers",-1)),e("div",M,[t(f,{modelValue:v.value,"onUpdate:modelValue":s[1]||(s[1]=c=>v.value=c),mandatory:"",divided:"",density:"compact"},{default:a(()=>[t(d,{value:!1},{default:a(()=>[...s[8]||(s[8]=[i("Off",-1)])]),_:1}),t(d,{value:!0},{default:a(()=>[...s[9]||(s[9]=[i("On",-1)])]),_:1})]),_:1},8,["modelValue"])]),s[11]||(s[11]=e("span",{class:"ds-spec"},"default numbering",-1))])])]),_:1}),t(u,{class:"ds-card"},{default:a(()=>[e("h6",S,r(o(n)("design-system.section.code-block.demo")),1),t(l,{code:m,lang:"python",variant:p.value,"show-line-numbers":v.value},null,8,["variant","show-line-numbers"])]),_:1}),t(u,{class:"ds-card"},{default:a(()=>[e("h6",T,r(o(n)("design-system.section.code-block.allVariants")),1),e("div",F,[e("div",q,[s[12]||(s[12]=e("span",{class:"ds-tag"},"minimal",-1)),t(l,{code:m,lang:"python",variant:"minimal"})]),e("div",P,[s[13]||(s[13]=e("span",{class:"ds-tag"},"icon",-1)),t(l,{code:m,lang:"python",variant:"icon"})]),e("div",U,[s[14]||(s[14]=e("span",{class:"ds-tag"},"accent",-1)),t(l,{code:m,lang:"python",variant:"accent"})]),e("div",G,[s[15]||(s[15]=e("span",{class:"ds-tag"},"compact — single-line code, copy on hover",-1)),t(l,{code:"uv run pytest --core",lang:"bash",variant:"compact"})])])]),_:1}),t(u,{class:"ds-card"},{default:a(()=>[e("h6",H,r(o(n)("design-system.section.code-block.languages")),1),e("div",J,[(y(),w(C,null,B(b,(c,_)=>e("div",{key:_,class:"lang-item"},[t(l,{code:c,lang:_,variant:"icon"},null,8,["code","lang"])])),64))])]),_:1})])]),_:1}))}}),X=I($,[["__scopeId","data-v-96c9f1a9"]]);export{X as default};
