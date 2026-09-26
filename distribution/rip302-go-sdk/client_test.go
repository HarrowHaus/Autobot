package agenteconomy

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestBrowseFilters(t *testing.T) {
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/agent/jobs" || r.URL.Query().Get("status") != "open" || r.URL.Query().Get("category") != "code" || r.URL.Query().Get("limit") != "5" {
			t.Fatalf("bad request: %s", r.URL.String())
		}
		json.NewEncoder(w).Encode(map[string]any{"jobs": []any{map[string]any{"job_id": "j1"}}})
	}))
	defer s.Close()
	c := New(s.URL, "")
	out, err := c.BrowseJobs(context.Background(), "", "code", 5)
	if err != nil {
		t.Fatal(err)
	}
	if out["jobs"] == nil {
		t.Fatal("jobs missing")
	}
}

func TestWriteWalletBinding(t *testing.T) {
	seen := []map[string]any{}
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var body map[string]any
		json.NewDecoder(r.Body).Decode(&body)
		seen = append(seen, body)
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"ok":true,"job_id":"j"}`))
	}))
	defer s.Close()
	c := New(s.URL, "wallet-a")
	if _, err := c.PostJob(context.Background(), "x", "code", 5, "", ""); err != nil {
		t.Fatal(err)
	}
	if _, err := c.ClaimJob(context.Background(), "j", ""); err != nil {
		t.Fatal(err)
	}
	if _, err := c.DeliverJob(context.Background(), "j", "", "https://example.invalid", "done"); err != nil {
		t.Fatal(err)
	}
	if seen[0]["poster_wallet"] != "wallet-a" || seen[1]["worker_wallet"] != "wallet-a" || seen[2]["worker_wallet"] != "wallet-a" {
		t.Fatal(seen)
	}
}

func TestAllLifecycleMethods(t *testing.T) {
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"ok":true}`))
	}))
	defer s.Close()
	c := New(s.URL, "w")
	ctx := context.Background()
	calls := []func() (map[string]any, error){
		func() (map[string]any, error) { return c.GetJob(ctx, "j") },
		func() (map[string]any, error) { return c.AcceptJob(ctx, "j", "", 5, "ok") },
		func() (map[string]any, error) { return c.DisputeJob(ctx, "j", "", "why") },
		func() (map[string]any, error) { return c.CancelJob(ctx, "j", "") },
		func() (map[string]any, error) { return c.Reputation(ctx, "") },
		func() (map[string]any, error) { return c.Stats(ctx) },
	}
	for _, fn := range calls {
		out, err := fn()
		if err != nil || out["ok"] != true {
			t.Fatalf("out=%v err=%v", out, err)
		}
	}
}

func TestHTTPError(t *testing.T) {
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(503)
		w.Write([]byte(`{"error":"offline"}`))
	}))
	defer s.Close()
	c := New(s.URL, "")
	_, err := c.Stats(context.Background())
	if err == nil {
		t.Fatal("expected error")
	}
	if _, ok := err.(*APIError); !ok {
		t.Fatalf("wrong error %T", err)
	}
}

func TestMissingWalletFailsBeforeNetwork(t *testing.T) {
	c := New("http://127.0.0.1:1", "")
	if _, err := c.ClaimJob(context.Background(), "j", ""); err == nil {
		t.Fatal("expected wallet error")
	}
}
