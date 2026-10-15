import * as THREE from "./vendor/three.module.min.js";
import {CONCEPTS,makeGraph,seededRandom,sceneProgress} from "./engine-data.mjs";

const pointVertex=`
attribute vec3 aScatter;
attribute vec3 aTint;
attribute float aSize;
attribute float aCluster;
uniform float uAssembly,uTime,uRatio,uScroll,uSelected;
varying vec3 vTint;
void main(){
  float t=clamp(uAssembly,0.,1.);t=t*t*(3.-2.*t);
  vec3 p=mix(aScatter,position,t);
  float branch=smoothstep(.13,.4,uScroll)*(1.-smoothstep(.65,.95,uScroll));
  p.x+=sin(aCluster*1.7)*branch*.8;
  p.y+=cos(aCluster*1.3)*branch*.6;
  p+=vec3(sin(uTime*.16+aCluster),cos(uTime*.13+aCluster),0.)*.024;
  vec4 view=modelViewMatrix*vec4(p,1.);
  gl_Position=projectionMatrix*view;
  float selected=1.-step(.4,abs(aCluster-uSelected));
  gl_PointSize=clamp(aSize*uRatio*(180./max(-view.z,1.)),1.,42.);
  vTint=mix(aTint,vec3(.6,1.,.94),selected*.6);
}`;
const pointFragment=`
varying vec3 vTint;
void main(){float d=length(gl_PointCoord-.5);if(d>.5)discard;
float glow=exp(-d*8.);float core=1.-smoothstep(.015,.12,d);
gl_FragColor=vec4(vTint*(.65+core*2.),glow*.72+core*.45);}`;
const lineVertex=`
attribute vec3 aScatter;attribute float aDistance;attribute float aPhase;
uniform float uAssembly;
varying float vDistance,vPhase;
void main(){float t=smoothstep(.05,1.,uAssembly);vec3 p=mix(aScatter,position,t);
vDistance=aDistance;vPhase=aPhase;gl_Position=projectionMatrix*modelViewMatrix*vec4(p,1.);}`;
const lineFragment=`
uniform float uTime,uAssembly,uScroll,uState;
varying float vDistance,vPhase;
void main(){float pulse=pow(max(0.,sin(vDistance*7.-uTime*1.2+vPhase)),18.);
vec3 cyan=vec3(.22,.8,.78);vec3 violet=vec3(.51,.34,.9);
vec3 tint=mix(cyan,violet,step(.75,fract(vPhase)));
float dim=mix(1.,.35,smoothstep(.24,.6,uScroll));
gl_FragColor=vec4(tint*(.65+pulse*1.8),(.22+pulse*.6)*smoothstep(.12,.8,uAssembly)*dim);}`;
const bloomFragment=`
uniform sampler2D tScene;uniform vec2 resolution;varying vec2 vUv;
void main(){vec3 base=texture2D(tScene,vUv).rgb;vec3 light=vec3(0.);
for(int x=-1;x<=1;x++){for(int y=-1;y<=1;y++){
vec3 c=texture2D(tScene,vUv+vec2(float(x),float(y))*3.5/resolution).rgb;
light+=max(c-vec3(.32),vec3(0.));}}
vec3 color=base+light*.2;float vignette=1.-length((vUv-.5)*.85)*.28;
gl_FragColor=vec4(color*vignette,1.);}`;

export function createEngineScene(canvas,{onStatus=()=>{},onFallback=()=>{}}={}) {
  const context=canvas.getContext("webgl2",{alpha:true,antialias:false,powerPreference:"low-power"});
  if(!context)throw new Error("WebGL2 is unavailable");
  const mobile=window.innerWidth<=800;
  const renderer=new THREE.WebGLRenderer({canvas,context,alpha:true,antialias:false,powerPreference:"low-power"});
  renderer.setClearColor(0x05080d,1);
  renderer.info.autoReset=false;
  renderer.outputColorSpace=THREE.SRGBColorSpace;
  const scene=new THREE.Scene();
  const camera=new THREE.PerspectiveCamera(46,1,.1,90);camera.position.set(0,0,12);
  const graph=new THREE.Group();scene.add(graph);
  const random=seededRandom(58),geometry=makeGraph(mobile?240:420);
  const state={progress:0,selected:0,scenario:0,pointerX:0,pointerY:0,paused:false};
  const uniforms={uAssembly:{value:0},uTime:{value:0},uRatio:{value:1},uScroll:{value:0},uSelected:{value:0},uState:{value:0}};
  function points(data,sizes,clusters) {
    const g=new THREE.BufferGeometry();
    g.setAttribute("position",new THREE.Float32BufferAttribute(data.positions,3));
    g.setAttribute("aScatter",new THREE.Float32BufferAttribute(data.scattered,3));
    g.setAttribute("aTint",new THREE.Float32BufferAttribute(data.colors,3));
    g.setAttribute("aSize",new THREE.Float32BufferAttribute(sizes,1));
    g.setAttribute("aCluster",new THREE.Float32BufferAttribute(clusters,1));
    return new THREE.Points(g,new THREE.ShaderMaterial({uniforms,vertexShader:pointVertex,fragmentShader:pointFragment,transparent:true,depthWrite:false,blending:THREE.AdditiveBlending}));
  }
  graph.add(points(geometry,Array.from({length:geometry.positions.length/3},()=>.22+random()*.24),Array.from({length:geometry.positions.length/3},(_,i)=>Math.floor(i/60))));
  const starData={positions:[],scattered:[],colors:[]},starSizes=[],starClusters=[];
  const starCount=mobile?1500:4200;
  for(let i=0;i<starCount;i++){
    const x=(random()-.5)*28,y=(random()-.5)*20,z=(random()-.5)*22;
    starData.positions.push(x,y,z);starData.scattered.push(x*1.15,y*1.15,z*1.15);
    starData.colors.push(.16+random()*.16,.32+random()*.3,.5+random()*.25);starSizes.push(.025+random()*.065);starClusters.push(-10);
  }
  scene.add(points(starData,starSizes,starClusters));
  const anchors={positions:[],scattered:[],colors:[]};
  CONCEPTS.forEach(concept=>{anchors.positions.push(...concept.position);anchors.scattered.push(...concept.position.map(n=>n*2));anchors.colors.push(.38,.95,.88);});
  graph.add(points(anchors,CONCEPTS.map(()=>1.2),CONCEPTS.map((_,i)=>i)));
  const positions=[],scattered=[],distances=[],phases=[];
  for(let i=0;i<geometry.edges.length;i+=2){
    const phase=random()*20;
    for(let endpoint=0;endpoint<2;endpoint++){
      const index=geometry.edges[i+endpoint]*3;
      positions.push(...geometry.positions.slice(index,index+3));
      scattered.push(...geometry.scattered.slice(index,index+3));distances.push(endpoint);phases.push(phase);
    }
  }
  const lines=new THREE.BufferGeometry();
  lines.setAttribute("position",new THREE.Float32BufferAttribute(positions,3));
  lines.setAttribute("aScatter",new THREE.Float32BufferAttribute(scattered,3));
  lines.setAttribute("aDistance",new THREE.Float32BufferAttribute(distances,1));
  lines.setAttribute("aPhase",new THREE.Float32BufferAttribute(phases,1));
  graph.add(new THREE.LineSegments(lines,new THREE.ShaderMaterial({uniforms,vertexShader:lineVertex,fragmentShader:lineFragment,transparent:true,depthWrite:false,blending:THREE.AdditiveBlending})));
  const branchGroup=new THREE.Group();graph.add(branchGroup);
  const branchMaterials=[];
  for(let i=0;i<3;i++){
    const curve=new THREE.CatmullRomCurve3([new THREE.Vector3(-2,0,0),new THREE.Vector3(-.2,0,0),new THREE.Vector3(1.4,(i-1)*1.3,0),new THREE.Vector3(3.4,(i-1)*2,1-i)]);
    const material=new THREE.LineBasicMaterial({color:[0xf3b36b,0x7df6e9,0xae90f8][i],transparent:true,opacity:0,blending:THREE.AdditiveBlending});
    branchMaterials.push(material);branchGroup.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(curve.getPoints(48)),material));
  }
  const shieldMaterial=new THREE.ShaderMaterial({uniforms:{opacity:{value:0}},vertexShader:`varying vec3 vNormal,vView;void main(){vec4 p=modelViewMatrix*vec4(position,1.);vNormal=normalize(normalMatrix*normal);vView=normalize(-p.xyz);gl_Position=projectionMatrix*p;}`,fragmentShader:`uniform float opacity;varying vec3 vNormal,vView;void main(){float f=pow(1.-abs(dot(normalize(vNormal),normalize(vView))),3.5);gl_FragColor=vec4(.35,.82,.79,f*opacity);}`,transparent:true,depthWrite:false,blending:THREE.AdditiveBlending,side:THREE.DoubleSide});
  graph.add(new THREE.Mesh(new THREE.SphereGeometry(3.25,32,24),shieldMaterial));
  let target=null,postScene=null,postCamera=null,postMaterial=null;
  if(!mobile){
    target=new THREE.WebGLRenderTarget(1,1,{depthBuffer:true});postScene=new THREE.Scene();postCamera=new THREE.OrthographicCamera(-1,1,1,-1,0,1);
    postMaterial=new THREE.ShaderMaterial({uniforms:{tScene:{value:target.texture},resolution:{value:new THREE.Vector2(1,1)}},vertexShader:`varying vec2 vUv;void main(){vUv=uv;gl_Position=vec4(position.xy,0.,1.);}`,fragmentShader:bloomFragment,depthTest:false,depthWrite:false});
    postScene.add(new THREE.Mesh(new THREE.PlaneGeometry(2,2),postMaterial));
  }
  let frame=0,lastFrame=0,time=0,started=performance.now(),disposed=false,hidden=document.hidden;
  const pins=[...document.querySelectorAll(".node-pin")];
  const layer=document.getElementById("node-pins");
  const hero=document.getElementById("top");
  const projected=new THREE.Vector3();
  function resize(){
    if(disposed)return;
    const ratio=Math.min(devicePixelRatio||1,mobile?1:1.5);renderer.setPixelRatio(ratio);
    renderer.setSize(innerWidth,innerHeight,false);camera.aspect=innerWidth/innerHeight;camera.updateProjectionMatrix();
    uniforms.uRatio.value=ratio;
    if(target){target.setSize(innerWidth*ratio,innerHeight*ratio);postMaterial.uniforms.resolution.value.set(innerWidth*ratio,innerHeight*ratio);}
    render(performance.now(),true);
  }
  function render(now,once=false){
    if(disposed||hidden)return;
    renderer.info.reset();
    const p=sceneProgress(state.progress);
    uniforms.uScroll.value=p;uniforms.uSelected.value=state.selected;uniforms.uState.value=state.scenario;
    if(!state.paused){time+=Math.min((now-lastFrame)/1000,.05);uniforms.uTime.value=time;}
    uniforms.uAssembly.value=state.paused?1:Math.min(1,(now-started)/2100);
    const narrow=innerWidth<=800;
    graph.position.set(narrow?0:3.5,narrow?-2.65:.05,0);graph.scale.setScalar(narrow?.78:1);
    graph.rotation.y=state.paused?-.12:Math.sin(time*.045)*.17+p*1.5;
    graph.rotation.z=state.paused?-.12:Math.sin(time*.035)*.04-.12+p*.2;
    camera.position.x+=((state.paused?0:state.pointerX*.45)-camera.position.x)*.045;
    camera.position.y+=((state.paused?0:state.pointerY*.3+p*.8)-camera.position.y)*.045;
    camera.position.z+=(12-p*3.8-camera.position.z)*.035;
    camera.lookAt(narrow?0:1.0,0,0);
    const branch=Math.max(0,1-Math.abs(p-.36)*5);
    branchGroup.rotation.y=-graph.rotation.y*.5;
    const selectedBranch=state.scenario===0?1:state.scenario===1?0:2;
    branchMaterials.forEach((material,index)=>{material.opacity=branch*(index===selectedBranch?.8:.12);});
    shieldMaterial.uniforms.opacity.value=Math.max(0,1-Math.abs(p-.7)*5)*.22;
    if(target&&postScene&&postCamera){renderer.setRenderTarget(target);renderer.render(scene,camera);renderer.setRenderTarget(null);renderer.render(postScene,postCamera);}else renderer.render(scene,camera);
    if(!narrow&&layer&&hero.getBoundingClientRect().bottom>0){
      graph.updateMatrixWorld();const rect=layer.getBoundingClientRect();
      CONCEPTS.forEach((concept,index)=>{
        projected.set(...concept.position).applyMatrix4(graph.matrixWorld).project(camera);
        const x=(projected.x*.5+.5)*innerWidth-rect.left,y=(-projected.y*.5+.5)*innerHeight-rect.top;
        if(pins[index]){pins[index].style.left=`${Math.max(90,Math.min(rect.width-85,x))}px`;pins[index].style.top=`${Math.max(24,Math.min(rect.height-12,y))}px`;}
      });
    }
    if(once)lastFrame=now;
  }
  function loop(now){
    frame=0;if(disposed||hidden||state.paused)return;
    const interval=1000/(mobile?30:45);
    if(now-lastFrame>=interval){render(now);lastFrame=now;}
    frame=requestAnimationFrame(loop);
  }
  function schedule(){if(!frame&&!hidden&&!disposed&&!state.paused)frame=requestAnimationFrame(loop);}
  function visibility(){hidden=document.hidden;if(hidden){cancelAnimationFrame(frame);frame=0;}else{lastFrame=performance.now();schedule();if(state.paused)render(lastFrame,true);}}
  function contextLost(event){event.preventDefault();if(!disposed){dispose();onFallback("WebGL context lost; static overview available");}}
  function update(values){Object.assign(state,values);if(state.paused){cancelAnimationFrame(frame);frame=0;render(performance.now(),true);}else schedule();}
  function dispose(){
    if(disposed)return;disposed=true;cancelAnimationFrame(frame);
    window.removeEventListener("resize",resize);document.removeEventListener("visibilitychange",visibility);canvas.removeEventListener("webglcontextlost",contextLost);
    const disposedGeometries=new Set(),disposedMaterials=new Set();
    for(const root of [scene,postScene])root?.traverse(object=>{
      if(object.geometry&&!disposedGeometries.has(object.geometry)){object.geometry.dispose();disposedGeometries.add(object.geometry);}
      for(const material of (Array.isArray(object.material)?object.material:[object.material]))if(material&&!disposedMaterials.has(material)){material.dispose();disposedMaterials.add(material);}
    });
    target?.dispose();renderer.dispose();
  }
  window.addEventListener("resize",resize,{passive:true});document.addEventListener("visibilitychange",visibility);canvas.addEventListener("webglcontextlost",contextLost);
  resize();schedule();onStatus("WEBGL2 / INTERACTIVE GRAPH");
  return {update,dispose,stats:()=>({drawCalls:renderer.info.render.calls,particles:starCount+geometry.positions.length/3+7,pixelRatio:renderer.getPixelRatio(),frameCap:mobile?30:45})};
}
