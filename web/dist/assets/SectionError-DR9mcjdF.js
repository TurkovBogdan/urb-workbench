import{bH as _,bL as p,dO as m,bC as f,bA as u,dg as v,dx as e,q as b,bz as a,dq as n,bV as h,dd as g,bw as c,c_ as i,a as S,bf as k}from"./index-p2dGIhHa.js";/**
 * @license @tabler/icons-vue v3.44.0 - MIT
 *
 * This source code is licensed under the MIT license.
 * See the LICENSE file in the root directory of this source tree.
 */var x=_("outline","search-off","SearchOff",[["path",{d:"M5.039 5.062a7 7 0 0 0 9.91 9.89m1.584 -2.434a7 7 0 0 0 -9.038 -9.057",key:"svg-0"}],["path",{d:"M3 3l18 18",key:"svg-1"}]]);const y={class:"section-error",role:"alert","aria-live":"polite"},B={class:"section-error__title"},C={class:"section-error__text"},E=p({__name:"SectionError",props:{error:{}},setup(o){const r=o,{t:s}=m(),t=c(()=>r.error instanceof S&&r.error.status===404),l=c(()=>t.value?s("common.errors.section.missing"):s("common.errors.section.failed"));return(d,I)=>(i(),f("div",y,[(i(),u(v(t.value?e(x):e(b)),{class:"section-error__icon",size:40,stroke:"1.5"})),a("p",B,n(l.value),1),a("p",C,n(e(h)(o.error)),1),g(d.$slots,"actions",{},void 0,!0)]))}}),O=k(E,[["__scopeId","data-v-8a77ab45"]]);export{O as S};
