// Record the Leaves.PH LinkedIn demo GIF + MP4 of the live interactive map.
//
// Reproducible recipe (run from site/):
//   pnpm build && pnpm preview --port 4330 &
//   node scripts/record_linkedin_demo.mjs
//
// Records the production preview build (no dev toolbar), drives the REAL map
// the way a visitor does (year scrubber, fly-in, satellite basemap, click a
// detected crown -> live Esri aerial of that tree), then ffmpeg palette-encodes
// to docs/demo/linkedin-demo.{gif,mp4}. The crown aerial popup is the same
// feature users trigger by clicking; it is opened deterministically here so the
// climax always lands. Skips the first-visit auto-sweep + onboarding tip.
import { chromium } from 'playwright';
import { execSync } from 'node:child_process';
import fs from 'node:fs';
const BASE='http://localhost:4330';
const OUT='/Users/xavier/Desktop/leaves-ph/docs/demo';
const WORK='/Users/xavier/Desktop/leaves-ph/tmp/demo-record';
fs.rmSync(WORK,{recursive:true,force:true}); fs.mkdirSync(WORK+'/video',{recursive:true}); fs.mkdirSync(OUT,{recursive:true});

const skipFx=()=>{ try{localStorage.setItem('leaves_swept','1');localStorage.setItem('leaves_onboarded','1');}catch(e){} };
const cursorInit=()=>{
  const c=document.createElement('div'); c.id='__cursor';
  c.style.cssText='position:fixed;left:-60px;top:-60px;width:22px;height:22px;border:2px solid #1a1a1a;border-radius:50%;background:rgba(182,87,36,0.4);box-shadow:0 1px 5px rgba(0,0,0,0.35);z-index:99999;pointer-events:none;transform:translate(-50%,-50%);transition:left 0.45s ease,top 0.45s ease;';
  const add=()=>{(document.body||document.documentElement).appendChild(c);};
  if(document.body) add(); else document.addEventListener('DOMContentLoaded',add);
  window.__cur=(x,y)=>{const e=document.getElementById('__cursor'); if(e){e.style.left=x+'px';e.style.top=y+'px';}};
  window.__pulse=()=>{const e=document.getElementById('__cursor'); if(e){e.animate([{transform:'translate(-50%,-50%) scale(1)'},{transform:'translate(-50%,-50%) scale(0.55)'},{transform:'translate(-50%,-50%) scale(1)'}],{duration:300});}};
};
// Reliable aerial-popup: same feature users trigger by clicking a crown, opened
// deterministically so the demo always lands the climax. Plain labels.
const POPUP=`function(status, nearLng, nearLat){
  var map=window.__map; if(!map) return null;
  var feats=map.queryRenderedFeatures({layers:['crowns-fill']});
  var feat=null,bs=-1e9;
  for(var i=0;i<feats.length;i++){ if(feats[i].properties.status!==status) continue;
    var a=+(feats[i].properties.area_m2||0); if(a<300||a>80000) continue;
    var g=feats[i].geometry, cc=g.type==='Polygon'?g.coordinates[0]:g.coordinates[0][0];
    var lo=0,la=0; for(var j=0;j<cc.length;j++){lo+=cc[j][0];la+=cc[j][1];} lo/=cc.length; la/=cc.length;
    var sc=Math.log(a); if(typeof nearLng==='number'){var dx=(lo-nearLng)*111000*Math.cos(la*Math.PI/180),dy=(la-nearLat)*111000;sc-=Math.sqrt(dx*dx+dy*dy)/60;}
    if(sc>bs){bs=sc;feat=feats[i];} }
  if(!feat) return null;
  var g=feat.geometry, coords=g.type==='Polygon'?g.coordinates[0]:g.coordinates[0][0];
  var mnx=1e9,mxx=-1e9,mny=1e9,mxy=-1e9;
  for(var k=0;k<coords.length;k++){var c=coords[k];if(c[0]<mnx)mnx=c[0];if(c[0]>mxx)mxx=c[0];if(c[1]<mny)mny=c[1];if(c[1]>mxy)mxy=c[1];}
  var pl=Math.max(0.0005,(mxx-mnx)*1.8),pa=Math.max(0.0005,(mxy-mny)*1.8);
  var bbox=[mnx-pl,mny-pa,mxx+pl,mxy+pa].join(','),W=420,H=420;
  var img='https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export?bbox='+bbox+'&size='+W+','+H+'&imageSR=4326&bboxSR=4326&format=jpg&f=image';
  var cx=(mnx+mxx)/2,cy=(mny+mxy)/2,p=feat.properties||{};
  var META={confirmed:{color:'#1f6634',label:'confirmed by street maps'},'new':{color:'#d4a019',label:'tall canopy (8 m or more)'},candidate:{color:'#9ca3af',label:'likely tree (5 to 8 m)'}};
  var m=META[status]||{color:'#1f3d2b',label:status};
  var isN=function(v){return typeof v==='number'&&!isNaN(v);};
  var area=isN(p.area_m2)?Number(p.area_m2).toFixed(0)+' m²':'--';
  var p95=isN(p.p95_height_m)?Number(p.p95_height_m).toFixed(1)+' m':'--';
  var lgu=(typeof p.lgu_name==='string'&&p.lgu_name&&p.lgu_name!=='null')?p.lgu_name:'';
  var html='<div style="font-family:\\'PT Serif\\',serif;max-width:'+W+'px;padding:4px;">'
    +'<div style="position:relative;width:'+W+'px;height:'+H+'px;background:#eee;overflow:hidden;border:1px solid #1a1a1a;">'
    +'<img src="'+img+'" alt="satellite photo of this tree" style="width:'+W+'px;height:'+H+'px;display:block;" />'
    +'<div style="position:absolute;left:8px;top:8px;padding:3px 8px;background:'+m.color+';color:#fff;font-family:\\'JetBrains Mono\\',monospace;font-size:11px;letter-spacing:0.1em;text-transform:uppercase;font-weight:600;">'+m.label+'</div></div>'
    +'<div style="font-family:\\'JetBrains Mono\\',monospace;font-size:11px;line-height:1.5;color:#1a1a1a;margin-top:8px;">'
    +'<div style="color:#5a4f3a;">'+(lgu?lgu+' \\u00b7 ':'')+'height '+p95+' \\u00b7 '+area+'</div></div></div>';
  document.querySelectorAll('.maplibregl-popup-close-button').forEach(function(b){b.click();});
  var sheet=document.getElementById('lgu-sheet'); if(sheet) sheet.classList.add('translate-x-full');
  var H2=map.getCanvas().getBoundingClientRect().height;
  map.flyTo({center:[cx,cy],zoom:Math.max(map.getZoom(),16),offset:[0,-H2*0.40],duration:600});
  setTimeout(function(){ new window.maplibregl.Popup({maxWidth:'460px',closeButton:true,anchor:'top',offset:6}).setLngLat([cx,cy]).setHTML(html).addTo(map); },680);
  return {status:status,lgu:lgu,lng:cx,lat:cy};
}`;

const b=await chromium.launch({headless:true});
const warm=await b.newContext({viewport:{width:1280,height:800}});
const wp=await warm.newPage(); await wp.addInitScript(skipFx);
await wp.goto(BASE+'/',{waitUntil:'domcontentloaded'});
await wp.waitForFunction(()=>window.__map&&window.__map.isStyleLoaded&&window.__map.isStyleLoaded()&&window.__map.getLayer('crowns-fill'),{timeout:60000});
await wp.evaluate(()=>window.__map.jumpTo({center:[121.065,14.655],zoom:15.6})); await wp.waitForTimeout(4000); await warm.close();

const ctx=await b.newContext({viewport:{width:1280,height:800}, deviceScaleFactor:2, recordVideo:{dir:WORK+'/video',size:{width:1280,height:800}}});
const page=await ctx.newPage();
await page.addInitScript(skipFx); await page.addInitScript(cursorInit);
await page.goto(BASE+'/',{waitUntil:'domcontentloaded'});
await page.waitForFunction(()=>window.__map&&window.__map.isStyleLoaded&&window.__map.isStyleLoaded()&&window.__map.getLayer('crowns-fill'),{timeout:60000});
await page.evaluate('window.__popup='+POPUP+';');
await page.waitForTimeout(1200);
const tLoaded=Date.now();
const cur=(x,y)=>page.evaluate(([x,y])=>window.__cur(x,y),[x,y]);
const setYear=(yr)=>page.evaluate((yr)=>{const s=document.getElementById('year-slider');s.value=String(yr);s.dispatchEvent(new Event('input',{bubbles:true}));},yr);

// BEAT 1: land NCR-wide @2026
await page.evaluate(()=>window.__map.jumpTo({center:[121.035,14.62],zoom:10.6})); await setYear(2026); await page.waitForTimeout(1300);
// BEAT 2: year sweep (choropleth breathes)
const sb=await page.locator('#year-slider').boundingBox(); const sx=(yr)=>sb.x+sb.width*((yr-2019)/7), sy=sb.y+sb.height/2;
await cur(sx(2026),sy); await page.waitForTimeout(250);
for(const yr of [2024,2021,2019]){ await setYear(yr); await cur(sx(yr),sy); await page.waitForTimeout(230); }
for(const yr of [2021,2024,2026]){ await setYear(yr); await cur(sx(yr),sy); await page.waitForTimeout(220); }
await page.waitForTimeout(250);
// BEAT 3: fly to a tree-dense belt (QC / UP Diliman)
await page.evaluate(()=>window.__map.flyTo({center:[121.065,14.655],zoom:15.2,duration:1700,essential:true})); await page.waitForTimeout(1800);
// BEAT 4: satellite basemap (aerial context under the crowns)
await page.evaluate(()=>{const r=document.getElementById('basemap-sat'); r.checked=true; r.dispatchEvent(new Event('change',{bubbles:true}));}); await page.waitForTimeout(1300);
// BEAT 5: cursor to a crown, click-pulse, open the satellite aerial popup
const px0=await page.evaluate(()=>{const p=window.__map.project([121.065,14.655]);return {x:p.x,y:p.y};});
await cur(px0.x,px0.y-20); await page.waitForTimeout(350); await page.evaluate(()=>window.__pulse());
let out=await page.evaluate(()=>window.__popup('confirmed',121.065,14.655));
if(!out) out=await page.evaluate(()=>window.__popup('new',121.065,14.655));
await page.waitForFunction(()=>{const i=document.querySelector('.maplibregl-popup-content img');return i&&i.complete&&i.naturalWidth>0;},{timeout:6000}).catch(()=>{});
await page.waitForTimeout(2500);
// BEAT 6: close, land on the find-your-barangay invite
await page.evaluate(()=>document.querySelectorAll('.maplibregl-popup-close-button').forEach(x=>x.click())); await page.waitForTimeout(300);
const srch=await page.locator('#barangay-search').boundingBox(); if(srch){ await cur(srch.x+srch.width*0.5, srch.y+srch.height/2);} await page.waitForTimeout(1100);
const tEnd=Date.now();
await ctx.close(); await b.close();

const beatsSec=((tEnd-tLoaded)/1000);
const webm=WORK+'/video/'+fs.readdirSync(WORK+'/video').find(f=>f.endsWith('.webm'));
const raw=OUT+'/linkedin-demo.webm'; fs.copyFileSync(webm,raw);
// trim to just the beats (tail), with 0.4s lead-in
const trim=WORK+'/trim.webm'; const tail=(beatsSec+0.4).toFixed(1);
execSync(`ffmpeg -y -sseof -${tail} -i "${raw}" -c:v libvpx-vp9 -b:v 3M -an "${trim}"`,{stdio:'ignore'});
const gif=OUT+'/linkedin-demo.gif', palette=WORK+'/palette.png', VF='fps=10,scale=720:-1:flags=lanczos';
execSync(`ffmpeg -y -i "${trim}" -vf "${VF},palettegen=max_colors=128:stats_mode=diff" "${palette}"`,{stdio:'ignore'});
execSync(`ffmpeg -y -i "${trim}" -i "${palette}" -lavfi "${VF}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=5" "${gif}"`,{stdio:'ignore'});
const mp4=OUT+'/linkedin-demo.mp4';
execSync(`ffmpeg -y -i "${trim}" -c:v libx264 -pix_fmt yuv420p -crf 21 -vf "scale=1280:-2:flags=lanczos,format=yuv420p" -movflags +faststart "${mp4}"`,{stdio:'ignore'});
console.log('beatsSec', beatsSec.toFixed(1), 'climax', JSON.stringify(out));
console.log('GIF_MB', (fs.statSync(gif).size/1e6).toFixed(2), 'MP4_MB', (fs.statSync(mp4).size/1e6).toFixed(2));
