import{bI as p,bM as _,dR as m,bC as f,bA as u,dj as v,dA as e,q as b,bz as a,dt as n,bW as h,dg as g,bw as c,d1 as i,a as S,bg as k}from"./index-Cs8WGrv5.js";/**
 * @license @tabler/icons-vue v3.44.0 - MIT
 *
 * This source code is licensed under the MIT license.
 * See the LICENSE file in the root directory of this source tree.
 */var I=p("outline","search-off","SearchOff",[["path",{d:"M5.039 5.062a7 7 0 0 0 9.91 9.89m1.584 -2.434a7 7 0 0 0 -9.038 -9.057",key:"svg-0"}],["path",{d:"M3 3l18 18",key:"svg-1"}]]);const x={class:"section-error",role:"alert","aria-live":"polite"},y={class:"section-error__title"},A={class:"section-error__text"},B=_({__name:"SectionError",props:{error:{}},setup(o){const r=o,{t:s}=m(),t=c(()=>r.error instanceof S&&r.error.status===404),l=c(()=>t.value?s("common.errors.section.missing"):s("common.errors.section.failed"));return(d,C)=>(i(),f("div",x,[(i(),u(v(t.value?e(I):e(b)),{class:"section-error__icon",size:40,stroke:"1.5"})),a("p",y,n(l.value),1),a("p",A,n(e(h)(o.error)),1),g(d.$slots,"actions",{},void 0,!0)]))}}),M=k(B,[["__scopeId","data-v-8a77ab45"]]);export{M as S};
