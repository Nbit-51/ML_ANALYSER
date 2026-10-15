import {CONCEPTS,SCENARIOS,FIXTURES,compareFixture,sceneProgress} from "./engine-data.mjs";

const $=id=>document.getElementById(id);
const motionQuery=matchMedia("(prefers-reduced-motion: reduce)");
let scene=null,sceneLoading=null,disposed=false,scrollFrame=0,motionContext=null;
const previewOptions=new URLSearchParams(location.search);
const staticGraphics=previewOptions.get("graphics")==="off";
let paused=motionQuery.matches||previewOptions.get("motion")==="reduce",progress=0,selected=0,scenario=0;
let userPaused=false;
const cleanups=[];
function listen(target,event,handler,options){target.addEventListener(event,handler,options);cleanups.push(()=>target.removeEventListener(event,handler,options));}

function selectConcept(id){
  const index=CONCEPTS.findIndex(concept=>concept.id===id);if(index<0)return;
  const concept=CONCEPTS[index];selected=index;
  $("concept-tag").textContent=concept.tag;$("concept-title").textContent=concept.title;$("concept-text").textContent=concept.text;
  $("ledger-explanation").textContent=`${concept.label}: ${concept.text}`;
  document.querySelectorAll("[data-concept]").forEach(button=>button.setAttribute("aria-pressed",String(button.dataset.concept===id)));
  scene?.update({selected});
}
function selectScenario(id){
  const data=SCENARIOS[id];if(!data)return;
  scenario=Object.keys(SCENARIOS).indexOf(id);document.body.dataset.scenario=id;
  $("scenario-title").textContent=data.title;$("scenario-title").style.color=data.color;
  $("scenario-text").textContent=data.text;
  document.querySelectorAll("[data-scenario]").forEach(button=>{if(button.tagName==="BUTTON")button.setAttribute("aria-pressed",String(button.dataset.scenario===id));});
  scene?.update({scenario});
}
function selectFixture(id){
  const data=FIXTURES[id];if(!data)return;const comparison=compareFixture(data);
  $("fixture-metric").textContent=data.metric;$("fixture-unit").textContent=data.unit;
  $("fixture-baseline").textContent=data.baseline;$("fixture-candidate").textContent=data.candidate;
  $("baseline-config").textContent=data.baselineLabel;$("candidate-config").textContent=data.candidateLabel;
  $("baseline-fill").style.width=`${comparison.baselineWidth}%`;$("candidate-fill").style.width=`${comparison.candidateWidth}%`;
  $("fixture-delta").textContent=String(comparison.delta).replace("-","−");
  $("fixture-percent").textContent=comparison.percent===null?"—":`${comparison.percent}%`;
  $("fixture-check").textContent=data.check;$("fixture-note").textContent=data.note;
  $("fixture-direction").textContent=data.direction==="minimize"?"↓ Lower is better":"↑ Higher is better";
  $("fixture-provenance").textContent=data.provenance;
  $("fixture-source").textContent=`${data.source} ↗`;$("fixture-source").href=`https://github.com/Nbit-51/ML_ANALYSER/blob/main/${data.source}`;
  document.querySelectorAll("[data-fixture]").forEach(button=>button.setAttribute("aria-pressed",String(button.dataset.fixture===id)));
}
function fallback(message="STATIC GRAPH / WEBGL UNAVAILABLE"){
  document.body.classList.remove("graphics-ready");$("graphics-status").textContent=message;
}
async function loadScene(){
  if(staticGraphics){fallback("STATIC GRAPH / 3D DISABLED FOR THIS PREVIEW");return null;}
  if(scene||disposed)return scene;if(sceneLoading)return sceneLoading;
  sceneLoading=(async()=>{
    try{
      const {createEngineScene}=await import("./engine-scene.mjs");
      if(disposed)return;
      scene=createEngineScene($("engine-canvas"),{onStatus:message=>{$("graphics-status").textContent=message;},onFallback:message=>{scene=null;fallback(message);}});
      scene.update({paused,progress:paused?0:progress,selected,scenario});
      document.body.classList.add("graphics-ready");
      const stats=scene.stats();
      $("engine-canvas").dataset.drawCalls=String(stats.drawCalls);$("engine-canvas").dataset.particles=String(stats.particles);$("engine-canvas").dataset.frameCap=String(stats.frameCap);$("engine-canvas").dataset.pixelRatio=String(stats.pixelRatio);
    }catch{fallback();}
  })();
  await sceneLoading;sceneLoading=null;return scene;
}
function readScroll(){
  scrollFrame=0;
  progress=sceneProgress(window.scrollY/Math.max(1,document.documentElement.scrollHeight-innerHeight));
  $("chapter-progress").style.height=`${progress*100}%`;
  scene?.update({progress:paused?0:progress});
}
function requestScroll(){if(!scrollFrame)scrollFrame=requestAnimationFrame(readScroll);}
function setupMotion(){
  motionContext?.revert();motionContext=null;
  if(paused||!window.gsap||!window.ScrollTrigger)return;
  const {gsap,ScrollTrigger}=window;gsap.registerPlugin(ScrollTrigger);
  motionContext=gsap.context(()=>{
    if(scrollY<100){
      gsap.from(".headline-line",{y:46,opacity:0,filter:"blur(9px)",duration:1.35,stagger:.13,delay:.16,ease:"power3.out",clearProps:"filter,transform,opacity"});
      gsap.from(".hero-copy .reveal",{y:15,opacity:0,duration:1,stagger:.12,delay:.25,ease:"power2.out",clearProps:"transform,opacity"});
    }
    gsap.utils.toArray(".engine-chapter .section-title,.benchmark-intro .section-title").forEach(title=>{
      gsap.from(title,{y:35,opacity:.38,ease:"none",scrollTrigger:{trigger:title,start:"top 92%",end:"top 48%",scrub:.7}});
    });
    gsap.utils.toArray(".repository-holo,.ledger-console").forEach(panel=>{
      gsap.fromTo(panel,{y:30},{y:-24,ease:"none",scrollTrigger:{trigger:panel,start:"top bottom",end:"bottom top",scrub:1.1}});
    });
  });
}
function setPaused(value){
  paused=value;document.body.classList.toggle("motion-paused",paused);
  $("motion-toggle").setAttribute("aria-pressed",String(paused));
  $("motion-toggle").innerHTML=paused?'Enable motion <span>▷</span>':'Pause motion <span>Ⅱ</span>';
  if(paused){scene?.update({paused:true,progress:0});$("graphics-status").textContent=(motionQuery.matches||previewOptions.get("motion")==="reduce")?"REDUCED MOTION / STATIC OVERVIEW":"MOTION PAUSED / INTERACTIVE OVERVIEW";}
  else{loadScene().then(()=>{scene?.update({paused:false,progress});if(scene)$("graphics-status").textContent="WEBGL2 / INTERACTIVE GRAPH";});}
  setupMotion();
}
for(const button of document.querySelectorAll("[data-concept]")){
  listen(button,"pointerenter",()=>selectConcept(button.dataset.concept));
  listen(button,"focus",()=>selectConcept(button.dataset.concept));
  listen(button,"click",()=>selectConcept(button.dataset.concept));
}
for(const button of document.querySelectorAll("button[data-scenario]"))listen(button,"click",()=>selectScenario(button.dataset.scenario));
for(const button of document.querySelectorAll("[data-fixture]"))listen(button,"click",()=>selectFixture(button.dataset.fixture));
listen($("motion-toggle"),"click",()=>{userPaused=!paused;setPaused(!paused);});
listen(motionQuery,"change",()=>{if(motionQuery.matches)setPaused(true);else if(!userPaused)setPaused(false);});
listen(window,"pointermove",event=>{if(!paused)scene?.update({pointerX:event.clientX/innerWidth-.5,pointerY:.5-event.clientY/innerHeight});},{passive:true});
listen(window,"scroll",requestScroll,{passive:true});listen(window,"resize",requestScroll,{passive:true});
listen(window,"pagehide",event=>{if(event.persisted){scene?.update({paused:true});return;}disposed=true;cancelAnimationFrame(scrollFrame);motionContext?.revert();scene?.dispose();cleanups.forEach(cleanup=>cleanup());});
listen(window,"pageshow",event=>{if(event.persisted)scene?.update({paused,progress});});
selectConcept("repository");selectScenario("accepted");selectFixture("regression");readScroll();
if(paused)setPaused(true);else{
  setupMotion();
  if("requestIdleCallback" in window)window.requestIdleCallback(()=>loadScene(),{timeout:1200});else setTimeout(()=>loadScene(),120);
}
