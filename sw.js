const CACHE='ai-remote-finder-v8';
const ASSETS=['./','./index.html','./app.js','./manifest.webmanifest','./icon.svg'];
const INDEX_URL=new URL('./index.html',self.registration.scope).toString();
const DATA_URL=new URL('./data/jobs.json',self.registration.scope).toString();

async function putSafe(key,response){
  try{
    const cache=await caches.open(CACHE);
    await cache.put(key,response);
  }catch{}
}

async function networkFirst(request,{cacheKey=request,fallbackKey=cacheKey}={}){
  try{
    const response=await fetch(request,{cache:'no-store'});
    if(response.ok)await putSafe(cacheKey,response.clone());
    return response;
  }catch{
    return (await caches.match(fallbackKey))||Response.error();
  }
}

async function cacheFirst(request){
  const cached=await caches.match(request);
  if(cached)return cached;
  try{
    const response=await fetch(request);
    if(response.ok)await putSafe(request,response.clone());
    return response;
  }catch{
    return Response.error();
  }
}

self.addEventListener('install',event=>{
  self.skipWaiting();
  event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(ASSETS)));
});

self.addEventListener('activate',event=>{
  event.waitUntil(Promise.all([
    self.clients.claim(),
    caches.keys().then(keys=>Promise.all(keys.filter(key=>key!==CACHE).map(key=>caches.delete(key))))
  ]));
});

self.addEventListener('fetch',event=>{
  const url=new URL(event.request.url);
  if(url.pathname.endsWith('/data/jobs.json')){
    event.respondWith(networkFirst(event.request,{cacheKey:DATA_URL,fallbackKey:DATA_URL}));
    return;
  }
  if(event.request.mode==='navigate'){
    event.respondWith(networkFirst(event.request,{cacheKey:INDEX_URL,fallbackKey:INDEX_URL}));
    return;
  }
  if(url.pathname.endsWith('/app.js')||url.pathname.endsWith('/index.html')){
    event.respondWith(networkFirst(event.request));
    return;
  }
  event.respondWith(cacheFirst(event.request));
});