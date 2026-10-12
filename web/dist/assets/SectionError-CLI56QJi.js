import{bD as p,bH as _,dB as m,by as f,bw as u,d8 as v,dk as e,o as b,bv as a,dd as n,bQ as h,d5 as k,bs as c,cU as i,a as S,bd as g}from"./index-DitlXhVX.js";/**
 * @license @tabler/icons-vue v3.44.0 - MIT
 *
 * This source code is licensed under the MIT license.
 * See the LICENSE file in the root directory of this source tree.
 */var y=p("outline","search-off","SearchOff",[["path",{d:"M5.039 5.062a7 7 0 0 0 9.91 9.89m1.584 -2.434a7 7 0 0 0 -9.038 -9.057",key:"svg-0"}],["path",{d:"M3 3l18 18",key:"svg-1"}]]);const B={class:"section-error",role:"alert","aria-live":"polite"},x={class:"section-error__title"},E={class:"section-error__text"},I=_({__name:"SectionError",props:{error:{}},setup(o){const r=o,{t:s}=m(),t=c(()=>r.error instanceof S&&r.error.status===404),l=c(()=>t.value?s("common.errors.section.missing"):s("common.errors.section.failed"));return(d,C)=>(i(),f("div",B,[(i(),u(v(t.value?e(y):e(b)),{class:"section-error__icon",size:40,stroke:"1.5"})),a("p",x,n(l.value),1),a("p",E,n(e(h)(o.error)),1),k(d.$slots,"actions",{},void 0,!0)]))}}),A=g(I,[["__scopeId","data-v-8a77ab45"]]);export{A as S};
