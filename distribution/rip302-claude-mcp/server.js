#!/usr/bin/env node
import readline from "node:readline";

const DEFAULT_NODE = process.env.RUSTCHAIN_NODE_URL || "https://50.28.86.131";

export class AgentEconomyMCP {
  constructor({baseUrl=DEFAULT_NODE, wallet=process.env.RUSTCHAIN_WALLET || null, fetchImpl=globalThis.fetch}={}) {
    this.baseUrl=baseUrl.replace(/\/$/,"");
    this.wallet=wallet;
    this.fetch=fetchImpl;
  }

  async request(method,path,body,query) {
    const url=new URL(this.baseUrl+path);
    for(const [k,v] of Object.entries(query||{})) if(v!==undefined&&v!==null&&v!=="") url.searchParams.set(k,String(v));
    const init={method,headers:{accept:"application/json"}};
    if(body!==undefined){init.headers["content-type"]="application/json";init.body=JSON.stringify(body);}
    let r;
    try{r=await this.fetch(url,init);}catch(e){throw new Error(`network error: ${e.message}`);}
    const text=await r.text();
    let data={};
    if(text){try{data=JSON.parse(text);}catch{throw new Error(`non-JSON response (HTTP ${r.status})`);}}
    if(!r.ok) throw new Error(data.error||data.message||`HTTP ${r.status}`);
    return data;
  }

  toolSpecs() {
    return [
      {name:"rustchain_jobs_browse",description:"Browse RIP-302 agent jobs",inputSchema:{type:"object",properties:{status:{type:"string"},category:{type:"string"},limit:{type:"integer"}}}},
      {name:"rustchain_job_get",description:"Get one RIP-302 job",inputSchema:{type:"object",required:["job_id"],properties:{job_id:{type:"string"}}}},
      {name:"rustchain_job_post",description:"Post a RIP-302 job using the configured or supplied poster wallet",inputSchema:{type:"object",required:["title","category","reward_rtc"],properties:{title:{type:"string"},category:{type:"string"},reward_rtc:{type:"number"},description:{type:"string"},poster_wallet:{type:"string"}}}},
      {name:"rustchain_job_claim",description:"Claim an open RIP-302 job",inputSchema:{type:"object",required:["job_id"],properties:{job_id:{type:"string"},worker_wallet:{type:"string"}}}},
      {name:"rustchain_job_deliver",description:"Deliver a claimed RIP-302 job",inputSchema:{type:"object",required:["job_id","deliverable_url"],properties:{job_id:{type:"string"},deliverable_url:{type:"string"},result_summary:{type:"string"},worker_wallet:{type:"string"}}}},
      {name:"rustchain_agent_reputation",description:"Read RIP-302 agent reputation",inputSchema:{type:"object",properties:{wallet:{type:"string"}}}},
      {name:"rustchain_agent_stats",description:"Read RIP-302 marketplace stats",inputSchema:{type:"object",properties:{}}},
    ];
  }

  needWallet(value,label) {
    const wallet=value||this.wallet;
    if(!wallet) throw new Error(`${label} wallet required (argument or RUSTCHAIN_WALLET)`);
    return wallet;
  }

  async call(name,args={}) {
    switch(name) {
      case "rustchain_jobs_browse":
        return this.request("GET","/agent/jobs",undefined,{status:args.status??"open",category:args.category,limit:args.limit});
      case "rustchain_job_get":
        return this.request("GET",`/agent/jobs/${encodeURIComponent(args.job_id)}`);
      case "rustchain_job_post":
        return this.request("POST","/agent/jobs",{poster_wallet:this.needWallet(args.poster_wallet,"poster"),title:args.title,category:args.category,reward_rtc:args.reward_rtc,description:args.description??""});
      case "rustchain_job_claim":
        return this.request("POST",`/agent/jobs/${encodeURIComponent(args.job_id)}/claim`,{worker_wallet:this.needWallet(args.worker_wallet,"worker")});
      case "rustchain_job_deliver":
        return this.request("POST",`/agent/jobs/${encodeURIComponent(args.job_id)}/deliver`,{worker_wallet:this.needWallet(args.worker_wallet,"worker"),deliverable_url:args.deliverable_url,result_summary:args.result_summary??""});
      case "rustchain_agent_reputation": {
        const wallet=this.needWallet(args.wallet,"reputation");
        return this.request("GET",`/agent/reputation/${encodeURIComponent(wallet)}`);
      }
      case "rustchain_agent_stats":
        return this.request("GET","/agent/stats");
      default: throw new Error(`unknown tool: ${name}`);
    }
  }

  async handle(msg) {
    if(msg.method==="initialize") return {jsonrpc:"2.0",id:msg.id,result:{protocolVersion:"2025-06-18",capabilities:{tools:{}},serverInfo:{name:"rustchain-agent-economy",version:"0.1.0"}}};
    if(msg.method==="notifications/initialized") return null;
    if(msg.method==="tools/list") return {jsonrpc:"2.0",id:msg.id,result:{tools:this.toolSpecs()}};
    if(msg.method==="tools/call") {
      try {
        const data=await this.call(msg.params?.name,msg.params?.arguments||{});
        return {jsonrpc:"2.0",id:msg.id,result:{content:[{type:"text",text:JSON.stringify(data,null,2)}],structuredContent:data}};
      } catch(e) {
        return {jsonrpc:"2.0",id:msg.id,result:{content:[{type:"text",text:e.message}],isError:true}};
      }
    }
    return {jsonrpc:"2.0",id:msg.id,error:{code:-32601,message:"Method not found"}};
  }
}

async function run() {
  const server=new AgentEconomyMCP();
  const rl=readline.createInterface({input:process.stdin,crlfDelay:Infinity});
  for await (const line of rl) {
    if(!line.trim()) continue;
    let msg;
    try{msg=JSON.parse(line);}catch{continue;}
    const response=await server.handle(msg);
    if(response) process.stdout.write(JSON.stringify(response)+"\n");
  }
}

if(import.meta.url===new URL(`file://${process.argv[1].replace(/\\/g,"/")}`).href) run();
