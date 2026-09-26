use rustchain_agent_economy::{AgentEconomyClient, AgentEconomyError, PostJob};
use serde_json::Value;
use std::thread;
use tiny_http::{Response, Server};

fn one_response(body: &'static str) -> String {
    let server = Server::http("127.0.0.1:0").unwrap();
    let addr = format!("http://{}", server.server_addr());
    thread::spawn(move || {
        let req = server.recv().unwrap();
        req.respond(Response::from_string(body).with_status_code(200)).unwrap();
    });
    addr
}

#[test]
fn browse_jobs_decodes_json() {
    let base = one_response(r#"{"jobs":[{"job_id":"j1"}]}"#);
    let c = AgentEconomyClient::new(base, None);
    let v = c.browse_jobs(Some("open"), None).unwrap();
    assert_eq!(v["jobs"][0]["job_id"], Value::String("j1".into()));
}

#[test]
fn write_method_requires_wallet_before_request() {
    let c = AgentEconomyClient::new("http://127.0.0.1:9", None);
    let err = c.claim_job("j1", None).unwrap_err();
    assert!(matches!(err, AgentEconomyError::WalletRequired));
}

#[test]
fn post_job_serializes_expected_shape() {
    let server = Server::http("127.0.0.1:0").unwrap();
    let addr = format!("http://{}", server.server_addr());
    thread::spawn(move || {
        let mut req = server.recv().unwrap();
        let mut body = String::new();
        req.as_reader().read_to_string(&mut body).unwrap();
        let v: Value = serde_json::from_str(&body).unwrap();
        assert_eq!(v["poster_wallet"], "poster");
        assert_eq!(v["reward_rtc"], 5.0);
        req.respond(Response::from_string(r#"{"ok":true}"#).with_status_code(200)).unwrap();
    });
    let c = AgentEconomyClient::new(addr, Some("poster".into()));
    let job = PostJob { title:"Research".into(), category:"research".into(), reward_rtc:5.0, description:None };
    assert_eq!(c.post_job(&job, None).unwrap()["ok"], true);
}
