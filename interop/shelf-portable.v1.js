/* PhiOS Universal Shelf R2 portable contract. Side-effect module for Web, Mobile and Node tests.
   A pin is a bookmark to a public source, NOT an install, launch permission, or an identity.
   No network, credentials, source execution, automatic sync, or native permissions. */
(function(root){
  'use strict';
  const FORMAT='phios-app-shelf',VERSION=1,LIMIT=24,MAX_BYTES=16384;
  const ID=/^github:[0-9]{1,20}$/;
  const KEYS=['catalog_source_sha','exported_at','format','pinned','version'];
  function catalogMap(catalog){
    if(!catalog || catalog.schema!=='phios.public-repo-catalog.v1' ||
      catalog.provenance?.owner!=='MichaelWave369' ||
      catalog.provenance?.scope!=='public' || catalog.provenance?.complete!==true ||
      !/^[0-9a-f]{40}$/.test(catalog.provenance.source_blob_sha||'') ||
      catalog.policy?.automatic_install!==false ||
      catalog.policy?.automatic_launch!==false ||
      catalog.policy?.review_required!==true ||
      !Array.isArray(catalog.apps) || catalog.apps.length>1000)throw Error('Untrusted public catalog');
    const map=new Map();
    for(const item of catalog.apps){
      if(!item||typeof item.id!=='string'||!ID.test(item.id)||
        item.repository!=='https://github.com/MichaelWave369/'+item.name||
        item.availability!=='source_only'||map.has(item.id))throw Error('Untrusted source identity');
      map.set(item.id,item);
    }
    return map;
  }
  function normalize(pinned,catalog){
    const map=catalogMap(catalog);
    if(!Array.isArray(pinned)||pinned.length>LIMIT)throw Error('Shelf exceeds 24 source pins');
    const seen=new Set();
    for(const id of pinned){
      if(typeof id!=='string'||!ID.test(id)||!map.has(id)||seen.has(id))throw Error('Invalid or duplicate public source pin');
      seen.add(id);
    }
    return [...pinned];
  }
  function packet(pinned,catalog,date=new Date()){
    const clean=normalize(pinned,catalog);
    if(!(date instanceof Date)||Number.isNaN(date.getTime()))throw Error('Invalid timestamp');
    return {format:FORMAT,version:VERSION,catalog_source_sha:catalog.provenance.source_blob_sha,exported_at:date.toISOString(),pinned:clean};
  }
  function parse(text,catalog){
    if(typeof text!=='string'||new TextEncoder().encode(text).length>MAX_BYTES)throw Error('Shelf backup exceeds 16 KiB');
    let raw;
    try{raw=JSON.parse(text);}catch{throw Error('Invalid shelf JSON');}
    if(!raw||typeof raw!=='object'||Array.isArray(raw)||
      Object.keys(raw).sort().join(',')!==KEYS.join(',')||
      raw.format!==FORMAT||raw.version!==VERSION||
      raw.catalog_source_sha!==catalog?.provenance?.source_blob_sha||
      typeof raw.exported_at!=='string'||!/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$/.test(raw.exported_at)||
      Number.isNaN(Date.parse(raw.exported_at)))throw Error('Unsupported or stale shelf backup contract');
    return normalize(raw.pinned,catalog);
  }
  function pin(pinned,id,catalog){
    const current=normalize(pinned,catalog);
    if(current.includes(id))return current;
    if(current.length>=LIMIT)throw Error('24 public-source pins maximum');
    return normalize([...current,id],catalog);
  }
  function unpin(pinned,id,catalog){return normalize(pinned,catalog).filter(x=>x!==id);}
  function move(pinned,id,delta,catalog){
    const list=normalize(pinned,catalog),index=list.indexOf(id);
    if(index<0||!Number.isInteger(delta))return list;
    const next=Math.min(list.length-1,Math.max(0,index+delta));
    if(next!==index){list.splice(index,1);list.splice(next,0,id);}
    return list;
  }
  function badge(entry){
    if(!entry||entry.availability!=='source_only')throw Error('Invalid source record');
    return entry.declared_homepage ? 'SOURCE ONLY · SITE DECLARED (UNVERIFIED)' : 'SOURCE ONLY · NO VERIFIED LAUNCH';
  }
  root.PhiShelf=Object.freeze({FORMAT,VERSION,LIMIT,MAX_BYTES,normalize,packet,parse,pin,unpin,move,badge,catalogMap});
})(globalThis);
