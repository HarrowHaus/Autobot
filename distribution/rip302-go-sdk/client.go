package agenteconomy

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

type Client struct {
	BaseURL string
	Wallet  string
	HTTP    *http.Client
}

type APIError struct {
	Status int
	Body   string
}

func (e *APIError) Error() string {
	return fmt.Sprintf("RustChain API error HTTP %d: %s", e.Status, e.Body)
}

func New(baseURL, wallet string) *Client {
	if strings.TrimSpace(baseURL) == "" {
		baseURL = "https://50.28.86.131"
	}
	return &Client{BaseURL: strings.TrimRight(baseURL, "/"), Wallet: wallet, HTTP: &http.Client{Timeout: 15 * time.Second}}
}

func (c *Client) do(ctx context.Context, method, path string, query url.Values, body any, out any) error {
	u := c.BaseURL + path
	if len(query) > 0 {
		u += "?" + query.Encode()
	}
	var r io.Reader
	if body != nil {
		b, err := json.Marshal(body)
		if err != nil {
			return err
		}
		r = bytes.NewReader(b)
	}
	req, err := http.NewRequestWithContext(ctx, method, u, r)
	if err != nil {
		return err
	}
	req.Header.Set("Accept", "application/json")
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	resp, err := c.HTTP.Do(req)
	if err != nil {
		return fmt.Errorf("network error: %w", err)
	}
	defer resp.Body.Close()
	raw, err := io.ReadAll(io.LimitReader(resp.Body, 4<<20))
	if err != nil {
		return err
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return &APIError{Status: resp.StatusCode, Body: string(raw)}
	}
	if out != nil && len(raw) > 0 {
		if err := json.Unmarshal(raw, out); err != nil {
			return fmt.Errorf("decode response: %w", err)
		}
	}
	return nil
}

func (c *Client) wallet(value, label string) (string, error) {
	if strings.TrimSpace(value) != "" {
		return value, nil
	}
	if strings.TrimSpace(c.Wallet) != "" {
		return c.Wallet, nil
	}
	return "", fmt.Errorf("%s wallet required", label)
}

func (c *Client) BrowseJobs(ctx context.Context, status, category string, limit int) (map[string]any, error) {
	q := url.Values{}
	if status == "" {
		status = "open"
	}
	q.Set("status", status)
	if category != "" {
		q.Set("category", category)
	}
	if limit > 0 {
		q.Set("limit", fmt.Sprint(limit))
	}
	out := map[string]any{}
	return out, c.do(ctx, http.MethodGet, "/agent/jobs", q, nil, &out)
}

func (c *Client) GetJob(ctx context.Context, id string) (map[string]any, error) {
	out := map[string]any{}
	return out, c.do(ctx, http.MethodGet, "/agent/jobs/"+url.PathEscape(id), nil, nil, &out)
}

func (c *Client) PostJob(ctx context.Context, title, category string, reward float64, description, poster string) (map[string]any, error) {
	w, err := c.wallet(poster, "poster")
	if err != nil {
		return nil, err
	}
	out := map[string]any{}
	body := map[string]any{"poster_wallet": w, "title": title, "category": category, "reward_rtc": reward, "description": description}
	return out, c.do(ctx, http.MethodPost, "/agent/jobs", nil, body, &out)
}

func (c *Client) ClaimJob(ctx context.Context, id, worker string) (map[string]any, error) {
	w, err := c.wallet(worker, "worker")
	if err != nil {
		return nil, err
	}
	out := map[string]any{}
	return out, c.do(ctx, http.MethodPost, "/agent/jobs/"+url.PathEscape(id)+"/claim", nil, map[string]any{"worker_wallet": w}, &out)
}

func (c *Client) DeliverJob(ctx context.Context, id, worker, deliverable, summary string) (map[string]any, error) {
	w, err := c.wallet(worker, "worker")
	if err != nil {
		return nil, err
	}
	out := map[string]any{}
	body := map[string]any{"worker_wallet": w, "deliverable_url": deliverable, "result_summary": summary}
	return out, c.do(ctx, http.MethodPost, "/agent/jobs/"+url.PathEscape(id)+"/deliver", nil, body, &out)
}

func (c *Client) AcceptJob(ctx context.Context, id, poster string, rating int, feedback string) (map[string]any, error) {
	w, err := c.wallet(poster, "poster")
	if err != nil {
		return nil, err
	}
	out := map[string]any{}
	body := map[string]any{"poster_wallet": w}
	if rating != 0 {
		body["rating"] = rating
	}
	if feedback != "" {
		body["feedback"] = feedback
	}
	return out, c.do(ctx, http.MethodPost, "/agent/jobs/"+url.PathEscape(id)+"/accept", nil, body, &out)
}

func (c *Client) DisputeJob(ctx context.Context, id, poster, reason string) (map[string]any, error) {
	w, err := c.wallet(poster, "poster")
	if err != nil {
		return nil, err
	}
	out := map[string]any{}
	return out, c.do(ctx, http.MethodPost, "/agent/jobs/"+url.PathEscape(id)+"/dispute", nil, map[string]any{"poster_wallet": w, "reason": reason}, &out)
}

func (c *Client) CancelJob(ctx context.Context, id, poster string) (map[string]any, error) {
	w, err := c.wallet(poster, "poster")
	if err != nil {
		return nil, err
	}
	out := map[string]any{}
	return out, c.do(ctx, http.MethodPost, "/agent/jobs/"+url.PathEscape(id)+"/cancel", nil, map[string]any{"poster_wallet": w}, &out)
}

func (c *Client) Reputation(ctx context.Context, wallet string) (map[string]any, error) {
	w, err := c.wallet(wallet, "reputation")
	if err != nil {
		return nil, err
	}
	out := map[string]any{}
	return out, c.do(ctx, http.MethodGet, "/agent/reputation/"+url.PathEscape(w), nil, nil, &out)
}

func (c *Client) Stats(ctx context.Context) (map[string]any, error) {
	out := map[string]any{}
	return out, c.do(ctx, http.MethodGet, "/agent/stats", nil, nil, &out)
}
