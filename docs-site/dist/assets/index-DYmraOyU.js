(function(){const t=document.createElement("link").relList;if(t&&t.supports&&t.supports("modulepreload"))return;for(const n of document.querySelectorAll('link[rel="modulepreload"]'))o(n);new MutationObserver(n=>{for(const i of n)if(i.type==="childList")for(const r of i.addedNodes)r.tagName==="LINK"&&r.rel==="modulepreload"&&o(r)}).observe(document,{childList:!0,subtree:!0});function s(n){const i={};return n.integrity&&(i.integrity=n.integrity),n.referrerPolicy&&(i.referrerPolicy=n.referrerPolicy),n.crossOrigin==="use-credentials"?i.credentials="include":n.crossOrigin==="anonymous"?i.credentials="omit":i.credentials="same-origin",i}function o(n){if(n.ep)return;n.ep=!0;const i=s(n);fetch(n.href,i)}})();/**
* @vue/shared v3.5.42
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/function qs(e){const t=Object.create(null);for(const s of e.split(","))t[s]=1;return s=>s in t}const K={},rt=[],Pe=()=>{},qo=()=>!1,fs=e=>e.charCodeAt(0)===111&&e.charCodeAt(1)===110&&(e.charCodeAt(2)>122||e.charCodeAt(2)<97),ds=e=>e.startsWith("onUpdate:"),ne=Object.assign,zs=(e,t)=>{const s=e.indexOf(t);s>-1&&e.splice(s,1)},ai=Object.prototype.hasOwnProperty,L=(e,t)=>ai.call(e,t),P=Array.isArray,$e=e=>Lt(e)==="[object Map]",ts=e=>Lt(e)==="[object Set]",bo=e=>Lt(e)==="[object Date]",F=e=>typeof e=="function",Q=e=>typeof e=="string",Me=e=>typeof e=="symbol",B=e=>e!==null&&typeof e=="object",zo=e=>(B(e)||F(e))&&F(e.then)&&F(e.catch),Jo=Object.prototype.toString,Lt=e=>Jo.call(e),ui=e=>Lt(e).slice(8,-1),Yo=e=>Lt(e)==="[object Object]",Js=e=>Q(e)&&e!=="NaN"&&e[0]!=="-"&&""+parseInt(e,10)===e,xt=qs(",key,ref,ref_for,ref_key,onVnodeBeforeMount,onVnodeMounted,onVnodeBeforeUpdate,onVnodeUpdated,onVnodeBeforeUnmount,onVnodeUnmounted"),ps=e=>{const t=Object.create(null);return s=>t[s]||(t[s]=e(s))},fi=/-\w/g,ge=ps(e=>e.replace(fi,t=>t.slice(1).toUpperCase())),di=/\B([A-Z])/g,ot=ps(e=>e.replace(di,"-$1").toLowerCase()),Zo=ps(e=>e.charAt(0).toUpperCase()+e.slice(1)),Es=ps(e=>e?`on${Zo(e)}`:""),Ae=(e,t)=>!Object.is(e,t),Os=(e,...t)=>{for(let s=0;s<e.length;s++)e[s](...t)},Xo=(e,t,s,o=!1)=>{Object.defineProperty(e,t,{configurable:!0,enumerable:!1,writable:o,value:s})},pi=e=>{const t=parseFloat(e);return isNaN(t)?e:t};let yo;const hs=()=>yo||(yo=typeof globalThis<"u"?globalThis:typeof self<"u"?self:typeof window<"u"?window:typeof global<"u"?global:{});function Nt(e){if(P(e)){const t={};for(let s=0;s<e.length;s++){const o=e[s],n=Q(o)?_i(o):Nt(o);if(n)for(const i in n)t[i]=n[i]}return t}else if(Q(e)||B(e))return e}const hi=/;(?![^(]*\))/g,gi=/:([^]+)/,mi=/\/\*[^]*?\*\//g;function _i(e){const t={};return e.replace(mi,"").split(hi).forEach(s=>{if(s){const o=s.split(gi);o.length>1&&(t[o[0].trim()]=o[1].trim())}}),t}function jt(e){let t="";if(Q(e))t=e;else if(P(e))for(let s=0;s<e.length;s++){const o=jt(e[s]);o&&(t+=o+" ")}else if(B(e))for(const s in e)e[s]&&(t+=s+" ");return t.trim()}const bi="itemscope,allowfullscreen,formnovalidate,ismap,nomodule,novalidate,readonly",yi=qs(bi);function en(e){return!!e||e===""}function Ti(e,t){if(e.length!==t.length)return!1;let s=!0;for(let o=0;s&&o<e.length;o++)s=gs(e[o],t[o]);return s}function To(e,t){if(e.size!==t.size)return!1;const s=Array.from(t),o=new Uint8Array(s.length);for(const n of e){let i=-1;for(let r=0;r<s.length;r++)if(!o[r]&&gs(n,s[r])){i=r;break}if(i<0)return!1;o[i]=1}return!0}function gs(e,t){if(e===t)return!0;let s=bo(e),o=bo(t);if(s||o)return s&&o?e.getTime()===t.getTime():!1;if(s=Me(e),o=Me(t),s||o)return e===t;if(s=P(e),o=P(t),s||o)return s&&o?Ti(e,t):!1;if(s=B(e),o=B(t),s||o){if(!s||!o)return!1;if(s=$e(e),o=$e(t),s||o||(s=ts(e),o=ts(t),s||o))return s&&o?To(e,t):!1;const n=Object.keys(e).length,i=Object.keys(t).length;if(n!==i)return!1;for(const r in e){const l=e.hasOwnProperty(r),c=t.hasOwnProperty(r);if(l&&!c||!l&&c||!gs(e[r],t[r]))return!1}}return String(e)===String(t)}const tn=e=>!!(e&&e.__v_isRef===!0),te=e=>Q(e)?e:e==null?"":P(e)||B(e)&&(e.toString===Jo||!F(e.toString))?tn(e)?te(e.value):JSON.stringify(e,sn,2):String(e),sn=(e,t)=>tn(t)?sn(e,t.value):$e(t)?{[`Map(${t.size})`]:[...t.entries()].reduce((s,[o,n],i)=>(s[ws(o,i)+" =>"]=n,s),{})}:ts(t)?{[`Set(${t.size})`]:[...t.values()].map(s=>ws(s))}:Me(t)?ws(t):B(t)&&!P(t)&&!Yo(t)?String(t):t,ws=(e,t="")=>{var s;return Me(e)?`Symbol(${(s=e.description)!=null?s:t})`:e};/**
* @vue/reactivity v3.5.42
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/let ee;class Ci{constructor(t=!1){this.detached=t,this._active=!0,this._on=0,this.effects=[],this.cleanups=[],this._isPaused=!1,this._warnOnRun=!0,this.__v_skip=!0,!t&&ee&&(ee.active?(this.parent=ee,this.index=(ee.scopes||(ee.scopes=[])).push(this)-1):(this._active=!1,this._warnOnRun=!1))}get active(){return this._active}pause(){if(this._active){this._isPaused=!0;let t,s;if(this.scopes){const o=this.scopes.slice();for(t=0,s=o.length;t<s;t++)o[t].pause()}for(t=0,s=this.effects.length;t<s;t++)this.effects[t].pause()}}resume(){if(this._active&&this._isPaused){this._isPaused=!1;let t,s;if(this.scopes){const n=this.scopes.slice();for(t=0,s=n.length;t<s;t++)n[t].resume()}const o=this.effects.slice();for(t=0,s=o.length;t<s;t++)o[t].resume()}}run(t){if(this._active){const s=ee;try{return ee=this,t()}finally{ee=s}}}on(){++this._on===1&&(this.prevScope=ee,ee=this)}off(){if(this._on>0&&--this._on===0){if(ee===this)ee=this.prevScope;else{let t=ee;for(;t;){if(t.prevScope===this){t.prevScope=this.prevScope;break}t=t.prevScope}}this.prevScope=void 0}}stop(t){if(this._active){this._active=!1;let s,o;for(s=0,o=this.effects.length;s<o;s++)this.effects[s].stop();for(this.effects.length=0,s=0,o=this.cleanups.length;s<o;s++)this.cleanups[s]();if(this.cleanups.length=0,this.scopes){const n=this.scopes.slice();for(s=0,o=n.length;s<o;s++)n[s].stop(!0);this.scopes.length=0}if(!this.detached&&this.parent&&!t){const n=this.parent.scopes.pop();n&&n!==this&&(this.parent.scopes[this.index]=n,n.index=this.index)}this.parent=void 0}}}function vi(){return ee}let $;const ks=new WeakSet;class on{constructor(t){this.fn=t,this.deps=void 0,this.depsTail=void 0,this.flags=5,this.next=void 0,this.cleanup=void 0,this.scheduler=void 0,ee&&(ee.active?ee.effects.push(this):this.flags&=-2)}pause(){this.flags|=64}resume(){this.flags&64&&(this.flags&=-65,ks.has(this)&&(ks.delete(this),this.trigger()))}notify(){this.flags&2&&!(this.flags&32)||this.flags&8||rn(this)}run(){if(!(this.flags&1))return this.fn();this.flags|=2,Co(this),ln(this);const t=$,s=me;$=this,me=!0;try{return this.fn()}finally{cn(this),$=t,me=s,this.flags&=-3}}stop(){if(this.flags&1){for(let t=this.deps;t;t=t.nextDep)Xs(t);this.deps=this.depsTail=void 0,Co(this),this.onStop&&this.onStop(),this.flags&=-2}}trigger(){this.flags&64?ks.add(this):this.scheduler?this.scheduler():this.runIfDirty()}runIfDirty(){Ls(this)&&this.run()}get dirty(){return Ls(this)}}let nn=0,Et,Ot;function rn(e,t=!1){if(e.flags|=8,t){e.next=Ot,Ot=e;return}e.next=Et,Et=e}function Ys(){nn++}function Zs(){if(--nn>0)return;if(Ot){let t=Ot;for(Ot=void 0;t;){const s=t.next;t.next=void 0,t.flags&=-9,t=s}}let e;for(;Et;){let t=Et;for(Et=void 0;t;){const s=t.next;if(t.next=void 0,t.flags&=-9,t.flags&1)try{t.trigger()}catch(o){e||(e=o)}t=s}}if(e)throw e}function ln(e){for(let t=e.deps;t;t=t.nextDep)t.version=-1,t.prevActiveLink=t.dep.activeLink,t.dep.activeLink=t}function cn(e){let t,s=e.depsTail,o=s;for(;o;){const n=o.prevDep;o.version===-1?(o===s&&(s=n),Xs(o),Si(o)):t=o,o.dep.activeLink=o.prevActiveLink,o.prevActiveLink=void 0,o=n}e.deps=t,e.depsTail=s}function Ls(e){for(let t=e.deps;t;t=t.nextDep)if(t.dep.version!==t.version||t.dep.computed&&(an(t.dep.computed)||t.dep.version!==t.version))return!0;return!!e._dirty}function an(e){if(e.flags&4&&!(e.flags&16)||(e.flags&=-17,e.globalVersion===Mt)||(e.globalVersion=Mt,!e.isSSR&&e.flags&128&&(!e.deps&&!e._dirty||!Ls(e))))return;e.flags|=2;const t=e.dep,s=$,o=me;$=e,me=!0;try{ln(e);const n=e.fn(e._value);(t.version===0||Ae(n,e._value))&&(e.flags|=128,e._value=n,t.version++)}catch(n){throw t.version++,n}finally{$=s,me=o,cn(e),e.flags&=-3}}function Xs(e,t=!1){const{dep:s,prevSub:o,nextSub:n}=e;if(o&&(o.nextSub=n,e.prevSub=void 0),n&&(n.prevSub=o,e.nextSub=void 0),s.subs===e&&(s.subs=o,!o&&s.computed)){s.computed.flags&=-5;for(let i=s.computed.deps;i;i=i.nextDep)Xs(i,!0)}!t&&!--s.sc&&s.map&&s.map.delete(s.key)}function Si(e){const{prevDep:t,nextDep:s}=e;t&&(t.nextDep=s,e.prevDep=void 0),s&&(s.prevDep=t,e.nextDep=void 0)}let me=!0;const un=[];function Ne(){un.push(me),me=!1}function je(){const e=un.pop();me=e===void 0?!0:e}function Co(e){const{cleanup:t}=e;if(e.cleanup=void 0,t){const s=$;$=void 0;try{t()}finally{$=s}}}let Mt=0;class xi{constructor(t,s){this.sub=t,this.dep=s,this.version=s.version,this.nextDep=this.prevDep=this.nextSub=this.prevSub=this.prevActiveLink=void 0}}class eo{constructor(t){this.computed=t,this.version=0,this.activeLink=void 0,this.subs=void 0,this.map=void 0,this.key=void 0,this.sc=0,this.__v_skip=!0}track(t){if(!$||!me||$===this.computed)return;let s=this.activeLink;if(s===void 0||s.sub!==$)s=this.activeLink=new xi($,this),$.deps?(s.prevDep=$.depsTail,$.depsTail.nextDep=s,$.depsTail=s):$.deps=$.depsTail=s,fn(s);else if(s.version===-1&&(s.version=this.version,s.nextDep)){const o=s.nextDep;o.prevDep=s.prevDep,s.prevDep&&(s.prevDep.nextDep=o),s.prevDep=$.depsTail,s.nextDep=void 0,$.depsTail.nextDep=s,$.depsTail=s,$.deps===s&&($.deps=o)}return s}trigger(t){this.version++,Mt++,this.notify(t)}notify(t){Ys();try{for(let s=this.subs;s;s=s.prevSub)s.sub.notify()&&s.sub.dep.notify()}finally{Zs()}}}function fn(e){if(e.dep.sc++,e.sub.flags&4){const t=e.dep.computed;if(t&&!e.dep.subs){t.flags|=20;for(let o=t.deps;o;o=o.nextDep)fn(o)}const s=e.dep.subs;s!==e&&(e.prevSub=s,s&&(s.nextSub=e)),e.dep.subs=e}}const Ns=new WeakMap,Xe=Symbol(""),js=Symbol(""),Ft=Symbol("");function se(e,t,s){if(me&&$){let o=Ns.get(e);o||Ns.set(e,o=new Map);let n=o.get(s);n||(o.set(s,n=new eo),n.map=o,n.key=s),n.track()}}function De(e,t,s,o,n,i){const r=Ns.get(e);if(!r){Mt++;return}const l=c=>{c&&c.trigger()};if(Ys(),t==="clear")r.forEach(l);else{const c=P(e),d=c&&Js(s);if(c&&s==="length"){const f=Number(o);r.forEach((p,T)=>{(T==="length"||T===Ft||!Me(T)&&T>=f)&&l(p)})}else switch((s!==void 0||r.has(void 0))&&l(r.get(s)),d&&l(r.get(Ft)),t){case"add":c?d&&l(r.get("length")):(l(r.get(Xe)),$e(e)&&l(r.get(js)));break;case"delete":c||(l(r.get(Xe)),$e(e)&&l(r.get(js)));break;case"set":$e(e)&&l(r.get(Xe));break}}Zs()}function nt(e){const t=H(e);return t===e?t:(se(t,"iterate",Ft),he(e)?t:t.map(_e))}function ms(e){return se(e=H(e),"iterate",Ft),e}function we(e,t){return Be(e)?dt(et(e)?_e(t):t):_e(t)}const Ei={__proto__:null,[Symbol.iterator](){return As(this,Symbol.iterator,e=>we(this,e))},concat(...e){return nt(this).concat(...e.map(t=>P(t)?nt(t):t))},entries(){return As(this,"entries",e=>(e[1]=we(this,e[1]),e))},every(e,t){return Fe(this,"every",e,t,void 0,arguments)},filter(e,t){return Fe(this,"filter",e,t,s=>s.map(o=>we(this,o)),arguments)},find(e,t){return Fe(this,"find",e,t,s=>we(this,s),arguments)},findIndex(e,t){return Fe(this,"findIndex",e,t,void 0,arguments)},findLast(e,t){return Fe(this,"findLast",e,t,s=>we(this,s),arguments)},findLastIndex(e,t){return Fe(this,"findLastIndex",e,t,void 0,arguments)},forEach(e,t){return Fe(this,"forEach",e,t,void 0,arguments)},includes(...e){return Ps(this,"includes",e)},indexOf(...e){return Ps(this,"indexOf",e)},join(e){return nt(this).join(e)},lastIndexOf(...e){return Ps(this,"lastIndexOf",e)},map(e,t){return Fe(this,"map",e,t,void 0,arguments)},pop(){return bt(this,"pop")},push(...e){return bt(this,"push",e)},reduce(e,...t){return vo(this,"reduce",e,t)},reduceRight(e,...t){return vo(this,"reduceRight",e,t)},shift(){return bt(this,"shift")},some(e,t){return Fe(this,"some",e,t,void 0,arguments)},splice(...e){return bt(this,"splice",e)},toReversed(){return nt(this).toReversed()},toSorted(e){return nt(this).toSorted(e)},toSpliced(...e){return nt(this).toSpliced(...e)},unshift(...e){return bt(this,"unshift",e)},values(){return As(this,"values",e=>we(this,e))}};function As(e,t,s){const o=ms(e),n=o[t]();return o!==e&&!he(e)&&(n._next=n.next,n.next=()=>{const i=n._next();return i.done||(i.value=s(i.value)),i}),n}const Oi=Array.prototype;function Fe(e,t,s,o,n,i){const r=ms(e),l=r!==e&&!he(e),c=r[t];if(c!==Oi[t]){const p=c.apply(e,i);return l?_e(p):p}let d=s;r!==e&&(l?d=function(p,T){return s.call(this,we(e,p),T,e)}:s.length>2&&(d=function(p,T){return s.call(this,p,T,e)}));const f=c.call(r,d,o);return l&&n?n(f):f}function vo(e,t,s,o){const n=ms(e),i=n!==e&&!he(e);let r=s,l=!1;n!==e&&(i?(l=o.length===0,r=function(d,f,p){return l&&(l=!1,d=we(e,d)),s.call(this,d,we(e,f),p,e)}):s.length>3&&(r=function(d,f,p){return s.call(this,d,f,p,e)}));const c=n[t](r,...o);return l?we(e,c):c}function Ps(e,t,s){const o=H(e);se(o,"iterate",Ft);const n=o[t](...s);return(n===-1||n===!1)&&no(s[0])?(s[0]=H(s[0]),o[t](...s)):n}function bt(e,t,s=[]){Ne(),Ys();const o=H(e)[t].apply(e,s);return Zs(),je(),o}const wi=qs("__proto__,__v_isRef,__isVue"),dn=new Set(Object.getOwnPropertyNames(Symbol).filter(e=>e!=="arguments"&&e!=="caller").map(e=>Symbol[e]).filter(Me));function ki(e){Me(e)||(e=String(e));const t=H(this);return se(t,"has",e),t.hasOwnProperty(e)}class pn{constructor(t=!1,s=!1){this._isReadonly=t,this._isShallow=s}get(t,s,o){if(s==="__v_skip")return t.__v_skip;const n=this._isReadonly,i=this._isShallow;if(s==="__v_isReactive")return!n;if(s==="__v_isReadonly")return n;if(s==="__v_isShallow")return i;if(s==="__v_raw")return o===(n?i?Ni:_n:i?mn:gn).get(t)||Object.getPrototypeOf(t)===Object.getPrototypeOf(o)?t:void 0;const r=P(t);if(!n){let c;if(r&&(c=Ei[s]))return c;if(s==="hasOwnProperty")return ki}const l=Reflect.get(t,s,oe(t)?t:o);if((Me(s)?dn.has(s):wi(s))||(n||se(t,"get",s),i))return l;if(oe(l)){const c=r&&Js(s)?l:l.value;return n&&B(c)?Gs(c):c}return B(l)?n?Gs(l):so(l):l}}class hn extends pn{constructor(t=!1){super(!1,t)}set(t,s,o,n){let i=t[s];const r=P(t)&&Js(s);if(!this._isShallow){const d=Be(i);if(!he(o)&&!Be(o)&&(i=H(i),o=H(o)),!r&&oe(i)&&!oe(o))return d||(i.value=o),!0}const l=r?Number(s)<t.length:L(t,s),c=Reflect.set(t,s,o,oe(t)?t:n);return t===H(n)&&c&&(l?Ae(o,i)&&De(t,"set",s,o):De(t,"add",s,o)),c}deleteProperty(t,s){const o=L(t,s);t[s];const n=Reflect.deleteProperty(t,s);return n&&o&&De(t,"delete",s,void 0),n}has(t,s){const o=Reflect.has(t,s);return(!Me(s)||!dn.has(s))&&se(t,"has",s),o}ownKeys(t){return se(t,"iterate",P(t)?"length":Xe),Reflect.ownKeys(t)}}class Ai extends pn{constructor(t=!1){super(!0,t)}set(t,s){return!0}deleteProperty(t,s){return!0}}const Pi=new hn,Mi=new Ai,Fi=new hn(!0);const Bs=e=>e,Qt=e=>Reflect.getPrototypeOf(e);function Ii(e,t,s){return function(...o){const n=this.__v_raw,i=H(n),r=$e(i),l=e==="entries"||e===Symbol.iterator&&r,c=e==="keys"&&r,d=n[e](...o),f=s?Bs:t?dt:_e;return!t&&se(i,"iterate",c?js:Xe),ne(Object.create(d),{next(){const{value:p,done:T}=d.next();return T?{value:p,done:T}:{value:l?[f(p[0]),f(p[1])]:f(p),done:T}}})}}function qt(e){return function(...t){return e==="delete"?!1:e==="clear"?void 0:this}}function Ri(e,t){const s={get(n){const i=this.__v_raw,r=H(i),l=H(n);e||(Ae(n,l)&&se(r,"get",n),se(r,"get",l));const{has:c}=Qt(r),d=t?Bs:e?dt:_e;if(c.call(r,n))return d(i.get(n));if(c.call(r,l))return d(i.get(l));i!==r&&i.get(n)},get size(){const n=this.__v_raw;return!e&&se(H(n),"iterate",Xe),n.size},has(n){const i=this.__v_raw,r=H(i),l=H(n);return e||(Ae(n,l)&&se(r,"has",n),se(r,"has",l)),n===l?i.has(n):i.has(n)||i.has(l)},forEach(n,i){const r=this,l=r.__v_raw,c=H(l),d=t?Bs:e?dt:_e;return!e&&se(c,"iterate",Xe),l.forEach((f,p)=>n.call(i,d(f),d(p),r))}};return ne(s,e?{add:qt("add"),set:qt("set"),delete:qt("delete"),clear:qt("clear")}:{add(n){const i=H(this),r=Qt(i),l=H(n),c=!t&&!he(n)&&!Be(n)?l:n;return r.has.call(i,c)||Ae(n,c)&&r.has.call(i,n)||Ae(l,c)&&r.has.call(i,l)||(i.add(c),De(i,"add",c,c)),this},set(n,i){!t&&!he(i)&&!Be(i)&&(i=H(i));const r=H(this),{has:l,get:c}=Qt(r);let d=l.call(r,n);d||(n=H(n),d=l.call(r,n));const f=c.call(r,n);return r.set(n,i),d?Ae(i,f)&&De(r,"set",n,i):De(r,"add",n,i),this},delete(n){const i=H(this),{has:r,get:l}=Qt(i);let c=r.call(i,n);c||(n=H(n),c=r.call(i,n)),l&&l.call(i,n);const d=i.delete(n);return c&&De(i,"delete",n,void 0),d},clear(){const n=H(this),i=n.size!==0,r=n.clear();return i&&De(n,"clear",void 0,void 0),r}}),["keys","values","entries",Symbol.iterator].forEach(n=>{s[n]=Ii(n,e,t)}),s}function to(e,t){const s=Ri(e,t);return(o,n,i)=>n==="__v_isReactive"?!e:n==="__v_isReadonly"?e:n==="__v_raw"?o:Reflect.get(L(s,n)&&n in o?s:o,n,i)}const Di={get:to(!1,!1)},Hi={get:to(!1,!0)},Li={get:to(!0,!1)};const gn=new WeakMap,mn=new WeakMap,_n=new WeakMap,Ni=new WeakMap;function ji(e){switch(e){case"Object":case"Array":return 1;case"Map":case"Set":case"WeakMap":case"WeakSet":return 2;default:return 0}}function so(e){return Be(e)?e:oo(e,!1,Pi,Di,gn)}function Bi(e){return oo(e,!1,Fi,Hi,mn)}function Gs(e){return oo(e,!0,Mi,Li,_n)}function oo(e,t,s,o,n){if(!B(e)||e.__v_raw&&!(t&&e.__v_isReactive)||e.__v_skip||!Object.isExtensible(e))return e;const i=n.get(e);if(i)return i;const r=ji(ui(e));if(r===0)return e;const l=new Proxy(e,r===2?o:s);return n.set(e,l),l}function et(e){return Be(e)?et(e.__v_raw):!!(e&&e.__v_isReactive)}function Be(e){return!!(e&&e.__v_isReadonly)}function he(e){return!!(e&&e.__v_isShallow)}function no(e){return e?!!e.__v_raw:!1}function H(e){const t=e&&e.__v_raw;return t?H(t):e}function Gi(e){return!L(e,"__v_skip")&&Object.isExtensible(e)&&Xo(e,"__v_skip",!0),e}const _e=e=>B(e)?so(e):e,dt=e=>B(e)?Gs(e):e;function oe(e){return e?e.__v_isRef===!0:!1}function lt(e){return Ki(e,!1)}function Ki(e,t){return oe(e)?e:new Vi(e,t)}class Vi{constructor(t,s){this.dep=new eo,this.__v_isRef=!0,this.__v_isShallow=!1,this._rawValue=s?t:H(t),this._value=s?t:_e(t),this.__v_isShallow=s}get value(){return this.dep.track(),this._value}set value(t){const s=this._rawValue,o=this.__v_isShallow||he(t)||Be(t);t=o?t:H(t),Ae(t,s)&&(this._rawValue=t,this._value=o?t:_e(t),this.dep.trigger())}}function He(e){return oe(e)?e.value:e}const $i={get:(e,t,s)=>t==="__v_raw"?e:He(Reflect.get(e,t,s)),set:(e,t,s,o)=>{const n=e[t];return oe(n)&&!oe(s)?(n.value=s,!0):Reflect.set(e,t,s,o)}};function bn(e){return et(e)?e:new Proxy(e,$i)}class Ui{constructor(t,s,o){this.fn=t,this.setter=s,this._value=void 0,this.dep=new eo(this),this.__v_isRef=!0,this.deps=void 0,this.depsTail=void 0,this.flags=16,this.globalVersion=Mt-1,this.next=void 0,this.effect=this,this.__v_isReadonly=!s,this.isSSR=o}notify(){if(this.flags|=16,!(this.flags&8)&&$!==this)return rn(this,!0),!0}get value(){const t=this.dep.track();return an(this),t&&(t.version=this.dep.version),this._value}set value(t){this.setter&&this.setter(t)}}function Wi(e,t,s=!1){let o,n;return F(e)?o=e:(o=e.get,n=e.set),new Ui(o,n,s)}const zt={},ss=new WeakMap;let Ze;function Qi(e,t=!1,s=Ze){if(s){let o=ss.get(s);o||ss.set(s,o=[]),o.push(e)}}function qi(e,t,s=K){const{immediate:o,deep:n,once:i,scheduler:r,augmentJob:l,call:c}=s,d=k=>n?k:he(k)||n===!1||n===0?Le(k,1):Le(k);let f,p,T,C,I=!1,M=!1;if(oe(e)?(p=()=>e.value,I=he(e)):et(e)?(p=()=>d(e),I=!0):P(e)?(M=!0,I=e.some(k=>et(k)||he(k)),p=()=>e.map(k=>{if(oe(k))return k.value;if(et(k))return d(k);if(F(k))return c?c(k,2):k()})):F(e)?t?p=c?()=>c(e,2):e:p=()=>{if(T){Ne();try{T()}finally{je()}}const k=Ze;Ze=f;try{return c?c(e,3,[C]):e(C)}finally{Ze=k}}:p=Pe,t&&n){const k=p,Y=n===!0?1/0:n;p=()=>Le(k(),Y)}const q=vi(),U=()=>{f.stop(),q&&q.active&&zs(q.effects,f)};if(i&&t){const k=t;t=(...Y)=>{const ye=k(...Y);return U(),ye}}let D=M?new Array(e.length).fill(zt):zt;const N=k=>{if(!(!(f.flags&1)||!f.dirty&&!k))if(t){const Y=f.run();if(k||n||I||(M?Y.some((ye,Te)=>Ae(ye,D[Te])):Ae(Y,D))){T&&T();const ye=Ze;Ze=f;try{const Te=[Y,D===zt?void 0:M&&D[0]===zt?[]:D,C];D=Y,c?c(t,3,Te):t(...Te)}finally{Ze=ye}}}else f.run()};return l&&l(N),f=new on(p),f.scheduler=r?()=>r(N,!1):N,C=k=>Qi(k,!1,f),T=f.onStop=()=>{const k=ss.get(f);if(k){if(c)c(k,4);else for(const Y of k)Y();ss.delete(f)}},t?o?N(!0):D=f.run():r?r(N.bind(null,!0),!0):f.run(),U.pause=f.pause.bind(f),U.resume=f.resume.bind(f),U.stop=U,U}function Le(e,t=1/0,s){if(t<=0||!B(e)||e.__v_skip||(s=s||new Map,(s.get(e)||0)>=t))return e;if(s.set(e,t),t--,oe(e))Le(e.value,t,s);else if(P(e))for(let o=0;o<e.length;o++)Le(e[o],t,s);else if(ts(e)||$e(e))e.forEach(o=>{Le(o,t,s)});else if(Yo(e)){for(const o in e)Le(e[o],t,s);for(const o of Object.getOwnPropertySymbols(e))Object.prototype.propertyIsEnumerable.call(e,o)&&Le(e[o],t,s)}return e}/**
* @vue/runtime-core v3.5.42
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/function Bt(e,t,s,o){try{return o?e(...o):e()}catch(n){_s(n,t,s)}}function be(e,t,s,o){if(F(e)){const n=Bt(e,t,s,o);return n&&zo(n)&&n.catch(i=>{_s(i,t,s)}),n}if(P(e)){const n=[];for(let i=0;i<e.length;i++)n.push(be(e[i],t,s,o));return n}}function _s(e,t,s,o=!0){const n=t?t.vnode:null,{errorHandler:i,throwUnhandledErrorInProduction:r}=t&&t.appContext.config||K;if(t){let l=t.parent;const c=t.proxy,d=`https://vuejs.org/error-reference/#runtime-${s}`;for(;l;){const f=l.ec;if(f){for(let p=0;p<f.length;p++)if(f[p](e,c,d)===!1)return}l=l.parent}if(i){Ne(),Bt(i,null,10,[e,c,d]),je();return}}zi(e,s,n,o,r)}function zi(e,t,s,o=!0,n=!1){if(n)throw e;console.error(e)}const le=[];let Oe=-1;const ct=[];let Ve=null,it=0;const yn=Promise.resolve();let os=null;function Tn(e){const t=os||yn;return e?t.then(this?e.bind(this):e):t}function Ji(e){let t=Oe+1,s=le.length;for(;t<s;){const o=t+s>>>1,n=le[o],i=It(n);i<e||i===e&&n.flags&2?t=o+1:s=o}return t}function io(e){if(!(e.flags&1)){const t=It(e),s=le[le.length-1];!s||!(e.flags&2)&&t>=It(s)?le.push(e):le.splice(Ji(t),0,e),e.flags|=1,Cn()}}function Cn(){os||(os=yn.then(Sn))}function Yi(e){if(!P(e))Ve&&e.id===-1?Ve.splice(it+1,0,e):e.flags&1||(ct.push(e),e.flags|=1);else for(let t=0;t<e.length;t++)ct.push(e[t]);Cn()}function So(e,t,s=Oe+1){for(;s<le.length;s++){const o=le[s];if(o&&o.flags&2){if(e&&o.id!==e.uid)continue;le.splice(s,1),s--,o.flags&4&&(o.flags&=-2),o(),o.flags&4||(o.flags&=-2)}}}function vn(e){if(ct.length){const t=[...new Set(ct)].sort((s,o)=>It(s)-It(o));if(ct.length=0,Ve){for(let s=0;s<t.length;s++)Ve.push(t[s]);return}for(Ve=t,it=0;it<Ve.length;it++){const s=Ve[it];s.flags&4&&(s.flags&=-2),s.flags&8||s(),s.flags&=-2}Ve=null,it=0}}const It=e=>e.id==null?e.flags&2?-1:1/0:e.id;function Sn(e){try{for(Oe=0;Oe<le.length;Oe++){const t=le[Oe];t&&!(t.flags&8)&&(t.flags&4&&(t.flags&=-2),Bt(t,t.i,t.i?15:14),t.flags&4||(t.flags&=-2))}}finally{for(;Oe<le.length;Oe++){const t=le[Oe];t&&(t.flags&=-2)}Oe=-1,le.length=0,vn(),os=null,(le.length||ct.length)&&Sn()}}let pe=null,xn=null;function ns(e){const t=pe;return pe=e,xn=e&&e.type.__scopeId||null,t}function Zi(e,t=pe,s){if(!t||e._n)return e;const o=(...n)=>{o._d&&Ro(-1);const i=ns(t),r=tt.length;let l;try{l=e(...n)}finally{for(let c=tt.length;c>r;c--)zn();ns(i),o._d&&Ro(1)}return l};return o._n=!0,o._c=!0,o._d=!0,o}function Xi(e,t){if(pe===null)return e;const s=vs(pe),o=e.dirs||(e.dirs=[]);for(let n=0;n<t.length;n++){let[i,r,l,c=K]=t[n];i&&(F(i)&&(i={mounted:i,updated:i}),i.deep&&Le(r),o.push({dir:i,instance:s,value:r,oldValue:void 0,arg:l,modifiers:c}))}return e}function ze(e,t,s,o){const n=e.dirs,i=t&&t.dirs;for(let r=0;r<n.length;r++){const l=n[r];i&&(l.oldValue=i[r].value);let c=l.dir[o];c&&(Ne(),be(c,s,8,[e.el,l,e,t]),je())}}function er(e,t){if(ae){let s=ae.provides;const o=ae.parent&&ae.parent.provides;o===s&&(s=ae.provides=Object.create(o)),s[e]=t}}function Yt(e,t,s=!1){const o=zr();if(o||ut){let n=ut?ut._context.provides:o?o.parent==null||o.ce?o.vnode.appContext&&o.vnode.appContext.provides:o.parent.provides:void 0;if(n&&e in n)return n[e];if(arguments.length>1)return s&&F(t)?t.call(o&&o.proxy):t}}const tr=Symbol.for("v-scx"),sr=()=>Yt(tr);function Zt(e,t,s){return En(e,t,s)}function En(e,t,s=K){const{immediate:o,deep:n,flush:i,once:r}=s,l=ne({},s),c=t&&o||!t&&i!=="post";let d;if(Ht){if(i==="sync"){const C=sr();d=C.__watcherHandles||(C.__watcherHandles=[])}else if(!c){const C=()=>{};return C.stop=Pe,C.resume=Pe,C.pause=Pe,C}}const f=ae;l.call=(C,I,M)=>be(C,f,I,M);let p=!1;i==="post"?l.scheduler=C=>{ue(C,f&&f.suspense)}:i!=="sync"&&(p=!0,l.scheduler=(C,I)=>{I?C():io(C)}),l.augmentJob=C=>{t&&(C.flags|=4),p&&(C.flags|=2,f&&(C.id=f.uid,C.i=f))};const T=qi(e,t,l);return Ht&&(d?d.push(T):c&&T()),T}function or(e,t,s){const o=this.proxy,n=Q(e)?e.includes(".")?On(o,e):()=>o[e]:e.bind(o,o);let i;F(t)?i=t:(i=t.handler,s=t);const r=Gt(this),l=En(n,i.bind(o),s);return r(),l}function On(e,t){const s=t.split(".");return()=>{let o=e;for(let n=0;n<s.length&&o;n++)o=o[s[n]];return o}}const nr=Symbol("_vte"),bs=e=>e.__isTeleport,Ms=Symbol("_leaveCb");function ir(e){let t=e[0];if(e.length>1){for(const s of e)if(s.type!==st){t=s;break}}return t}function wn(e){if(!lo(e))return bs(e.type)&&e.children?ir(e.children):e;if(e.component)return e.component.subTree;const{shapeFlag:t,children:s}=e;if(s){if(t&16)return s[0];if(t&32&&F(s.default))return s.default()}}function ro(e,t){if(e.shapeFlag&6&&e.component){e.transition=t;const s=e.component.subTree;ro(bs(s.type)&&wn(s)||s,t)}else e.shapeFlag&128?(e.ssContent.transition=t.clone(e.ssContent),e.ssFallback.transition=t.clone(e.ssFallback)):e.transition=t}function kn(e){e.ids=[e.ids[0]+e.ids[2]+++"-",0,0]}function xo(e,t){let s;return!!((s=Object.getOwnPropertyDescriptor(e,t))&&!s.configurable)}const is=new WeakMap;function wt(e,t,s,o,n=!1){if(P(e)){e.forEach((M,q)=>wt(M,t&&(P(t)?t[q]:t),s,o,n));return}if(kt(o)&&!n){o.shapeFlag&512&&o.type.__asyncResolved&&o.component.subTree.component&&wt(e,t,s,o.component.subTree);return}const i=o.shapeFlag&4?vs(o.component):o.el,r=n?null:i,{i:l,r:c}=e,d=t&&t.r,f=l.refs===K?l.refs={}:l.refs,p=l.setupState,T=H(p),C=p===K?qo:M=>xo(f,M)?!1:L(T,M),I=(M,q)=>!(q&&xo(f,q));if(d!=null&&d!==c){if(Eo(t),Q(d))f[d]=null,C(d)&&(p[d]=null);else if(oe(d)){const M=t;I(d,M.k)&&(d.value=null),M.k&&(f[M.k]=null)}}if(F(c))Bt(c,l,12,[r,f]);else{const M=Q(c),q=oe(c);if(M||q){const U=()=>{if(e.f){const D=M?C(c)?p[c]:f[c]:I()||!e.k?c.value:f[e.k];if(n)P(D)&&zs(D,i);else if(P(D))D.includes(i)||D.push(i);else if(M)f[c]=[i],C(c)&&(p[c]=f[c]);else{const N=[i];I(c,e.k)&&(c.value=N),e.k&&(f[e.k]=N)}}else M?(f[c]=r,C(c)&&(p[c]=r)):q&&(I(c,e.k)&&(c.value=r),e.k&&(f[e.k]=r))};if(r){const D=()=>{U(),is.delete(e)};D.id=-1,is.set(e,D),ue(D,s)}else Eo(e),U()}}}function Eo(e){const t=is.get(e);t&&(t.flags|=8,is.delete(e))}hs().requestIdleCallback;hs().cancelIdleCallback;const kt=e=>!!e.type.__asyncLoader,lo=e=>e.type.__isKeepAlive;function rr(e,t){An(e,"a",t)}function lr(e,t){An(e,"da",t)}function An(e,t,s=ae){const o=e.__wdc||(e.__wdc=()=>{let n=s;for(;n;){if(n.isDeactivated)return;n=n.parent}return e()});if(ys(t,o,s),s){let n=s.parent;for(;n&&n.parent;)lo(n.parent.vnode)&&cr(o,t,s,n),n=n.parent}}function cr(e,t,s,o){const n=ys(t,e,o,!0);Mn(()=>{zs(o[t],n)},s)}function ys(e,t,s=ae,o=!1){if(s){const n=s[e]||(s[e]=[]),i=t.__weh||(t.__weh=(...r)=>{Ne();const l=Gt(s),c=be(t,s,e,r);return l(),je(),c});return o?n.unshift(i):n.push(i),i}}const Ge=e=>(t,s=ae)=>{(!Ht||e==="sp")&&ys(e,(...o)=>t(...o),s)},ar=Ge("bm"),co=Ge("m"),ur=Ge("bu"),fr=Ge("u"),Pn=Ge("bum"),Mn=Ge("um"),dr=Ge("sp"),pr=Ge("rtg"),hr=Ge("rtc");function gr(e,t=ae){ys("ec",e,t)}const mr=Symbol.for("v-ndc");function at(e,t,s,o){let n;const i=s,r=P(e);if(r||Q(e)){const l=r&&et(e);let c=!1,d=!1;l&&(c=!he(e),d=Be(e),e=ms(e)),n=new Array(e.length);for(let f=0,p=e.length;f<p;f++)n[f]=t(c?d?dt(_e(e[f])):_e(e[f]):e[f],f,void 0,i)}else if(typeof e=="number"){n=new Array(e);for(let l=0;l<e;l++)n[l]=t(l+1,l,void 0,i)}else if(B(e))if(e[Symbol.iterator])n=Array.from(e,(l,c)=>t(l,c,void 0,i));else{const l=Object.keys(e);n=new Array(l.length);for(let c=0,d=l.length;c<d;c++){const f=l[c];n[c]=t(e[f],f,c,i)}}else n=[];return n}const Ks=e=>e?Xn(e)?vs(e):Ks(e.parent):null,At=ne(Object.create(null),{$:e=>e,$el:e=>e.vnode.el,$data:e=>e.data,$props:e=>e.props,$attrs:e=>e.attrs,$slots:e=>e.slots,$refs:e=>e.refs,$parent:e=>Ks(e.parent),$root:e=>Ks(e.root),$host:e=>e.ce,$emit:e=>e.emit,$options:e=>In(e),$forceUpdate:e=>e.f||(e.f=()=>{io(e.update)}),$nextTick:e=>e.n||(e.n=Tn.bind(e.proxy)),$watch:e=>or.bind(e)}),Fs=(e,t)=>e!==K&&!e.__isScriptSetup&&L(e,t),_r={get({_:e},t){if(t==="__v_skip")return!0;const{ctx:s,setupState:o,data:n,props:i,accessCache:r,type:l,appContext:c}=e;if(t[0]!=="$"){const T=r[t];if(T!==void 0)switch(T){case 1:return o[t];case 2:return n[t];case 4:return s[t];case 3:return i[t]}else{if(Fs(o,t))return r[t]=1,o[t];if(n!==K&&L(n,t))return r[t]=2,n[t];if(L(i,t))return r[t]=3,i[t];if(s!==K&&L(s,t))return r[t]=4,s[t];Vs&&(r[t]=0)}}const d=At[t];let f,p;if(d)return t==="$attrs"&&se(e.attrs,"get",""),d(e);if((f=l.__cssModules)&&(f=f[t]))return f;if(s!==K&&L(s,t))return r[t]=4,s[t];if(p=c.config.globalProperties,L(p,t))return p[t]},set({_:e},t,s){const{data:o,setupState:n,ctx:i}=e;return Fs(n,t)?(n[t]=s,!0):o!==K&&L(o,t)?(o[t]=s,!0):L(e.props,t)||t[0]==="$"&&t.slice(1)in e?!1:(i[t]=s,!0)},has({_:{data:e,setupState:t,accessCache:s,ctx:o,appContext:n,props:i,type:r}},l){let c;return!!(s[l]||e!==K&&l[0]!=="$"&&L(e,l)||Fs(t,l)||L(i,l)||L(o,l)||L(At,l)||L(n.config.globalProperties,l)||(c=r.__cssModules)&&c[l])},defineProperty(e,t,s){return s.get!=null?e._.accessCache[t]=0:L(s,"value")&&this.set(e,t,s.value,null),Reflect.defineProperty(e,t,s)}};function Oo(e){return P(e)?e.reduce((t,s)=>(t[s]=null,t),{}):e}let Vs=!0;function br(e){const t=In(e),s=e.proxy,o=e.ctx;Vs=!1,t.beforeCreate&&wo(t.beforeCreate,e,"bc");const{data:n,computed:i,methods:r,watch:l,provide:c,inject:d,created:f,beforeMount:p,mounted:T,beforeUpdate:C,updated:I,activated:M,deactivated:q,beforeDestroy:U,beforeUnmount:D,destroyed:N,unmounted:k,render:Y,renderTracked:ye,renderTriggered:Te,errorCaptured:Ke,serverPrefetch:Kt,expose:We,inheritAttrs:ht,components:Vt,directives:$t,filters:Ss}=t;if(d&&yr(d,o,null),r)for(const W in r){const V=r[W];F(V)&&(o[W]=V.bind(s))}if(n){const W=n.call(s,s);B(W)&&(e.data=so(W))}if(Vs=!0,i)for(const W in i){const V=i[W],Qe=F(V)?V.bind(s,s):F(V.get)?V.get.bind(s,s):Pe,Ut=!F(V)&&F(V.set)?V.set.bind(s):Pe,qe=ft({get:Qe,set:Ut});Object.defineProperty(o,W,{enumerable:!0,configurable:!0,get:()=>qe.value,set:Ce=>qe.value=Ce})}if(l)for(const W in l)Fn(l[W],o,s,W);if(c){const W=F(c)?c.call(s):c;Reflect.ownKeys(W).forEach(V=>{er(V,W[V])})}f&&wo(f,e,"c");function ie(W,V){P(V)?V.forEach(Qe=>W(Qe.bind(s))):V&&W(V.bind(s))}if(ie(ar,p),ie(co,T),ie(ur,C),ie(fr,I),ie(rr,M),ie(lr,q),ie(gr,Ke),ie(hr,ye),ie(pr,Te),ie(Pn,D),ie(Mn,k),ie(dr,Kt),P(We))if(We.length){const W=e.exposed||(e.exposed={});We.forEach(V=>{Object.defineProperty(W,V,{get:()=>s[V],set:Qe=>s[V]=Qe,enumerable:!0})})}else e.exposed||(e.exposed={});Y&&e.render===Pe&&(e.render=Y),ht!=null&&(e.inheritAttrs=ht),Vt&&(e.components=Vt),$t&&(e.directives=$t),Kt&&kn(e)}function yr(e,t,s=Pe){P(e)&&(e=$s(e));for(const o in e){const n=e[o];let i;B(n)?"default"in n?i=Yt(n.from||o,n.default,!0):i=Yt(n.from||o):i=Yt(n),oe(i)?Object.defineProperty(t,o,{enumerable:!0,configurable:!0,get:()=>i.value,set:r=>i.value=r}):t[o]=i}}function wo(e,t,s){be(P(e)?e.map(o=>o.bind(t.proxy)):e.bind(t.proxy),t,s)}function Fn(e,t,s,o){let n=o.includes(".")?On(s,o):()=>s[o];if(Q(e)){const i=t[e];F(i)&&Zt(n,i)}else if(F(e))Zt(n,e.bind(s));else if(B(e))if(P(e))e.forEach(i=>Fn(i,t,s,o));else{const i=F(e.handler)?e.handler.bind(s):t[e.handler];F(i)&&Zt(n,i,e)}}function In(e){const t=e.type,{mixins:s,extends:o}=t,{mixins:n,optionsCache:i,config:{optionMergeStrategies:r}}=e.appContext,l=i.get(t);let c;return l?c=l:!n.length&&!s&&!o?c=t:(c={},n.length&&n.forEach(d=>rs(c,d,r,!0)),rs(c,t,r)),B(t)&&i.set(t,c),c}function rs(e,t,s,o=!1){const{mixins:n,extends:i}=t;i&&rs(e,i,s,!0),n&&n.forEach(r=>rs(e,r,s,!0));for(const r in t)if(!(o&&r==="expose")){const l=Tr[r]||s&&s[r];e[r]=l?l(e[r],t[r]):t[r]}return e}const Tr={data:ko,props:Ao,emits:Ao,methods:Ct,computed:Ct,beforeCreate:re,created:re,beforeMount:re,mounted:re,beforeUpdate:re,updated:re,beforeDestroy:re,beforeUnmount:re,destroyed:re,unmounted:re,activated:re,deactivated:re,errorCaptured:re,serverPrefetch:re,components:Ct,directives:Ct,watch:vr,provide:ko,inject:Cr};function ko(e,t){return t?e?function(){return ne(F(e)?e.call(this,this):e,F(t)?t.call(this,this):t)}:t:e}function Cr(e,t){return Ct($s(e),$s(t))}function $s(e){if(P(e)){const t={};for(let s=0;s<e.length;s++)t[e[s]]=e[s];return t}return e}function re(e,t){return e?[...new Set([].concat(e,t))]:t}function Ct(e,t){return e?ne(Object.create(null),e,t):t}function Ao(e,t){return e?P(e)&&P(t)?[...new Set([...e,...t])]:ne(Object.create(null),Oo(e),Oo(t??{})):t}function vr(e,t){if(!e)return t;if(!t)return e;const s=ne(Object.create(null),e);for(const o in t)s[o]=re(e[o],t[o]);return s}function Rn(){return{app:null,config:{isNativeTag:qo,performance:!1,globalProperties:{},optionMergeStrategies:{},errorHandler:void 0,warnHandler:void 0,compilerOptions:{}},mixins:[],components:{},directives:{},provides:Object.create(null),optionsCache:new WeakMap,propsCache:new WeakMap,emitsCache:new WeakMap}}let Sr=0;function xr(e,t){return function(o,n=null){F(o)||(o=ne({},o)),n!=null&&!B(n)&&(n=null);const i=Rn(),r=new WeakSet,l=[];let c=!1;const d=i.app={_uid:Sr++,_component:o,_props:n,_container:null,_context:i,_instance:null,version:tl,get config(){return i.config},set config(f){},use(f,...p){return r.has(f)||(f&&F(f.install)?(r.add(f),f.install(d,...p)):F(f)&&(r.add(f),f(d,...p))),d},mixin(f){return i.mixins.includes(f)||i.mixins.push(f),d},component(f,p){return p?(i.components[f]=p,d):i.components[f]},directive(f,p){return p?(i.directives[f]=p,d):i.directives[f]},mount(f,p,T){if(!c){const C=d._ceVNode||Ue(o,n);return C.appContext=i,T===!0?T="svg":T===!1&&(T=void 0),e(C,f,T),c=!0,d._container=f,f.__vue_app__=d,vs(C.component)}},onUnmount(f){l.push(f)},unmount(){c&&(be(l,d._instance,16),e(null,d._container),delete d._container.__vue_app__)},provide(f,p){return i.provides[f]=p,d},runWithContext(f){const p=ut;ut=d;try{return f()}finally{ut=p}}};return d}}let ut=null;const Er=(e,t)=>t==="modelValue"||t==="model-value"?e.modelModifiers:e[`${t}Modifiers`]||e[`${ge(t)}Modifiers`]||e[`${ot(t)}Modifiers`];function Or(e,t,...s){if(e.isUnmounted)return;const o=e.vnode.props||K;let n=s;const i=t.startsWith("update:"),r=i&&Er(o,t.slice(7));r&&(r.trim&&(n=s.map(f=>Q(f)?f.trim():f)),r.number&&(n=n.map(pi)));let l,c=o[l=Es(t)]||o[l=Es(ge(t))];!c&&i&&(c=o[l=Es(ot(t))]),c&&be(c,e,6,n);const d=o[l+"Once"];if(d){if(!e.emitted)e.emitted={};else if(e.emitted[l])return;e.emitted[l]=!0,be(d,e,6,n)}}const wr=new WeakMap;function Dn(e,t,s=!1){const o=s?wr:t.emitsCache,n=o.get(e);if(n!==void 0)return n;const i=e.emits;let r={},l=!1;if(!F(e)){const c=d=>{const f=Dn(d,t,!0);f&&(l=!0,ne(r,f))};!s&&t.mixins.length&&t.mixins.forEach(c),e.extends&&c(e.extends),e.mixins&&e.mixins.forEach(c)}return!i&&!l?(B(e)&&o.set(e,null),null):(P(i)?i.forEach(c=>r[c]=null):ne(r,i),B(e)&&o.set(e,r),r)}function Ts(e,t){return!e||!fs(t)?!1:(t=t.slice(2),t=t==="Once"?t:t.replace(/Once$/,""),L(e,t[0].toLowerCase()+t.slice(1))||L(e,ot(t))||L(e,t))}function Po(e){const{type:t,vnode:s,proxy:o,withProxy:n,propsOptions:[i],slots:r,attrs:l,emit:c,render:d,renderCache:f,props:p,data:T,setupState:C,ctx:I,inheritAttrs:M}=e,q=ns(e);let U,D;try{if(s.shapeFlag&4){const k=n||o,Y=k;U=ke(d.call(Y,k,f,p,C,T,I)),D=l}else{const k=t;U=ke(k.length>1?k(p,{attrs:l,slots:r,emit:c}):k(p,null)),D=t.props?l:kr(l)}}catch(k){tt.length=0,_s(k,e,1),U=Ue(st)}let N=U;if(D&&M!==!1){const k=Object.keys(D),{shapeFlag:Y}=N;k.length&&Y&7&&(i&&k.some(ds)&&(D=Ar(D,i)),N=pt(N,D,!1,!0))}if(s.dirs&&(N=pt(N,null,!1,!0),N.dirs=N.dirs?N.dirs.concat(s.dirs):s.dirs),s.transition){const k=bs(N.type)&&wn(N)||N;ro(k,s.transition)}return U=N,ns(q),U}const kr=e=>{let t;for(const s in e)(s==="class"||s==="style"||fs(s))&&((t||(t={}))[s]=e[s]);return t},Ar=(e,t)=>{const s={};for(const o in e)(!ds(o)||!(o.slice(9)in t))&&(s[o]=e[o]);return s};function Pr(e,t,s){const{props:o,children:n,component:i}=e,{props:r,children:l,patchFlag:c}=t,d=i.emitsOptions;if(t.dirs||t.transition)return!0;if(s&&c>=0){if(c&1024)return!0;if(c&16)return o?Mo(o,r,d):!!r;if(c&8){const f=t.dynamicProps;for(let p=0;p<f.length;p++){const T=f[p];if(Hn(r,o,T)&&!Ts(d,T))return!0}}}else return(n||l)&&(!l||!l.$stable)?!0:o===r?!1:o?r?Mo(o,r,d):!0:!!r;return!1}function Mo(e,t,s){const o=Object.keys(t);if(o.length!==Object.keys(e).length)return!0;for(let n=0;n<o.length;n++){const i=o[n];if(Hn(t,e,i)&&!Ts(s,i))return!0}return!1}function Hn(e,t,s){const o=e[s],n=t[s];return s==="style"&&B(o)&&B(n)?!gs(o,n):o!==n}function Mr({vnode:e,parent:t,suspense:s},o){for(;t;){const n=t.subTree;if(n.suspense&&n.suspense.activeBranch===e&&(n.suspense.vnode.el=n.el=o,e=n),n===e)(e=t.vnode).el=o,t=t.parent;else break}s&&s.activeBranch===e&&(s.vnode.el=o)}const Ln={},Nn=()=>Object.create(Ln),jn=e=>Object.getPrototypeOf(e)===Ln;function Fr(e,t,s,o=!1){const n={},i=Nn();e.propsDefaults=Object.create(null),Bn(e,t,n,i);for(const r in e.propsOptions[0])r in n||(n[r]=void 0);s?e.props=o?n:Bi(n):e.type.props?e.props=n:e.props=i,e.attrs=i}function Ir(e,t,s,o){const{props:n,attrs:i,vnode:{patchFlag:r}}=e,l=H(n),[c]=e.propsOptions;let d=!1;if((o||r>0)&&!(r&16)){if(r&8){const f=e.vnode.dynamicProps;for(let p=0;p<f.length;p++){let T=f[p];if(Ts(e.emitsOptions,T))continue;const C=t[T];if(c)if(L(i,T))C!==i[T]&&(i[T]=C,d=!0);else{const I=ge(T);n[I]=Us(c,l,I,C,e,!1)}else C!==i[T]&&(i[T]=C,d=!0)}}}else{Bn(e,t,n,i)&&(d=!0);let f;for(const p in l)(!t||!L(t,p)&&((f=ot(p))===p||!L(t,f)))&&(c?s&&(s[p]!==void 0||s[f]!==void 0)&&(n[p]=Us(c,l,p,void 0,e,!0)):delete n[p]);if(i!==l)for(const p in i)(!t||!L(t,p))&&(delete i[p],d=!0)}d&&De(e.attrs,"set","")}function Bn(e,t,s,o){const[n,i]=e.propsOptions;let r=!1,l;if(t)for(let c in t){if(xt(c))continue;const d=t[c];let f;n&&L(n,f=ge(c))?!i||!i.includes(f)?s[f]=d:(l||(l={}))[f]=d:Ts(e.emitsOptions,c)||(!(c in o)||d!==o[c])&&(o[c]=d,r=!0)}if(i){const c=H(s),d=l||K;for(let f=0;f<i.length;f++){const p=i[f];s[p]=Us(n,c,p,d[p],e,!L(d,p))}}return r}function Us(e,t,s,o,n,i){const r=e[s];if(r!=null){const l=L(r,"default");if(l&&o===void 0){const c=r.default;if(r.type!==Function&&!r.skipFactory&&F(c)){const{propsDefaults:d}=n;if(s in d)o=d[s];else{const f=Gt(n);o=d[s]=c.call(null,t),f()}}else o=c;n.ce&&n.ce._setProp(s,o)}r[0]&&(i&&!l?o=!1:r[1]&&(o===""||o===ot(s))&&(o=!0))}return o}const Rr=new WeakMap;function Gn(e,t,s=!1){const o=s?Rr:t.propsCache,n=o.get(e);if(n)return n;const i=e.props,r={},l=[];let c=!1;if(!F(e)){const f=p=>{c=!0;const[T,C]=Gn(p,t,!0);ne(r,T),C&&l.push(...C)};!s&&t.mixins.length&&t.mixins.forEach(f),e.extends&&f(e.extends),e.mixins&&e.mixins.forEach(f)}if(!i&&!c)return B(e)&&o.set(e,rt),rt;if(P(i))for(let f=0;f<i.length;f++){const p=ge(i[f]);Fo(p)&&(r[p]=K)}else if(i)for(const f in i){const p=ge(f);if(Fo(p)){const T=i[f],C=r[p]=P(T)||F(T)?{type:T}:ne({},T),I=C.type;let M=!1,q=!0;if(P(I))for(let U=0;U<I.length;++U){const D=I[U],N=F(D)&&D.name;if(N==="Boolean"){M=!0;break}else N==="String"&&(q=!1)}else M=F(I)&&I.name==="Boolean";C[0]=M,C[1]=q,(M||L(C,"default"))&&l.push(p)}}const d=[r,l];return B(e)&&o.set(e,d),d}function Fo(e){return e[0]!=="$"&&!xt(e)}const ao=e=>e==="_"||e==="_ctx"||e==="$stable",uo=e=>P(e)?e.map(ke):[ke(e)],Dr=(e,t,s)=>{if(t._n)return t;const o=Zi((...n)=>uo(t(...n)),s);return o._c=!1,o},Kn=(e,t,s)=>{const o=e._ctx;for(const n in e){if(ao(n))continue;const i=e[n];if(F(i))t[n]=Dr(n,i,o);else if(i!=null){const r=uo(i);t[n]=()=>r}}},Vn=(e,t)=>{const s=uo(t);e.slots.default=()=>s},$n=(e,t,s)=>{for(const o in t)(s||!ao(o))&&(e[o]=t[o])},Hr=(e,t,s)=>{const o=e.slots=Nn();if(e.vnode.shapeFlag&32){const n=t._;n?($n(o,t,s),s&&Xo(o,"_",n,!0)):Kn(t,o)}else t&&Vn(e,t)},Lr=(e,t,s)=>{const{vnode:o,slots:n}=e;let i=!0,r=K;if(o.shapeFlag&32){const l=t._;l?s&&l===1?i=!1:$n(n,t,s):(i=!t.$stable,Kn(t,n)),r=t}else t&&(Vn(e,t),r={default:1});if(i)for(const l in n)!ao(l)&&r[l]==null&&delete n[l]},ue=Kr;function Nr(e){return jr(e)}function jr(e,t){const s=hs();s.__VUE__=!0;const{insert:o,remove:n,patchProp:i,createElement:r,createText:l,createComment:c,setText:d,setElementText:f,parentNode:p,nextSibling:T,setScopeId:C=Pe,insertStaticContent:I}=e,M=(a,u,h,b=null,_=null,g=null,S=void 0,v=null,y=!!u.dynamicChildren)=>{if(a===u)return;a&&!yt(a,u)&&(b=Wt(a),Ce(a,_,g,!0),a=null),u.patchFlag===-2&&(y=!1,u.dynamicChildren=null);const{type:m,ref:w,shapeFlag:x}=u;switch(m){case Cs:q(a,u,h,b);break;case st:U(a,u,h,b);break;case Rs:a==null&&D(u,h,b,S);break;case ce:Vt(a,u,h,b,_,g,S,v,y);break;default:x&1?Y(a,u,h,b,_,g,S,v,y):x&6?$t(a,u,h,b,_,g,S,v,y):(x&64||x&128)&&m.process(a,u,h,b,_,g,S,v,y,mt)}w!=null&&_?wt(w,a&&a.ref,g,u||a,!u):w==null&&a&&a.ref!=null&&wt(a.ref,null,g,a,!0)},q=(a,u,h,b)=>{if(a==null)o(u.el=l(u.children),h,b);else{const _=u.el=a.el;u.children!==a.children&&d(_,u.children)}},U=(a,u,h,b)=>{a==null?o(u.el=c(u.children||""),h,b):u.el=a.el},D=(a,u,h,b)=>{[a.el,a.anchor]=I(a.children,u,h,b,a.el,a.anchor)},N=({el:a,anchor:u},h,b)=>{let _;for(;a&&a!==u;)_=T(a),o(a,h,b),a=_;o(u,h,b)},k=({el:a,anchor:u})=>{let h;for(;a&&a!==u;)h=T(a),n(a),a=h;n(u)},Y=(a,u,h,b,_,g,S,v,y)=>{if(u.type==="svg"?S="svg":u.type==="math"&&(S="mathml"),a==null)ye(u,h,b,_,g,S,v,y);else{const m=a.el&&a.el._isVueCE?a.el:null;try{m&&m._beginPatch(),Kt(a,u,_,g,S,v,y)}finally{m&&m._endPatch()}}},ye=(a,u,h,b,_,g,S,v)=>{let y,m;const{props:w,shapeFlag:x,transition:E,dirs:A}=a;if(y=a.el=r(a.type,g,w&&w.is,w),x&8?f(y,a.children):x&16&&Ke(a.children,y,null,b,_,Is(a,g),S,v),A&&ze(a,null,b,"created"),Te(y,a,a.scopeId,S,b),w){for(const G in w)G!=="value"&&!xt(G)&&i(y,G,null,w[G],g,b);"value"in w&&i(y,"value",null,w.value,g),(m=w.onVnodeBeforeMount)&&Ee(m,b,a)}A&&ze(a,null,b,"beforeMount");const R=Br(_,E);R&&E.beforeEnter(y),o(y,u,h),((m=w&&w.onVnodeMounted)||R||A)&&ue(()=>{try{m&&Ee(m,b,a),R&&E.enter(y),A&&ze(a,null,b,"mounted")}finally{}},_)},Te=(a,u,h,b,_)=>{if(h&&C(a,h),b)for(let g=0;g<b.length;g++)C(a,b[g]);if(_){let g=_.subTree;if(u===g||qn(g.type)&&(g.ssContent===u||g.ssFallback===u)){const S=_.vnode;Te(a,S,S.scopeId,S.slotScopeIds,_.parent)}}},Ke=(a,u,h,b,_,g,S,v,y=0)=>{for(let m=y;m<a.length;m++){const w=a[m]=v?Re(a[m]):ke(a[m]);M(null,w,u,h,b,_,g,S,v)}},Kt=(a,u,h,b,_,g,S)=>{const v=u.el=a.el;let{patchFlag:y,dynamicChildren:m,dirs:w}=u;y|=a.patchFlag&16;const x=a.props||K,E=u.props||K;let A;if(h&&Je(h,!1),(A=E.onVnodeBeforeUpdate)&&Ee(A,h,u,a),w&&ze(u,a,h,"beforeUpdate"),h&&Je(h,!0),m&&(!a.dynamicChildren||a.dynamicChildren.length!==m.length)&&(y=0,S=!1,m=null),(x.innerHTML&&E.innerHTML==null||x.textContent&&E.textContent==null)&&f(v,""),m?We(a.dynamicChildren,m,v,h,b,Is(u,_),g):S||V(a,u,v,null,h,b,Is(u,_),g,!1),y>0){if(y&16)ht(v,x,E,h,_);else if(y&2&&x.class!==E.class&&i(v,"class",null,E.class,_),y&4&&i(v,"style",x.style,E.style,_),y&8){const R=u.dynamicProps;for(let G=0;G<R.length;G++){const j=R[G],z=x[j],X=E[j];(X!==z||j==="value")&&i(v,j,z,X,_,h)}}y&1&&a.children!==u.children&&f(v,u.children)}else!S&&m==null&&ht(v,x,E,h,_);((A=E.onVnodeUpdated)||w)&&ue(()=>{A&&Ee(A,h,u,a),w&&ze(u,a,h,"updated")},b)},We=(a,u,h,b,_,g,S)=>{for(let v=0;v<u.length;v++){const y=a[v],m=u[v],w=y.el&&(y.type===ce||!yt(y,m)||y.shapeFlag&198)?p(y.el):h;M(y,m,w,null,b,_,g,S,!0)}},ht=(a,u,h,b,_)=>{if(u!==h){if(u!==K)for(const g in u)!xt(g)&&!(g in h)&&i(a,g,u[g],null,_,b);for(const g in h){if(xt(g))continue;const S=h[g],v=u[g];S!==v&&g!=="value"&&i(a,g,v,S,_,b)}"value"in h&&i(a,"value",u.value,h.value,_)}},Vt=(a,u,h,b,_,g,S,v,y)=>{const m=u.el=a?a.el:l(""),w=u.anchor=a?a.anchor:l("");let{patchFlag:x,dynamicChildren:E,slotScopeIds:A}=u;A&&(v=v?v.concat(A):A),a==null?(o(m,h,b),o(w,h,b),Ke(u.children||[],h,w,_,g,S,v,y)):x>0&&x&64&&E&&a.dynamicChildren&&a.dynamicChildren.length===E.length?(We(a.dynamicChildren,E,h,_,g,S,v),(u.key!=null||_&&u===_.subTree)&&Un(a,u,!0)):V(a,u,h,w,_,g,S,v,y)},$t=(a,u,h,b,_,g,S,v,y)=>{u.slotScopeIds=v,a==null?u.shapeFlag&512?_.ctx.activate(u,h,b,S,y):Ss(u,h,b,_,g,S,y):fo(a,u,y)},Ss=(a,u,h,b,_,g,S)=>{const v=a.component=qr(a,b,_);if(lo(a)&&(v.ctx.renderer=mt),Jr(v,!1,S),v.asyncDep){if(_&&_.registerDep(v,ie,S),!a.el){const y=v.subTree=Ue(st);U(null,y,u,h),a.placeholder=y.el}}else ie(v,a,u,h,_,g,S)},fo=(a,u,h)=>{const b=u.component=a.component;if(Pr(a,u,h))if(b.asyncDep&&!b.asyncResolved){W(b,u,h);return}else b.next=u,b.update();else u.el=a.el,b.vnode=u},ie=(a,u,h,b,_,g,S)=>{const v=()=>{if(a.isMounted){let{next:x,bu:E,u:A,parent:R,vnode:G}=a;{const Se=Wn(a);if(Se){x&&(x.el=G.el,W(a,x,S)),Se.asyncDep.then(()=>{ue(()=>{a.isUnmounted||m()},_)});return}}let j=x,z;Je(a,!1),x?(x.el=G.el,W(a,x,S)):x=G,E&&Os(E),(z=x.props&&x.props.onVnodeBeforeUpdate)&&Ee(z,R,x,G),Je(a,!0);const X=Po(a),ve=a.subTree;a.subTree=X,M(ve,X,p(ve.el),Wt(ve),a,_,g),x.el=X.el,j===null&&Mr(a,X.el),A&&ue(A,_),(z=x.props&&x.props.onVnodeUpdated)&&ue(()=>Ee(z,R,x,G),_)}else{let x;const{el:E,props:A}=u,{bm:R,m:G,parent:j,root:z,type:X}=a,ve=kt(u);Je(a,!1),R&&Os(R),!ve&&(x=A&&A.onVnodeBeforeMount)&&Ee(x,j,u),Je(a,!0);{z.ce&&z.ce._hasShadowRoot()&&z.ce._injectChildStyle(X,a.parent?a.parent.type:void 0);const Se=a.subTree=Po(a);M(null,Se,h,b,a,_,g),u.el=Se.el}if(G&&ue(G,_),!ve&&(x=A&&A.onVnodeMounted)){const Se=u;ue(()=>Ee(x,j,Se),_)}(u.shapeFlag&256||j&&kt(j.vnode)&&j.vnode.shapeFlag&256)&&a.a&&ue(a.a,_),a.isMounted=!0,u=h=b=null}};a.scope.on();const y=a.effect=new on(v);a.scope.off();const m=a.update=y.run.bind(y),w=a.job=y.runIfDirty.bind(y);w.i=a,w.id=a.uid,y.scheduler=()=>io(w),Je(a,!0),m()},W=(a,u,h)=>{u.component=a;const b=a.vnode.props;a.vnode=u,a.next=null,Ir(a,u.props,b,h),Lr(a,u.children,h),Ne(),So(a),je()},V=(a,u,h,b,_,g,S,v,y=!1)=>{const m=a&&a.children,w=a?a.shapeFlag:0,x=u.children,{patchFlag:E,shapeFlag:A}=u;if(E>0){if(E&128){Ut(m,x,h,b,_,g,S,v,y);return}else if(E&256){Qe(m,x,h,b,_,g,S,v,y);return}}A&8?(w&16&&gt(m,_,g),x!==m&&f(h,x)):w&16?A&16?Ut(m,x,h,b,_,g,S,v,y):gt(m,_,g,!0):(w&8&&f(h,""),A&16&&Ke(x,h,b,_,g,S,v,y))},Qe=(a,u,h,b,_,g,S,v,y)=>{a=a||rt,u=u||rt;const m=a.length,w=u.length,x=Math.min(m,w);let E;for(E=0;E<x;E++){const A=u[E]=y?Re(u[E]):ke(u[E]);M(a[E],A,h,null,_,g,S,v,y)}m>w?gt(a,_,g,!0,!1,x):Ke(u,h,b,_,g,S,v,y,x)},Ut=(a,u,h,b,_,g,S,v,y)=>{let m=0;const w=u.length;let x=a.length-1,E=w-1;for(;m<=x&&m<=E;){const A=a[m],R=u[m]=y?Re(u[m]):ke(u[m]);if(yt(A,R))M(A,R,h,null,_,g,S,v,y);else break;m++}for(;m<=x&&m<=E;){const A=a[x],R=u[E]=y?Re(u[E]):ke(u[E]);if(yt(A,R))M(A,R,h,null,_,g,S,v,y);else break;x--,E--}if(m>x){if(m<=E){const A=E+1,R=A<w?u[A].el:b;for(;m<=E;)M(null,u[m]=y?Re(u[m]):ke(u[m]),h,R,_,g,S,v,y),m++}}else if(m>E)for(;m<=x;)Ce(a[m],_,g,!0),m++;else{const A=m,R=m,G=new Map;for(m=R;m<=E;m++){const fe=u[m]=y?Re(u[m]):ke(u[m]);fe.key!=null&&G.set(fe.key,m)}let j,z=0;const X=E-R+1;let ve=!1,Se=0;const _t=new Array(X);for(m=0;m<X;m++)_t[m]=0;for(m=A;m<=x;m++){const fe=a[m];if(z>=X){Ce(fe,_,g,!0);continue}let xe;if(fe.key!=null)xe=G.get(fe.key);else for(j=R;j<=E;j++)if(_t[j-R]===0&&yt(fe,u[j])){xe=j;break}xe===void 0?Ce(fe,_,g,!0):(_t[xe-R]=m+1,xe>=Se?Se=xe:ve=!0,M(fe,u[xe],h,null,_,g,S,v,y),z++)}const go=ve?Gr(_t):rt;for(j=go.length-1,m=X-1;m>=0;m--){const fe=R+m,xe=u[fe],mo=u[fe+1],_o=fe+1<w?mo.el||Qn(mo):b;_t[m]===0?M(null,xe,h,_o,_,g,S,v,y):ve&&(j<0||m!==go[j]?qe(xe,h,_o,2):j--)}}},qe=(a,u,h,b,_=null)=>{const{el:g,type:S,transition:v,children:y,shapeFlag:m}=a;if(m&6){qe(a.component.subTree,u,h,b);return}if(m&128){a.suspense.move(u,h,b);return}if(m&64){S.move(a,u,h,mt);return}if(S===ce){o(g,u,h);for(let x=0;x<y.length;x++)qe(y[x],u,h,b);o(a.anchor,u,h);return}if(S===Rs){N(a,u,h);return}if(b!==2&&m&1&&v)if(b===0)v.persisted&&!g[Ms]?o(g,u,h):(v.beforeEnter(g),o(g,u,h),ue(()=>v.enter(g),_));else{const{leave:x,delayLeave:E,afterLeave:A}=v,R=()=>{a.ctx.isUnmounted?n(g):o(g,u,h)},G=()=>{const j=g._isLeaving||!!g[Ms];g._isLeaving&&g[Ms](!0),v.persisted&&!j?R():x(g,()=>{R(),A&&A()})};E?E(g,R,G):G()}else o(g,u,h)},Ce=(a,u,h,b=!1,_=!1)=>{const{type:g,props:S,ref:v,children:y,dynamicChildren:m,shapeFlag:w,patchFlag:x,dirs:E,cacheIndex:A,memo:R}=a;if(x===-2&&(_=!1),v!=null&&(Ne(),wt(v,null,h,a,!0),je()),A!=null&&(u.renderCache[A]=void 0),w&256){u.ctx.deactivate(a);return}const G=w&1&&E,j=!kt(a);let z;if(j&&(z=S&&S.onVnodeBeforeUnmount)&&Ee(z,u,a),w&6)ci(a.component,h,b);else{if(w&128){a.suspense.unmount(h,b);return}G&&ze(a,null,u,"beforeUnmount"),w&64?a.type.remove(a,u,h,mt,b):m&&!m.hasOnce&&(g!==ce||x>0&&x&64)?gt(m,u,h,!1,!0):(g===ce&&x&384||!_&&w&16)&&gt(y,u,h),b&&po(a)}const X=R!=null&&A==null;(j&&(z=S&&S.onVnodeUnmounted)||G||X)&&ue(()=>{z&&Ee(z,u,a),G&&ze(a,null,u,"unmounted"),X&&(a.el=null)},h)},po=a=>{const{type:u,el:h,anchor:b,transition:_}=a;if(u===ce){li(h,b);return}if(u===Rs){k(a);return}const g=()=>{n(h),_&&!_.persisted&&_.afterLeave&&_.afterLeave()};if(a.shapeFlag&1&&_&&!_.persisted){const{leave:S,delayLeave:v}=_,y=()=>S(h,g);v?v(a.el,g,y):y()}else g()},li=(a,u)=>{let h;for(;a!==u;)h=T(a),n(a),a=h;n(u)},ci=(a,u,h)=>{const{bum:b,scope:_,job:g,subTree:S,um:v,m:y,a:m}=a;Io(y),Io(m),b&&Os(b),_.stop(),g&&(g.flags|=8,Ce(S,a,u,h)),v&&ue(v,u),ue(()=>{a.isUnmounted=!0},u)},gt=(a,u,h,b=!1,_=!1,g=0)=>{for(let S=g;S<a.length;S++)Ce(a[S],u,h,b,_)},Wt=a=>{if(a.shapeFlag&6)return Wt(a.component.subTree);if(a.shapeFlag&128)return a.suspense.next();const u=T(a.anchor||a.el),h=u&&u[nr];return h?T(h):u};let xs=!1;const ho=(a,u,h)=>{let b;a==null?u._vnode&&(Ce(u._vnode,null,null,!0),b=u._vnode.component):M(u._vnode||null,a,u,null,null,null,h),u._vnode=a,xs||(xs=!0,So(b),vn(),xs=!1)},mt={p:M,um:Ce,m:qe,r:po,mt:Ss,mc:Ke,pc:V,pbc:We,n:Wt,o:e};return{render:ho,hydrate:void 0,createApp:xr(ho)}}function Is({type:e,props:t},s){return s==="svg"&&e==="foreignObject"||s==="mathml"&&e==="annotation-xml"&&t&&t.encoding&&t.encoding.includes("html")?void 0:s}function Je({effect:e,job:t},s){s?(e.flags|=32,t.flags|=4):(e.flags&=-33,t.flags&=-5)}function Br(e,t){return(!e||e&&!e.pendingBranch)&&t&&!t.persisted}function Un(e,t,s=!1){const o=e.children,n=t.children;if(P(o)&&P(n))for(let i=0;i<o.length;i++){const r=o[i];let l=n[i];l.shapeFlag&1&&!l.dynamicChildren&&((l.patchFlag<=0||l.patchFlag===32)&&(l=n[i]=Re(n[i]),l.el=r.el),!s&&l.patchFlag!==-2&&Un(r,l)),l.type===Cs&&(l.patchFlag===-1&&(l=n[i]=Re(l)),l.el=r.el),l.type===st&&!l.el&&(l.el=r.el)}}function Gr(e){const t=e.slice(),s=[0];let o,n,i,r,l;const c=e.length;for(o=0;o<c;o++){const d=e[o];if(d!==0){if(n=s[s.length-1],e[n]<d){t[o]=n,s.push(o);continue}for(i=0,r=s.length-1;i<r;)l=i+r>>1,e[s[l]]<d?i=l+1:r=l;d<e[s[i]]&&(i>0&&(t[o]=s[i-1]),s[i]=o)}}for(i=s.length,r=s[i-1];i-- >0;)s[i]=r,r=t[r];return s}function Wn(e){const t=e.subTree.component;if(t)return t.asyncDep&&!t.asyncResolved?t:Wn(t)}function Io(e){if(e)for(let t=0;t<e.length;t++)e[t].flags|=8}function Qn(e){if(e.placeholder)return e.placeholder;const t=e.component;return t?Qn(t.subTree):null}const qn=e=>e.__isSuspense;function Kr(e,t){t&&t.pendingBranch?P(e)?t.effects.push(...e):t.effects.push(e):Yi(e)}const ce=Symbol.for("v-fgt"),Cs=Symbol.for("v-txt"),st=Symbol.for("v-cmt"),Rs=Symbol.for("v-stc"),tt=[];let de=null;function J(e=!1){tt.push(de=e?null:[])}function zn(){tt.pop(),de=tt[tt.length-1]||null}let Rt=1;function Ro(e,t=!1){Rt+=e,e<0&&de&&t&&(de.hasOnce=!0)}function Jn(e){return e.dynamicChildren=Rt>0?de||rt:null,zn(),Rt>0&&de&&de.push(e),e}function Z(e,t,s,o,n,i){return Jn(O(e,t,s,o,n,i,!0))}function Do(e,t,s,o,n){return Jn(Ue(e,t,s,o,n,!0))}function Yn(e){return e?e.__v_isVNode===!0:!1}function yt(e,t){return e.type===t.type&&e.key===t.key}const Zn=({key:e})=>e??null,Xt=({ref:e,ref_key:t,ref_for:s})=>(typeof e=="number"&&(e=""+e),e!=null?Q(e)||oe(e)||F(e)?{i:pe,r:e,k:t,f:!!s}:e:null);function O(e,t=null,s=null,o=0,n=null,i=e===ce?0:1,r=!1,l=!1){const c={__v_isVNode:!0,__v_skip:!0,type:e,props:t,key:t&&Zn(t),ref:t&&Xt(t),scopeId:xn,slotScopeIds:null,children:s,component:null,suspense:null,ssContent:null,ssFallback:null,dirs:null,transition:null,el:null,anchor:null,target:null,targetStart:null,targetAnchor:null,staticCount:0,shapeFlag:i,patchFlag:o,dynamicProps:n,dynamicChildren:null,appContext:null,ctx:pe};return l?(cs(c,s),i&128&&e.normalize(c)):s&&(c.shapeFlag|=Q(s)?8:16),Rt>0&&!r&&de&&(c.patchFlag>0||i&6)&&c.patchFlag!==32&&de.push(c),c}const Ue=Vr;function Vr(e,t=null,s=null,o=0,n=null,i=!1){if((!e||e===mr)&&(e=st),Yn(e)){const l=pt(e,t,!0);return s&&cs(l,s),Rt>0&&!i&&de&&(l.shapeFlag&6?de[de.indexOf(e)]=l:de.push(l)),l.patchFlag=-2,l}if(el(e)&&(e=e.__vccOpts),t){t=$r(t);let{class:l,style:c}=t;l&&!Q(l)&&(t.class=jt(l)),B(c)&&(no(c)&&!P(c)&&(c=ne({},c)),t.style=Nt(c))}const r=Q(e)?1:qn(e)?128:bs(e)?64:B(e)?4:F(e)?2:0;return O(e,t,s,o,n,r,i,!0)}function $r(e){return e?no(e)||jn(e)?ne({},e):e:null}function pt(e,t,s=!1,o=!1){const{props:n,ref:i,patchFlag:r,children:l,transition:c}=e,d=t?Ur(n||{},t):n,f={__v_isVNode:!0,__v_skip:!0,type:e.type,props:d,key:d&&Zn(d),ref:t&&t.ref?s&&i?P(i)?i.concat(Xt(t)):[i,Xt(t)]:Xt(t):i,scopeId:e.scopeId,slotScopeIds:e.slotScopeIds,children:l,target:e.target,targetStart:e.targetStart,targetAnchor:e.targetAnchor,staticCount:e.staticCount,shapeFlag:e.shapeFlag,patchFlag:t&&e.type!==ce?r===-1?16:r|16:r,dynamicProps:e.dynamicProps,dynamicChildren:e.dynamicChildren,appContext:e.appContext,dirs:e.dirs,transition:c,component:e.component,suspense:e.suspense,ssContent:e.ssContent&&pt(e.ssContent),ssFallback:e.ssFallback&&pt(e.ssFallback),placeholder:e.placeholder,el:e.el,anchor:e.anchor,ctx:e.ctx,ce:e.ce};return c&&o&&ro(f,c.clone(f)),f}function ls(e=" ",t=0){return Ue(Cs,null,e,t)}function ke(e){return e==null||typeof e=="boolean"?Ue(st):P(e)?Ue(ce,null,e.slice()):Yn(e)?Re(e):Ue(Cs,null,String(e))}function Re(e){return e.el===null&&e.patchFlag!==-1||e.memo?e:pt(e)}function cs(e,t){let s=0;const{shapeFlag:o}=e;if(t==null)t=null;else if(P(t))s=16;else if(typeof t=="object")if(o&65){const n=t.default;n&&(n._c&&(n._d=!1),cs(e,n()),n._c&&(n._d=!0));return}else{s=32;const n=t._;!n&&!jn(t)?t._ctx=pe:n===3&&pe&&(pe.slots._===1?t._=1:(t._=2,e.patchFlag|=1024))}else if(F(t)){if(o&65){cs(e,{default:t});return}t={default:t,_ctx:pe},s=32}else t=String(t),o&64?(s=16,t=[ls(t)]):s=8;e.children=t,e.shapeFlag|=s}function Ur(...e){const t={};for(let s=0;s<e.length;s++){const o=e[s];for(const n in o)if(n==="class")t.class!==o.class&&(t.class=jt([t.class,o.class]));else if(n==="style")t.style=Nt([t.style,o.style]);else if(fs(n)){const i=t[n],r=o[n];r&&i!==r&&!(P(i)&&i.includes(r))?t[n]=i?[].concat(i,r):r:r==null&&i==null&&!ds(n)&&(t[n]=r)}else n!==""&&(t[n]=o[n])}return t}function Ee(e,t,s,o=null){be(e,t,7,[s,o])}const Wr=Rn();let Qr=0;function qr(e,t,s){const o=e.type,n=(t?t.appContext:e.appContext)||Wr,i={uid:Qr++,vnode:e,type:o,parent:t,appContext:n,root:null,next:null,subTree:null,effect:null,update:null,job:null,scope:new Ci(!0),render:null,proxy:null,exposed:null,exposeProxy:null,withProxy:null,provides:t?t.provides:Object.create(n.provides),ids:t?t.ids:["",0,0],accessCache:null,renderCache:[],components:null,directives:null,propsOptions:Gn(o,n),emitsOptions:Dn(o,n),emit:null,emitted:null,propsDefaults:K,inheritAttrs:o.inheritAttrs,ctx:K,data:K,props:K,attrs:K,slots:K,refs:K,setupState:K,setupContext:null,suspense:s,suspenseId:s?s.pendingId:0,asyncDep:null,asyncResolved:!1,isMounted:!1,isUnmounted:!1,isDeactivated:!1,bc:null,c:null,bm:null,m:null,bu:null,u:null,um:null,bum:null,da:null,a:null,rtg:null,rtc:null,ec:null,sp:null};return i.ctx={_:i},i.root=t?t.root:i,i.emit=Or.bind(null,i),e.ce&&e.ce(i),i}let ae=null;const zr=()=>ae||pe;let as,Dt;{const e=hs(),t=(s,o)=>{let n;return(n=e[s])||(n=e[s]=[]),n.push(o),i=>{n.length>1?n.forEach(r=>r(i)):n[0](i)}};as=t("__VUE_INSTANCE_SETTERS__",s=>ae=s),Dt=t("__VUE_SSR_SETTERS__",s=>Ht=s)}const Gt=e=>{const t=ae;return as(e),e.scope.on(),()=>{e.scope.off(),as(t)}},Ho=()=>{ae&&ae.scope.off(),as(null)};function Xn(e){return e.vnode.shapeFlag&4}let Ht=!1;function Jr(e,t=!1,s=!1){t&&Dt(t);const{props:o,children:n}=e.vnode,i=Xn(e);Fr(e,o,i,t),Hr(e,n,s||t);const r=i?Yr(e,t):void 0;return t&&Dt(!1),r}function Yr(e,t){const s=e.type;e.accessCache=Object.create(null),e.proxy=new Proxy(e.ctx,_r);const{setup:o}=s;if(o){Ne();const n=e.setupContext=o.length>1?Xr(e):null,i=Gt(e),r=Bt(o,e,0,[e.props,n]),l=zo(r);if(je(),i(),(l||e.sp)&&!kt(e)&&kn(e),l){if(r.then(Ho,Ho),t)return r.then(c=>{Dt(!0);try{Lo(e,c,t)}finally{Dt(!1)}}).catch(c=>{_s(c,e,0)});e.asyncDep=r}else Lo(e,r)}else ei(e)}function Lo(e,t,s){F(t)?e.type.__ssrInlineRender?e.ssrRender=t:e.render=t:B(t)&&(e.setupState=bn(t)),ei(e)}function ei(e,t,s){const o=e.type;e.render||(e.render=o.render||Pe);{const n=Gt(e);Ne();try{br(e)}finally{je(),n()}}}const Zr={get(e,t){return se(e,"get",""),e[t]}};function Xr(e){const t=s=>{e.exposed=s||{}};return{attrs:new Proxy(e.attrs,Zr),slots:e.slots,emit:e.emit,expose:t}}function vs(e){return e.exposed?e.exposeProxy||(e.exposeProxy=new Proxy(bn(Gi(e.exposed)),{get(t,s){if(s in t)return t[s];if(s in At)return At[s](e)},has(t,s){return s in t||s in At}})):e.proxy}function el(e){return F(e)&&"__vccOpts"in e}const ft=(e,t)=>Wi(e,t,Ht),tl="3.5.42";/**
* @vue/runtime-dom v3.5.42
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/let Ws;const No=typeof window<"u"&&window.trustedTypes;if(No)try{Ws=No.createPolicy("vue",{createHTML:e=>e})}catch{}const ti=Ws?e=>Ws.createHTML(e):e=>e,sl="http://www.w3.org/2000/svg",ol="http://www.w3.org/1998/Math/MathML",Ie=typeof document<"u"?document:null,jo=Ie&&Ie.createElement("template"),nl={insert:(e,t,s)=>{t.insertBefore(e,s||null)},remove:e=>{const t=e.parentNode;t&&t.removeChild(e)},createElement:(e,t,s,o)=>{const n=t==="svg"?Ie.createElementNS(sl,e):t==="mathml"?Ie.createElementNS(ol,e):s?Ie.createElement(e,{is:s}):Ie.createElement(e);return e==="select"&&o&&o.multiple!=null&&n.setAttribute("multiple",o.multiple),n},createText:e=>Ie.createTextNode(e),createComment:e=>Ie.createComment(e),setText:(e,t)=>{e.nodeValue=t},setElementText:(e,t)=>{e.textContent=t},parentNode:e=>e.parentNode,nextSibling:e=>e.nextSibling,querySelector:e=>Ie.querySelector(e),setScopeId(e,t){e.setAttribute(t,"")},insertStaticContent(e,t,s,o,n,i){const r=s?s.previousSibling:t.lastChild;if(n&&(n===i||n.nextSibling))for(;t.insertBefore(n.cloneNode(!0),s),!(n===i||!(n=n.nextSibling)););else{jo.innerHTML=ti(o==="svg"?`<svg>${e}</svg>`:o==="mathml"?`<math>${e}</math>`:e);const l=jo.content;if(o==="svg"||o==="mathml"){const c=l.firstChild;for(;c.firstChild;)l.appendChild(c.firstChild);l.removeChild(c)}t.insertBefore(l,s)}return[r?r.nextSibling:t.firstChild,s?s.previousSibling:t.lastChild]}},il=Symbol("_vtc");function rl(e,t,s){const o=e[il];o&&(t=(t?[t,...o]:[...o]).join(" ")),t==null?e.removeAttribute("class"):s?e.setAttribute("class",t):e.className=t}const us=Symbol("_vod"),si=Symbol("_vsh"),ll={name:"show",beforeMount(e,{value:t},{transition:s}){e[us]=e.style.display==="none"?"":e.style.display,s&&t?s.beforeEnter(e):Tt(e,t)},mounted(e,{value:t},{transition:s}){s&&t&&s.enter(e)},updated(e,{value:t,oldValue:s},{transition:o}){!t!=!s&&(o?t?(o.beforeEnter(e),Tt(e,!0),o.enter(e)):o.leave(e,()=>{Tt(e,!1)}):Tt(e,t))},beforeUnmount(e,{value:t}){Tt(e,t)}};function Tt(e,t){e.style.display=t?e[us]:"none",e[si]=!t}const cl=Symbol(""),al=/(?:^|;)\s*display\s*:/;function ul(e,t,s){const o=e.style,n=Q(s);let i=!1;if(s&&!n){if(t)if(Q(t))for(const r of t.split(";")){const l=r.slice(0,r.indexOf(":")).trim();s[l]==null&&vt(o,l,"")}else for(const r in t)s[r]==null&&vt(o,r,"");for(const r in s){r==="display"&&(i=!0);const l=s[r];l!=null?dl(e,r,!Q(t)&&t?t[r]:void 0,l)||vt(o,r,l):vt(o,r,"")}}else if(n){if(t!==s){const r=o[cl];r&&(s+=";"+r),o.cssText=s,i=al.test(s)}}else t&&e.removeAttribute("style");us in e&&(e[us]=i?o.display:"",e[si]&&(o.display="none"))}const Jt=/\s*!important$/;function vt(e,t,s){if(P(s))s.forEach(o=>vt(e,t,o));else if(s==null&&(s=""),t.startsWith("--"))Jt.test(s)?e.setProperty(t,s.replace(Jt,""),"important"):e.setProperty(t,s);else{const o=fl(e,t);Jt.test(s)?e.setProperty(ot(o),s.replace(Jt,""),"important"):e[o]=s}}const Bo=["Webkit","Moz","ms"],Ds={};function fl(e,t){const s=Ds[t];if(s)return s;let o=ge(t);if(o!=="filter"&&o in e)return Ds[t]=o;o=Zo(o);for(let n=0;n<Bo.length;n++){const i=Bo[n]+o;if(i in e)return Ds[t]=i}return t}function dl(e,t,s,o){return e.tagName==="TEXTAREA"&&(t==="width"||t==="height")&&Q(o)&&s===o}const Go="http://www.w3.org/1999/xlink";function Ko(e,t,s,o,n,i=yi(t)){o&&t.startsWith("xlink:")?s==null?e.removeAttributeNS(Go,t.slice(6,t.length)):e.setAttributeNS(Go,t,s):s==null||i&&!en(s)?e.removeAttribute(t):e.setAttribute(t,i?"":Me(s)?String(s):s)}function Vo(e,t,s,o,n){if(t==="innerHTML"||t==="textContent"){s!=null&&(e[t]=t==="innerHTML"?ti(s):s);return}const i=e.tagName;if(t==="value"&&i!=="PROGRESS"&&!i.includes("-")){const l=i==="OPTION"?e.getAttribute("value")||"":e.value,c=s==null?e.type==="checkbox"?"on":"":String(s);(l!==c||!("_value"in e))&&(e.value=c),s==null&&e.removeAttribute(t),e._value=s;return}let r=!1;if(s===""||s==null){const l=typeof e[t];l==="boolean"?s=en(s):s==null&&l==="string"?(s="",r=!0):l==="number"&&(s=0,r=!0)}try{e[t]=s}catch{}r&&e.removeAttribute(n||t)}function pl(e,t,s,o){e.addEventListener(t,s,o)}function hl(e,t,s,o){e.removeEventListener(t,s,o)}const $o=Symbol("_vei");function gl(e,t,s,o,n=null){const i=e[$o]||(e[$o]={}),r=i[t];if(o&&r)r.value=o;else{const[l,c]=bl(t);if(o){const d=i[t]=Cl(o,n);pl(e,l,d,c)}else r&&(hl(e,l,r,c),i[t]=void 0)}}const ml=/(Once|Passive|Capture)$/,_l=/^on:?(?:Once|Passive|Capture)$/;function bl(e){let t,s;for(;(s=e.match(ml))&&!_l.test(e);)t||(t={}),e=e.slice(0,e.length-s[1].length),t[s[1].toLowerCase()]=!0;return[e[2]===":"?e.slice(3):ot(e.slice(2)),t]}let Hs=0;const yl=Promise.resolve(),Tl=()=>Hs||(yl.then(()=>Hs=0),Hs=Date.now());function Cl(e,t){const s=o=>{if(!o._vts)o._vts=Date.now();else if(o._vts<=s.attached)return;const n=s.value;if(P(n)){const i=o.stopImmediatePropagation;o.stopImmediatePropagation=()=>{i.call(o),o._stopped=!0};const r=n.slice(),l=[o];for(let c=0;c<r.length&&!o._stopped;c++){const d=r[c];d&&be(d,t,5,l)}}else be(n,t,5,[o])};return s.value=e,s.attached=Tl(),s}const Uo=e=>e.charCodeAt(0)===111&&e.charCodeAt(1)===110&&e.charCodeAt(2)>96&&e.charCodeAt(2)<123,vl=(e,t,s,o,n,i)=>{const r=n==="svg";t==="class"?rl(e,o,r):t==="style"?ul(e,s,o):fs(t)?ds(t)||gl(e,t,s,o,i):(t[0]==="."?(t=t.slice(1),!0):t[0]==="^"?(t=t.slice(1),!1):Sl(e,t,o,r))?(Vo(e,t,o),!e.tagName.includes("-")&&(t==="value"||t==="checked"||t==="selected")&&Ko(e,t,o,r,i,t!=="value")):e._isVueCE&&(xl(e,t)||e._def.__asyncLoader&&(/[A-Z]/.test(t)||!Q(o)))?Vo(e,ge(t),o,i,t):(t==="true-value"?e._trueValue=o:t==="false-value"&&(e._falseValue=o),Ko(e,t,o,r))};function Sl(e,t,s,o){if(o)return!!(t==="innerHTML"||t==="textContent"||t in e&&Uo(t)&&F(s));if(t==="spellcheck"||t==="draggable"||t==="translate"||t==="autocorrect"||t==="sandbox"&&e.tagName==="IFRAME"||t==="form"||t==="list"&&e.tagName==="INPUT"||t==="type"&&e.tagName==="TEXTAREA")return!1;if(t==="width"||t==="height"){const n=e.tagName;if(n==="IMG"||n==="VIDEO"||n==="CANVAS"||n==="SOURCE")return!1}return Uo(t)&&Q(s)?!1:t in e}function xl(e,t){const s=e._def.props;if(!s)return!1;const o=ge(t);return Array.isArray(s)?s.some(n=>ge(n)===o):Object.keys(s).some(n=>ge(n)===o)}const El=["ctrl","shift","alt","meta"],Ol={stop:e=>e.stopPropagation(),prevent:e=>e.preventDefault(),self:e=>e.target!==e.currentTarget,ctrl:e=>!e.ctrlKey,shift:e=>!e.shiftKey,alt:e=>!e.altKey,meta:e=>!e.metaKey,left:e=>"button"in e&&e.button!==0,middle:e=>"button"in e&&e.button!==1,right:e=>"button"in e&&e.button!==2,exact:(e,t)=>El.some(s=>e[`${s}Key`]&&!t.includes(s))},es=(e,t)=>{if(!e)return e;const s=e._withMods||(e._withMods={}),o=t.join(".");return s[o]||(s[o]=(n,...i)=>{for(let r=0;r<t.length;r++){const l=Ol[t[r]];if(l&&l(n,t))return}return e(n,...i)})},wl=ne({patchProp:vl},nl);let Wo;function kl(){return Wo||(Wo=Nr(wl))}const Al=(...e)=>{const t=kl().createApp(...e),{mount:s}=t;return t.mount=o=>{const n=Ml(o);if(!n)return;const i=t._component;!F(i)&&!i.render&&!i.template&&(i.template=n.innerHTML),n.nodeType===1&&(n.textContent="");const r=s(n,!1,Pl(n));return n instanceof Element&&(n.removeAttribute("v-cloak"),n.setAttribute("data-v-app","")),r},t};function Pl(e){if(e instanceof SVGElement)return"svg";if(typeof MathMLElement=="function"&&e instanceof MathMLElement)return"mathml"}function Ml(e){return Q(e)?document.querySelector(e):e}function oi(){let e=(location.hash||"#/").replace(/^#/,"");e.startsWith("/")||(e="/"+e);const t=e.indexOf("?"),s={};if(t>=0){const o=e.slice(t+1);for(const n of o.split("&")){const i=n.indexOf("=");if(i<=0)continue;const r=decodeURIComponent(n.slice(0,i)),l=decodeURIComponent(n.slice(i+1));s[r]=l}e=e.slice(0,t)}return{path:e,query:s}}const ni=oi(),Pt=lt(ni.path),ii=lt(ni.query);function St(e){Pt.value===e&&location.hash==="#"+e||(location.hash=e)}window.addEventListener("hashchange",()=>{const e=oi();Pt.value=e.path,ii.value=e.query,window.scrollTo(0,0)});const Fl=[{id:"intro",title:"平台简介与核心理念",body:`# 工业能碳智控平台 · 系统介绍（v2.1.0）

> **给每座工厂派驻一位"工业级具身智能体"**
>
> 它看得见现场、**懂能、懂碳、懂市场**——算得清能源账、碳账与成本账，想得出方案、动得了参数、写得好报告，24 小时在岗，为企业的节能降碳保驾护航。

## 一、核心理念：一位懂能、懂碳、懂市场的"数字专家"

### 1. 工业级具身智能 —— 不只是"会聊天"的 AI

人工智能正在发生深刻变革：AI 不再只是"会聊天、能对话"的软件，而是进化出了**感知、认知、决策、行动**的完整能力——它看得见、想得到、更做得出，这就是前沿的"具身智能"。

**工业级具身智能，就是把这样的智能体派驻到您的工厂。** 过去，节能减排靠老师傅的经验、靠外请专家诊断、靠反复试验摸索；现在，平台将工厂"全要素数字化"后，AI 智能体便有了一个可以持续感知和行动的"身体"，成为工厂里"24 小时在岗的数字专家"。

这位数字专家与众不同之处在于——它**不是只盯着碳**，而是同时长着三双眼睛：

| 洞察维度 | 关注什么 | 行业场景（以钢铁为例） |
| --- | --- | --- |
| **懂能** | 能源消耗、能效水平 | 每吨产品烧了多少电、多少煤气、多少燃料（吨钢、吨熟料……），能效哪里还有空间 |
| **懂碳** | 碳排放、碳强度 | 每道工序排了多少碳，全厂一本明白账，控排履约有底气 |
| **懂市场** | 碳价、原料价、行业资讯 | 碳配额什么价、焦煤什么价、政策有什么新动向，决策有依据 |

### 2. 云边协同 —— "就近感知、云端思考"的分工合作

要让数字专家足够聪明、反应足够快，平台采用了一套聪明的分工方式——**云边协同**：

- **厂里放一个"耳朵"（能碳一体机）**：部署在工厂现场，就近收集能源、生产、计量各类数据，随采随算，网络波动也不影响数据采集；
- **云端有一颗"大脑"（平台系统）**：汇聚全厂数据，负责深度的核算、推演、学习与思考，越用越聪明；
- **两边默契配合**：现场数据源源不断传上云端，云端智慧随时下发指导，一台数字专家、两处协同工作。

> 简单说：**现场的事，就近办；深度的事，云端想——反应快，还不丢数据，两全其美。**`},{id:"cap-1",title:"能力全景（上）看得见 · 建得真 · 算得清",body:`## 二、它能做什么：八大能力

### 1. 看得见 —— 把整座工厂"搬"进电脑

- 钢铁的烧结、焦化、高炉、转炉、连铸、轧钢，水泥的生料磨、回转窑、粉磨站，化工的反应、精制装置……20 多种工序设备按真实比例呈现在三维场景中，整条产线尽收眼底；
- 想看哪道工序点哪里，物料怎么流动、能耗高低分布，用颜色就能看得清清楚楚；

> 不用进现场，也能随时掌握全厂的**能源消耗与碳排状况**。

### 2. 建得真 —— 工艺流程自己搭，设备信息自己配

平台不仅预置了标准产线，更把"定义工厂"的能力交到企业自己手中：

- **工艺流程自己搭**：像搭积木一样，拖一拖、连一连，就能搭出企业真实的工艺流程——钢铁的原料、炼铁、炼钢到轧钢，水泥的生料、熟料到粉磨，流程怎么走，企业说了算；
- **设备信息自己配**：每台设备的量程、运行范围、规模大小都可以按企业实际"量身定制"；
- **改完马上生效**：流程搭好、设备配好，三维场景和仿真结果随即更新；
- **上手无门槛**：内置行业模板一键载入，在模板基础上自由修改即可。

> 平台不替您决定工艺，而是把"定义工艺的能力"交给您——**一厂一策，千厂千面。**

### 3. 算得清 —— 全厂一本"能源账 + 碳账 + 成本账"

- **能源账**：从原料到成品，每道工序的电、气、煤、焦消耗自动汇总，全厂能耗一目了然，吨钢、吨熟料等单耗随手可查；
- **碳账**：每道工序的碳排放自动核算，全厂碳排总量、单位产品碳强度（吨钢、吨熟料等）一键可得；
- **成本账**：每次调整都同步估算成本变化——燃料、电力、物料省了多少，清清楚楚；
- **账目可追溯**：每一笔能源、每一笔碳从哪来、到哪去，清清楚楚，经得起核查。

> 能、碳、钱三本账一起算——**能耗看得见、碳排算得明、成本省得着。**`},{id:"cap-2",title:"能力全景（中）推演得准 · 想得出 · 动得了",body:`### 4. 推演得准 —— 改参数之前，先"预演"一遍

- **一键仿真**：输入工艺参数，平台立即算出对应的能耗、碳排与成本；
- **零风险试错**：在仿真模式下随意调整、反复试算，改坏了也不影响真实数据，退出即还原；
- **效果对比**：执行某项减排策略后，平台自动展示"改之前 vs 改之后"——能耗降多少、减排多少吨、降本多少元，一目了然。

> 每一项工艺调整，先看到结果再决定，不再"拍脑袋"。

### 5. 想得出 —— AI 当"能碳参谋"

- **用大白话下指令**：像和人说话一样，输入 **"焦比降低 5%"**、**"提高喷煤量 10%"**（水泥行业则说 **"吨熟料煤耗降 3%"**），AI 自动理解并转化为可执行的调整方案；
- **一工序一模型，专门算法建模**：不是一套算法"包打天下"，而是**针对每一个工艺环节都建立了专门优化的 AI 算法模型**——高炉有高炉的焓平衡燃烧模型、烧结有烧结的工艺寻优、转炉有转炉的配比优化，水泥有水泥的窑炉热平衡模型、化工有化工的反应单元寻优……每个工序都有专属的"数字师傅"，用最贴合本工序机理的算法提供最专业的判断；
- **会学习的优化引擎**：AI 持续学习工厂运行数据，自动寻找"既保产量、又降能耗、还省钱"的最优参数组合，越用越聪明；
- **策略知识库**：内置成熟的节能降碳策略模板，企业自己的好做法也能保存成"自定义策略"，形成专属的能碳管理经验库。

> 企业降碳不再依赖个别专家，每个工序都有深耕本专业的"AI 数字师傅"。

### 6. 动得了 —— 从"给建议"到"动手干"

- **智能自动控制**：优化模型找到更优参数后，在三级防护校验范围内自动下发到可调设备，形成"感知—寻优—执行"的智能闭环；
- **一句话指挥仿真**：输入简单指令即可运行、停止仿真、切换视角，操控整个"数字工厂"；
- **智能体仿真控制**：输入一句话，AI 自动完成"解析 → 确认 → 应用 → 对比"全流程，让"您说、它调、您验"成为现实。

> AI 不只给建议，还能动手干，节能减碳闭环真正跑起来。`},{id:"cap-3",title:"能力全景（下）守得住 · 会汇报",body:`### 7. 守得住 —— AI 聪明，更要守规矩

让 AI 自主行动，安全是第一位的。平台为智能体的每一个动作都装上了**三级防护**，确保它"有想法、更有分寸"：

**第一级 · 参数边界防护**
- 每一台设备、每一项可调参数都设有**安全运行区间**（如温度、风量、配比的上下限）；
- AI 的任何操作一旦触碰边界，立刻被拦截并提示，**绝不越雷池一步**。

**第二级 · 耦合一致性防护**
- 自动识别自相矛盾的操作组合（如"降温的同时却提高风温"），在源头上拦截不合理策略；
- 多参数联动时自动校验相互影响，防止"按下葫芦浮起瓢"。

**第三级 · 执行确认防护**
- 关键操作必须**经工程师确认后方可执行**，全程操作留痕、可查可溯；
- 每一步都"有人把关、有账可查"，即使出问题也能快速定位。

**两种协作模式，主动权始终在工程师手中：**

| 模式 | 工作方式 | 适合场景 |
| --- | --- | --- |
| 自动模式 | 防护校验通过后，优化参数自动下发执行 | 工况稳定、信任成熟时全自动运行 |
| 建议模式 | AI 只提供优化建议，工程师结合现场经验自主判断、手动调整 | 工况复杂、需要专家判断时人工把关 |

> 机器给建议、人做决定——**AI 再聪明，安全边界与最终决策权，始终牢牢掌握在工程师手中。**

### 8. 会汇报 —— 行情资讯自动更新，成果一键成文

- **每日自动获取碳市场数据**：碳市场配额价格、自愿减排量价格自动更新，走势图直观呈现，未来价格趋势智能预测；
- **每日自动获取原料与能源市场资讯**：煤炭、焦炭、天然气、电力等原料能源价格与市场快讯自动抓取，价格波动、政策动向第一时间掌握；
- **智能报告**：能耗盘点、碳排放盘点、减排效果、优化建议，自动生成条理清晰的分析报告，支持下载与分享。

> 能价、碳价、原料价自动更新，报告自动生成——**市场一有风吹草动，您第一时间掌握。**`},{id:"device",title:"能碳一体机",body:`## 三、能碳一体机 —— 数字专家的"顺风耳"

平台的感知能力，来自我们自主研发的**能碳一体机**。它是一台部署在工厂现场的智能设备，也是连接"真实工厂"与"数字工厂"的桥梁。

### 两大接入方式，真正"开箱即用"

**1. 不打扰、不改造——轻轻接入企业现有系统**
- 无需改造企业现有系统，不触碰生产网络，像"旁路"一样顺路采集能源与碳排数据；
- 企业已有的计量系统、能源系统、数据中心，历史与实时数据均可平滑接入；
- 部署"无感"，不干扰正常生产，实施周期短、上线快。

**2. 直接连——现场设备随手接**
- 电表、气表、水表、流量计、传感器等现场计量设备可直接接入；
- 就地采集、就地处理，实时汇聚能源消耗与排放数据；
- 即使网络不畅，数据也先稳稳保存在现场，随时补传，一条都不丢。

### 一体机带来的四大好处

| 好处 | 说明 |
| --- | --- |
| **接入快** | 不改造企业系统，实施几乎零风险 |
| **数据全** | 系统数据 + 现场设备双通道汇聚，能碳数据更细、更完整 |
| **反应快** | 现场就近采集处理，网络波动也不怕，数据实时可靠 |
| **成本省** | 软硬一体、开箱即用，总投入更低 |

### 软硬一体 · 依托自研云边协同系统

能碳一体机采用**软硬一体**设计，依托平台**自主研发的云边协同系统**，把"设备接入、模型下发、数据上云"做成一件开箱即用的事：

- **自研云边协同系统**：云端 K3s + KubeEdge 作为唯一控制平面，一体机内置 EdgeCore 边缘节点，经 CloudHub 安全长连接与云端实时同步——控制下发与数据回传双通道毫秒级响应，断线自动重连、数据补传不丢失；
- **软硬一体、开箱即用**：工业级硬件与采集、边缘计算软件深度预装预调，出厂即"可上云"，无需现场拼装与专业调试；
- **快速设备模型建立与下发**：基于 KubeEdge 设备模型（DeviceModel / Device），支持五种主流协议的可视化建模，YAML 一键生成、秒级下发到一体机——新增设备即建即用；
- **远程下发 AI 模型**：AI 优化模型与采集程序支持云端远程一键下发、版本管理与回滚，模型更新全程自动化，无需现场、无需登录盒子；
- **傻瓜式部署盒子**：部署包自动生成（内置 edgecore 配置模板与 token / caHash），现场一条命令完成接入，约 10 分钟上线，无需专业运维；
- **完善的管理平台**：设备管理、关联映射、实时数据、消息流追踪、健康诊断一站式云端管控——一体机上云即可远程运营。

> 一台软硬一体的能碳一体机 + 一套自研云边协同系统：**设备模型秒级建立、AI 模型远程下发、盒子傻瓜式部署、平台一站式管理——把"上云"做成一件简单的事。**

> 有了能碳一体机，数字专家才有了真正的"感官"——**用最轻的方式，获得最全的数据，让每一笔能源、每一笔碳都"有源可查"。**`},{id:"platform",title:"多平台支持",body:`## 四、随时随地可用 —— 办公、出差、会议室，想看就看

这套系统**一套能力、多种载体**，按企业需要自由选择：

| 使用方式 | 特点 | 适合场景 |
| --- | --- | --- |
| 浏览器访问 | 免安装，打开即用 | 办公室、会议室演示、多部门使用 |
| 桌面应用（电脑版） | 双击运行，原生体验 | 日常办公、离线演示 |
| 集团集中部署 | 一处部署、全员共享 | 集团/厂级统一管理，全厂一套数据口径 |
| 轻量工具 | 极简轻巧 | 技术人员快速调用 |

> 出差、开会、办公室，随时打开都能看；集团集中部署，全厂数据一个口径。

同时，平台界面风格**与品牌调性完全统一**：默认**科技蓝**主题、顶栏与底栏亮色分层、冷白金属质感，支持**四套主题色**（科技蓝 / 品牌黄 / 生态绿 / 中国红）与**夜间模式**一键切换，白天办公、夜间值守都舒适。`},{id:"scenario",title:"控排企业的一天",body:`## 五、走进真实场景：控排企业的一天

以率先落地的**钢铁行业**为例，看看这套系统如何改变企业的工作方式——同样的方法，完全适用于水泥、化工、有色等行业：

**过去**：减排目标下达 → 技术科翻报表、凭经验提方案 → 生产试验数月 → 结果难量化、汇报靠估计。

**现在**：

1. **部署**：厂里装上一台能碳一体机，对接已有系统、接上关键计量设备，**一个周末即可完成**，生产零改动；
2. **建模**：工程师按企业真实产线，搭出"烧结 → 高炉 → 转炉 → 连铸 → 轧钢"工艺流程，配好各设备参数，三维场景随即生成；
3. **早上**：打开平台，全厂状态尽收眼底，昨日各工序能耗与碳排自动汇总，碳市场、原料市场行情与快讯已自动更新，一屏掌握全局；
4. **上午**：接到"单位产品碳强度再降 3%"的目标（如钢铁的吨钢碳强度），工程师在平台输入 **"焦比降低 5%，喷煤提高 8%"**，AI 立即解析并仿真，10 秒后给出预测——能耗降多少、减排多少、成本省多少，同时呈现；
5. **下午**：对比多个方案后选定最优策略保存入库；开启 AI 优化，系统持续寻找"更节能、更低碳、更低成本"的参数组合；
6. **周末**：AI 训练出更优参数，经工程师确认后在安全边界内自动下发，同时生成一份《本周能效与碳排分析报告》，一键分享给管理层；
7. **季度**：全厂能源账、碳账、成本账清晰可查，控排履约数据完备，汇报材料一键导出。

**结果**：节能减碳从"以月为单位试错"变成"分钟级推演"，决策从"凭经验"变成"靠数据 + AI"。

> 无论钢铁、水泥、化工还是有色，这套"感知 → 建模 → 仿真 → 寻优 → 执行 → 汇报"的闭环方法一以贯之——换个行业，只是换一套工序模型。`},{id:"future",title:"持续进化的智能能力",body:`## 六、持续进化的智能能力

平台的智能能力覆盖完整，且随着使用不断进化：

### 1. 全自动的"智能操作员"
说一句话（如"把焦比降低 10%"），AI 自动解析、确认后自动应用，并实时展示前后对比。更进一步的**全自动仿真控制**，AI 根据目标自主规划调整路径、自动执行多轮寻优——真正"全自动操作"。

### 2. 会沉淀、会进化的"策略大脑"
AI 从企业历史运行数据中自动总结"什么工况、用什么策略最节能、最省碳"，形成企业专属的策略知识库；并已实现"能耗 + 碳排 + 成本"的多目标综合优化，帮企业算总账、算长账。

### 3. 一套平台、服务全行业
平台面向**全国碳市场四大重点控排行业**——钢铁、水泥、化工、有色，并持续拓展更多高耗能行业。其中**钢铁行业率先全面落地**（20 多种工序设备建模就绪），**水泥、化工、有色行业同步就绪**，同构复用、快速上线。每个行业、每个工序都有**专门建模的专属算法**，AI 模型库覆盖全行业、持续深耕。

### 4. 与真实生产紧密相连
能碳一体机支持多种数据来源，数字工厂**由真实生产数据实时驱动**，仿真与生产无缝衔接，数字专家的"感知"越来越敏锐、越来越真实。

### 5. 秒级实时遥测，云端历史一条曲线
能碳一体机（边缘 mapper）以**秒级频率**将设备读数通过 MQTT 实时上报云端，平台 WebSocket 消息流与孪生读数同步刷新；云端**时序数据库（TDengine）**自动落盘归档，数据视图一键切换"实时 / 历史"曲线，均值、峰值、谷值随窗计算——现场每一下心跳，都有迹可查。

### 6. 云端消息流与智能对话
平台提供**云端消息流追踪**，设备上报、服务状态、部署回执全链路可视化，断链自动重连；**LLM 智能体**支持自然语言问答、策略解析与 AI 报告生成，数字专家随问随答，报告一键生成。`},{id:"vision",title:"设计愿景",body:`## 七、设计愿景：低耗能 · 低碳 · 保护地球

### 我们的愿景主张

- **低耗能**：用 AI 的"精打细算"代替设备的"大拆大换"——同样的产量，烧得更少、耗得更低；
- **低碳**：让每一次生产决策都算得清碳、降得下碳，帮助企业以可承受的代价走向深度减排；
- **保护地球**：面向钢铁、水泥、化工、有色等全国碳市场重点控排行业及更多高耗能行业，让每一家控排企业都成为绿色转型的参与者，用智慧守护我们的地球家园。

### 节能减排与降本增效，从来不是二选一

很长一段时间里，企业常常面临一个两难：**要减碳，就得投大钱、换大件**——新设备、新工艺、大修大改，动辄数亿的投资，让不少企业"想减却不敢减"。

**这个平台要打破的，正是这个观念。**

### 节能降碳，不只有"大投资"一条路

- **高投入的工艺改进**（更新装备、改造产线）当然是一条路径，但它周期长、资金压力大、风险高，并非所有企业都走得动；
- 而**同样可观**的节能减碳空间，往往藏在日常运行的"细枝末节"里：参数调一调、配比改一改、调度优化一步——不动一台设备、不改一条产线，靠**聪明的算法调度**，就能把能耗和碳排放"挤"出来。

### 算法调度：花小钱、办大事的节能减碳路径

| 方式 | 投入 | 特点 |
| --- | --- | --- |
| 工艺装备大改造 | 高（数亿级） | 周期长、见效大、风险高 |
| 智能算法调度优化 | 低（平台级投入） | 快见效、可持续、零产线改动 |

平台的 AI 优化引擎正是为此而生：持续学习运行数据，找到"既保产量、又降能耗、还省钱"的最优参数组合——**焦比怎么调、窑温怎么控、配比怎么改、各工序能耗怎么平衡**，一遍遍仿真寻优，把藏在日常运行中的节能减碳空间一点点挖掘出来。

### 一鱼两吃：减碳的同时，成本同步下降

- 平台**每一次仿真，都同步算出能耗、碳排与成本变化**——节能降碳带来的燃料、电力、物料节省，清清楚楚地呈现在同一张图上；
- 减少消耗本身就是在降低成本：**烧得少、排得少、花得少**，节能、降碳、增效在多数场景下同向而行；
- 平台让企业看到的，不只是"减排了多少吨"，更是"省下了多少钱"——**用数据证明：节能减排，可以不与降低成本冲突，反而常常双赢。**

> 设计愿景：让节能减碳从"拼投入"走向"拼智慧"，让每一家企业都能以可承受的代价，走出一条**既降耗、又降碳、还增效**的可持续发展之路。`},{id:"why",title:"为什么选择我们",body:`## 八、为什么选择我们

- **看得见**：三维数字孪生，全厂状态一屏掌握；
- **建得真**：工艺流程自己搭、设备信息自己配，一厂一策灵活建模；
- **算得清**：能源账、碳账、成本账三本账同步核算，清清楚楚；
- **推演准**：先仿真、后决策，节能降碳与降本效果提前预知；
- **有智能**：AI 策略 + 优化引擎 + 自动控制，能碳管理从"人治"走向"智治"；
- **模型专**：一工序一模型，每个工艺环节都有专门优化的 AI 算法建模，专业判断更可信；
- **守得住**：三级安全防护 + 工程师自主决策，AI 聪明更守规矩；
- **懂市场**：碳市场、原料市场、能源资讯每日自动获取，决策更有底；
- **易落地**：能碳一体机轻轻接入 + 多平台随手可用，部署快、上手易、扩展灵活。`},{id:"ending",title:"结语",body:`## 九、结语

**工业能碳智控平台——懂能、懂碳、懂市场的工业级具身智能，为企业节能降碳而生。**

从一台能碳一体机的"轻轻接入"，到自主流程建模的"一厂一策"，再到三维数字孪生的"全厂尽收眼底"与 AI 策略引擎的"深思熟虑"——它是一位 24 小时在岗的数字专家：看得见全厂、算得清能源账碳账成本账、推演得准效果、执行得了方案、写得好报告，更看得懂市场。而三级安全防护，则确保它始终"聪明又守规矩"——**机器给建议，人做决定，安全边界与最终决策权始终掌握在企业自己手中。** 面向钢铁、水泥、化工、有色等全行业，让每一家控排企业，都拥有一双"智慧的眼睛"和一颗"AI 的大脑"。

**让节能降碳，从今天开始变得简单、确定、看得见。**`}],Il=[{id:"overview",title:"界面总览与分区",body:`# 工业能碳智控平台 · 使用手册（v2.1.0）

本手册按「操作逻辑」讲解：每一步在哪里点、点了之后会发生什么、如何退出并恢复原状。建议先通读第一章，再按章节动手操作。

## 一、界面分区

打开系统后，首先出现**欢迎页**（见第二章），点击「进入系统」后进入主界面。主界面自上而下、自左而右分为八大区域：

| 区域 | 位置 | 作用 |
| --- | --- | --- |
| 经典菜单条 | 最顶部一行 | 文件 / 仿真 / 视图 / 编辑 / 工具 / 帮助 六组下拉菜单；右侧含「界面主题」与「夜间模式」切换入口 |
| 工具条 | 菜单条下方 | 单行按钮组，随当前模式（3D 孪生 / 编排画布）切换可用按钮（见第四章） |
| 活动栏 | 最左侧竖直窄条 | VS Code 式图标栏：资源管理器 / 搜索 / 场景 / 连接 四个入口，点击切换左侧面板（见第五章） |
| 左侧面板 | 活动栏右侧 | 随活动栏选中项切换：资源管理器（工艺/物料/策略）、搜索结果、场景资源树或数据源连接列表 |
| 3D 孪生场景 | 中央 | 可视化全厂，点击工序聚焦、查看热力图；也可切换为数据视图 / 碳资产管理（见第三章菜单） |
| 检视器 | 右侧栏 | 按当前选中对象显示总览 / 属性 / 报告等内容 |
| 命令行窗口 | 底部 | 输入自然语言、孪生控制命令，显示系统反馈日志 |
| 状态栏 | 最底部一行 | 实时链路状态 / 工序与物流数 / 监测点位 / 市场快讯滚动 / 策略情景 / 时钟 / 通知铃铛（见第二章） |

> 提示：左右两侧栏底部边缘有拖拽手柄，可按住左右拖动调整宽度，宽度会被记忆保存；点击活动栏底部的「收起/展开」按钮或拖动侧栏也可收起面板。

## 二、欢迎页与第一次使用建议流程
启动系统后先显示欢迎页，可：

- 查看平台**功能特性**（3D 数字孪生 / 能碳核算 / AI 策略寻优 / 实时监测预警）与平台能力链路（工艺建模 → 能碳核算 → 情景推演 → 策略寻优）；
- 在「最近」列表中选择项目模板：**钢铁企业 · 长流程**（推荐，10 道工序）或 **钢铁企业 · 短流程**（低碳，5 道工序），点击「进入系统」即可载入对应工艺模型；标注「规划中」的项目暂不可用。

进入主界面后的建议操作流程：

1. 点击左侧活动栏「资源管理器」，在「工艺」中展开并点击任意工序，右侧检视器会显示该工序的属性。
2. 点击左侧「策略」标签，展开「内置」分组，点击任一策略查看说明。
3. 点击右侧该策略底部的「策略仿真」按钮，进入仿真模式体验参数对比。
4. 点击场景右上角「退出仿真」，所有修改自动恢复原状。
5. 试试底部状态栏的「市场快讯」滚动条，以及顶栏「视图 → 碳市场」查看实时碳行情。

### 底部状态栏

主界面最底部一行从左到右依次为：

| 项 | 说明 |
| --- | --- |
| 实时链路 | 数据源运行状态（Mqtt 实时 / WebSocket / HTTP），点击可打开「连接」面板 |
| 工序 / 物流 | 当前流程模型规模（如 10 工序 · 12 物流） |
| 监测点位 | 当前可监测设备数 |
| 可调约束 | 当前可调参数数量 |
| 市场快讯 | 滚动播报最新行业快讯（鼠标悬停可暂停查看） |
| 策略情景 | 当前仿真情景名称（基线情景 / 策略情景激活） |
| 时钟 / 通知 | 系统时间与通知铃铛（有未读提醒时高亮，点击打开通知中心） |

> 状态栏信息均为只读概览，具体操作都在对应面板中完成。

下面各章按区域逐一讲解操作逻辑。`},{id:"menubar",title:"顶栏菜单操作",body:`## 三、顶栏菜单操作

顶栏六个菜单点击后弹出下拉项。带灰色「禁用」状态的项当前不可用（如未运行仿真时的「停止」）。

### 文件

| 菜单项 | 操作逻辑 |
| --- | --- |
| 新建方案 | 点击后在命令行提示「已清空当前编排」，用于开始新的编排设计 |
| 打开方案… | 提示去左侧「策略」中载入已存方案（原型占位） |
| 保存方案 (Ctrl+S) | 将当前方案保存至本地工作区，命令行提示保存成功 |
| 连接数据源… | 弹出数据源配置对话框，选择实时数据来源（Mqtt 实时 / WebSocket / HTTP 轮询） |
| 导出分析报告 | 若尚未运行仿真则提示「请先运行仿真」；否则打开右侧「报告面板」配置并生成报告 |
| 设置… | 打开系统设置对话框：布局开关 / 场景（仿真情景与场景环境）/ 实时链路 / LLM 模型与密钥配置等 |
| 界面主题… | 切换系统主题色：**科技蓝**（默认）/ 品牌黄 / 生态绿 / 中国红；勾选「夜间模式」切换深色界面，顶栏与底栏同步亮/暗分层，选择即生效 |

### 仿真

| 菜单项 | 操作逻辑 |
| --- | --- |
| 运行仿真 (Ctrl+Enter) | 若已有启用的策略则按策略运行；否则重新计算全厂碳素流、能流与排放 |
| 重置仿真参数 | 重新计算并刷新全部结果，回到初始参数 |
| 应用当前情景 | 按当前选中的情景重新计算并应用到场景 |
| 高炉数值分析 (Alt+T) | 仅仿真模式下可用，打开高炉 TFT 数值分析面板（见第九章） |

### 视图

| 菜单项 | 操作逻辑 |
| --- | --- |
| 数字孪生 → 环境（子菜单） | 切换 3D 环境主题：虚空 / 工业 / 沙漠 / 城市 / 海滩，勾选项为当前环境 |
| 数据 | 开关：打开/关闭「数据视图」，用传感器历史数据表格替换中央 3D 场景（见第十一章） |
| 碳资产管理 | 开关：打开/关闭「碳资产管理视图」，用 CEA / CCER 行情与碳资产报告工具替换中央 3D 场景（见第十二章）；与「数据视图」互斥，打开其一自动关闭另一个 |

### 编辑

| 菜单项 | 操作逻辑 |
| --- | --- |
| 进入流程编排 / 完成编排 | 切换「3D 场景」与「编排画布」两种工作模式（见第十四章） |
| 撤销 (Ctrl+Z) / 重做 (Ctrl+Y) | 仅编排模式下可用，用于回退/重做画布操作 |
| 放大画布 / 缩小画布 / 适配视图 / 自动布局 | 仅编排模式下可用，编排画布视图控制 |
| 新建小组 / 复制小组 / 删除小组 | 仅编排模式下可用，对选中小组的分组操作 |
| 长流程示例 / 短流程示例 / 清空画布 | 仅编排模式下可用，一键载入示例流程 / 清空画布（清空不可撤销） |

### 工具

| 菜单项 | 操作逻辑 |
| --- | --- |
| 碳素流守恒审计 | 打开守恒审计面板，核查全流程碳输入与输出的平衡（见第十章） |
| 参数优化 | 提示切换至「数据」工具条 → 策略生成，用自然语言描述优化目标（见第十章） |
| 数据校准 | 打开设备数据校准向导，对监测设备量程与系数进行可视化标定（见第十三章） |

### 帮助

| 菜单项 | 操作逻辑 |
| --- | --- |
| 宣传手册 (F1) | 打开系统宣传手册，了解平台功能与价值亮点 |
| 使用手册 | 打开本手册 |
| 技术文档 | 打开系统技术架构与算法详解 |
| 快捷键 | 命令行输出快捷键速查 |
| 关于本平台 | 显示版本与版权信息 |

> 操作逻辑要点：菜单项执行后大多在命令行窗口输出一条系统反馈，用于确认操作已生效。`},{id:"ribbon",title:"工具条操作",body:`## 四、工具条（单行按钮组）

工具条与菜单条配合使用，按钮随当前工作模式切换，没有标签页。

### 3D 孪生模式（默认）

| 按钮 | 操作逻辑 |
| --- | --- |
| 运行仿真 / 退出仿真 | 主开关。未进入仿真时显示「运行仿真」，点击后进入仿真模式（场景右上角出现对比浮层，所有修改仅预览）；已进入时显示「退出仿真」，点击后恢复仿真前状态 |
| 流程编排 / 完成编排 | 切换至编排画布工作模式 / 完成编排回到 3D 场景 |
| 自动环视 | 开关：开启后相机缓慢自动旋转环视全厂 |
| 刷新视角 | 相机回到园区俯瞰视角 |
| 全屏 | 将场景区切换为全屏显示，Esc 退出 |
| 全景数据 | 仿真运行后可用，弹出全景数据对话框浏览全场数据 |
| 亮度 | 拖动滑杆调整场景环境光亮度 |

### 编排模式（进入流程编排后）

| 按钮 | 操作逻辑 |
| --- | --- |
| 撤销 / 重做 | 编排历史操作回退 |
| 自动布局 | 一键整理画布节点布局 |
| 放大 / 缩小 / 适配视图 | 编排画布的视图控制 |
| 长流程示例 / 短流程示例 | 一键载入示例流程 |
| 清空画布 | 删除画布全部节点连线（不可撤销，会二次确认） |

> 操作逻辑要点：工具条按钮执行后同样会在命令行给出反馈，注意观察命令行确认状态变化。`},{id:"activitybar",title:"活动栏与侧边面板",body:`## 五、活动栏与侧边面板

活动栏位于主界面最左侧的竖直窄条，共四个图标入口，点击后在左侧显示对应面板：**资源管理器 / 搜索 / 场景 / 连接**。再点击当前高亮的图标可收起面板。

### 资源管理器

即「工艺 / 物料 / 策略」三标签面板（详见第六章），是浏览与选中资产的主入口。

### 搜索

全局搜索面板，用于快速定位任意对象：

- **搜索对象**：工序 / 物料 / 策略 / 设备（按名称模糊匹配，支持中文与拼音前缀）。
- **操作**：输入关键词 → 下方实时列出匹配项 → 点击条目：左侧资源管理器切换到对应标签并选中，右侧检视器显示详情，3D 场景同步聚焦到该对象（设备会框选高亮）。
- **分类展示**：结果按「工序」「物料」「策略」「设备」分组计数展示，便于区分同名对象。

### 场景

场景控制面板，集中管理 3D 场景显示与视角：

- **环境主题**：切换虚空 / 工业 / 沙漠 / 城市 / 海滩；
- **显示开关**：网格 / 轴向 / 标签 / 连线 / 热力图等图层显隐；
- **视角工具**：自动环视、刷新视角、全屏等快捷按钮，与工具条对应功能一致。

### 连接

数据链路连接面板，集中展示各数据来源的运行状态：

- 顶部「Mqtt 实时数据源」卡片展示平台默认数据源状态：后端订阅云端 MQTT Broker（Broker 配置在「能碳一体机管理」视图前端配置）获取真实设备读数，不生成模拟数据；
- 下方列出 **Mqtt 实时 / WebSocket / HTTP 轮询** 各链路；当前启用的链路显示绿色「在线」，未启用显示灰色「离线」；
- 每条链路提供**连接 / 断开**操作；
- 点击「数据源配置」按钮可直接打开数据源配置对话框（见第十三章）。

### 能碳一体机管理（云端管理台）

视图菜单「视图 → 能碳一体机管理」打开能碳一体机管理视图（中间 3D 场景切换为管理面板），
原「数据概览」与「设备管理」两个页签已合并为**单界面**（云端设备关联功能已下线），自上而下为：

1. **工具栏**：盒子接入 / 新建设备 / 刷新；状态行显示本地设备数与云端 CRD 生效数；
2. **云端数据链路**：MQTT Broker 实时统计（在线客户端 / 累计收发 / 订阅数 / 版本 / 运行时长）、CloudCore 状态、证书与 Token 有效期（均由云端 cloud-agent 采集并经 MQTT 推送，非 SSH；云端不可达时明确报错，不伪造数据）；
3. **实时消息流与发测试消息**：展示云端 Broker → 本平台的消息活动，可向云端 Broker 发布测试消息调试；
4. **设备管理**：DeviceModel / Device（KubeEdge 设备模型与实例）CRUD——五协议（Modbus / OPC-UA / Bluetooth / LoRaWAN / Cellular）创建表单、YAML 预览（dryRun）、保存本地配置 / 一键下发云端 K3s（apply）、删除；拓扑图展示云端 → 盒子 → 设备结构，点击设备可查看 DMI 实时读数；
5. **盒子接入**：输入盒子主机名 / 云端 CloudCore IP / 盒子 IP，生成 edgecore.yaml（模板渲染）+ 共享 Token + CA 指纹 + 完整部署命令（① keadm join → ② 配置下发 → ③ 云端创建设备 → ④ box-deploy 采集包部署 → ⑤ 触发路由验证）。

关键规则：
- **总体架构**：控制平面全在云端 K3s（轻量 K8s，172.19.134.45）+ KubeEdge CloudCore；盒子边缘只安装 EdgeCore（不部署 k3s-server、无本地控制平面），经 CloudHub（云端 10002 端口）长连接云端，边缘运行 Pod / mosquitto / mapper（DMI 采集，云边协同断点续传）；
- **一键重启**：拓扑图中 CloudCore / cloud-agent / MQTT Broker 模块均有「↻ 重启」按钮，边端盒子有「↻ Mapper」按钮——CloudCore 为 kubectl 滚动重启；cloud-agent / MQTT Broker 为云端 systemctl 重启（重启 cloud-agent 自身延迟 2 秒自动拉起）；box-mapper 由云端 agent 经 SSH 到边缘盒子执行 systemctl restart（需在 agent 的 \`/opt/cloud-agent/config.json\` 配置 \`edge\` 节点：host / user / password 或 key，密码方式需安装 sshpass）。重启 Broker 会短暂断开云边 MQTT 长连接，数秒后自动重连；
- 设备/模型在设备管理创建（后端持久化 \`backend/config/box_devices.json\`），可从设备库导入模板（皮带秤/电表/流量计等）；盒子接入模板预览为 \`backend/config/edgecore.template.yaml\`；
- 管理台只做「配置」与「读取展示」，传感器读数经 DMI 链路获取（断连期间由边缘 SQLite 缓存 + 恢复后补传，数据不丢）。

> 操作逻辑要点：活动栏只控制「左侧显示哪个面板」，不改变中央场景内容；搜索与连接面板都支持回车快速操作。`},{id:"sidebar",title:"左侧资源管理器",body:`## 六、左侧资源管理器

左侧栏三个标签：**工艺 / 物料 / 策略**。点击标签切换，点击条目即选中并联动右侧检视器。

### 工艺

- 展开「工艺」根节点，按 **长流程炼钢 / 短流程炼钢 / 节能减碳** 三个分组展示工序类型。
- 点击工序类型 → 右侧显示「工艺属性」（厂内实例及其实时数据）。
- 点击某台具体设备 → 右侧切换为「设备详情」，可调节运行设定（见第九章）。
- 点亮的圆点表示该工序/设施已部署至 3D 场景；右侧数字表示实例数量。

### 物料

- 按 **原料 / 中间产物 / 产品** 三组展示物料清单。
- 点击物料 → 右侧显示其隐含碳因子与配置信息。

### 策略

- **内置** 分组：按工艺展示绿色策略与系统预置策略。
  - 系统预置策略（图标带「已应用」圆点）：点击后右侧显示策略属性，底部有「策略仿真」按钮。
  - 工艺绿色策略（带「已启用」标签）：点击后右侧可勾选**启用 / 停用**，启用即实时参与仿真。
- **自定义（仿真保存）** 分组：仿真模式下保存的策略，可点击查看/编辑，右侧 ✕ 按钮删除。

> 操作逻辑要点：左侧所有条目都是「点击选中 → 右侧联动」模式，选中状态会高亮。`},{id:"scene",title:"3D 孪生场景",body:`## 七、3D 孪生场景

中央场景是系统的主视图，支持以下交互：

### 选中与聚焦

- **点击工序 / 设备**：选中并聚焦，右侧检视器联动显示属性。
- 按 **F** 可聚焦当前选中工序；或使用命令行 \`view top|front|side|focus\` 切换预设视角。

### 场景右上角按钮

- **保存策略**：仅仿真模式下显示。点击后在命令行提示「请在下方命令行输入策略名称后回车保存」，输入名称回车即保存到「策略 → 自定义」；输入 \`cancel\` 或 \`取消\` 可放弃。
- **退出仿真 / 进入仿真**：切换仿真模式。
- **对比浮层**：仿真模式下浮层展示「仿真前 → 当前」各工序关键指标变化，便于对比基准与策略后差异。

> 亮度调节、自动环视、全屏等按钮位于菜单条下方的工具条（见第四章）。`},{id:"inspector",title:"右侧检视器",body:`## 八、右侧检视器

检视器内容随「当前选中对象」联动，头部标题会随模式变化：

| 模式 | 出现条件 | 主要内容 |
| --- | --- | --- |
| 总览 | 未选中任何对象 | 全厂综合能耗/单位能耗/电耗、能碳流桑基图（碳素流/能流双标签）、排放最高工序（点击可跳转选中） |
| 工艺属性 | 点击左侧「工艺」工序 | 工艺类型说明、厂内实例列表、实时数据 |
| 物料 | 点击「物料」条目 | 隐含碳因子与配置 |
| 策略 | 点击「策略」条目 | 策略属性面板（见第十章） |
| 设备详情 | 点击具体设备 | 运行设定调节、衍生指标、实时/历史趋势（见第九章） |
| 报告 | 点击「文件 → 导出分析报告」或顶栏导出按钮 | 报告面板（见第十六章） |

### 总览中的交互

- 桑基图顶部可切换 **碳素流 / 能流** 两种视图。
- 点击「排放最高工序」卡片中的工序，场景自动聚焦到该工序并显示其属性。`},{id:"device",title:"设备属性与调节",body:`## 九、设备属性与调节

在左侧「工艺」树中点击某台设备，或在 3D 场景中点击设备实体，右侧进入「设备详情」。

### 运行设定

- 部分设备是**可调设备**（如高炉），显示运行设定滑块与输入框。
- 拖动滑块或输入数值即时生效；未进入仿真模式时调整会提示需要先进入仿真模式。
- 附加可调项（如鼓风机鼓风湿度）同样可直接调节。

### 高炉 TFT 面板

- 选中高炉类可调设备时，面板顶部出现 **TFT（理论燃烧温度）** 策略提示。
- 展示按当前风口参数折算的 TFT 值、判定结果（正常 / 过高 / 过低）与调节建议。
- 调节鼓风、喷煤等参数后，TFT 实时重新折算。

### 衍生指标与依据

- 展示设备运行产生的衍生指标（如热风温度、富氧率）。
- 「减碳影响依据」区块说明该设备调节影响哪些排放项（耦合透明度）。

### 趋势

- 设备详情内可查看实时遥测与历史趋势图。
- 实时数据经 WebSocket 推送，约 10 分钟环形缓冲，历史曲线随推送滚动更新。

> 操作逻辑要点：设备调节是「仿真模式」下最重要的交互——先进入仿真模式再调节，可随时退出恢复。`},{id:"strategy",title:"策略应用与仿真",body:`## 十、策略应用与仿真

系统提供三类策略，应用方式不同：

### 系统预置策略（内置）

1. 左侧「策略 → 内置」中点击目标策略（如「焦比优化」）。
2. 右侧出现策略属性面板，展示策略文本、理解的操作与预期减排效果。
3. 点击面板底部 **「策略仿真」** 按钮 → 自动进入仿真模式并解析执行该策略，场景右上角出现「对比浮层」显示基准与策略后的差异。
4. 满意后点击「保存策略」输入名称入库；或点击「退出仿真」恢复原状。

### 工艺绿色策略（内置 · 可启用）

1. 左侧「策略 → 内置」对应工艺分组下点击绿色策略。
2. 右侧面板中勾选 **启用** 开关 → 策略立即参与下一次仿真计算；再次取消勾选即停用。
3. 可在同一面板查看「所属工艺」并跳转到该工艺属性。

### 自定义策略（仿真保存）

1. 仿真模式下调整参数后，点击场景右上角「保存策略」，在命令行输入名称回车。
2. 该策略出现在左侧「策略 → 自定义」分组，带「自定义」标签。
3. 点击自定义策略 → 右侧面板可**编辑名称与数值调整**，点击「保存修改」生效，点击「策略仿真」重新加载执行。
4. 右侧 ✕ 按钮删除（需确认）。

### AI 生成策略（已支持）

- 内置策略面板、工序策略面板均提供**自然语言策略输入框**：输入如「焦比降低 5%」「喷煤提高 10%」，由 LLM 智能体（无密钥时自动回退本地引擎）解析为可执行参数操作，立即参与仿真计算。
- 解析结果展示为操作列表与置信度；无有效操作时提示重新描述。

### AI 优化模型（SEQ / RL / GA / PSO / CLU 在线训练）

- 入口：左侧「策略 → AI优化模型」分组，点击「模型列表（按类别）」或模型后右侧打开面板；关闭某个模型的面板时自动退回「模型列表（按类别）」。
- 模型列表按类别分组：**时序预测**（序列预测算法 SEQ）、**参数优化**（强化学习优化策略 RL / 遗传算法优化策略 GA / 粒子群优化策略 PSO）与**聚类分析**（聚类工况识别 CLU），点击卡片进入对应训练面板。
- **序列预测算法（SEQ）**：适用于预测未来工况，内置 LSTM / LightGBM / XGBoost（时间序列大模型暂不实现）。属性面板可切换预测模型、设定**预测目标**（全厂工况负荷或指定设备指标）与**影响变量**（参与预测的监测设备），设定最佳策略或调节变量进行仿真分析。
- **强化学习优化策略（RL）**：在线策略梯度，随实时数据先探索后利用。
- **遗传算法优化策略（GA）**：适用于设备启停与连续参数复合的混合场景，对启停开关与喷煤比、焦比等连续参数组合做选择/交叉/变异，全局搜索最低碳排配置。
- **粒子群优化策略（PSO）**：适用于连续参数空间下最优解的探索，粒子在参数空间协同飞行，快速逼近最优运行点。
- **聚类工况识别（CLU）**：适用于历史工况的自动聚类与模式划分，属性面板可选 K-Means / DBSCAN / 层次聚类，设定**聚类特征变量**（参与聚类的监测设备），自动识别低/中/高负荷典型工况及其占比，辅助制定分工况调节策略（只输出工况识别结果，不下发参数）。
- 策略模型（RL / GA / PSO）属性面板支持设定**决策变量**（勾选参与优化的工艺参数，未勾选保持当前设定值不参与寻优）与**优化目标**（吨钢碳强度 / 吨钢综合能耗 / 全厂 CO₂ 排放总量，均向最小化方向搜索），训练日志与最优参数以该目标指标为准。
- 右侧面板展示模型状态、迭代轮数、训练曲线（聚类模型为工况簇分布）、最优参数建议；支持「开始/暂停自动训练」「训练一轮」「重置模型」。
- 最优参数可直接「应用」到流程设备参与仿真；模型版本可保存、切换与归档。
- 关闭「自动化控制」时仅提醒不自动下发；开启后模型变优自动下发参数。

### 仿真模式的通用规则

- **进入**：点击「运行仿真」、输入 \`/sim\` 或执行任一「策略仿真」。
- **预览**：进入后所有参数修改仅作用于预览，不改动原始方案。
- **退出**：点击「退出仿真」或输入 \`stop\`，自动恢复进入前的全部状态。
- **自然语言（仿真模式命令行）**：在命令行窗口直接输入操作指令由智能体解析为操作（规划中），敬请期待。`},{id:"sim",title:"仿真运行与情景",body:`## 十一、仿真运行与情景

### 运行仿真

- 顶部「运行仿真」按钮或快捷键 **Ctrl+Enter**。
- 若已启用工艺策略 → 按策略重新计算；否则刷新全厂碳素流、能流与排放。
- 运行期间按钮变为「停止」，点击停止仿真循环。

### 情景切换

- 「文件 → 设置…」对话框 →「场景」区 →「仿真情景」选择情景（四大控排行业），点击后立即生效。
- 不同情景对应不同的工艺流程与排放水平（非钢铁情景当前为占位模型）。
- 「仿真 → 应用当前情景」按当前选中的情景重新计算并应用到场景。

### 重置

- 「仿真 → 重置仿真参数」重新计算回初始参数。
- 工具条「刷新视角」只复位相机，不影响仿真数据。

### 数据流说明

仿真计算链路：**设备运行参数 → 碳素流仿真引擎（后端）→ 各工序排放/能耗 → 全厂汇总 → 3D 热力图与检视器展示**。命令行会以 \`simulate >>\` 前缀输出每次计算的摘要。

### 数据视图

- 菜单「视图 → 数据」开关打开数据视图面板：中央 3D 场景替换为传感器历史数据表格。
- 左侧为「传感器」页签（每台有历史数据的计量/监测设备一个页签，显示实时读数）；右侧为当前传感器的实时读数、均值/峰值/谷值、采样点数与超限状态。
- 表格按时间列出读数、变化量与状态（超限 / 正常）；右上角 ✕ 关闭返回数字孪生。`},{id:"carbonmarket",title:"碳资产管理与市场快讯",body:`## 十二、碳资产管理与市场快讯

碳资产管理视图用于跟踪全国碳市场（CEA）与自愿减排市场（CCER）的价格走势，并一键生成碳资产管理报告，帮助评估碳成本、履约缺口、交易策略与减排收益。

### 打开碳资产管理视图

- 菜单「视图 → 碳资产管理」，中央 3D 场景替换为碳资产管理面板；
- 与「数据视图」互斥：打开碳资产管理会自动关闭数据视图，反之亦然；
- 点击视图右上角 ✕ 返回数字孪生；行情数据继续在后端缓存刷新。

### 行情卡片

顶部两张行情卡片实时展示（每 15 秒自动刷新，也可点击「刷新」手动更新）：

| 卡片 | 内容 |
| --- | --- |
| CEA · 全国碳排放配额 | 最新成交价、较昨收涨跌幅、成交量；附今开 / 最高 / 最低 / 昨日收 |
| CCER · 国家核证自愿减排量 | 最新成交均价、成交量；附最新价 / 数据源 / 成交量 / CEA 基准参考 |

- 标题栏右侧显示数据来源（上海环交所 / 北京绿交所）、更新时间，以及 **「实时数据」/「模拟行情」徽标**：外网不可用时自动回退为内置模拟数据并标注「模拟行情」；
- 行情接口使用 60 秒缓存，手动刷新可能滞后 1 分钟以内。

### 走势图

- 通过页签在 **CEA 日K线**（蜡烛图）与 **CCER 均价**（折线图）之间切换；
- **价格预测**：点击「预测 开/关」按钮可叠加 **未来 10 日线性回归预测**（虚线蜡烛 / 虚线折线）与置信带（±1.65σ 阴影），用于粗略预判价格区间；
- **图例**：历史数据（实线）与预测（虚线）分色区分；
- 图表底部滚动条提示实时刷新周期，并提供「查看官方页面 ↗」链接跳转交易所行情页。

### 碳资产报告

- 点击面板右上角「生成碳资产报告」按钮（或顶栏工具栏同名按钮），从右侧滑出报告中心；
- 选择**报告类型**：
  - **履约综合分析**：覆盖执行摘要、碳资产现状、履约合规分析、交易策略建议、价格预测与风险提示、减排路径与 CCER 机会、结论与下一步行动；
  - **碳交易简报**：聚焦 CEA/CCER 价格走势、成交概况、配额与 CCER 动态及近期交易信号；
  - **政策摘要**：梳理近期政策要点与市场快讯，说明对企业履约与交易节奏的影响；
- 选择**价格预测方法**：线性回归（含置信区间）/ 移动平均 / 指数平滑 SES，报告中的预测章节按所选方法生成；
- 填写报告标题、核算周期、分析重点（履约合规 / 交易策略 / 价格预测 / 政策研判 / 减排路径）与补充说明后提交；
- 提交后进入**运行中任务**卡片：实时显示进度条与阶段消息，可随时**取消**任务；完成后自动刷新历史列表并打开报告预览；
- 历史报告支持**关键字搜索、类型筛选与分页**；每条报告可**在线阅读（HTML 阅读页，新窗口/可打印）**、下载 Markdown 或删除；
- 打开报告时自动提炼「先看结论 / 执行摘要」章节，以结论卡片形式置顶展示。

### 市场快讯

- 主界面**底部状态栏**左侧滚动播报「市场快讯」摘要（煤炭 / 碳市场相关动态），无需打开碳资产管理视图即可看到；鼠标悬停滚动条可暂停滚动以便细读；
- 快讯数据由后端定时从中国煤炭交易网「市场快讯」栏目抓取（60 秒缓存，前端每 5 分钟刷新一次）；无外网或抓取失败时显示「快讯暂不可用」，不影响其它功能；
- 快讯的显示 / 隐藏可在「文件 → 设置 → 布局」中通过「快讯滚动条」开关控制。

> 操作逻辑要点：行情与快讯为**只读信息展示**，报告生成不会修改仿真数据；关闭视图不影响后端行情缓存继续刷新。`},{id:"datasettings",title:"数据源、系统设置与数据校准",body:`## 十三、数据源、系统设置与数据校准

本章讲解三类与运行环境相关的配置：实时数据从哪里来（数据源）、界面与仿真怎么调（系统设置）、监测读数如何标定（数据校准）。

### 数据源配置（文件 → 连接数据源…）

系统支持三种实时数据来源，在数据源配置对话框中切换：

| 类型 | 说明 | 配置项 |
| --- | --- | --- |
| Mqtt 实时 | 默认数据源：后端订阅云端 MQTT Broker（Broker 配置在「能碳一体机管理」视图前端配置）获取真实设备读数，不生成模拟数据 | 刷新间隔（默认 1 秒） |
| WebSocket | 连接外部实时数据服务 | 服务器地址 ws://…、端口、采样间隔；可「测试连接」验证连通性 |
| HTTP 轮询 | 定时轮询外部 REST 接口 | 接口地址、轮询间隔；可「测试连接」验证 |

- 每种数据源可独立设置**启停**与**采样间隔**；启用后主界面状态栏左侧实时链路指示灯随之变化；
- 对话框内每项均有「测试连接」按钮，点击后在对话框内显示连接结果（成功 / 失败原因），方便排查地址错误；
- 配置保存在本地工作区，重启后自动应用。

### 系统设置（文件 → 设置…）

设置对话框按页签分组：

| 页签 | 内容 |
| --- | --- |
| 布局 | 各功能面板（命令行 / 检视器 / 状态栏 / 快讯等）的显隐开关，取消勾选即时隐藏 |
| 场景 | **仿真情景**（四大控排行业，切换立即生效）与**场景环境**（虚空 / 工业 / 沙漠 / 城市 / 海滩） |
| 实时链路 | 数据源启停开关（与「连接数据源」对话框联动） |
| LLM | AI 功能的大模型配置：**模型名称**（如 glm-4-flash）、**API 密钥**、**API 地址**；用于自然语言解析、策略生成与 AI 报告 |

> 提示：LLM 配置为可选。未配置时自然语言功能使用本地规则兜底，AI 报告退化为本地模板模式，其余功能不受影响。

### 数据校准（工具 → 数据校准）

对监测设备进行可视化标定，修正读数偏差：

- **步骤 1 选择设备**：从下拉框选择要校准的计量 / 监测设备（仅显示有实时读数的设备）；
- **步骤 2 输入标定点**：至少输入两个标准值与设备当前读数的对应关系（如 标准值 100 ↔ 读数 95）；
- **步骤 3 计算并预览**：系统按线性回归拟合校准曲线，预览修正后的读数与误差；
- **步骤 4 应用**：点击「应用校准」保存，实时读数立即按新系数换算，检视器与趋势图同步更新；
- 校准结果持久化保存，重启后仍生效；可随时重新校准或「重置为出厂」。

> 操作逻辑要点：数据源决定「数据从哪来」，系统设置决定「界面与仿真怎么跑」，数据校准决定「读数准不准」——三者互不干扰，均可在运行中修改。`},{id:"flowedit",title:"流程编排",body:`## 十四、流程编排

编排模式用于拖拽式设计工艺流程图，编排完成后自动生成 3D 场景布局。

### 进入 / 退出编排

- 入口：菜单「编辑 → 进入流程编排」、工具条「流程编排」按钮或命令行 \`edit\`。
- 退出：菜单「编辑 → 完成编排」、工具条「完成编排」按钮或命令行 \`done\`。

### 画布操作

| 操作 | 方式 |
| --- | --- |
| 添加节点 | 从左侧「工艺 / 物料」中**拖拽**条目到画布（编排态下条目变为可拖拽） |
| 连接流程 | 从节点输出端口拖向另一节点输入端口画线 |
| 修改物料 | 双击节点端口弹出物料选择 |
| 右键菜单 | 右键节点或资源打开上下文菜单：选中 / 参数敏感性扫描 / 重命名 / 复制 / 删除 |
| 删除连线 | 点击选中连线后按 Del |
| 删除节点 | 点击节点右上角 ✕，或选中后按 Del |
| 重命名 / 复制节点 | 选中节点后按 F2 重命名、Ctrl+D 复制（编排模式） |
| 平移 / 缩放 | 画布空白拖拽平移，滚轮缩放 |
| 自动布局 | 工具条「自动布局」按钮一键整理布局 |
| 撤销 / 重做 | Ctrl+Z / Ctrl+Y（仅编排模式） |

### 小组与子编排

- 「编辑 → 新建小组」可将选中节点归组；组可整体拖动、复制、删除，双击小组卡片即可进入子编排，在组内嵌套编辑流程图。
- 小组在 3D 场景中呈现为独立布局区域。

### 示例与清空

- 工具条「长流程示例 / 短流程示例」一键载入完整示例流程。
- 「清空画布」删除画布全部内容（不可撤销，会二次确认）。

### 完成编排

点击「完成编排」回到 3D 场景，画布中的节点自动生成设施布局；此后仍可在左侧资产树中继续管理。`},{id:"cmd",title:"命令行窗口",body:`## 十五、命令行窗口

命令行是系统的「交互中枢」，输入后回车执行，反馈输出到上方日志区。

### 三种模式

| 模式 | 切换方式 | 用途 |
| --- | --- | --- |
| 聊天 | 默认 / \`/back\` 返回 | 直接输入自然语言与助手对话 |
| 代码 | \`/code\` | 以资深程序员助手身份回答编程问题 |
| 规划 | \`/plan\` | 把诉求拆解为有序可执行步骤 |

- \`/quit\`：退出当前模式回到聊天。
- \`/clear\`：清空日志区。

### 孪生控制命令（首词命中即执行）

| 命令 | 行为 |
| --- | --- |
| \`help\` | 输出全部命令说明 |
| \`run\` / \`sim\` | 运行仿真 / 进入仿真模式 |
| \`stop\` | 停止仿真 / 退出仿真模式 |
| \`reset\` | 重置相机视角 |
| \`overview\` / \`home\` | 相机回到全景 |
| \`view top|front|side|focus\` | 按预设视角聚焦当前选中工序 |
| \`edit\` | 进入流程编排 |
| \`done\` | 完成编排 |
| \`clear\` | 清屏 |

### 特殊流程：保存策略

仿真模式下点击场景「保存策略」后，命令行进入「等待输入名称」状态：

- 输入名称并回车 → 策略保存至「自定义」分组。
- 输入 \`cancel\` 或 \`取消\` → 放弃保存。

### 自然语言

- 聊天模式下：非命令内容直接对话。
- 仿真模式下：非命令内容交由智能体解析为仿真操作（规划中），命令行会提示规划进度。`},{id:"report",title:"报告生成与导出",body:`## 十六、报告生成与导出

### 前置条件

必须先运行过一次仿真（存在仿真数据），否则点击导出会提示「请先运行仿真」。

### 操作路径

1. 菜单「文件 → 导出分析报告」或顶栏右侧「导出」按钮（未运行仿真会提示先运行）。
2. 右侧打开「报告面板」，配置：
   - 报告标题（留空则自动拼接「策略名 · 场景」）；
   - 生成引擎：自动 / AI 生成 / 本地模板（AI 无密钥时自动回退本地模板）；
   - 分析深度：精简 / 标准 / 深入；
   - 是否包含「附录：全流程明细」表格。
3. 点击 **「生成报告」**，等待进度完成后查看。
4. 生成后可在面板内复制内容、下载 Markdown、或在**新页面打开 HTML 报告**（可打印/分享）。
5. 历史报告保存在报告列表，可再次查看或删除。

### 报告内容

报告基于当前仿真结果自动汇总：全厂能耗与碳排放总量、各工序排放分布、所应用策略的减排效果对比、优化建议（AI 引擎含数据洞察与策略评估段落）。所有数值表格由本地代码生成，保证精确可复现。`},{id:"faq",title:"快捷键与常见问题",body:`## 十七、快捷键与常见问题

### 快捷键速查

| 快捷键 | 功能 |
| --- | --- |
| Ctrl+Enter | 运行仿真 |
| Ctrl+S | 保存方案 |
| Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y | 撤销 / 重做（编排模式） |
| F | 聚焦当前选中的工序（3D 场景） |
| F1 | 在命令行输出操作指南速览 |
| Alt+T | 高炉数值分析（仅仿真模式） |
| F2 | 重命名选中节点（编排模式） |
| Ctrl+D | 复制选中节点（编排模式） |
| Del | 删除选中节点 / 连线（编排模式） |
| Esc | 关闭对话框 / 退出全屏 |

### 常见问题（Q&A）

**Q1：为什么点击导出报告提示「请先运行仿真」？**
报告需要仿真结果数据，请先按 Ctrl+Enter 或「仿真 → 运行仿真」执行一次计算。

**Q2：在设备上调节了参数，为什么退出仿真后参数又变回去了？**
这是仿真模式的预期行为——所有修改仅在预览层生效，退出时自动恢复原状。若希望保留，请在退出前点击「保存策略」将当前参数存为自定义策略。

**Q3：如何把调节好的参数保存下来复用？**
进入仿真模式 → 调节参数 → 点击场景右上角「保存策略」→ 命令行输入名称回车 → 之后在左侧「策略 → 自定义」中随时加载。

**Q4：左侧策略带「已启用」标签和带圆点的策略有什么区别？**
带「已启用」的是工艺绿色策略，通过右侧开关勾选参与计算；带圆点且可「策略仿真」的是系统预置策略，通过底部按钮测试执行。

**Q5：命令行输入命令没反应？**
请确认首词拼写与命令表一致（如 \`view focus\` 需要先选中工序）；非命令内容会走自然语言对话，不会当作命令执行。

**Q6：想撤销编排画布上误删的节点？**
编排模式下按 Ctrl+Z 可撤销（含删除操作）；注意「清空画布」不可撤销，操作前会二次确认。

**Q7：环境切换后 3D 场景没变化？**
环境主题（虚空/工业/沙漠/城市/海滩）只影响场景背景与氛围，不影响设施与仿真数据；若画面异常可用工具条「刷新视角」复位相机。

**Q8：碳市场行情显示「模拟」是怎么回事？**
行情接口优先从上海环交所（CEA）与北京绿交所（CCER）拉取真实数据；外网不可用或接口超时时自动回退为内置模拟数据，卡片右上角标注「模拟」提醒，不影响其它功能。

**Q9：状态栏的快讯想细看但一闪就过了？**
直接点击快讯文字即可弹出快讯详情弹窗，可翻看最近若干条资讯；快讯每 60 秒刷新一次，弹窗内数据为点击时的快照。

**Q10：切了「连接」面板后左侧没有数据源？**
先点击面板内「数据源配置」按钮，或在文件菜单「连接数据源…」中新建一个 WebSocket / HTTP 数据源并启用；默认「Mqtt 实时」数据源始终在线，其读数来自后端 MQTT 订阅的真实数据（Broker 配置在「能碳一体机管理」视图前端配置）。

**Q11：数据校准后读数变化很大，能恢复吗？**
可以。重新打开「工具 → 数据校准」→ 选择设备 → 点击「重置为出厂」，即可恢复系统默认量程与系数。`}],Rl=[{id:"arch",title:"系统技术架构",body:`# 工业能碳智控平台 · 技术文档（v2.1.0）

本平台是面向全国碳市场重点控排行业（钢铁、水泥、化工、有色及更多高耗能行业）的能碳数字孪生仿真系统，覆盖设备监控、碳素流仿真、碳排放核算与操作策略推荐四大能力。钢铁行业已率先全面落地，水泥、化工、有色等行业同步就绪，各行业工艺均支持自主流程建模与专属算法寻优。

## 一、总体架构

系统采用「前端可视化 + 后端计算引擎」的前后端分离架构：

| 层级 | 技术栈 | 职责 |
| --- | --- | --- |
| 前端 | Vue 3（Composition API）+ Vite + Pinia + Three.js | 3D 场景渲染、流程编排、实时遥测、策略提示 |
| 后端 | Python + FastAPI + Uvicorn | 碳素流仿真、碳排放核算、策略解析、报告生成 |
| 通信 | REST API + WebSocket + MQTT | 实时遥测下发、仿真结果回传、云端实时数据订阅 |
| 存储 | 内存缓存 + 本地文件 + TDengine 时序库 | 仿真缓存、策略库、历史报告、设备时序数据 |
| 云边协同 | K3s + KubeEdge（CloudCore / EdgeCore）+ 能碳一体机 | 边缘节点管理、设备模型下发、AI 模型远程部署 |

### 云边协同架构（v2.0.0 新增）

平台以「云端控制平面 + 边缘能碳一体机」的云边协同架构，打通真实生产数据链路：

- **云端控制平面**：K3s 轻量 Kubernetes + KubeEdge CloudCore 作为唯一控制平面；MQTT Broker（41883）汇聚设备实时数据，TDengine 时序数据库落盘历史读数，云端 cloud-agent 本地采集经 MQTT 长连接推送到平台；
- **边缘节点**：每台能碳一体机仅安装 EdgeCore（无本地控制平面），经 CloudHub 长连接云端，由 box-mapper 采集设备读数并以 MQTT 实时上报；
- **数据链路**：边缘实时读数 → 云端 MQTT Broker → 平台订阅解析 → WebSocket 推送前端 3D 场景，全链路秒级更新；历史数据经 TDengine 降采样后供趋势分析与报表回放。

## 二、目录结构

\`\`\`text
frontend/src/
  ├─ App.vue              # 主界面：顶栏菜单 / 活动栏 / 状态栏 / 3D 场景 / 检视器
  ├─ stores/sim.js        # Pinia 全局状态（流程、仿真、实验、撤销重做、活动栏/数据源/视图开关）
  ├─ stores/audit.js      # 碳素流守恒审计对话框状态
  ├─ utils/               # tft.js TFT算法 / energy.js 能耗 / markdown.js 渲染
  ├─ data/flowLibrary.js  # 设备耦合推导 deriveProcessOpParams
  ├─ three/scene.js       # TwinScene 3D 场景（环境/巡检/热力图/物流动画）
  ├─ api/client.js        # REST / WebSocket 客户端
  ├─ composables/         # useGlobalShortcuts 全局快捷键 / contextMenu 上下文菜单
  └─ components/          # 界面组件（见「前端可视化与交互」章节完整清单）

backend/
  ├─ app/
  │  ├─ main.py              # FastAPI 路由（REST + WebSocket + SPA 托管）
  │  ├─ carbon_engine.py     # 碳素流仿真引擎（RULES 注册表 + 缓存）
  │  ├─ calculators.py       # 能耗折算与排放因子计算
  │  ├─ factors.py           # 排放因子表
  │  ├─ devices.py           # 监测设备库（活动数据来源）
  │  ├─ realtime.py          # WebSocket 遥测推送 + 历史 ring buffer
  │  ├─ cloud_agent.py       # 云端数据代理（HTTP 42083 状态/CRD/时序库查询 + 缓存）
  │  ├─ mqtt_source/         # 云端 MQTT 订阅线程（cloud/state、cloud/crds、cloud/logs、data/# 解析）
  │  ├─ nl_parser.py         # 自然语言 → 策略操作（启发式）
  │  ├─ llm_strategy.py      # LLM 策略解析/对话（可选，无 Key 自动回退）
  │  ├─ llm_settings.py      # LLM 配置接口与密钥管理
  │  ├─ kb_settings.py       # 知识库设置
  │  ├─ param_schema.py      # 工序参数分级元数据
  │  ├─ carbon_market.py     # 碳市场行情服务（CEA/CCER 拉取 + TTL 缓存 + 价格预测）
  │  ├─ market_news.py       # 市场快讯服务（中国煤炭交易网爬取 + TTL 缓存）
  │  ├─ report.py            # AI 报告生成（骨架本地 + 分析 LLM）
  │  ├─ report_store.py      # 历史报告持久化
  │  ├─ md_render.py         # Markdown → HTML 分享页渲染
  │  ├─ presets.py           # 默认流程模型与示例策略
  │  ├─ optimizers.py        # AI 优化模型引擎（GA/PSO/RL 在线训练 + 版本管理）
  │  ├─ specs.py             # 设备规格档位
  │  ├─ store.py             # 策略持久化
  │  ├─ github_deploy.py     # 盒子一键接入（GitHub 托管 · 配置驱动）
  │  ├─ api/                 # REST 路由（overview / devices / box_router / help / tsdb 等）
  │  ├─ services/            # 业务服务层（部署、报告、行情、优化等）
  │  └─ models.py            # 前后端数据契约（Pydantic）
  ├─ config/                 # 统一配置目录：requirements.txt / run.sh / .env（LLM 密钥，不入库）/ strategies.json
  └─ data/reports/           # 历史报告输出

## 三、数据流

\`\`\`
设备遥测(WS) ──► 前端状态(Pinia) ──► 设备耦合推导(deriveProcessOpParams)
      │                                       │
      └──► 3D 场景 / 检视器 ◄── 仿真结果 ──► 后端碳素流引擎 / 碳排核算
                                                │
                                                └──► TFT 焓平衡 → 策略提示
\`\`\`

核心设计原则：**前端负责交互与可视化，后端负责守恒计算；所有设备调节均先走耦合推导再进入仿真，保证操作前后参数自洽。**`},{id:"carbon-flow",title:"碳素流仿真引擎",body:`## 碳素流仿真引擎

后端 \`carbon_engine.py\` 采用**设备级物料平衡**方法，通过规则注册表（RULES）驱动，逐设备核算碳素流与排放。

## 一、规则注册表机制

系统将所有核算规则集中注册，按「工序类型 → 计算函数」组织：

\`\`\`js
RULES: {
  sinter_plant:  烧结机核算（矿/燃料碳入 → CO2 排放 + 烧结矿带碳）
  blast_furnace: 高炉核算（焦炭/喷煤碳入 → 铁水渗碳 + 煤气带碳 + CO2）
  bof:           转炉核算（铁水碳 → 钢水固碳 + 炉气 CO2）
  ...
}
\`\`\`

每个工序的核算都遵循统一输出契约 \`UnitResult\`：
- \`carbon_in\`：tC/h 入炉碳；
- \`carbon_to_co2\`：tC/h 以 CO2 排出（燃烧 + 分解）；
- \`carbon_to_steel\`：tC/h 固结于钢（扣除项）；
- \`carbon_captured\`：tC/h 被捕集（CCS，碳捕集与封存，扣减项）；
- \`breakdown\`：核算明细台账（每项含 qty / basis / formula / co2）。

## 二、核算边界与守恒

- **总碳守恒**：入炉碳（焦炭 + 喷煤 + 炉料）恒等于 出铁碳 + 炉渣碳 + 炉顶煤气碳 + 捕集碳；
- **设备输入输出**：每个设备节点只允许「入口碳 = 出口碳 ± 变化量」，保证流经可追踪；
- **排放统计**：按范围一（燃烧/工艺/分解直接排放）与范围二（外购电间接排放）分类，汇总得到整炉碳排放强度（kgCO₂/t）；
- **碳利用率** \`carbon_utilization\`：固碳量 / 输入碳，用于衡量碳的利用效率。

## 三、缓存与性能

- 设备参数采用 **LRU（最近最少使用）缓存**（\`cached_simulate\`）：相同输入不重复计算，连续重复仿真（前端轮询/防抖后请求）命中缓存；
- 诊断端点 \`GET /api/cache/stats\` 返回缓存命中率；
- 计算粒度到设备级，支持单设备调节后快速重算（增量刷新）。

## 四、能耗输出（先能后碳）

引擎在碳核算之外同步输出能耗字段，遵循「先能后碳」主题：
- \`elec\`：MWh/h 电耗（外购电）；
- \`fuel_energy\`：GJ/h 燃料能耗（燃料燃烧低位热值之和）；
- \`energy_total\`：GJ/h 综合能耗（燃料 + 电折标，1 MWh = 3.6 GJ）；
- \`energy_intensity\`：kgce/t 单位产品综合能耗（综合能耗 × 34.12 / 主产物产量）。`},{id:"co2",title:"碳排放核算方法",body:`## 碳排放核算方法

依据 **GB/T 32151.5《钢铁生产企业温室气体排放核算方法与报告指南》** 与 **GHG Protocol**，采用**物料平衡法 + 排放因子法**相结合，活动数据来自监测设备，因子可配置。

## 一、排放源分类与范围

| 排放源 | 归属 | 说明 | 计算方法 |
| --- | --- | --- | --- |
| 燃料燃烧排放 | 范围一（直接） | 焦炭、煤粉、煤气、重油燃烧 | 活动数据 × 单位热值 × 含碳率 × 3.667 |
| 原材料分解排放 | 范围一（直接） | 石灰石/白云石分解 | 碳酸盐量 × 化学计量 |
| 工艺排放 | 范围一（直接） | 铁水渗碳、炉渣带走碳 | 产出量 × 含碳率 |
| 间接排放 | 范围二（间接） | 外购电力/热力 | 购入量 × 电网排放因子 |
| 扣减项 | 减排 | CCS（碳捕集与封存）捕集、余热回收、富氢替代 | 实际捕集/回收量扣减 |

## 二、碳排放台账（LedgerItem）

每个工序的排放结果附带**核算明细台账** \`breakdown\`，把「用了什么、因子多少、贡献多少 CO₂」逐项讲清楚：

\`\`\`text
item:    焦炭（入炉）
qty:     3360 t/h
basis:   NCV（低位发热量） 28.435 GJ/t × CC（单位热值含碳量） 0.0295 tC/GJ × 3.667
formula: 3360 × 28.435 × 0.0295 × 3.667 = 10331 tCO₂/h
co2:     10331
scope:   direct
\`\`\`

该结构使**每一个数字都可追溯**，满足审计与报告要求。

## 三、排放因子体系

默认因子表 \`factors.py\` 提供：
- **燃料参数**：NCV（低位发热量）、CC（单位热值含碳量）——焦炭、煤粉、天然气、BFG（高炉煤气）等；
- **电网因子**：外购电力排放因子；
- **碳酸盐/电极因子**：石灰石分解、电极消耗；
- 前端「数据」面板可查看因子表，仿真请求可携带自定义 \`factors\` 覆盖默认值。

## 四、技术修正项

- **CCS（碳捕集与封存）**：炉顶煤气中 CO₂ 捕集量从总排放中扣除；
- **余热回收**：回收热量折抵燃料燃烧排放；
- **富氢喷吹**：氢替代部分碳，降低碳素消耗，按氢还原份额折算减排量。

平台在右侧检视器 / 分析报告中展示各分项碳流占比与排放强度趋势。`},{id:"energy",title:"能耗计算（先能后碳）",body:`## 能耗计算（先能后碳）

节能减碳主题下平台遵循「**先能后碳**」：先核算能耗，再核算碳排放。能耗计算与后端 \`factors._energy_of\` 同源，前端 \`utils/energy.js\` 保持实现一致。

## 一、能耗构成

| 项目 | 单位 | 来源 |
| --- | --- | --- |
| 电耗 elec | MWh/h | 外购电力（智能电表活动数据） |
| 燃料能耗 fuel_energy | GJ/h | 燃料燃烧低位热值之和 |
| 综合能耗 energy_total | GJ/h | 燃料 + 电折标（1 MWh = 3.6 GJ） |
| 能耗强度 energy_intensity | kgce/t | 综合能耗 × 34.12 / 主产物产量 |

## 二、折标系数

\`\`\`js
// frontend/src/utils/energy.js
const CC_FUEL = { coke: 0.0295, coal: 0.0262, ng: 0.0153 }  // tC/GJ
const GJ_PER_MWH = 3.6     // 电折热
const KGCE_PER_GJ = 34.12  // 热折标煤（kgce/GJ）

// 由碳素流反推燃料能耗（当后端未直接返回时）：
fuel = carbon_by_fuel[k] / CC_FUEL[k]   // GJ/h
total = fuel + elec × 3.6
intensity = steel > 0 ? total × 34.12 / steel : 0
\`\`\`

前端优先采用后端返回的 \`energy_total / elec / fuel_energy / energy_intensity\` 字段；缺失时由台账 + 碳素流反推，保证离线与在线结果一致。

## 三、典型工艺能耗参考

- 高炉：燃料能耗占绝对主导（焦炭 + 喷煤），电耗为辅；
- 电炉（EAF，电弧炉）：电耗主导，燃料极少；
- 氢基直接还原：氢燃料能耗 + 电耗混合。`},{id:"devices",title:"监测设备库与活动数据",body:`## 监测设备库与活动数据

碳排放是**因变量**，由「活动数据（自变量）× 排放因子（系数）」算出。活动数据来自现场监测设备。

## 一、设备类型库（DEVICE_LIBRARY）

平台内置 8 类标准监测设备：

| 设备 | 测量对象 | 用途 |
| --- | --- | --- |
| 皮带秤 belt_scale | 固体质量流量 t/h | 矿、焦、煤、烧结矿等，碳核算「活动数据」主源头 |
| 失重秤 loss_in_weight | 粉料/喷吹质量 t/h | 高炉喷吹煤粉、熔剂精确给料 |
| 料斗秤 hopper_scale | 批料质量 t/批 | 焦比、喷煤比、熔剂比单耗实测 |
| 钢水/铸坯秤 weigher | 产品/半产品质量 t/h | 钢中固碳扣减与产量统计 |
| 气体流量计 gas_flowmeter | 气体体积流量 m³/h | BFG（高炉煤气）/LDG（转炉煤气）/天然气/氧气，燃料类直接排放活动数据 |
| 智能电表 power_meter | 电功率 MWh/h | 范围二（外购电）间接排放 |
| 成分分析仪 composition_analyzer | 物料成分/品位 | 精化排放因子（替代默认 CC 假设） |
| CEMS（烟气连续排放监测系统） cems | CO₂ 浓度×流量 | 点源直接监测法，因子法交叉校验 |

## 二、工序设备规格（_UNIT_DEVICE_SPECS）

每个工序按工艺挂载一组设备实例，每台设备声明：
- \`dev\`：设备类型；\`mount\`：3D 图挂载方位（feed/fuel/power/control）；
- \`measured\`：实测量中文说明；\`feeds\`：喂给引擎的输入/公式说明。

例如烧结机挂载：智能电表·主抽（喂 \`electricity\`）、成分分析仪·烧结矿（精化因子）。

## 三、检测设备去重原则

检测设备（只读监测）与**可调设备**（设定值 SP→测定值 PV）各有分工。若某检测设备监测的物理量恰为同工序可调设备的测定值，则该检测设备**不再内置**，避免双源数据冲突。平台仿真计算统一以可调设备**设定值为准**（输入框中的数字即工况值），测定值仅保留用于数据建模与真实 SCADA（数据采集与监视控制系统）场景。已去除的冗余检测设备包括：

- 烧结 / 球团 / 焦化的**皮带秤**（物料/燃料流量）→ 由 皮带机、给料机 的测定值覆盖；
- 高炉的**失重秤·喷吹煤**（喷吹煤粉量）→ 由 喷吹系统 的喷吹速率覆盖；
- 电炉 / 精炼炉的**智能电表**（电弧加热电耗）→ 由 电极调节器 的电弧功率覆盖。

保留的检测设备监测的均非可调设备测定值：气体流量计（煤气/天然气产量）、钢水秤/铁水秤（产量）、料斗秤（熔剂）、成分分析仪、CEMS（烟气连续排放监测系统），以及无电极调节器工序（烧结主抽/造球辊/炼焦/鼓风除尘/吹炼/电解制氢/结晶拉矫/轧制/压球压缩）的智能电表等。

## 四、模拟读数生成

\`compute_device_readings\` 依据工序活动数据生成模拟读数（\`reading\` 字段随仿真结果下发）。**接入真实工厂时，只需将该函数替换为读取 SCADA（数据采集与监视控制系统）/ EMS（能源管理系统）实测值**，其余管线不动。`},{id:"nlp",title:"自然语言策略解析",body:`## 自然语言策略解析

后端 \`nl_parser.py\` 将用户用自然语言描述的操作目标解析为**可执行的策略参数调整**，支持**双引擎**：LLM 引擎优先（需 API Key），失败自动回退确定性启发式引擎。

## 一、解析流程

\`\`\`
自然语言 ──► 分词/关键词匹配（LLM 或启发式）──► 操作拆解(5类) ──► 约束校验
      ──► ParsedOp 列表 ──► apply_ops 应用到流程 ──► 仿真对比
\`\`\`

## 二、五类操作（ParsedOp.action）

| 操作 | 语义 | 示例 |
| --- | --- | --- |
| replace_type | 工序换型 | 「高炉 改为 氢冶金」 |
| add_unit | 新增工序 | 「新增 一座 电炉」 |
| remove_unit | 删除工序 | 「删除 高炉」 |
| set_param | 修改参数 | 「焦比 降到 360」「喷煤 提高 15%」（absolute / relative 两种模式） |
| apply_tech | 应用技术 | 「应用 碳捕集」「应用 余热回收」 |

每条操作附带 \`note\`（给人看的自然语言描述）与 \`mode\`（absolute=绝对 / relative=相对百分比）。

## 三、关键词体系

- **工序关键词** UNIT_KEYWORDS：烧结机、高炉、转炉、电炉、氢基直接还原、熔融还原等 20 种；
- **参数关键词** PARAM_KEYWORDS：焦比、喷煤比、富氧率、热风温度、风量、矿比等 18 项；
- **技术关键词** TECH_KEYWORDS：碳捕集（ccs）、余热回收（waste_heat）、富氢喷吹（h2_inj）。

## 四、置信度

\`\`\`python
confidence = min(1.0, 0.4 + 0.15 × 操作数)
\`\`\`

识别到 1 个操作置信度 0.55，4 个以上即 1.0；无法解析时返回 warnings 提示，不下发空策略。

## 五、约束校验

解析结果必须通过设备可调域与耦合一致性校验后方可下发执行，防止出现「降温却提风温」等矛盾策略。`},{id:"llm",title:"LLM 智能体与 AI 报告",body:`## LLM 智能体与 AI 报告

平台在核心守恒计算**绝不依赖大模型**的前提下，用 LLM 增强两处**分析类**能力：策略解析与报告解读。

## 一、LLM 策略解析（llm_strategy.py）

- \`llm_parse\`：用结构化 Prompt 让 LLM 把自然语言拆解为 \`ParsedOp\` 列表；
- 无 API Key / 超时 / 输出异常 → **自动回退启发式引擎**（nl_parser），保证离线可用；
- 返回 \`engine: "llm" | "heuristic"\` 标记实际使用的引擎。

## 二、AI 报告生成（report.py）——双引擎架构

\`\`\`python
_ENGINE_LLM = "llm"        # LLM 分析段落
_ENGINE_TEMPLATE = "template"  # 确定性模板回退
\`\`\`

**核心原则：报告骨架与所有数值表格由本地代码生成（数字精确、可复现、无幻觉）；执行摘要 / 数据洞察 / 策略效果评估 / 优化建议等分析段落由 LLM 基于给定数据撰写。**

- LLM 只负责「解读与建议」，不参与数字计算；
- 无 Key / 超时 / 输出异常时自动回退确定性文案。

## 三、报告生成流程（异步任务）

1. 前端提交 \`POST /api/report\`（baseline / strategy / 参数配置）；
2. 后端**后台线程**执行，按段回调进度（\`progress_cb\`）；
3. 前端轮询 \`GET /api/report/task/{id}\` 获取 \`{done, progress, stage, result}\`；
4. 完成后写入历史库（\`report_store\`），返回分享 URL。

## 四、报告配置项

| 配置 | 取值 | 说明 |
| --- | --- | --- |
| engine | auto / llm / template | 分析段落引擎 |
| depth | brief / standard / deep | 详细程度分级 |
| with_appendix | true/false | 是否含「附录：全流程明细」 |
| title | 自定义 | 空则自动拼接「策略名 · 场景」 |

## 五、报告分享页

\`GET /report/{rid}\` 将历史报告 Markdown 渲染为**独立 HTML 分享页**（新标签页查看/打印），可分享给他人审阅。`},{id:"tft",title:"TFT 理论燃烧温度算法",body:`## TFT 理论燃烧温度焓平衡算法（含讲解实例）

TFT（Theoretical Flame Temperature，理论燃烧温度）是高炉风口回旋区燃烧热状态的量化指标。本平台采用**焓平衡 + 氧限制**方法计算，支持焦炭、喷煤、重油、煤气等固/液/气多燃料混合燃烧场景。

## 一、物理模型与边界假设

在风口回旋区，鼓风中的氧与燃料在高温下发生**缺氧不完全燃烧**，主要产物为 CO 与 H2O：

- 碳的燃烧为 **C → CO**（非 C → CO2），每 kgC 放出 **9.79 MJ** 热量；
- 氢的燃烧为 **H → H2O**，每 kgH 放出 **120 MJ** 热量；
- 缺氧环境下氢并非全部燃烧，仅按比例 \`hCombRatio\`（默认 0.6）燃烧，其余氢以 H2 形式进入炉缸煤气；
- 燃料中原生 CO 不参与二次燃烧；
- **鼓风氧是燃烧耗氧的唯一来源**，燃料碳氢超出鼓风氧供给能力的部分视为未燃，不计放热与产气（避免 TFT 虚高）。

## 二、算法常量（TFT_CONST）

\`\`\`js
const TFT_CONST = {
  Q_C_CO: 9.79,      // C→CO 燃烧热 MJ/kgC
  Q_H_H2O: 120,      // H→H2O 燃烧热 MJ/kgH
  V_CO_PER_C: 1.867, // C→CO 产气系数 Nm³/kgC（1 kgC = 83.33 molC → 1.867 Nm³CO）
  V_H2O_PER_H: 11.2, // H→H2O 产气系数 Nm³/kgH（1 kgH = 0.5 kmolH2 → 11.2 Nm³H2O）
  Q_CH4: 35.88,      // CH4 燃烧热 MJ/Nm³
  Q_C2H6: 63.74,     // C2H6 燃烧热 MJ/Nm³
}
\`\`\`

## 三、默认工况参数（TFT_PARAM_DEFAULTS）

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| hot_blast_temp | 1250 ℃ | 热风温度 |
| wind_rate | 600 kNm³/h | 风量（绝对供风量） |
| o2_flow | 0 Nm³/h | 纯氧流量（氧枪注入主风管，与鼓风真实混合） |
| oxygen_enrich | 0 % | 富氧率（富氧增量，由 o2_flow + 风量 + 铁水产量派生，只读） |
| hot_metal | 8000 t/h | 铁水产量 |
| coke_rate | 360 kg/tFe | 焦比 |
| coal_inj | 150 kg/tFe | 喷煤比 |

比风量口径：比风量 = 鼓风量 ÷ 铁水产量 = wind_rate(kNm³/h) × 1000 ÷ hot_metal(t/h)，单位 **Nm³/tFe**（2026-08 变更：由"相对倍率基准"改为真实供需推导，TFT 现随铁水产量变化）。

其中 **鼓风量 = wind_rate（kNm³/h，绝对供风量）**、**铁水产量 = hot_metal（t/h，系统实际值）**。比风量由二者真实比值推导，因此 TFT 现随铁水产量变化：相同鼓风量下产量越低、比风量越大、TFT 越高（反之亦然）。系统实际产量示例 8000 t/h；本讲解实例按该真实产量手算，与系统一致。

## 四、焓平衡方程与变量说明

TFT 的物理意义：假设风口燃烧放出的热量**全部**用于加热生成的炉腹煤气（无散热、无对外做功），煤气所能达到的温度。这是热力学第一定律 Q = m·cp·ΔT 的反推——把煤气视作从 0℃ 被加热到 TFT，故 ΔT = TFT：

\`\`\`
TFT = Q_total_in / (V_gas_total × cp)
\`\`\`

| 变量 | 中文含义 | 单位 | 计算来源 |
| --- | --- | --- | --- |
| TFT | 理论燃烧温度：燃烧放热全部转化为煤气显热时煤气能达到的温度 | ℃ | Q_total_in ÷ (V_gas_total × cp) |
| Q_total_in | 风口回旋区总收入热（鼓风显热 + 燃烧放热） | MJ/tFe | Q_sensible_air + Q_combustion |
| V_gas_total | 炉腹煤气总量（CO + H2O + H2 + 惰性组分 + 鼓风 N2） | Nm³/tFe | V_CO + V_H2O + V_H2 + V_inert + V_N2_blast（见本节分母构成） |
| cp | 炉腹煤气定压比热：1 Nm³ 煤气升温 1℃ 所需热量 | MJ/(Nm³·℃) | 默认 0.0015，可随煤气组分微调 |

**分子（收入热）各项：**

| 变量 | 中文含义 | 单位 | 计算来源 |
| --- | --- | --- | --- |
| Q_sensible_air | 鼓风显热：热风本身携带的物理热，随鼓风带入炉内 | MJ/tFe | B × cpAir × t_blast |
| B | 比风量：每吨铁水对应的鼓风量，是整条计算链路的"脊柱" | Nm³/tFe | 鼓风量/铁水产量 = wind_rate×1000 ÷ hot_metal（kNm³/h ÷ t/h） |
| cpAir | 鼓风（空气）定压比热 | MJ/(Nm³·℃) | 默认 0.0013 |
| t_blast | 热风温度（对应系统参数 hot_blast_temp） | ℃ | 默认 1250 |
| Q_combustion | 燃料燃烧净放热 = 碳燃烧放热 + 氢燃烧放热 - 热解吸热 + 气体燃料放热 | MJ/tFe | C_burn×9.79 + H_total×120×hCombRatio - decomp_heat + Q_gas_fuel |
| C_burn | 实际燃烧的碳量（受鼓风氧限制，见 §五） | kgC/tFe | min(C_total, C_burnable) |
| H_total | 固/液燃料带入的氢总量 | kgH/tFe | Σ(用量 × 含氢率) |
| hCombRatio | 氢的燃烧比例：缺氧下仅部分氢烧成 H2O，其余以 H2 直接进炉腹煤气 | 无量纲 | 默认 0.6 |
| decomp_heat | 燃料热解吸热：喷吹燃料入炉先分解吸热 | MJ/tFe | Σ(用量 × 单位热解吸热) |
| Q_gas_fuel | 气体燃料（如焦炉煤气）燃烧放热，无气体燃料时为 0 | MJ/tFe | Σ(组分体积 × 组分燃烧热) |

**分母（炉腹煤气）构成：**

| 变量 | 中文含义 | 单位 | 计算来源 |
| --- | --- | --- | --- |
| V_CO | 燃烧生成的 CO 量 | Nm³/tFe | V_CO_solid × burnRatio + V_CO_gas |
| V_H2O | 燃烧生成的 H2O 量 | Nm³/tFe | V_H2O_solid × hCombRatio + V_H2O_gas |
| V_H2 | 未燃烧的 H2 量（直接进炉腹煤气） | Nm³/tFe | V_H2O_solid × (1 - hCombRatio) |
| V_inert | 燃料自带的 N2、CO2 等惰性组分 | Nm³/tFe | Σ(燃料惰性组分 × 用量) |
| V_N2_blast | 鼓风带入的 N2（占空气约 79%，不燃烧但同样被加热） | Nm³/tFe | B × N2_blow |

## 五、燃烧份额：鼓风氧限制

碳能烧多少**不由燃料决定，而由鼓风氧决定**。鼓风是回旋区唯一的氧源：氧先供氢燃烧，剩余氧再供碳燃烧，超出氧供给能力的碳视为未燃（不计放热、不计产气）：

\`\`\`
V_O2_blast = B × O2_blow                         // 鼓风总氧，Nm³/tFe
O2_for_H = 0.5 × V_H2O_solid × hCombRatio        // 氢燃烧耗氧
O2_for_C_avail = max(0, V_O2_blast - O2_for_H)   // 剩余氧供碳
C_burnable = O2_for_C_avail / 0.9333             // 氧可支撑的碳燃烧量，kgC/tFe
C_burn = min(C_total, C_burnable)                // 实际燃烧碳
burnRatio = C_burn / C_total                     // 碳燃烧份额
\`\`\`

| 变量 | 中文含义 | 单位 | 计算来源 |
| --- | --- | --- | --- |
| O2_blow | 鼓风绝对氧浓度 = 空气氧 21% + 富氧增量 | 体积分数 | 0.21 + 0.01 × wO |
| wO | 富氧率：相对空气 21% 的提升量（系统口径） | % | 默认 0，范围 0~14 |
| N2_blow | 鼓风氮气浓度（惰性，不燃烧但被加热吸热） | 体积分数 | 1 - O2_blow |
| V_O2_blast | 每吨铁的鼓风总氧量 | Nm³/tFe | B × O2_blow |
| V_H2O_solid | 固/液燃料氢若全部燃烧的理论 H2O 产气 | Nm³/tFe | 11.2 × H_total |
| O2_for_H | 氢按 hCombRatio 燃烧所消耗的氧 | Nm³/tFe | 0.5 × V_H2O_solid × hCombRatio |
| O2_for_C_avail | 扣除氢耗氧后、可供碳燃烧的剩余氧 | Nm³/tFe | max(0, V_O2_blast - O2_for_H) |
| 0.9333 | 每 kgC 燃烧成 CO 的耗氧量（1 kgC = 83.33 mol，需 41.67 mol O2） | Nm³ O2/kgC | 常数 |
| C_burnable | 鼓风氧最多能支撑燃烧的碳量 | kgC/tFe | O2_for_C_avail ÷ 0.9333 |
| C_total | 固/液燃料总碳（焦炭碳 + 煤粉碳） | kgC/tFe | Σ(用量 × 含碳率) |
| C_burn | 实际燃烧碳量（总碳与氧能力的较小者） | kgC/tFe | min(C_total, C_burnable) |
| burnRatio | 碳燃烧份额：实际燃烧碳占总碳的比例 | 无量纲 | C_burn ÷ C_total |

每 kgC 生成 1.867 Nm³ CO 需耗 0.9333 Nm³ O2；每 kgH 燃烧成 H2O 需耗 0.5 Nm³ O2 / Nm³ H2O。

## 六、比风量在计算中的作用：同时控制分子与分母

比风量 B（Nm³/tFe）即"每吨铁的送风强度"，从两个方向同时影响 TFT：

| 通道 | 机制 | 对 TFT 的影响 |
| --- | --- | --- |
| 供氧（分子） | B 越大 → V_O2_blast 越大 → 可烧碳越多 → 燃烧放热越多 | 升温 |
| N2 稀释（分母） | B 越大 → V_N2_blast 越大 → 惰性 N2 吸热越多 → 煤气总量越大 | 降温 |

不富氧时两条通道几乎相互抵消（风量翻倍，供氧与 N2 同步翻倍，碳/氮比值不变），所以 **TFT 对风量不敏感，风量主要用于调节产量**；真正有效调节 TFT 的手段是**富氧率**（提高氧浓度、压缩 N2 占比）与**风温**（直接增大鼓风显热）。讲解实例中 V_N2_blast = 790 Nm³/tFe 占煤气总量 1238.4 的 64%，正是这一作用的直观体现。

## 七、为什么焦炭/煤粉的"燃烧率"不影响 TFT

### 1. 概念澄清

"燃烧率"（燃尽率）指燃料中真正在风口燃烧的比例。真实高炉中二者差异很大：

| 燃料 | 风口燃烧率（典型值） | 未燃部分去向 |
| --- | --- | --- |
| 焦炭 | 仅 25%~40% | 进入炉缸：渗碳（铁水含碳 ~4.5%）、死焦层骨架、渣铁界面反应 |
| 喷吹煤粉 | 90%+（要求高燃尽率） | 少量未燃煤粉，量很小 |

### 2. 当前系统模型：合并总碳池，统一受氧限制

系统不区分焦/煤各自的燃烧率，把所有燃料碳合并为总碳 C_total，再统一取 C_burn = min(C_total, C_burnable)。只要 C_burnable < C_total（本例 202.1 < 414），实际燃烧碳就完全由鼓风氧钉死，与焦/煤如何分配无关。

### 3. 数学证明：燃料分配在分子分母中被约掉

把 TFT 分子分母中所有燃料相关项展开：

| 项 | 公式 | 展开后 | 结论 |
| --- | --- | --- | --- |
| 碳燃烧放热（分子） | C_burn × 9.79 | = 202.1 × 9.79 | 只依赖总量 C_burn |
| CO 产气（分母） | V_CO_solid × burnRatio | = 1.867 × C_total × (C_burn/C_total) = **1.867 × C_burn** | C_total 被约掉，只依赖 C_burn |
| H2O + H2 产气（分母） | V_H2O_solid×hc + V_H2O_solid×(1-hc) | = V_H2O_solid = 11.2 × H_total | hc 被自身抵消，只依赖总量 |
| N2（分母） | B × N2_blow | — | 与燃料无关 |

所以 TFT 的分子分母中，**燃料相关项全部只出现 C_burn 与 H_total 两个总量**：C_burn 被氧钉死、H_total 是焦煤加权成分——"这 202.1 kgC 里焦炭占多少、煤粉占多少"在数学上被约掉了。

### 4. 若显式引入独立燃烧率，会发生什么

假设给焦炭设 35%、煤粉设 92%（行业典型值）：

\`\`\`
可燃烧碳 = 306×0.35 + 108×0.92 = 206.5 kgC/tFe ＞ 氧能力 202.1
C_burn = min(C_total, ...) 仍取氧能力 202.1 → TFT 不变
\`\`\`

只有当组合后"可燃烧碳"低于氧能力时才生效：

\`\`\`
若焦炭率压到 20%：可燃烧碳 = 306×0.20 + 108×0.92 = 160.6 ＜ 202.1 → 供碳不足，TFT 下降
\`\`\`

### 5. 为什么真实高炉也适用"氧限制"模型

真实高炉稳态恰好运行在氧限制边界附近：煤粉 90%+ 燃尽率 + 焦炭 25~40% 燃烧率，两者合计刚好"喂饱"鼓风氧（≈206.5 ≈ 202.1）。这就是行业用"氧限制 + 部分燃烧"模型即可很好预测 TFT 的原因——高炉稳态本身就是一个被氧喂饱的系统。

### 6. 什么情况下必须显式考虑燃烧率

| 场景 | 原因 |
| --- | --- |
| 炉缸碳平衡 | 未燃焦炭（本例占 51.2%）的去向——渗碳、死焦层消耗，直接影响碳素流 |
| 炉顶煤气成分 | 焦/煤燃烧率影响 CO/CO2 比 → 间接还原度、煤气热值（BFG 发电量） |
| 喷煤极限 | 提高喷煤比时煤粉燃尽率下降才是限制喷煤量的关键 |

## 八、热状态判定规则

| 状态 | 判定条件 | 含义 | 处置方向 |
| --- | --- | --- | --- |
| 正常 | tftLow ≤ TFT ≤ tftHigh | 热制度稳定 | 维持 |
| TFT 偏低 | TFT < tftLow（默认 2050℃） | 燃烧能量不足、炉温偏凉 | 升温 |
| TFT 偏高 | TFT > tftHigh（默认 2250℃） | 风口过热、炉况热过载 | 降温 |

阈值 \`tftLow/tftHigh\` 可随炉役与冶炼品种配置。

## 九、讲解实例（手算推演）

**工况设定**：热风温度 1250℃，风量 600 kNm³/h（= 相对 1.0），富氧率 0%（无富氧），铁水产量 40 tFe/h（手算标定基准，见上节说明）；焦比 360 kg/tFe，喷煤比 150 kg/tFe。

| 燃料 | 固定碳 FC | 氢 H | 热解吸热 | 用量 |
| --- | --- | --- | --- | --- |
| 焦炭 | 0.85 | 0.001 | 0 | 360 kg/tFe |
| 喷吹煤粉 | 0.72 | 0.04 | 0.35 MJ/kg | 150 kg/tFe |

**第 1 步 · 比风量与鼓风氧**

\`\`\`
QB = 1.0 × 40000 = 40000 Nm³/h
PFe = 40 tFe/h
B = 40000 / 40 = 1000 Nm³/tFe
O2_blow = 0.21
N2_blow = 0.79
V_O2_blast = 1000 × 0.21 = 210 Nm³/tFe
\`\`\`

**第 2 步 · 燃料碳氢总量与理论产气**

\`\`\`
C_total = 360×0.85 + 150×0.72 = 306 + 108 = 414 kgC/tFe
H_total = 360×0.001 + 150×0.04 = 0.36 + 6.0 = 6.36 kgH/tFe
decomp_heat = 0 + 150×0.35 = 52.5 MJ/tFe
V_CO_solid = 1.867 × 414 = 772.9 Nm³/tFe
V_H2O_solid = 11.2 × 6.36 = 71.2 Nm³/tFe
\`\`\`

**第 3 步 · 鼓风氧限制下的实际燃烧碳**

\`\`\`
O2_for_H = 0.5 × 71.2 × 0.6 = 21.36 Nm³/tFe
O2_for_C_avail = 210 - 21.36 = 188.64 Nm³/tFe
C_burnable = 188.64 / 0.9333 = 202.1 kgC/tFe
C_burn = min(414, 202.1) = 202.1 kgC/tFe
burnRatio = 202.1 / 414 = 0.488（仅约 48.8% 的碳实际燃烧）
\`\`\`

**第 4 步 · 放热与产气**

\`\`\`
Q_sensible_air = 1000 × 0.0013 × 1250 = 1625 MJ/tFe
Q_combustion = 202.1×9.79 + 6.36×120×0.6 - 52.5
             = 1978.6 + 457.9 - 52.5 = 2384.0 MJ/tFe
V_CO = 772.9 × 0.488 = 377.2 Nm³/tFe
V_H2O = 71.2 × 0.6 = 42.7 Nm³/tFe
V_H2 = 71.2 × 0.4 = 28.5 Nm³/tFe
V_N2_blast = 1000 × 0.79 = 790.0 Nm³/tFe
V_gas_total = 377.2 + 42.7 + 28.5 + 790.0 = 1238.4 Nm³/tFe
\`\`\`

**第 5 步 · 计算 TFT 并判定**

\`\`\`
Q_total_in = 1625 + 2384.0 = 4009.0 MJ/tFe
TFT = 4009.0 / (1238.4 × 0.0015) = 4009.0 / 1.8576 ≈ 2158 ℃
\`\`\`

**判定**：2050 ≤ 2158 ≤ 2250 → **热制度正常**，无需调整。

**引申 · 若 TFT 偏低如何操作**：平台通过设备调节预览逐项探测（风温 +30℃、风量设定 +520 m³/h（约 +60 kNm³/h）、喷煤量 ±20 kg/h 等），保留使 TFT 升高的调节作为建议——例如提高热风温度可同时增大鼓风显热并提升燃烧温度，是降温工况下的首选升温手段。

## 十、TFT 约束下的节能减碳策略

### 1. 本质：TFT 是约束，减碳是目标

节能减碳不是"随便降燃料"，而是**在 TFT 钉在合规区间（2050~2250℃）的前提下，最小化每吨铁水的碳投入**。TFT 是约束条件（硬边界），减碳是目标函数，二者通过四个可调旋钮联动：

\`\`\`
TFT = (鼓风显热 + 燃烧放热 - 热解吸热) / (煤气总量 × cp)
        ↑热风         ↑焦/煤/油              ↑N2 稀释
\`\`\`

### 2. 四大旋钮：作用与减碳逻辑

| 旋钮 | 对 TFT 的影响 | 减碳逻辑 |
| --- | --- | --- |
| 热风炉·风温 ↑ | 鼓风显热↑ → TFT ↑ | 不直接减碳，但**免费热量顶替焦炭燃烧放热**：风温每 +50℃ 可降焦比 8~12 kg/tFe |
| 鼓风机·富氧 ↑ | 分母 N2↓ + 供氧↑ → TFT ↑↑ | 压缩惰性 N2、提高单位风量燃烧能力，为降焦比/提喷煤腾出 TFT 空间（富氧耗电，需权衡间接排放） |
| 喷吹·喷煤比 ↑ | 热解吸热 + 产 H2O 稀释 → TFT ↓ | 煤粉碳含量（0.72）< 焦炭（0.85），替代焦炭大幅降焦比，**最大减排杠杆** |
| 鼓风机·风量 ↑ | 供氧与 N2 同步变化，近抵消 | 产量通道，TFT 基本不变，减碳贡献小 |

### 3. 标准减碳操作路径（四步）

**第 1 步 · 风温打满**：热风温度提到上限，鼓风显热↑ → TFT↑，**创造减碳空间**（成本最低、零碳排放的升温手段）。

**第 2 步 · 用 TFT 空间换碳**：空间出现后降焦比——焦比每降 10 kg/tFe ≈ 少投入 8.5 kg 焦炭碳 ≈ 减排 31 kgCO2/tFe（×3.667）；同时增喷煤比替代等热量焦炭。两项措施都会使 TFT 回落，正好消耗第 1 步的空间——**每项减碳措施都从分子扣热量，扣到 TFT = tftLow 就是减碳极限**。

**第 3 步 · 富氧兜底**：焦比压到下限、喷煤受 TFT 限制上不去时，提富氧率压缩 N2 分母 → TFT 回升 → 释放新一轮降焦/提煤空间（富氧的代价是制氧电耗，是否划算看电价与焦炭价差）。

**第 4 步 · 监控闭环**：全程盯 TFT 状态——偏低 → 提风温/提富氧/降喷煤；正常 → 继续试探性降焦比；偏高 → 本身即是减碳信号，优先降焦比。

### 4. 为什么 TFT 下限是减碳的天然护栏

利用燃烧份额的氧限制特性：焦比降太多时，燃料总碳 C_total 低于鼓风氧能力 C_burnable，供碳不足，TFT 会直线下跌至阈值以下——**TFT 下限就是减碳的物理底线，炉况自行拦截，无需人为设指标**。

### 5. 平台实现

「高炉数值分析」面板对每个可调参数做全范围扫描，绘制 TFT 响应曲线（含合规区间带与当前工况点），直观展示：风温曲线线性上升、富氧曲线加速上升、风量曲线近水平（供氧/N2 抵消）、焦比曲线近水平（氧限制钉死 C_burn，降焦比零温度代价）、喷煤曲线缓降（热解吸热 + 稀释）。结合 TFT_DEVICE_PROBES 设备探测与后端 carbon_engine 碳素流核算，每次调整可同时看到 TFT 与 CO2 变化，形成"温度合规 + 碳减排"双目标闭环。`},{id:"coupling",title:"设备耦合参数推导",body:`## 设备耦合参数推导

设备调节不能孤立生效——改变鼓风机风量会牵动热风炉风温、喷吹系统喷煤等上下游工序参数。前端 \`flowLibrary.js\` 中的 \`deriveProcessOpParams\` 负责**从设备设定反推全局工序参数**，保证仿真自洽。

## 一、推导语义

\`\`\`js
deriveProcessOpParams(unitType, devices, baseParams) → overrides
\`\`\`

- 输入：工序类型、设备调节列表（类型 + 设定值）、当前工序参数；
- 输出：受影响的工序参数覆盖集（如 hot_blast_temp、wind_rate、oxygen_enrich 等）。

## 二、典型耦合关系

| 设备调节 | 影响工序参数 | 说明 |
| --- | --- | --- |
| 热风炉 · 风温 | hot_blast_temp | 直接决定鼓风显热 |
| 鼓风机 · 风量 | wind_rate | 改变比风量，影响 TFT 与煤气量 |
| 鼓风机 · 鼓风湿度 | blast_humidity | 鼓风含湿（加湿/脱湿）参与水分分解吸热，湿度↑→TFT↓、焦比↑ |
| 喷吹系统 · 喷煤量 | coal_inj | ~~可调~~ 已锁定：随工况设定固定，富氧率提升时自动联动增加，不再作为可调项 |

## 三、TFT 设备探测（TFT_DEVICE_PROBES）

TFT 策略模块通过**设备级探测**评估每个可调设备的调节效果：

\`\`\`js
const TFT_DEVICE_PROBES = [
  { type: 'hot_blast_stove', label: '热风炉·风温',   step: 30,  unit: '℃' },
  { type: 'blower',           label: '鼓风机·风量',   step: 520, unit: 'm³/h' },
  { type: 'blower',           label: '鼓风机·鼓风湿度', step: 1, unit: 'g/Nm³', extraKey: 'humidity', def: 10 },
  // 喷吹系统·喷煤量已锁定不可调，不再列入探测
]
\`\`\`

对每个设备按 step 试探调节，经 \`deriveProcessOpParams\` 折算后重新计算 TFT，保留使热状态回到正常区间且 ΔTFT 最大的调节作为推荐。

## 四、设备建议与系统建议

- \`buildDeviceTftAdvices\`：针对单个设备的调节建议（含 ΔTFT 预测）；
- \`buildSystemTftAdvices\`：全局视角（正常时提示维持现状）；
- 两类建议均标注方向（升温 ↑ / 降温 ↓ / 维持 ✓）与调节量。

## 五、实时参数折算

\`buildRealtimeTftParams\` 将「工序基础参数 + 当前实际设备设定（含附加可调项）」折算为 TFT 实时计算参数，与系统 \`refresh()\` 的折算语义一致——**拖动可调设备滑块后，TFT 面板与仿真结果实时一致**。`},{id:"telemetry",title:"实时遥测系统",body:`## 实时遥测系统

后端 \`realtime.py\` 负责 WebSocket 长连接推送与监测设备历史时序（内存 ring buffer）。

## 一、架构

| 组件 | 职责 |
| --- | --- |
| FeedManager | 维护当前活跃 WebSocket 连接集合 |
| DEVICE_HISTORY | 每台设备最近读数的内存环形缓冲（**600 点 ≈ 10 分钟**，1Hz 采样） |
| ws_feed | 客户端连接后每秒推送带噪声的实时遥测帧 |
| seed_history | 流程变更/启动时回填设备历史基线，保证首屏即有趋势数据 |

## 二、WebSocket 协议

\`\`\`json
// 客户端 → 服务端（设定当前流程）
{ "type": "model", "model": { "units": [...], "flows": [...] } }

// 服务端 → 客户端（每秒一帧）
{
  "devices": [{ "id", "unit_id", "label", "type", "reading", "unit" }, ...],
  "units": [...]
}
\`\`\`

- 客户端发送 \`type:'model'\` 设定流程后，服务端重新 \`seed_history\` 并基于该流程持续推送；
- 流程变更 → 自动重建设备历史基线。

## 三、模拟噪声

\`\`\`python
def _noise(v, pct=0.04):
    return max(0.0, v * (1 + random.uniform(-pct, pct)))
\`\`\`

- 实时帧：基准读数 ×（1 ± 4%）随机抖动，模拟真实仪表抖动；
- 历史回填（seed）：×（1 ± 5%）抖动生成 180 秒趋势；
- 读数由**活动数据**算出基准值，再叠加时间噪声。

## 四、历史查询

前端「数据 → 设备历史」图表数据来自 \`DEVICE_HISTORY\`（或 \`GET /api/devices/history\`），展示每台设备近 10 分钟趋势。

## 五、数据源支持

平台支持三种数据源（文件 → 连接数据源…）：
1. **Mqtt 实时**：默认数据源，后端订阅云端 MQTT Broker（Broker 配置前端化：能碳一体机管理界面 → 配置 Broker；链路：边缘盒子（能碳一体机）box-mapper 仪表采集 → 实时发布 Broker \`data/{box}/{device}/{instance}/{property}\` 主题）获取真实设备读数，不生成模拟数据；边缘 mapper 云边断连恢复后的补传历史（带真实采集时间戳）也经 \`data/#\` 回填平台折线图缺口；
2. **自定义 WebSocket**：外部系统推送（接入真实工厂时使用）；
3. **HTTP 轮询**：REST 拉取。

### 能碳一体机管理台 API

| 接口 | 返回要点 |
| --- | --- |
| GET /api/box/overview | 概览：\`{ broker:{connected,stats($SYS 真实统计)}, cloudcore, nodes, ports, certs, token, cloud_source(live|stale|degraded|unreachable), cloud_error }\`（cloudcore/节点/端口/证书/token 由云端 cloud-agent 本地采集并经 MQTT 长连接推送缓存，非 SSH；cloud_source 四态：live=推送实时且 CloudCore 运行、stale=推送中断展示过期缓存、degraded=推送实时但组件异常、unreachable=云端完全不可达；token 优先 CA 重签 1 年长期 token，失败回退 tokensecret；无节点返回空数组，不伪造数据） |
| GET /api/box/devices | \`{ models[], devices[], cloud_devices }\`（DeviceModel/Device 列表 + 云端识别设备，本地持久化 \`config/box_devices.json\`） |
| POST /api/box/devices | 创建设备/模型：\`mode=dryRun\` 返回五协议（Modbus/OPC-UA/Bluetooth/LoRaWAN/Cellular）**v1beta1** YAML 预览（\`devices.kubeedge.io/v1beta1\`，协议映射在 \`spec.protocol.configData.visitors\`，见「能碳一体机接入运维」章节 §5.2）；\`mode=apply\` 保存到本地配置 \`box_devices.json\`（可一键下发云端 K3s）；body 含 protocol/modelName/deviceName/nodeName/properties/comm/opcua/bluetooth/lora/cellular |
| POST /api/box/devices/delete | 删除：\`{kind: device|model|both, name, namespace}\` |
| GET /api/box/devices/realtime | \`{ devices:[{name,state,lastOnlineTime,twins:[{propertyName,reported,observedDesired,timestamp,unit}],history}] }\`，reported 读数一律来自 MQTT 链路 |
| POST /api/box/nodes/onboard | 盒子接入：\`{hostname,cloudIP,boxIP}\` → \`{edgecore, token, token_source, token_expires, caHash, commands}\`（模板 \`config/edgecore.template.yaml\`；token 用云端 CA 私钥 HMAC-SHA256 重签 1 年长期 token（§5.4），失败回退 \`kubectl get secret tokensecret\`；caHash=rootCA.crt DER sha256；云端不可达时返回 ok=false 明确报错） |
| GET /api/box/stats | \`{ stats, messages }\`：Broker $SYS 统计 + 最近 100 条实时消息流 |
| POST /api/box/publish | 发测试消息：\`{topic, payload}\`，向云端 Broker 发布（实时仪表盘调试） |
  `},{id:"kubeedge-ops",title:"能碳一体机接入运维（KubeEdge）",body:`## 能碳一体机接入运维（KubeEdge）

本平台接入 KubeEdge 云端/边缘体系。盒子傻瓜式接入（GitHub 托管 · 配置文件驱动）见本章节后「盒子一键接入（GitHub 托管 · 配置驱动）」；以下为云端/边缘体系要点速查。

## 一、总体架构

- 云端 \`172.19.134.45\` 运行 **K3s + KubeEdge CloudCore**，是**唯一控制平面**；
- 盒子边缘设备只部署 **EdgeCore**（不部署 k3s-server，边缘不存在本地 K8s 控制平面），边缘通过 **CloudHub（10002 端口）** 长连接云端，运行 Pod（edged 拉起）、mosquitto（本地 MQTT）、box-mapper（仪表采集，DMI 上报 twins + MQTT 实时发布 data/#）；
- 数据链路：边缘 box-mapper 仪表采集（Modbus/OPC-UA 等）→ ①DMI→edgecore→CloudHub→CloudCore→K3s Device.status.twins；②MQTT 实时发布→云端 MQTT Broker（TCP 41883）\`data/#\`；本平台订阅识别云端设备、与设备实例关联后同步读数。

## 二、端口清单

| 端口 | 用途 |
| --- | --- |
| 22 | 云端 SSH（root） |
| 10000 | CloudCore 注册/join（keadm join --cloudcore-ipport） |
| 10001 | CloudHub QUIC（通常禁用） |
| 10002 | CloudHub HTTP/HTTPS（TLS，边缘长连接） |
| 10003 | edgeStream（metrics/log/exec 数据面） |
| 10004 | CloudHub WebSocket |
| 41883 | 云端 MQTT Broker（边缘 box-mapper 实时数据 data/#） |

## 三、设备 CRD 结构（v1beta1，DMI 时代）

**注意：本环境已按 v1beta1 生成 YAML；旧 v1alpha2 结构（\`spec.propertyVisitors\`、\`spec.protocol.modbus.rtu\` 等）在 v1beta1 CRD 下会报 unknown field。**

DeviceModel（属性为标量枚举 INT/FLOAT/DOUBLE/STRING/BOOLEAN/BYTES/STREAM）：

\`\`\`yaml
apiVersion: devices.kubeedge.io/v1beta1
kind: DeviceModel
metadata:
  name: temperature-model
  namespace: default
spec:
  properties:
  - name: temperature
    type: FLOAT
    accessMode: ReadOnly
    unit: "°C"
\`\`\`

Device（spec 顶层仅 deviceModelRef/methods/nodeName/properties/protocol 五字段；协议映射在 \`spec.protocol.configData\`，visitors 在 configData 内）：

\`\`\`yaml
apiVersion: devices.kubeedge.io/v1beta1
kind: Device
metadata:
  name: temperature-device
spec:
  deviceModelRef:
    name: temperature-model
  nodeName: nt001
  protocol:
    protocolName: modbus
    configData:
      com:
        commType: serial
        serialPort: /dev/ttyS0
        baudRate: 9600
        dataBits: 8
        parity: none
        stopBits: 1
      slaveID: 1
      visitors:
      - propertyName: temperature
        register: HoldingRegister
        offset: 1
        limit: 0
        scale: 0.1
        isSwap: false
        isRegisterSwap: false
  properties:
  - name: temperature
    collectCycle: 1000
\`\`\`

协议 configData / visitor 要点：

| 协议 | configData 关键字段 | visitor 字段 |
| --- | --- | --- |
| modbus | com.commType=serial/tcp、slaveID | register（HoldingRegister/InputRegister/CoilRegister/DiscreteInputRegister）、offset、limit、scale、isSwap、isRegisterSwap |
| opcua | url、userName、password、securityMode、securityPolicy | opcua.nodeID |
| bluetooth | macAddress（可选） | bluetooth.characteristicUUID |
| lora | broker（盒子上 ChirpStack 上行推送目标，默认 127.0.0.1:1883）、applicationID、devEUI、appKey、region（CN470）、dataRate（SF7BW125） | lora.payloadKey（上行 JSON 键，支持 a.b.c 嵌套路径） |
| cellular | serialPort（AT 口，默认 /dev/ttyUSB2）、baudRate、apn、iface（蜂窝网卡，默认 wwan0） | cellular.kind（signal/csq/rsrp/rsrq/sinr/iccid/imsi/imei/reg/rx_rate/tx_rate） |

> LoRa：LoRa 传感器 → LoRaWAN 射频 → 盒子 LoRa 网关板（SX1302/SX1261）→ ChirpStack → 本地 mosquitto（\`application/{appID}/device/{devEUI}/event/up\`）→ mapper LoraReader 解析上行 JSON → DMI twins；
> Cellular：5G/4G 模块自监控，mapper CellularReader 经 AT 口（AT+CSQ / AT+QENG="servingcell" / AT+ICCID / AT+CEREG?）采集信号/ICCID/注册态，\`/proc/net/dev\` 蜂窝网卡计数差分算上下行速率；\`iccid/imsi/imei\` 为字符串值走 twins 字符串上报。

## 四、共享 Token 机制

- KubeEdge token 为**四段式** \`caHash.header.payload.signature\`（HS256），caHash = 云端 \`rootCA.crt\` DER 的 SHA256；
- cloudcore 每次重启会重签 **24 小时** token（k8s secret \`tokensecret\`）；管理台用云端 CA 私钥（\`/etc/kubeedge/ca/rootCA.key\` DER）**HMAC 重签 1 年长期 token**，保证不急着接盒子也随时能接；
- 获取 token：\`kubectl -n kubeedge get secret tokensecret -o jsonpath='{.data.tokendata}' | base64 -d\`（注意：\`/etc/kubeedge/token\` 文件不存在，不要从该路径读取）。

## 五、边缘接入流程

1. 全新盒子先 \`keadm join\`（下载 edgecore 二进制、本地生成边缘证书 \`/etc/kubeedge/certs/server.{crt,key}\`、注册 systemd）：

\`\`\`bash
keadm join --cloudcore-ipport=172.19.134.45:10000 --token=<token> --kubeedge-version=v1.20.0 --with-edge-core
\`\`\`

2. 覆盖 \`/etc/kubeedge/config/edgecore.yaml\`（管理台模板替换 \`{{HOSTNAME}}/{{TOKEN}}/{{CLOUDIP}}\`，关键项：edgeHub.httpServer=10002、websocket=10004、deviceTwin.dmiSockPath=/etc/kubeedge/dmi.sock、edged 运行时 containerd、顶层 database 用 sqlite3）；
3. \`systemctl daemon-reload && systemctl restart edgecore.service\`；
4. 云端 \`kubectl get nodes\` 确认节点 Ready；
5. 部署 box-deploy 采集包（mapper 仪表采集 + mosquitto + 云边协同断点续传）：
   - 平台本机上传：\`scp -r platform/box-deploy root@<盒子IP>:/opt/weight-bridge/box-deploy\`
   - 盒子一键部署（幂等）：\`ssh root@<盒子IP> "cd /opt/weight-bridge/box-deploy && ./deploy_box.sh"\`
   - 按现场定制 \`/opt/weight-bridge/config.json\`（deviceName/property 与云端 Device 一致、serial.port 串口、modbus 寄存器、mqtt.boxId），改完 \`systemctl restart box-mapper\`
   - 链路自检：\`./deploy_box.sh --check\`（只读验证 edgecore/dmi.sock/依赖/缓存目录）
6. 云端创建 DeviceModel/Device（平台「能碳一体机管理」界面「新建设备」一键下发，或参考 \`platform/box-deploy/mapper/config.json\` 模板）；
7. 云端触发路由并验证读数：\`kubectl annotate device <name> -n default sync=$(date +%s) --overwrite\` 后 \`kubectl get device <name> -o json | grep reported\`。

注意：
- 边缘证书由 keadm 在**盒子本地生成**（客户端身份），不要拷贝云端 cloudcore 的 server.{crt,key}；
- 以上命令即「盒子接入」弹窗生成的部署命令，可在「能碳一体机管理」界面工具栏「盒子接入」一键复制。

## 六、常见故障排查

| 现象 | 排查方向 |
| --- | --- |
| 边缘节点 NotReady | NTP 时间不同步；edgehub 连不上 10002/10004（nc 测试）；证书过期（看概览「证书与 Token 有效期」） |
| 应用设备报 unknown field | 用了旧 v1alpha2 字段，确认 protocolName + configData 结构 |
| 云端识别设备为空 | \`box_config.json\` 的 ignored_devices 是否误过滤 + 云端 41883 是否可达（nc 172.19.134.45 41883） |
| cloudcore 非 Running | kubectl get pod -n kubeedge 查看状态，关注概览页 CloudCore 卡片 |
| 盒子到云端网络 | nc 依次测试 22 / 10002 / 10004 / 41883，定位防火墙或服务未监听 |

## 七、证书与端口核查命令（云端）

\`\`\`bash
openssl x509 -enddate -noout -in /etc/kubeedge/ca/rootCA.crt
openssl x509 -enddate -noout -in /etc/kubeedge/certs/server.crt
ss -tlnp | grep -E ':(1000[0-4])[^0-9]'
\`\`\``},{id:"box-onboard",title:"盒子一键接入（GitHub 托管 · 配置驱动）",body:"## 盒子一键接入（GitHub 托管 · 配置文件驱动）\n\n「能碳一体机管理 → 盒子接入」提供三种接入方式，其中 **GitHub 托管**为推荐方式：现场无需平台、无需源码，只凭一份 **box-config.json** + 仓库引导脚本，一条命令完成接入（EdgeCore join + box-deploy 采集部署 + 链路自检，幂等可重跑）。\n\n## 一、三种接入方式对比\n\n| 方式 | 适用场景 | 现场动作 |\n| --- | --- | --- |\n| ① GitHub 托管（推荐） | 盒子有外网，可访问 GitHub | 配置放盒子 /opt/weight-bridge/ + 一条 curl 命令 |\n| ② 自解压脚本 onboard_box.sh | 离线 / 内网，无法访问 GitHub | U 盘 / 局域网传 18MB 脚本，bash 执行 |\n| ③ 云端 agent 远程一键接入 | 盒子可达（现场部署 / 手机热点） | 平台点「远程一键接入」推送执行 |\n\n## 二、GitHub 托管接入（平台侧）\n\n平台操作路径：「能碳一体机管理 → 盒子接入 → GitHub 托管」：\n\n1. 填写 owner / repo / 分支（默认 master）/ GitHub PAT（仅「同步写入」需要，contents 写权限；公开仓库盒子现场拉取无需验证，留空沿用已保存），保存配置；\n2. 「🔄 同步到 GitHub」：平台把五类资产幂等推送到仓库 `onboard/` 目录：\n   - `onboard_box.sh`：轻量引导脚本（约 4KB，配置文件驱动）；\n   - `box-deploy.tar.gz`：采集部署包（约 13MB）；\n   - `edgecore.yaml`：保留 `{{HOSTNAME}}` / `{{TOKEN}}` / `{{CLOUDIP}}` 占位符，由盒子端按配置统一替换 —— 云端重建 / token 重签**无需重新同步**；\n   - `rootCA.crt` / `token`：共享接入凭据；\n3. 「⬇ 导出 box-config.json」：生成现场配置文件（现场无平台、无源码时使用）。\n\n## 三、box-config.json 字段\n\n| 字段 | 必填 | 说明 |\n| --- | --- | --- |\n| boxId | 是 | 盒子主机名（与云端 K8s 节点名一致，如 my-box-01） |\n| cloudIP | 是 | 云端 CloudCore / MQTT Broker 地址（如 172.19.134.45） |\n| token | 否 | 共享接入 token；留空时脚本自动从仓库 `onboard/token` 拉取 |\n| repo | 否 | 镜像仓库 owner/repo（如改用 gitee 镜像时填写，覆盖脚本内置仓库地址） |\n| branch | 否 | 镜像仓库分支（默认 master） |\n\n其余未知字段（如平台导出的 `_说明`）脚本一律忽略，导出内容可直接使用。\n\n## 四、现场一条命令（盒子 root）\n\n```bash\n# 方式 A（推荐）：配置放到 /opt/weight-bridge/box-config.json 后，脚本自动识别\ncurl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/<branch>/onboard/onboard_box.sh | bash\n\n# 方式 B：显式指定配置路径（配置不在默认位置时）\ncurl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/<branch>/onboard/onboard_box.sh | bash -s -- -c /path/box-config.json\n\n# 方式 C：无配置文件，命令行直接给参数\ncurl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/<branch>/onboard/onboard_box.sh | bash -s -- -i 172.19.134.45 -n my-box-01\n\n# 方式 D：仅指定主机名（其余用脚本内置默认 + 仓库 token）\ncurl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/<branch>/onboard/onboard_box.sh | bash -s my-box-01\n```\n\n引导脚本自动完成：\n\n1. **参数解析与配置读取**：`-c` / `-i` / `-n` 命令行 > box-config.json（默认路径 `/opt/weight-bridge/box-config.json` 或 `-c` 指定）> 脚本内置默认值；\n2. **① EdgeCore 接入**：edgecore 未运行且有 keadm → `keadm join`（已接入自动跳过）；\n3. **② 配置下发**：rootCA + edgecore.yaml 从仓库拉取，python3 一次替换 `{{HOSTNAME}}` / `{{TOKEN}}` / `{{CLOUDIP}}`，重启 edgecore；\n4. **③ 部署包解包**：box-deploy.tar.gz 解压到 `/opt/weight-bridge/box-deploy/`；\n5. **④ config.json 定制**：首次生成时自动设 `mqtt.boxId` / `mqtt.broker.host`；\n6. **⑤ 一键部署 + 链路自检**：`./deploy_box.sh` + `./deploy_box.sh --check`。\n\n## 五、注意事项\n\n- **仓库公开则盒子现场拉取无需任何验证**（推荐公开，盒子一条 `curl` 即可拉全资产；内含共享 token 与 rootCA，是否公开请自行权衡）。token 重签后需平台重新「同步到 GitHub」，或现场 box-config.json 填入新 token（edgecore.yaml 无需重推）；\n- **box-deploy 部署包升级**后需平台重新「同步到 GitHub」一次；\n- 盒子主机名 = 云端 K8s 节点名（拼写不一致会导致断链，如 chengzhong1 与 chengzhong 不匹配）；\n- keadm join 与 edgecore.yaml 的 token 均按「配置文件 > 仓库拉取 > 报错提示」取值；\n- 离线 / 内网环境请使用「方式 ② 自解压脚本」或「方式 ③ 云端 agent 远程接入」。\n\n## 六、GitHub 源码一键部署（全新服务器 + 全新盒子）\n\n仓库公开后，除「GitHub 托管（平台预同步资产）」外，还支持**直接从源码仓库一键部署**，适合**全新服务器 + 全新盒子**场景，全程无需平台先同步资产：\n\n### 全新服务器 · 一键部署平台\n\n```bash\n# 服务器 root（Ubuntu / Debian / CentOS），自动：拉源码 → 装依赖 → 构建前端 → systemd 启动\ncurl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/<branch>/deploy/server.sh | bash\n# 自定义仓库 / 分支 / 目录 / 端口（默认 40013，遵循 40000+ 端口规范）：\ncurl -fsSL <同上> | bash -s -- -r gitee.com/user/mirror -b main -d /opt/carbon-platform -p 40013\n```\n\n平台监听 40013（可用 `-p` 修改），前端由后端托管、单端口对外；如需云端能力（K3s + CloudCore + cloud-agent），另用 `platform/cloud-deploy/deploy_cloud.sh` 部署。\n\n### 全新盒子 · 一键接入（免平台预同步）\n\n```bash\n# 盒子 root；先放好 /opt/weight-bridge/box-config.json（boxId/cloudIP/token 必填）\ncurl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/<branch>/deploy/box.sh | bash\n# 或命令行直接给参数（无配置文件）：\ncurl -fsSL <同上> | bash -s -- -i 172.19.134.45 -n my-box-01 -t <token>\n```\n\n与 `onboard_box.sh` 的区别：`deploy/box.sh` 直接拉**公开源码仓库** tarball（内含 box-deploy 部署包与 edgecore 模板），**无需平台「同步到 GitHub」**；唯一仍需现场提供的是**共享 token**（公开仓库不存放动态凭证，平台「导出 box-config.json」可自动填入）。box-config.json 额外支持 `rootCA`（base64，可选；keadm join 会自动从云端拉取）。\n\n| 脚本 | 前置条件 | 适用场景 |\n| --- | --- | --- |\n| `onboard_box.sh`（仓库 `onboard/` 目录） | 平台已「同步到 GitHub」 | 有平台、现场只有一份配置文件 |\n| `deploy/box.sh`（源码仓库） | 公开仓库 + token | 全新盒子 / 无平台预同步 |\n\n### 更新（服务器 · 数据安全优先）\n\n```bash\n# 已部署实例升级，先备份现场数据 → 更新 → 恢复 → 重建前端 → 重启\ncurl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/<branch>/deploy/update.sh | bash -s -- -d /opt/carbon-platform\n```\n\n- 必须用 `update.sh` 而不是重跑 `server.sh`：源码仓库**跟踪**了 `backend/config/` 下的 `box_config.json` / `box_devices.json`（设备 CRD）/ `links.json`（设备关联）/ `mqtt.yaml`（云端 MQTT）与 `backend/data/`（碳合规、历史报告），直接 `git reset --hard` 会把这些**现场数据覆盖丢失**；update.sh 更新前自动备份到 `<安装目录>/.update-backup-<时间戳>`、更新后自动恢复，全程不丢数据。\n- `platform_config.json` / `strategies.json` / `.env` / `github_config.json` 已被 gitignore，常规更新不受影响（备份逻辑同样覆盖，双保险）。\n- `server.sh` 检测到已部署实例时会导向 `update.sh`，不会自行覆盖。\n- 盒子侧更新：重新执行 `deploy/box.sh` 即可（幂等——edgecore 运行中跳过 join、`/opt/weight-bridge/config.json` 现场配置保留，仅更新 box-deploy 程序）。\n\n### 云端时序数据库（TDengine · 设备历史落时序库）\n\n盒子实时读数（`data/{box}/{device}/{instance}/{property}`）默认只在平台内存保留最近约 10 分钟；若需**云端持久化历史**并支持跨天查询曲线，可在云端部署 TDengine 时序库：\n\n```bash\n# 云端：完整部署会一并装时序库；也可只装时序库\n./deploy_cloud.sh --tsdb-only          # 仅部署 TDengine（已装自动跳过）\n./deploy_cloud.sh --bootstrap --ip <IP> # 完整一键（含时序库）\n# 云端无外网：先手动下载 TDengine-server-<ver>-Linux-<arch>.tar.gz\n# TDSB_TAR=/path/tdengine.tar.gz ./deploy_cloud.sh --tsdb-only\n```\n\n- 部署内容：TDengine（taosd 6030 / taosadapter REST 6041，**仅本地监听不对外放行**），初始化库 `nengtan`（保留 `TSDB_KEEP` 天，默认 30）与超表 `readings(ts, value) TAGS(box, device, instance, property)`。\n- 数据写入：云端 `collector`（nengtan-collector.service）订阅 `data/#`，数值读数**每秒批量**写入时序库（REST，失败不阻塞订阅，原始数据仍全量落盘 collected/ 日志兜底）。\n- 查询链路：平台「数据视图 → 云端时序」或「盒子接入 → 设备列表 → 📈 历史」→ 后端 → cloud-agent `/api/history`（Bearer 认证）→ 云端本地查 TDengine → 按时间窗口降采样返回曲线。支持时间范围（近 1 小时 / 6 小时 / 24 小时 / 7 天），四元组自动从设备 node/name/twins 推导（property 可切换）。「数据视图」默认展示本地模拟历史，切到「云端时序」后设备列表来自 /box/devices/realtime（云端 CRD 设备），历史数据即从 TDengine 拉取，与盒子上报数据同源。\n- 自检：`./deploy_cloud.sh --check` 会显示 taosd 状态、6041 监听与 `readings` 总点数。\n- 数据量说明：单盒子单属性 1Hz ≈ 8.6 万点/天；TDengine 超表按 tag 自动建子表、压缩率高，几十个盒子完全无压力。\n\n## 七、关联章节\n\n- 云端体系 / 设备 CRD / 常见故障排查见「能碳一体机接入运维（KubeEdge）」；\n- 采集 mapper / 部署包 / 诊断工具说明见「能碳一体机管理」界面「接入指引」页签。"},{id:"contract",title:"数据契约模型",body:`## 数据契约模型

所有前后端交互的数据契约集中在 \`backend/app/models.py\`（Pydantic），保证类型一致、前后端可校验。

## 一、流程模型

| 模型 | 字段 | 说明 |
| --- | --- | --- |
| Unit | id / type / name / x / z / rot / enabled / params / techs | 工序节点（位置、参数、已应用技术） |
| Flow | id / from_unit / to_unit / material / rate | 物流连线（hot_metal/scrap/steel/dri） |
| ProcessModel | units / flows | 完整流程 |

## 二、策略解析

| 模型 | 说明 |
| --- | --- |
| ParsedOp | 单条操作：action / target / param / value / mode(absolute|relative) / tech / note |
| ParseResult | raw_text / understood / ops / confidence / warnings / engine(llm|heuristic) |

## 三、仿真结果

| 模型 | 说明 |
| --- | --- |
| LedgerItem | 碳排放台账项：item / qty / qty_unit / basis / formula / co2 / scope(direct|indirect) |
| UnitResult | 单工序结果：co2_direct/indirect/total、carbon_in/to_co2/to_steel/captured、heat(0~1 热力图)、能耗字段、breakdown 台账、devices 监测设备 |
| SimTotals | 全厂汇总：co2_total、carbon_utilization、steel_output、intensity(kgCO₂/t)、energy 字段 |
| SankeyNode / SankeyLink | 桑基图数据：燃料源 → 工序 → 去向，链路值为 tC/h |
| SimResult | totals / units / sankey |

## 四、策略与请求

| 模型 | 说明 |
| --- | --- |
| Strategy | 已保存策略：id / name / description / raw_text / ops / applied |
| ParseRequest | 解析请求：text + 当前模型 |
| SimulateRequest | 仿真请求：model + 可选 ops（策略操作）+ factors（自定义因子） |
| SimulateResponse | 仿真响应：baseline + 可选 strategy（策略后）+ delta（前后差值） |
| ReportRequest | 报告请求：baseline/strategy/engine/depth/with_appendix 等 |

## 五、delta 结构（策略对比）

\`\`\`json
{
  "co2_total": -312.5,          // tCO₂/h 差值
  "co2_direct": -298.1,
  "co2_indirect": -14.4,
  "intensity": -8.3,            // kgCO₂/t
  "carbon_utilization": 0.0184,
  "steel_output": 0.0,
  "co2_reduction_pct": 12.6     // 减排百分比
}
\`\`\`

## 六、审计 / 优化器请求

以下端点使用 \`dict\` 请求体（不经 Pydantic），由后端按需读取：

| 端点 | 请求体字段 |
| --- | --- |
| POST /api/audit | model（流程）+ 可选 ops |
| POST /api/optimizers/context | model + factors（训练上下文） |
| PUT /api/optimizers/{oid}/settings | auto_control / schedule{enabled,interval_h,start,end} / samples |
| POST /api/optimizers/{oid}/train | steps（训练步数） |

## 七、碳市场 / 快讯契约

| 模型 | 说明 |
| --- | --- |
| Quote | \`{ t, price/close, change_pct, source }\`；CEA / CCER 各一组 |
| MarketQuotes | \`{ ok, simulated, queried_at, cea, ccer, cea_monthly[], daily_count, intraday }\` |
| ChartPoint | \`{ t, open?, high?, low?, close, volume? }\`（K 线）或 \`{ t, price/close }\`（折线） |
| ChartSeries | \`{ ok, instrument, kind, title, unit, source_name, source_page, queried_at, points[] }\` |
| ForecastPoint | \`{ t, price, high, low }\`（high/low = ±1.65σ 置信带）；ForecastSeries 含 method/confidence/slope/base_date/history_tail/forecast[] |
| NewsItem | \`{ id, time, content, tags[], views }\`；返回 \`{ ok, items[], source, source_name, queried_at }\`，ok=false 表示抓取失败 |
`},{id:"protocol",title:"仿真协议与接口",body:`## 仿真协议与接口

## 一、REST API（后端 FastAPI）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | /api/health | 健康检查 |
| GET | /api/cache/stats | 仿真缓存命中率（诊断） |
| GET | /api/model/preset | 默认流程模型 |
| GET | /api/presets/strategies | 内置示例策略（一键体验） |
| GET | /api/factors | 默认排放因子表 |
| GET | /api/param-schema | 工序参数分级元数据（config/optim、label、单位、参考范围） |
| GET | /api/devices | 内置监测设备库（设备元数据 + 工序规格 + 设备规格档位库） |
| GET | /api/devices/history | 设备历史时序（内存环形缓冲） |
| POST | /api/parse | 自然语言 → 策略操作（LLM/启发式双引擎） |
| POST | /api/simulate | 仿真（baseline + 可选策略对比 delta） |
| POST | /api/apply | 直接对流程应用一组操作 |
| POST | /api/strategies | 创建策略；GET/PUT/DELETE /api/strategies/{id}；POST /api/strategies/{id}/apply 应用策略 |
| POST | /api/audit | 全流程碳素流守恒审计（碳输入 = 排 CO₂ + 固钢 + 入渣 + 捕集 + 产品携出） |
| POST | /api/optimizers/context | 同步 AI 优化训练上下文（当前流程 + 因子，供优化器建模） |
| GET | /api/optimizers | 优化模型列表与训练状态（迭代/曲线/最优参数摘要） |
| GET | /api/optimizers/{oid} | 单个优化器详情（训练轨迹/超参/版本/建议/提醒） |
| POST | /api/optimizers/{oid}/start | 开启自动训练（后台随实时数据定时迭代） |
| POST | /api/optimizers/{oid}/stop | 停止自动训练 |
| POST | /api/optimizers/{oid}/train | 手动训练 N 步（steps 参数） |
| POST | /api/optimizers/{oid}/reset | 重置模型权重 |
| PUT | /api/optimizers/{oid}/hyper | 保存算法超参数（GA/PSO/RL） |
| POST | /api/optimizers/{oid}/apply | 应用最优参数到流程（best → 可调设备） |
| PUT | /api/optimizers/{oid}/settings | 更新控制与自训练设置（自动化控制/频率/时段/样本量） |
| POST | /api/optimizers/{oid}/archive | 手动存档当前模型版本 |
| POST | /api/optimizers/{oid}/switch | 切换到历史版本 |
| POST | /api/optimizers/{oid}/ack | 确认调优提醒（清除未读标记） |
| POST | /api/report | 创建报告生成任务（后台线程） |
| GET | /api/report/task/{id} | 轮询报告进度（done/progress/stage/result） |
| GET | /api/reports | 历史报告列表（倒序） |
| GET | /api/report/{rid} | 单个历史报告详情（Markdown 原文） |
| DELETE | /api/reports/{rid} | 删除历史报告 |
| POST | /api/chat | 命令行窗口自然语言对话（LLM，无 Key 兜底提示） |
| GET | /api/carbon-market/quotes | 碳市场实时报价（CEA/CCER 最新价 + 涨跌幅 + 月聚合，60s 缓存） |
| GET | /api/carbon-market/chart?instrument=cea|ccer | 图表序列：CEA 日K线 / CCER 成交均价折线（60s 缓存） |
| GET | /api/carbon-market/forecast?instrument=cea|ccer&days=10&method=linear|moving_average|exponential | 价格预测：线性回归 / 移动平均 / 指数平滑外推 + ±1.65σ 置信带 |
| GET | /api/market-news | 市场快讯列表（中国煤炭交易网抓取 + 60s 缓存，失败返回 ok=false 与空列表） |
| GET | /report/{rid} | 报告分享页（独立 HTML，新标签查看/打印） |
| POST | /api/carbon-assistant/report | 碳资产报告任务（report_type：compliance_analysis|market_brief|policy_digest；forecast_method：linear|moving_average|exponential） |
| GET | /api/carbon-assistant/reports?keyword=&report_type=&offset=&limit= | 碳资产报告列表（关键字/类型筛选 + 分页，返回 total） |
| GET | /api/carbon-assistant/reports/{rid} | 碳资产报告详情（Markdown 原文 + report_type） |
| GET | /api/carbon-assistant/reports/{rid}/view | 碳资产报告 HTML 阅读页（新窗口） |
| GET | /api/carbon-assistant/reports/{rid}/download | 碳资产报告 Markdown 下载 |
| DELETE | /api/carbon-assistant/reports/{rid} | 删除碳资产报告 |
| GET | /api/carbon-assistant/tasks/{tid} | 碳资产报告任务状态（含 progress 0-100） |
| POST | /api/carbon-assistant/tasks/{tid}/cancel | 取消碳资产报告任务 |

## 二、WebSocket 遥测

- 路径：\`/api/ws/feed\`；
- 协议见「实时遥测系统」章节；
- 支持 Mqtt 实时（默认，后端订阅云端 MQTT Broker 获取真实读数）、自定义 WebSocket、HTTP 轮询三种数据源（文件 → 连接数据源…）。

## 三、SPA 托管

后端以 **Catch-all 路由**托管前端构建产物：
- 存在真实静态文件（模型/解码器等）时直接返回，避免全部回退 index.html；
- 其余路径回退到 SPA 入口，保证前端路由（若有）可刷新直达。

## 四、报告导出

平台支持将当前工况的碳流、碳排、TFT 状态汇总导出为 Markdown 分析报告，并渲染为可分享的 HTML 页面（文件 → 导出分析报告）。`},{id:"carbon-market",title:"碳市场行情服务",body:`## 碳市场行情服务

后端 \`carbon_market.py\` 提供 CEA（全国碳市场配额）与 CCER（自愿减排量）两类碳资产的行情数据服务：实时报价、K 线/折线序列、价格预测，供前端「碳市场视图」与底部状态栏使用。

## 一、数据来源与降级策略

- **CEA**：从上海环境能源交易所公开行情页解析（日 K 序列 + 最新价 + 月聚合）；
- **CCER**：优先从全国温室气体自愿减排交易系统（北京绿色交易所）日行情列表拉取，失败回退碳中和网整理的历史表 + 最新报价解析；
- 任一环节失败（网络不可用 / 超时 / 解析失败）时，**不做模拟兜底**，回退显示最近一次成功拉取的**历史数据**（进程内缓存）；无历史数据时对应品种返回空对象，前端显示 \`--\`；
- 全接口采用 **60 秒 TTL 缓存**（\`_TtlCache\` + 线程锁）：首次请求后缓存 60 秒，期间请求直接命中缓存，避免高频打外网。

## 二、API 契约

| 接口 | 返回要点 |
| --- | --- |
| GET /api/carbon-market/quotes | \`{ ok, simulated, queried_at, cea, ccer, cea_monthly[], daily_count, intraday }\`；cea/ccer 含 \`t\`/价格/\`change_pct\`（涨跌幅）/来源；\`simulated\` 恒为 false（无模拟数据，远程失败回退历史缓存） |
| GET /api/carbon-market/chart?instrument=cea|ccer&kind=daily | \`{ ok, instrument, kind, title, unit, source_name, source_page, queried_at, points[] }\`；CEA 返回日K线（t/开/高/低/收/量），CCER 返回成交均价折线；远程失败回退最近一次成功的历史序列 |
| GET /api/carbon-market/forecast?instrument=cea|ccer&days=10 | \`{ ok, instrument, days, method, confidence, slope, base_date, source_name, history_tail[], forecast[] }\`；forecast 中每点带 \`t/price/high/low\`（high/low 为 ±1.65σ 置信带），days 默认 10，上限 30 |

## 三、预测算法（forecast_series）

- 取最近 **90 个历史点**做最小二乘线性回归 \\(y = a + b\\,x\\)（\`_ols\`），\\(b\\) 即价格趋势斜率；
- 残差标准差 \\(s=\\sqrt{\\sum r_i^2/(n-2)}\\)，置信带带宽按 \\(1.65\\,s\\,\\sqrt{1+i/n}\\) 随外推天数 \\(i\\) 递增（约 90% 置信）；
- 未来日期按历史平均间隔推进并跳过周六/周日（\`_next_trade_date\`）；
- 该算法定位为**趋势参考**而非精确预测；前端在图上以虚线（预测线）与阴影带（high/low 区间）呈现。

## 四、前端集成

- \`CarbonAssistantView.vue\`：碳资产管理主入口，集成行情卡片（CEA 最新价/涨跌幅/成交量/今开/最高/最低/昨收 + CCER 最新均价/成交量/基准参考）、CEA 蜡烛图（30 日 OHLCV）与 CCER 折线页签切换、预测叠加与置信带（±1.65σ）；右上角与顶栏工具栏提供「生成碳资产报告」入口，侧边栏报告中心支持三种报告类型（履约综合分析 / 碳交易简报 / 政策摘要）与三种预测方法（线性回归 / 移动平均 / 指数平滑），后台任务含进度条与取消，历史报告支持搜索/筛选/分页、结论摘要卡片、HTML 阅读页、Markdown 下载与删除；15 秒轮询，断开自动停止；
- \`StatusBar.vue\`：底部滚动播报快讯摘要（与「市场快讯服务」联动），鼠标悬停暂停滚动。`},{id:"market-news",title:"市场快讯服务",body:"## 市场快讯服务\n\n后端 `market_news.py` 定时从**中国煤炭交易网「市场快讯」栏目**抓取行业资讯（煤炭 / 碳市场相关动态），转换为结构化的快讯列表供前端展示。\n\n## 一、抓取与缓存\n\n- 首次请求时发起抓取，成功后缓存 **60 秒（TTL）**（`_TtlCache` + 线程锁），期间后续请求直接返回缓存，避免频繁请求外网；\n- 编码兼容 UTF-8 / GBK，请求带浏览器 UA 头；失败（网络不可用 / 目标页结构变化 / 超时）时返回 `ok=false` 与空列表，前端显示「快讯暂不可用」，不阻断其它功能；\n- 返回字段：`ok`（是否成功）、`items`（快讯数组，含 `id` / `time` / `content` / `tags` / `views`）、`source` / `source_name`（来源标识与名称）、`queried_at`（查询时间）。\n\n## 二、API 契约\n\n| 接口 | 返回要点 |\n| --- | --- |\n| GET /api/market-news?page=1 | `{ ok, items: [{ id, time, content, tags, views }], source, source_name, queried_at }`；page 默认 1 |\n\n## 三、前端集成\n\n- `StatusBar.vue`：左侧「市场快讯」滚动条持续轮播（每条约 18s 滚动周期，自适应条数），鼠标悬停暂停滚动；每 5 分钟自动刷新一次；\n- 快讯的显隐由系统设置「布局」页签「快讯滚动条」开关控制（`newsTickerOn`，存于 Pinia）；\n- 快讯与碳资产管理视图相互独立：快讯常驻状态栏，碳资产管理视图需「视图 → 碳资产管理」打开。"},{id:"optimizer",title:"AI 优化模型引擎",body:`## AI 优化模型引擎

后端 \`optimizers.py\` 提供五套在线自学习优化模型（**序列预测算法 SEQ / 强化学习优化策略 RL / 遗传算法优化策略 GA / 粒子群优化策略 PSO / 聚类工况识别 CLU**），随流程运行与实时传感器数据后台持续训练，输出碳强度最优的设备参数建议或典型工况分布，并支持版本管理与自动化控制。

## 一、模型架构

| 组件 | 职责 |
| --- | --- |
| OptimizerBase | 优化器基类：归一化状态、适应度求值、训练循环、版本/提醒管理 |
| SequencePredictOptimizer | 序列预测算法（SEQ）：指数平滑时序外推预测未来工况，支持预测目标 / 影响变量设定，在预测工况下采样调节变量做仿真评估 |
| 决策变量 decisions | 策略模型（RL / GA / PSO / SEQ）属性面板勾选参与优化的工艺参数，未启用的维度在训练中冻结为当前设定值 |
| 优化目标 objective | 策略模型可切换优化目标（吨钢碳强度 / 吨钢综合能耗 / 全厂 CO₂ 排放总量），适应度评估与日志单位随目标动态调整 |
| GeneticOptimizer | 遗传算法优化策略（GA）：选择 / 交叉 / 变异算子，适用于设备启停与连续参数复合的混合场景 |
| ParticleSwarmOptimizer | 粒子群优化策略（PSO）：惯性权重 + 个体/全局最优引导，适用于连续参数空间最优解探索 |
| ReinforcementOptimizer | 强化学习优化策略（RL）：在线策略梯度 REINFORCE，随实时数据先探索后利用 |
| ClusteringOptimizer | 聚类工况识别（CLU）：基于最近传感器读数构造工况快照（特征设备归一化读数 + 负荷因子），内置 K-Means / DBSCAN / 层次聚类，输出典型工况簇占比与代表负荷（不寻优、不产生版本） |
| 聚类特征 feature_vars | 聚类模型设定参与工况聚类的监测设备（空 = 全部设备），支持 \`method\`（算法）与 \`feature_vars\`（特征）下发 |
| TrainingScheduler | 后台调度线程：按配置频率定时迭代全部活跃优化器 |

## 二、优化空间与上下文

- 优化目标是 **单位产品碳强度（kgCO₂/t）** 最小化；
- 可优化参数来自 \`/api/optimizers/context\` 同步的当前流程模型（各工序可调设备参数）与排放因子；
- 状态输入为**归一化实时遥测读数**（映射到 [0,1] 区间），保证跨设备可比；
- 适应度（fitness）= 基于当前流程计算出的碳强度，训练越久越接近流程最优参数组合。

## 三、训练与更新机制

- **自动训练**：\`POST /api/optimizers/{oid}/start\` 开启后，后台 \`TrainingScheduler\` 按自训练设置（频率/时段/样本量）随实时数据定时迭代；
- **手动训练**：\`POST /api/optimizers/{oid}/train\` 单步推进，便于观察收敛过程；
- 每次取得更优解即记录**最优参数建议**与**强度提升百分比**，前端轮询 \`GET /api/optimizers\` 展示「模型逐渐变优」。

## 四、控制模式与提醒

- **自动化控制**（\`settings.auto_control\` 开启）：模型变优后由后端直接下发最优参数到可调设备，命令行输出应用日志；
- **手动模式**：仅生成调优提醒（reminder），在策略属性面板确认（ack）后可手动应用（apply）；
- 提醒包含最优强度、较上版提升百分比，按需展示。

## 五、版本管理

- 每次取得阶段性更优解自动存档版本（含超参数、权重、最优参数、时间）；
- 手动存档 \`POST /api/optimizers/{oid}/archive\`、切换历史版本 \`POST /api/optimizers/{oid}/switch\`、重置权重 \`POST /api/optimizers/{oid}/reset\`；
- 超参数（GA/PSO/RL 各自模板）经 \`PUT /api/optimizers/{oid}/hyper\` 持久化。

## 六、数据契约

优化器 API 使用 \`dict\` 请求体（不经 Pydantic），主要字段：
\`\`\`json
// settings
{ "auto_control": true, "schedule": { "enabled": true, "interval_h": 1, "start": "09:00", "end": "18:00" }, "samples": 60 }
// train
{ "steps": 5 }
\`\`\`
状态响应（GET /api/optimizers/{oid}）包含：\`status / iteration / best_fitness / best_params / history(曲线) / versions / reminder / hyper / settings\`。`},{id:"viz",title:"前端可视化与交互",body:`## 前端可视化与交互

## 一、3D 场景（three/scene.js · TwinScene）

基于 Three.js 构建的数字孪生场景：

- **工序模型库 UNIT_META**：烧结机、球团、焦炉、高炉、转炉、电炉、精炼炉、连铸机、热轧机等 20+ 种工艺，按实际规模差异化缩放（高炉巨大、转炉中等、精炼偏小）；
- **赛博朋克材质工厂**：高金属感、低粗糙度、蓝黑基底；
- **环境模式 ENV**：五种可切换场景——void 赛博虚空（深空背景 + 霓虹网格）、industrial 工业（厂房与管道剪影）、desert 沙漠、city 城市（远景建筑群）、coast 海滩（水面 + 椰树），各有独立天空渐变、地表色与雾效；
- **平台地坪与网格**：随环境模式切换配色与霓虹网格（void 模式）；
- **聚焦/选中高亮**：点击工序聚焦相机并高亮唯一标签与选中环，\`focus\`/框架视图（\`frameAll\`）一键复位。

## 二、热力图与物流动画

- **热力图 heat layers**：按 \`UnitResult.heat\`（0~1）为工序外壳着色，直观呈现各工序热负荷/排放强弱；
- **物流动画 flows**：物流连线上的粒子/进度动画，展示 hot_metal / scrap / steel / dri 的流向与速率；
- 热风炉等容器类工序支持外壳半透明显示内部结构。

## 三、Pinia 全局状态（stores/sim.js）

- 流程编排：工序/物流的增删改、撤销重做（history）、方案保存；
- 仿真状态：baseline / strategy / delta、实验对比（同时仿真多方案）；
- 策略：解析结果、已保存策略、应用状态；
- 设备：实时遥测读数、历史趋势、设备设定（滑块）；
- 环境模式状态、3D 聚焦目标。

## 四、桑基图（碳流可视化）

仿真结果生成 Sankey 图数据（燃料源 → 工序 → 去向，链路值 tC/h），可视化展示碳素流分配、固碳与捕集去向。

## 五、分析类面板

| 面板 | 入口 | 说明 |
| --- | --- | --- |
| 碳素流守恒审计 | 工具菜单 → 碳素流守恒审计 | 逐工序核算碳输入/输出五项平衡，输出偏差与守恒率（POST /api/audit） |
| 高炉数值分析（TftAnalysisDialog） | 仿真菜单 → 高炉数值分析（Alt+T） | 全厂高炉 TFT 数值总览、鼓风/喷煤调参推演，复用 utils/tft.js 焓平衡 |
| 参数范围/设备量程内化 | 编排模式工序/设备节点属性面板 | 节点属性面板直接编辑参数运行空间（min/max/step）与设备量程，随方案持久化，无需全局配置（优先级：节点自定义 > 设备规格 ranges > 默认） |
| AI 优化模型（策略详情面板） | 左侧「策略 → AI优化模型」点击模型 | GA/PSO/RL 在线训练面板：状态/迭代/曲线/最优参数建议，支持训练控制、应用最优参数、版本管理与提醒确认（/api/optimizers/*） |
| 数据视图（DataView） | 视图菜单 → 数据 | 全屏传感器历史数据表格：设备页签 + 实时读数/均值/峰值/谷值/超限状态 + 时序表格 |
| 碳市场行情（CarbonMarketView） | 视图菜单 → 碳市场 | 行情卡片 + CEA 蜡烛图 / CCER 折线 + 线性回归预测与置信带；15s 轮询，详情见「碳市场行情服务」章节 |
| 数据校准（CalibrationWizard） | 工具菜单 → 数据校准 | 选择设备 → 输入标准/读数标定点 → 线性回归拟合校准曲线 → 预览误差 → 应用/重置（校准系数持久化） |

## 六、系统级 UI 组件（欢迎页 / 活动栏 / 状态栏）

面向整体工作台的壳层组件，承载模式选择、面板切换与全局信息展示：

| 组件 | 职责 |
| --- | --- |
| — | 无宣传页：打开网址直接进入系统主界面，按已保存方案/默认长流程展示数字孪生 |
| ActivityBar | 类 VS Code 活动栏：资源管理器 / 搜索 / 场景 / 连接 四个入口，切换左侧面板 |
| StatusBar | 底部状态栏：实时链路状态、工序/物流计数、监测点位、市场快讯滚动（点击弹详情）、策略情景、时钟与通知 |
| SearchPanel | 全局搜索：按名称模糊匹配工序 / 物料 / 策略 / 设备，点击结果联动检视器、资源管理器与 3D 聚焦 |
| ScenePanel | 场景控制：环境主题切换、显示图层开关（网格/轴向/标签/连线/热力图）、视角工具 |
| ConnectionsPanel | 连接面板：三种数据源（模拟/WebSocket/HTTP）运行状态展示与在线启停，入口直达数据源配置 |
| CarbonBoxView | 能碳一体机管理（视图 → 能碳一体机管理）：原「数据概览」+「设备管理」合并为单界面——工具栏（盒子接入/新建设备/刷新）、云端数据链路（Broker $SYS 统计 + CloudCore 状态 + 证书与 Token，由云端 cloud-agent 经 MQTT 长连接推送，非 SSH；云端状态四态：云端实时/数据过期/部分异常/不可达）、实时消息流与发测试消息、设备管理（DeviceModel/Device 五协议 CRUD + v1beta1 YAML 生成，config/box_devices.json + 一键下发云端 K3s）、拓扑图 + 云端 CRD 生效态；盒子接入（edgecore.yaml 模板渲染 + 云端 CA 重签 1 年 token/caHash + 完整部署命令：① keadm join → ② 配置下发 → ③ 云建设备 → ④ box-deploy 采集包 → ⑤ 路由验证）；云端设备关联 / 边缘节点 / twins 实时值 / CloudHub 端口显示已移除；总体架构：云端 K3s + CloudCore 控制平面，盒子边缘仅装 EdgeCore（无本地控制平面，运行 Pod / mosquitto / mapper，DMI 采集 + 云边协同断点续传） |

## 七、数据源管理与系统设置

- **DataSourceDialog**（文件 → 连接数据源…）：配置三种实时数据来源——Mqtt 实时（默认，读数来自后端 MQTT 订阅，Broker 在「能碳一体机管理」视图前端配置）、WebSocket（ws:// 服务器）、HTTP 轮询（REST 接口）；每项支持启停、采样间隔与「测试连接」；配置持久化到本地，重启自动应用；
- **SystemSettingsDialog**（文件 → 设置…）：按页签分组——布局（面板显隐）、场景（仿真情景 / 环境）、实时链路（数据源启停）、LLM（模型名 / API 密钥 / API 地址，可选，未配置自动回退本地规则与本地模板报告）；
- 两种对话框状态存于 Pinia（\`showDataSource\` / \`showSettings\`），数据源配置与连接面板共享同一状态源。

## 八、命令行窗口（CommandConsole）

底部命令行为交互中枢：聊天 / 代码 / 规划三模式 + 孪生控制命令（run/sim/stop/reset/overview/home/view/edit/done/clear），走 \`POST /api/chat\`；内置策略与工序策略的自然语言输入则走 \`POST /api/parse\`（LLM 优先、启发式回退）。`}],Qs=[{key:"promo",path:"/promo",nav:"宣传手册",desc:"平台核心理念、功能亮点与价值主张，快速了解平台全貌。",accent:"#2F6FED",sections:Fl},{key:"manual",path:"/manual",nav:"使用手册",desc:"从界面总览到各功能模块，一步步教您上手使用平台。",accent:"#2F6FED",sections:Il},{key:"tech",path:"/tech",nav:"技术文档",desc:"系统架构、仿真算法、数据模型与安全设计等深度技术说明。",accent:"#2F6FED",sections:Rl}],Dl={class:"home"},Hl={class:"vision"},Ll={class:"vision-grid"},Nl={class:"vision-tag"},jl={class:"tech"},Bl={class:"tech-grid"},Gl={class:"cards"},Kl=["onClick"],Vl={class:"card-num"},$l={__name:"HomePage",setup(e){const t=[{key:"save",title:"低耗能",desc:"AI 算法调度持续挖掘日常运行中的节能空间：焦比怎么调、喷煤配多少、工序能耗怎么平衡，一遍遍仿真寻优，花小钱、办大事，让每一度电、每一吨燃料都物尽其用。"},{key:"low-carbon",title:"低碳",desc:'碳素流仿真与碳排放核算双引擎，从"算得清"到"降得下"：每一次仿真同步算出能耗、碳排与成本，帮助企业以可承受的代价走向深度减排。'},{key:"earth",title:"保护地球",desc:"面向钢铁、水泥、化工、有色等全国碳市场重点控排行业及更多高耗能行业，让每一家控排企业都拥有一双智慧的眼睛和一颗 AI 的大脑，让节能减碳变得简单、确定、看得见，共同守护我们的绿色家园。"}],s=[{name:"3D 数字孪生",desc:"20+ 工序模型，热力图着色与物流粒子动画"},{name:"云边协同",desc:"KubeEdge 云边一体，能碳一体机一条命令接入"},{name:"碳素流仿真引擎",desc:"设备级物料平衡，先能后碳双重核算"},{name:"AI 优化模型引擎",desc:"GA / PSO / RL / 时序预测 / 聚类五套在线模型"},{name:"LLM 智能体",desc:"自然语言策略解析、AI 报告与知识库"},{name:"碳市场行情",desc:"CEA / CCER 实时行情与价格趋势预测"},{name:"实时遥测",desc:"WebSocket + MQTT 云端 Broker 真实读数"},{name:"时序数据库",desc:"TDengine 云端存储与历史曲线降采样"}];return(o,n)=>(J(),Z("div",Dl,[n[5]||(n[5]=O("section",{class:"hero"},[O("h1",null,[ls("工业能碳智控平台 "),O("span",{class:"hero-ver"},"v2.0.0")]),O("p",null,"懂能、懂碳、懂市场的工业级智能平台，为每一家控排企业的节能降碳而生。")],-1)),O("section",Hl,[n[0]||(n[0]=O("h2",{class:"block-title"},"平台愿景",-1)),n[1]||(n[1]=O("p",{class:"block-sub"},"低耗能 · 低碳 · 保护地球 —— 让节能减碳从「拼投入」走向「拼智慧」",-1)),O("div",Ll,[(J(),Z(ce,null,at(t,i=>O("div",{key:i.key,class:"vision-card"},[O("span",Nl,te(i.title),1),O("p",null,te(i.desc),1)])),64))])]),O("section",jl,[n[2]||(n[2]=O("h2",{class:"block-title"},"前沿技术",-1)),n[3]||(n[3]=O("p",{class:"block-sub"},"以最新数字化技术，赋能企业能碳管理全流程",-1)),O("div",Bl,[(J(),Z(ce,null,at(s,i=>O("div",{key:i.name,class:"tech-item"},[O("h3",null,te(i.name),1),O("p",null,te(i.desc),1)])),64))])]),O("section",Gl,[(J(!0),Z(ce,null,at(He(Qs),(i,r)=>(J(),Z("div",{key:i.key,class:"card",style:Nt({"--accent":i.accent}),onClick:l=>He(St)(i.path)},[O("div",Vl,te(String(r+1).padStart(2,"0")),1),O("h2",null,te(i.nav),1),O("p",null,te(i.desc),1),n[4]||(n[4]=O("span",{class:"card-go"},"开始阅读 →",-1))],12,Kl))),128))])]))}};function ri(e){return String(e).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")}function Ye(e){let t=ri(e);return t=t.replace(/`([^`]+)`/g,(s,o)=>"<code>"+o+"</code>"),t=t.replace(/\*\*([^*]+)\*\*/g,"<strong>$1</strong>"),t=t.replace(/\*([^*]+)\*/g,"<em>$1</em>"),t}function Ul(e,t={}){const s=!!(t&&t.headingIds),o=String(e||"").split(`
`),n=[];let i=0,r=0;const l=c=>/^\s*\|.*\|\s*$/.test(c);for(;i<o.length;){const d=o[i].trim();if(!d){i++;continue}if(d.startsWith("```")){const f=[];for(i++;i<o.length&&!o[i].trim().startsWith("```");)f.push(o[i]),i++;i++,n.push('<pre class="rp-code"><code>'+ri(f.join(`
`))+"</code></pre>");continue}if(l(d)){const f=[];for(;i<o.length&&l(o[i].trim());)f.push(o[i].trim()),i++;if(f.length>=2){const p=f[0].split("|").slice(1,-1).map(C=>C.trim()),T=f.slice(2).map(C=>C.split("|").slice(1,-1).map(I=>I.trim()));n.push("<table><thead><tr>"+p.map(C=>"<th>"+Ye(C)+"</th>").join("")+"</tr></thead><tbody>"+T.map(C=>"<tr>"+C.map(I=>"<td>"+Ye(I)+"</td>").join("")+"</tr>").join("")+"</tbody></table>")}else n.push("<p>"+Ye(f[0])+"</p>"),i-=f.length-1;continue}if(/^#{1,4}\s/.test(d)){const f=d.match(/^#+/)[0].length;r+=1;const p=s?' id="md-h-'+r+'"':"";n.push("<h"+f+p+">"+Ye(d.replace(/^#+\s*/,""))+"</h"+f+">"),i++;continue}if(/^(-{3,}|\*{3,})$/.test(d)){n.push("<hr/>"),i++;continue}if(/^>\s?/.test(d)){const f=[];for(;i<o.length&&/^\s*>\s?/.test(o[i]);)f.push(o[i].replace(/^\s*>\s?/,"")),i++;n.push("<blockquote>"+f.map(p=>Ye(p)).join("<br/>")+"</blockquote>");continue}if(/^\s*[-*]\s/.test(d)||/^\s*\d+\.\s/.test(d)){const f=/^\s*\d+\.\s/.test(d),p=[];for(;i<o.length&&(f?/^\s*\d+\.\s/.test(o[i]):/^\s*[-*]\s/.test(o[i]));)p.push(Ye(o[i].replace(/^\s*\d+\.\s/,"").replace(/^\s*[-*]\s/,""))),i++;const T=f?"ol":"ul";n.push("<"+T+">"+p.map(C=>"<li>"+C+"</li>").join("")+"</"+T+">");continue}n.push("<p>"+Ye(d)+"</p>"),i++}return n.join(`
`)}const Wl={class:"toc"},Ql={class:"toc-title"},ql={class:"toc-list"},zl=["onClick"],Jl={class:"toc-no"},Yl={class:"doc-body"},Zl={class:"doc-head"},Xl=["id"],ec={class:"sec-title"},tc={class:"sec-badge"},sc=["innerHTML"],oc={class:"doc-end"},nc={__name:"DocPage",props:{doc:{type:Object,required:!0}},setup(e){const t=e,s=lt(null),o=lt(""),n=lt(!1),i=ft(()=>t.doc.sections.map((p,T)=>({id:p.id,title:p.title,no:T+1}))),r=ft(()=>{const p=new Map(t.doc.sections.map((T,C)=>[T.id,C+1]));return T=>p.get(T)||""});function l(p){o.value=p;const T=document.getElementById(p);T&&s.value&&s.value.scrollTo({top:T.offsetTop-20,behavior:"smooth"})}function c(){const p=s.value;if(!p)return;n.value=p.scrollTop>400;let T=t.doc.sections.length?t.doc.sections[0].id:"";for(const C of t.doc.sections){const I=document.getElementById(C.id);I&&I.offsetTop<=p.scrollTop+140&&(T=C.id)}T!==o.value&&(o.value=T)}function d(){s.value&&s.value.scrollTo({top:0,behavior:"smooth"})}function f(){o.value=t.doc.sections.length?t.doc.sections[0].id:"",n.value=!1,s.value&&(s.value.scrollTop=0)}return Zt(()=>t.doc,()=>{Tn(f)}),co(f),Pn(()=>{}),(p,T)=>(J(),Z("div",{class:"doc",style:Nt({"--accent":e.doc.accent})},[O("aside",Wl,[O("div",Ql,te(e.doc.nav),1),O("div",ql,[(J(!0),Z(ce,null,at(i.value,C=>(J(),Z("a",{key:C.id,class:jt({active:o.value===C.id}),onClick:es(I=>l(C.id),["prevent"])},[O("span",Jl,te(C.no),1),ls(te(C.title),1)],10,zl))),128))])]),O("div",{ref_key:"scrollEl",ref:s,class:"doc-scroll",onScrollPassive:c},[O("div",Yl,[O("header",Zl,[O("h1",null,te(e.doc.nav),1)]),(J(!0),Z(ce,null,at(e.doc.sections,C=>(J(),Z("section",{key:C.id,id:C.id,class:"doc-section"},[O("h2",ec,[O("span",tc,te(r.value(C.id)),1),ls(te(C.title),1)]),O("div",{class:"doc-md",innerHTML:He(Ul)(C.body)},null,8,sc)],8,Xl))),128)),O("footer",oc,"—— "+te(e.doc.nav)+" 完 ——",1)]),Xi(O("button",{class:"to-top",onClick:d},"回到顶部",512),[[ll,n.value]])],544)],4))}},ic={class:"site"},rc={class:"topbar"},lc={class:"nav"},cc=["href","onClick"],ac=["title"],uc={key:0,viewBox:"0 0 16 16",fill:"none",stroke:"currentColor","stroke-width":"1.5","stroke-linecap":"round"},fc={key:1,viewBox:"0 0 16 16",fill:"none",stroke:"currentColor","stroke-width":"1.5","stroke-linecap":"round","stroke-linejoin":"round"},dc=["href"],pc={class:"main"},hc={key:2,class:"notfound"},Qo="docs-site-dark",gc={__name:"App",setup(e){const t=ft(()=>Pt.value==="/"||Pt.value===""),s=ft(()=>Qs.find(l=>l.path===Pt.value)),o=ft(()=>ii.value.from||""),n=lt(!1);function i(l){n.value=l,document.body.classList.toggle("dark",l)}function r(){i(!n.value),localStorage.setItem(Qo,n.value?"1":"0")}return co(()=>{const l=localStorage.getItem(Qo);l&&i(l==="1")}),(l,c)=>(J(),Z("div",ic,[O("header",rc,[O("div",{class:"brand",onClick:c[0]||(c[0]=d=>He(St)("/"))},[...c[3]||(c[3]=[O("span",{class:"brand-badge"},"能碳",-1),O("span",{class:"brand-name"},"能碳一体机 · 文档中心",-1)])]),O("nav",lc,[(J(!0),Z(ce,null,at(He(Qs),d=>(J(),Z("a",{key:d.key,class:jt({active:s.value&&s.value.key===d.key}),href:d.path,onClick:es(f=>He(St)(d.path),["prevent"])},te(d.nav),11,cc))),128))]),O("button",{class:"theme-toggle",title:n.value?"切换到日间模式":"切换到夜间模式",onClick:r},[n.value?(J(),Z("svg",uc,[...c[4]||(c[4]=[O("circle",{cx:"8",cy:"8",r:"3.2"},null,-1),O("path",{d:"M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.4 3.4l1.4 1.4M11.2 11.2l1.4 1.4M12.6 3.4l-1.4 1.4M4.8 11.2l-1.4 1.4"},null,-1)])])):(J(),Z("svg",fc,[...c[5]||(c[5]=[O("path",{d:"M13.5 9.2A5.6 5.6 0 0 1 6.8 2.5a5.6 5.6 0 1 0 6.7 6.7Z"},null,-1)])])),O("span",null,te(n.value?"日间":"夜间"),1)],8,ac),o.value?(J(),Z("a",{key:0,class:"back-platform",href:o.value},"返回平台",8,dc)):(J(),Z("a",{key:1,class:"back-platform",href:"#/",onClick:c[1]||(c[1]=es(d=>He(St)("/"),["prevent"]))},"首页"))]),O("main",pc,[t.value?(J(),Do($l,{key:0})):s.value?(J(),Do(nc,{key:1,doc:s.value},null,8,["doc"])):(J(),Z("div",hc,[c[6]||(c[6]=O("h2",null,"页面不存在",-1)),O("a",{href:"#/",onClick:c[2]||(c[2]=es(d=>He(St)("/"),["prevent"]))},"返回首页")]))]),c[7]||(c[7]=O("footer",{class:"foot"},"能碳一体机 · 文档中心 · v2.1.0",-1))]))}};Al(gc).mount("#app");
