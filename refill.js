(()=>{
  'use strict';

  // Start checking for a newer published feed while there is still a full
  // 30-row reserve behind the visible 30. This only reloads jobs.json; it never
  // calls SerpApi, dispatches Actions, or exposes credentials.
  const ACTION_REFILL_TRIGGER=60;
  const REFILL_COOLDOWN_MS=30_000;
  const FOREGROUND_RECHECK_MS=5*60_000;
  let lastAttempt=0;
  let inFlight=null;

  function availableCount(){
    const node=document.querySelector('#countAvailable');
    if(!node)return null;
    const value=Number.parseInt(String(node.textContent||'').replace(/[^0-9]/g,''),10);
    return Number.isFinite(value)?value:null;
  }

  async function reloadLatestIfLow({force=false}={}){
    const available=availableCount();
    if(!force&&(available===null||available>=ACTION_REFILL_TRIGGER))return false;
    if(typeof window.loadFeed!=='function')return false;
    const now=Date.now();
    if(inFlight||(!force&&now-lastAttempt<REFILL_COOLDOWN_MS))return false;
    lastAttempt=now;
    inFlight=Promise.resolve()
      .then(()=>window.loadFeed())
      .catch(()=>false)
      .finally(()=>{inFlight=null;});
    await inFlight;
    return true;
  }

  // The card's own onclick handler updates the local action state first. Run on
  // the next task so countAvailable reflects the post-action stock before we
  // decide whether a network refresh is useful.
  document.addEventListener('click',event=>{
    const action=event.target.closest?.('.applied,.decline');
    if(!action)return;
    setTimeout(()=>{void reloadLatestIfLow();},0);
  });

  // Returning to the PWA is another natural point to pick up a newer feed.
  document.addEventListener('visibilitychange',()=>{
    if(document.visibilityState==='visible')void reloadLatestIfLow();
  });

  // While the app stays open, poll only when local stock is low. The request is
  // a cache-busted static jobs.json fetch through loadFeed(), not a search API.
  window.setInterval(()=>{
    if(document.visibilityState==='visible')void reloadLatestIfLow();
  },FOREGROUND_RECHECK_MS);

  window.__candidateRefill={
    trigger:ACTION_REFILL_TRIGGER,
    reloadLatestIfLow,
  };
})();
