import{bx as m,bB as _,ds as d,bs as f,bq as u,d0 as v,db as e,m as b,bp as a,d4 as c,bJ as h,cZ as S,bm as n,cN as i,a as g,b8 as k}from"./index-CUAQiMuq.js";/**
 * @license @tabler/icons-vue v3.44.0 - MIT
 *
 * This source code is licensed under the MIT license.
 * See the LICENSE file in the root directory of this source tree.
 */var x=m("outline","search-off","SearchOff",[["path",{d:"M5.039 5.062a7 7 0 0 0 9.91 9.89m1.584 -2.434a7 7 0 0 0 -9.038 -9.057",key:"svg-0"}],["path",{d:"M3 3l18 18",key:"svg-1"}]]);const B={class:"section-error",role:"alert","aria-live":"polite"},y={class:"section-error__title"},E={class:"section-error__text"},I=_({__name:"SectionError",props:{error:{}},setup(o){const r=o,{t:s}=d(),t=n(()=>r.error instanceof g&&r.error.status===404),l=n(()=>t.value?s("common.errors.section.missing"):s("common.errors.section.failed"));return(p,C)=>(i(),f("div",B,[(i(),u(v(t.value?e(x):e(b)),{class:"section-error__icon",size:40,stroke:"1.5"})),a("p",y,c(l.value),1),a("p",E,c(e(h)(o.error)),1),S(p.$slots,"actions",{},void 0,!0)]))}}),D=k(I,[["__scopeId","data-v-8a77ab45"]]);export{D as S};
