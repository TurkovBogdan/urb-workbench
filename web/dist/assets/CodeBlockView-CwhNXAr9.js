import{bg as V,c0 as h,b7 as k,cb as a,b6 as e,bc as t,bX as o,bV as r,an as b,al as i,bb as d,ao as u,b9 as w,bO as B,F as C,b0 as x,bM as f,bH as g,a$ as I}from"./index-B56bojGT.js";import{P as N}from"./PageHeader-BIbeNy1D.js";import{C as l}from"./CodeBlock-D0jYgjld.js";const E={class:"ds-page"},O={class:"ds-card__title"},D={class:"ds-props"},M={class:"ds-row"},R={class:"ds-controls"},S={class:"ds-row ds-row--border"},T={class:"ds-controls"},A={class:"ds-card__title"},L={class:"ds-card__title"},F={class:"variants"},H={class:"variant-item"},P={class:"variant-item"},U={class:"variant-item"},$={class:"variant-item"},q={class:"ds-card__title"},j={class:"lang-grid"},m=`def fetch_vacancies(status: str, limit: int = 50) -> list[Vacancy]:
    with session_scope() as session:
        return (
            session.query(Vacancy)
            .filter(Vacancy.status == status)
            .order_by(Vacancy.published_at.desc())
            .limit(limit)
            .all()
        )`,J=V({__name:"CodeBlockView",setup(W){const p=f("icon"),v=f(!1),{t:n}=h(),y={json:`{
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
LIMIT 20;`};return(X,s)=>(g(),k(x,null,{default:a(()=>[e("div",E,[t(N,{title:o(n)("design-system.page.code-block.title"),description:o(n)("design-system.page.code-block.description"),"back-to":"/design-system"},null,8,["title","description"]),t(u,{class:"ds-card"},{default:a(()=>[e("h6",O,r(o(n)("design-system.section.code-block.props")),1),e("div",D,[e("div",M,[s[6]||(s[6]=e("span",{class:"ds-tag"},"variant",-1)),e("div",R,[t(b,{modelValue:p.value,"onUpdate:modelValue":s[0]||(s[0]=c=>p.value=c),mandatory:"",divided:"",density:"compact"},{default:a(()=>[t(i,{value:"minimal"},{default:a(()=>[...s[2]||(s[2]=[d("Minimal",-1)])]),_:1}),t(i,{value:"icon"},{default:a(()=>[...s[3]||(s[3]=[d("Icon",-1)])]),_:1}),t(i,{value:"accent"},{default:a(()=>[...s[4]||(s[4]=[d("Accent",-1)])]),_:1}),t(i,{value:"compact"},{default:a(()=>[...s[5]||(s[5]=[d("Compact",-1)])]),_:1})]),_:1},8,["modelValue"])]),s[7]||(s[7]=e("span",{class:"ds-spec"},"header template",-1))]),e("div",S,[s[10]||(s[10]=e("span",{class:"ds-tag"},"showLineNumbers",-1)),e("div",T,[t(b,{modelValue:v.value,"onUpdate:modelValue":s[1]||(s[1]=c=>v.value=c),mandatory:"",divided:"",density:"compact"},{default:a(()=>[t(i,{value:!1},{default:a(()=>[...s[8]||(s[8]=[d("Off",-1)])]),_:1}),t(i,{value:!0},{default:a(()=>[...s[9]||(s[9]=[d("On",-1)])]),_:1})]),_:1},8,["modelValue"])]),s[11]||(s[11]=e("span",{class:"ds-spec"},"default numbering",-1))])])]),_:1}),t(u,{class:"ds-card"},{default:a(()=>[e("h6",A,r(o(n)("design-system.section.code-block.demo")),1),t(l,{code:m,lang:"python",variant:p.value,"show-line-numbers":v.value},null,8,["variant","show-line-numbers"])]),_:1}),t(u,{class:"ds-card"},{default:a(()=>[e("h6",L,r(o(n)("design-system.section.code-block.allVariants")),1),e("div",F,[e("div",H,[s[12]||(s[12]=e("span",{class:"ds-tag"},"minimal",-1)),t(l,{code:m,lang:"python",variant:"minimal"})]),e("div",P,[s[13]||(s[13]=e("span",{class:"ds-tag"},"icon",-1)),t(l,{code:m,lang:"python",variant:"icon"})]),e("div",U,[s[14]||(s[14]=e("span",{class:"ds-tag"},"accent",-1)),t(l,{code:m,lang:"python",variant:"accent"})]),e("div",$,[s[15]||(s[15]=e("span",{class:"ds-tag"},"compact — однострочный код, копирование по наведению",-1)),t(l,{code:"uv run pytest --core",lang:"bash",variant:"compact"})])])]),_:1}),t(u,{class:"ds-card"},{default:a(()=>[e("h6",q,r(o(n)("design-system.section.code-block.languages")),1),e("div",j,[(g(),w(C,null,B(y,(c,_)=>e("div",{key:_,class:"lang-item"},[t(l,{code:c,lang:_,variant:"icon"},null,8,["code","lang"])])),64))])]),_:1})])]),_:1}))}}),K=I(J,[["__scopeId","data-v-5f20a1c5"]]);export{K as default};
