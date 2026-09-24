const DEFAULTS = {
  network: "eip155:8453",
  asset: "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
  payTo: "0xa47930496923574a33325b9be28fe84fa8d2b1c6",
  amount: "10000",
  facilitator: "https://facilitator.x402endpoints.online",
  stateUrl: "https://raw.githubusercontent.com/HarrowHaus/Autobot/refs/heads/claude/monetizable-project-concepts-b97bv2/data/mesh-state.json",
};

const jsonHeaders = {"content-type":"application/json; charset=utf-8","cache-control":"no-store"};

function cfg(env={}) {
  return {
    network: env.A0_PAYMENT_NETWORK || DEFAULTS.network,
    asset: env.A0_USDC_ASSET || DEFAULTS.asset,
    payTo: env.A0_PAY_TO || DEFAULTS.payTo,
    amount: env.A0_ROUTE_PRICE_ATOMIC || DEFAULTS.amount,
    facilitator: (env.A0_FACILITATOR_URL || DEFAULTS.facilitator).replace(/\/$/,""),
    stateUrl: env.A0_SWARMBRAIN_STATE_URL || DEFAULTS.stateUrl,
  };
}

function encodeJson(value) {
  const bytes=new TextEncoder().encode(JSON.stringify(value));
  let s=""; for (const b of bytes) s+=String.fromCharCode(b);
  return btoa(s);
}
function decodeJson(value) {
  const s=atob(value);
  const bytes=Uint8Array.from(s,c=>c.charCodeAt(0));
  return JSON.parse(new TextDecoder().decode(bytes));
}
export function tokenize(value) {
  return [...new Set(String(value||"").toLowerCase().match(/[a-z0-9]+/g)||[])];
}
export function rankPeers(state, query, limit=3) {
  const terms=tokenize(query);
  const peers=Object.values(state?.peers||{});
  const rows=[];
  for (const p of peers) {
    if (!["connected","card_verified"].includes(p.status)) continue;
    const caps=(p.capabilities||[]).flatMap(c=>[c.id,c.name,...(c.tags||[])]);
    const hay=tokenize([p.id,p.name,p.kind,p.region,...caps].join(" "));
    const h=new Set(hay);
    const matched=terms.filter(t=>h.has(t));
    if (matched.length===0) continue;
    const overlap=matched.length/Math.max(1,terms.length);
    const calls=Number(p.calls||0), accepted=Number(p.verified_results||0);
    const outcome=(accepted+1)/(calls+2);
    const activation=overlap*(0.5+outcome);
    rows.push({
      peer:p.id,
      name:p.name||p.id,
      activation:Number(activation.toFixed(6)),
      matched_terms:matched,
      capabilities:(p.capabilities||[]).map(c=>c.id||c.name).filter(Boolean).slice(0,12),
      protocol_version:p.protocol_version||null,
      endpoint:p.endpoint||null,
      observed_reliability:p.response_reliability??null
    });
  }
  return rows.sort((a,b)=>b.activation-a.activation||a.peer.localeCompare(b.peer))
    .slice(0,Math.max(1,Math.min(10,Number(limit)||3)));
}
export function buildPaymentRequired(requestUrl, env={}) {
  const c=cfg(env); const u=new URL(requestUrl); u.pathname="/v1/route"; u.search="";
  return {
    x402Version:2,
    resource:{
      url:u.toString(),
      description:"Read-only ranked routing over the SwarmBrain peer graph",
      mimeType:"application/json",
      serviceName:"A0 Route Intelligence",
      tags:["agents","routing","swarm","x402","discovery"]
    },
    accepts:[{
      scheme:"exact",network:c.network,amount:String(c.amount),asset:c.asset,payTo:c.payTo,
      maxTimeoutSeconds:60,extra:{name:"USD Coin",version:"2"}
    }],
    extensions:{
      bazaar:{
        info:{
          input:{type:"http",method:"POST",bodyType:"json",body:{query:"verification",limit:3}},
          output:{type:"json",example:{task_id:"sale-example",query:"verification",routes:[{peer:"attractor",activation:0.75}],scope:"read_only_route_selection"}}
        },
        schema:{
          type:"object",
          properties:{query:{type:"string",description:"Capability or task terms to route"},limit:{type:"integer",minimum:1,maximum:10}},
          required:["query"]
        }
      }
    }
  };
}
function challenge(request, env, reason="payment_required") {
  const requirement=buildPaymentRequired(request.url,env);
  return new Response(JSON.stringify({error:reason,x402Version:2,paymentRequired:requirement}),{
    status:402,headers:{...jsonHeaders,"PAYMENT-REQUIRED":encodeJson(requirement)}
  });
}
async function facilitatorPost(base,path,payload) {
  const r=await fetch(base+path,{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify(payload)});
  let body={}; try{body=await r.json()}catch{body={error:"invalid_facilitator_response"}}
  return {status:r.status,body,headers:r.headers};
}
async function routeWork(c,query,limit) {
  const r=await fetch(c.stateUrl,{headers:{"user-agent":"A0-merchant-worker/0.28"}});
  if(!r.ok) throw new Error("peer_state_unavailable:"+r.status);
  const state=await r.json();
  return {query,routes:rankPeers(state,query,limit),scope:"read_only_route_selection",state_coordinator:state.coordinator||null};
}
async function paidRoute(request,env) {
  const c=cfg(env);
  let body; try{body=await request.json()}catch{return new Response(JSON.stringify({error:"invalid_json"}),{status:400,headers:jsonHeaders})}
  const query=String(body?.query||"").trim();
  if(!query||query.length>1000)return new Response(JSON.stringify({error:"query_required"}),{status:400,headers:jsonHeaders});
  const limit=Math.max(1,Math.min(10,Number(body?.limit)||3));
  const signature=request.headers.get("PAYMENT-SIGNATURE");
  if(!signature)return challenge(request,env);
  let paymentPayload; try{paymentPayload=decodeJson(signature)}catch{return challenge(request,env,"invalid_payment_signature_header")}
  const requirement=buildPaymentRequired(request.url,env);
  const accepted=requirement.accepts[0];
  const verification=await facilitatorPost(c.facilitator,"/verify",{x402Version:2,paymentPayload,paymentRequirements:accepted});
  if(verification.status===401||verification.status===403)return new Response(JSON.stringify({error:"facilitator_auth_rejected"}),{status:502,headers:jsonHeaders});
  if(verification.body?.isValid!==true)return challenge(request,env,verification.body?.invalidReason||"payment_invalid");
  let result; try{result=await routeWork(c,query,limit)}catch(e){return new Response(JSON.stringify({error:"resource_execution_failed",detail:String(e.message||e).slice(0,200)}),{status:502,headers:jsonHeaders})}
  const settlement=await facilitatorPost(c.facilitator,"/settle",{x402Version:2,paymentPayload,paymentRequirements:accepted});
  if(settlement.body?.success!==true)return new Response(JSON.stringify({error:"payment_settlement_failed",settlement:settlement.body}),{status:502,headers:jsonHeaders});
  const headers={...jsonHeaders,"PAYMENT-RESPONSE":encodeJson(settlement.body)};
  const ext=settlement.headers.get("EXTENSION-RESPONSES"); if(ext) headers["EXTENSION-RESPONSES"]=ext;
  return new Response(JSON.stringify({result,payment:{network:settlement.body.network||c.network,transaction:settlement.body.transaction||null,payer:settlement.body.payer||null,amount_atomic:c.amount,asset:c.asset,pay_to:c.payTo}}),{status:200,headers});
}

export default {
  async fetch(request,env) {
    const u=new URL(request.url);
    if(request.method==="GET"&&u.pathname==="/health") return new Response(JSON.stringify({ok:true,service:"a0-route-intelligence",payments:"x402-v2",network:cfg(env).network}),{status:200,headers:jsonHeaders});
    if(request.method==="GET"&&u.pathname==="/catalog") {
      const c=cfg(env); return new Response(JSON.stringify({service:"A0 Route Intelligence",endpoint:new URL("/v1/route",u.origin).toString(),method:"POST",price_atomic:c.amount,asset:c.asset,network:c.network,pay_to:c.payTo,facilitator:c.facilitator}),{status:200,headers:jsonHeaders});
    }
    if(request.method==="GET"&&u.pathname==="/.well-known/x402") {
      return new Response(JSON.stringify({version:1,resources:[new URL("/v1/route",u.origin).toString()]}),{status:200,headers:jsonHeaders});
    }
    if(request.method==="GET"&&(u.pathname==="/.well-known/agent-card.json"||u.pathname==="/.well-known/agent.json")) {
      const endpoint=new URL("/v1/route",u.origin).toString();
      const card={
        name:"A0 Route Intelligence",
        description:"Paid read-only routing across the SwarmBrain public peer graph. Returns ranked agent routes for capability/task terms.",
        url:u.origin,
        protocolVersion:"0.3",
        version:"0.28.0",
        provider:{organization:"A0 / SwarmBrain",url:"https://github.com/HarrowHaus/Autobot/issues/33"},
        capabilities:{streaming:false,pushNotifications:false,stateTransitionHistory:false},
        defaultInputModes:["application/json","text/plain"],
        defaultOutputModes:["application/json"],
        skills:[{
          id:"paid-route-intelligence",
          name:"Paid Agent Route Intelligence",
          description:"Rank known agent peers for requested capabilities. Read-only; does not dispatch work.",
          tags:["routing","agents","discovery","verification","research","x402","USDC","Base"],
          examples:["verification research routing","x402 payment verification routing"]
        }],
        metadata:{
          payment_protocol:"x402-v2",
          network:cfg(env).network,
          asset:"USDC",
          price_atomic:String(cfg(env).amount),
          payment_discovery:new URL("/.well-known/x402",u.origin).toString(),
          openapi:new URL("/openapi.json",u.origin).toString(),
          skill_document:new URL("/skill.md",u.origin).toString(),
          storefront:"https://github.com/HarrowHaus/Autobot/issues/33",
          paid_endpoint:endpoint
        }
      };
      return new Response(JSON.stringify(card),{status:200,headers:jsonHeaders});
    }
    if(request.method==="GET"&&u.pathname==="/openapi.json") {
      const c=cfg(env);
      return new Response(JSON.stringify({
        openapi:"3.1.0",
        info:{title:"A0 Route Intelligence",version:"0.28.0",description:"Paid read-only routing over the SwarmBrain public peer graph."},
        servers:[{url:u.origin}],
        paths:{"/v1/route":{post:{
          summary:"Rank useful agent routes",
          operationId:"routeAgents",
          requestBody:{required:true,content:{"application/json":{schema:{type:"object",properties:{query:{type:"string"},limit:{type:"integer",minimum:1,maximum:10}},required:["query"]}}}},
          responses:{"200":{description:"Paid routing result"},"402":{description:"x402 payment required"}},
          "x-payment-info":{protocols:["x402"],amount:"0.01",currency:"USDC",network:c.network}
        }}}
      }),{status:200,headers:jsonHeaders});
    }
    if(request.method==="GET"&&u.pathname==="/skill.md") {
      const text=[
        "# A0 Route Intelligence",
        "",
        "Use POST /v1/route with JSON {\"query\":\"capability terms\",\"limit\":3}.",
        "The endpoint uses x402 v2 exact payments on Base in USDC.",
        "An unpaid request returns HTTP 402 with PAYMENT-REQUIRED.",
        "The service is read-only: it ranks known SwarmBrain peers and does not dispatch work.",
        "Discovery: /.well-known/x402 and /openapi.json."
      ].join("\n");
      return new Response(text,{status:200,headers:{"content-type":"text/markdown; charset=utf-8","cache-control":"no-store"}});
    }
    if(request.method==="POST"&&u.pathname==="/v1/route") return paidRoute(request,env);
    return new Response(JSON.stringify({error:"not_found"}),{status:404,headers:jsonHeaders});
  }
};
