import{bd as _,bg as m,c0 as d,b9 as b,b7 as f,bR as u,bX as e,h as v,b6 as a,bV as c,bk as h,bP as g,b5 as n,bH as i,a as k,a$ as S}from"./index-CtJp1Su1.js";/**
 * @license @tabler/icons-vue v3.44.0 - MIT
 *
 * This source code is licensed under the MIT license.
 * See the LICENSE file in the root directory of this source tree.
 */var x=_("outline","search-off","SearchOff",[["path",{d:"M5.039 5.062a7 7 0 0 0 9.91 9.89m1.584 -2.434a7 7 0 0 0 -9.038 -9.057",key:"svg-0"}],["path",{d:"M3 3l18 18",key:"svg-1"}]]);const y={class:"section-error",role:"alert","aria-live":"polite"},B={class:"section-error__title"},E={class:"section-error__text"},I=m({__name:"SectionError",props:{error:{}},setup(o){const r=o,{t:s}=d(),t=n(()=>r.error instanceof k&&r.error.status===404),l=n(()=>t.value?s("common.errors.section.missing"):s("common.errors.section.failed"));return(p,C)=>(i(),b("div",y,[(i(),f(u(t.value?e(x):e(v)),{class:"section-error__icon",size:40,stroke:"1.5"})),a("p",B,c(l.value),1),a("p",E,c(e(h)(o.error)),1),g(p.$slots,"actions",{},void 0,!0)]))}}),A=S(I,[["__scopeId","data-v-10bc09e0"]]);export{A as S};
