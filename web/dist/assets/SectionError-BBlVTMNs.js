import{bg as p,bj as m,c6 as d,bc as b,ba as f,bW as u,c0 as e,h as v,b9 as a,b_ as c,bn as h,bU as g,b8 as n,bM as i,a as S,b2 as k}from"./index-Cf-SeS3Z.js";/**
 * @license @tabler/icons-vue v3.44.0 - MIT
 *
 * This source code is licensed under the MIT license.
 * See the LICENSE file in the root directory of this source tree.
 */var x=p("outline","search-off","SearchOff",[["path",{d:"M5.039 5.062a7 7 0 0 0 9.91 9.89m1.584 -2.434a7 7 0 0 0 -9.038 -9.057",key:"svg-0"}],["path",{d:"M3 3l18 18",key:"svg-1"}]]);const y={class:"section-error",role:"alert","aria-live":"polite"},B={class:"section-error__title"},E={class:"section-error__text"},I=m({__name:"SectionError",props:{error:{}},setup(o){const r=o,{t:s}=d(),t=n(()=>r.error instanceof S&&r.error.status===404),l=n(()=>t.value?s("common.errors.section.missing"):s("common.errors.section.failed"));return(_,C)=>(i(),b("div",y,[(i(),f(u(t.value?e(x):e(v)),{class:"section-error__icon",size:40,stroke:"1.5"})),a("p",B,c(l.value),1),a("p",E,c(e(h)(o.error)),1),g(_.$slots,"actions",{},void 0,!0)]))}}),A=k(I,[["__scopeId","data-v-10bc09e0"]]);export{A as S};
