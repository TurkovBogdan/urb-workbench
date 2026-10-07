import{bv as _,bz as m,dp as d,bq as f,bo as u,cZ as v,d8 as e,m as b,bn as a,d1 as c,bG as h,cW as k,bk as n,cK as i,a as S,b8 as g}from"./index-bQ8JD7MY.js";/**
 * @license @tabler/icons-vue v3.44.0 - MIT
 *
 * This source code is licensed under the MIT license.
 * See the LICENSE file in the root directory of this source tree.
 */var x=_("outline","search-off","SearchOff",[["path",{d:"M5.039 5.062a7 7 0 0 0 9.91 9.89m1.584 -2.434a7 7 0 0 0 -9.038 -9.057",key:"svg-0"}],["path",{d:"M3 3l18 18",key:"svg-1"}]]);const y={class:"section-error",role:"alert","aria-live":"polite"},B={class:"section-error__title"},E={class:"section-error__text"},I=m({__name:"SectionError",props:{error:{}},setup(o){const r=o,{t:s}=d(),t=n(()=>r.error instanceof S&&r.error.status===404),l=n(()=>t.value?s("common.errors.section.missing"):s("common.errors.section.failed"));return(p,C)=>(i(),f("div",y,[(i(),u(v(t.value?e(x):e(b)),{class:"section-error__icon",size:40,stroke:"1.5"})),a("p",B,c(l.value),1),a("p",E,c(e(h)(o.error)),1),k(p.$slots,"actions",{},void 0,!0)]))}}),A=g(I,[["__scopeId","data-v-8a77ab45"]]);export{A as S};
