# RustChain RIP-302 Go SDK

Standard-library Go client for the live RIP-302 Agent Economy API, built for the open #685 Tier-1 Go SDK bounty (50 RTC).

It covers browse/detail/post/claim/deliver/accept/dispute/cancel/reputation/stats, supports a configurable node URL/default public wallet identifier, uses context-aware HTTP calls, caps response reads, and returns explicit network/API/decode errors.

## Example

```go
client := agenteconomy.New("https://50.28.86.131", "my-wallet")
jobs, err := client.BrowseJobs(context.Background(), "open", "code", 10)
```

## Test

```bash
go test ./...
```

Tests use `httptest` only. They do not create live jobs, claim work, or move RTC.
