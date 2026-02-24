# Phase 1: Design Gap Audit

Status: COMPLETE

Reviewed every `docs/reference/` file against the question: "Could a developer implement this file correctly from what is written here?"

---

## architecture.md — Mostly Solid

**Adequate:**
- File tree (29 files, 7 dirs) is clear and complete
- Dependency graph has no circular deps
- Design philosophy is well-articulated
- Data flow direction is explicit

**Gaps:**
1. **Startup wiring not specified** — `__main__.py` described as "CLI entry: subcommands + bot runner" but no spec for: load .env → init DB → seed defaults → construct adapters → initialize adapters → check wallet → start engine → attach dashboard. Exact order matters for error handling.
2. **Graceful shutdown not specified** — signal handling (SIGINT, SIGTERM), adapter cleanup order, DB flush, asyncio task cancellation
3. **EngineListener methods are sync** — but the architecture mentions async listeners (FastAPI, Telegram). If listeners are sync-only, async use cases need clarification. (Probably fine — listeners can queue events internally — but should be explicit.)

---

## models.md — Several Type Mismatches

**Adequate:**
- Field names and types are clear for all 6 model files
- Enum definitions are explicit

**Gaps:**
4. **Signal holds full `TargetConfig` reference** — but the `signals` DB table only stores `target_address` and `target_label`. This means `Signal` is an in-memory-only model that can't be round-tripped from the DB without a target lookup. Is this intentional? If `get_recent_signals()` returns Signal objects, where does the TargetConfig come from?
5. **Market model has no asset_id mapping** — Market has `outcomes: list[str]` (e.g., ["Yes", "No"]) but no way to map outcomes to asset/token IDs. The engine needs this for redemption (knowing which asset_id corresponds to the winning outcome). Either Market needs an `outcome_asset_ids: dict[str, str]` field, or this mapping lives elsewhere.
6. **`get_price(asset_id)` return ambiguity** — the PlatformAdapter method returns a single float, but for buying you want the ask price and for selling you want the bid. The current interface doesn't distinguish. Options: (a) add a `side` parameter, (b) return a `(bid, ask)` tuple, (c) document that it always returns mid-price and slippage tolerance handles the rest.
7. **OrderResult doesn't carry `signal_id`** — but `store/trades.insert_trade(order_result, signal_id)` needs one. The signal_id must be threaded from signal insertion through sizing to execution. Where is it attached?
8. **No typed Settings model** — `get_current(conn)` returns a dict, but the engine accesses `settings.poll_interval_seconds` as a number. Where does string→number coercion happen? Need either a Settings dataclass or documented coercion in `get_current()`.
9. **TargetPosition.avg_price** — where does this come from for target wallets? Does the Gamma API provide it, or must we calculate it? If calculated, from what data?
10. **OurPosition.total_cost update logic** — how is total_cost updated on additional buys into the same position? On partial fills? This is accounting logic that needs to be specified.

---

## platform-adapters.md — Underspecified Implementation

**Adequate:**
- ABC interface is well-defined with clear method signatures
- Separation of lifecycle, read, write, and metadata is clean
- Adapter registry pattern is simple and correct

**Gaps:**
11. **No API schemas for Polymarket** — endpoint paths, query parameters, and response JSON shapes are completely absent for both Gamma API and CLOB API. Cannot implement `positions_api.py` or `orderbook.py` without these.
12. **No signing details** — EIP-712 domain separator, type definitions, and order structure for CLOB order signing not specified
13. **No contract addresses** — CTF Exchange, USDC, ConditionalTokens addresses on Polygon mainnet not listed
14. **`fetch_target_portfolio_value`** — is this total USD value of all positions? Does it include liquid balance? The strategy's buy ratio (`target_budget / target_portfolio_value`) depends on this definition.
15. **`redeem_if_needed` parameter mismatch** — takes `market_id` and `OurPosition`, but Polymarket redemption requires a `condition_id`, not `market_id`. How is market_id mapped to condition_id?
16. **No error taxonomy** — what exceptions can adapter methods throw? Network errors, auth errors, insufficient balance, invalid order? The engine needs to know which errors are retryable.
17. **`get_price` lacks side context** — see gap #6 above. Buy vs sell needs different prices.
18. **Order type not specified** — `submit_order` implies limit orders (has price + size), but is this always the case? Polymarket CLOB supports both limit and market-like orders.
19. **pmxt SDK not evaluated** — docs reference pmxt (github.com/pmxt-dev/pmxt) but no decision on whether to use it. Could replace significant portions of the adapter. (Research in progress.)

---

## engine.md — Several Algorithmic Ambiguities

**Adequate:**
- Monitor diff logic is well-specified (5 cases + dust filter)
- Strategy buy algorithm is step-by-step (12 steps)
- Strategy sell algorithm is step-by-step (9 steps) with good rationale
- Executor flow is clear at a high level
- Redeemer P&L calculation is explicit

**Gaps:**
20. **Slippage check undefined** — mentioned in both buy and sell algorithms ("return None if exceeded") but never defined. Slippage compared to what baseline? `signal.target_price` vs `get_price()`? What formula? `abs(current - target) / target > tolerance`?
21. **`aggregation_window_seconds` unexplained** — setting exists (default 0), `aggregate_signals` function exists in executor, but no description of behavior. At 0: is aggregation skipped entirely? At >0: are signals within the window batched? Deduplicated? How?
22. **Error handling in loops** — what happens when `poll_target` throws? (API down, timeout, malformed response.) Does the monitor loop crash? Skip that target and continue? Log + continue to next target? Same question for executor errors.
23. **Engine `store` parameter type** — `Engine.__init__(store, adapters)` — what type is `store`? A bare sqlite3.Connection? A namespace/module with `.settings`, `.targets`, `.portfolio` sub-modules? A wrapper class?
24. **Portfolio value includes dry-run?** — "liquid_balance + sum(all deployed positions at current market value)" — dry-run positions don't have real money. If portfolio_value includes them, the budget is fictional. If not, budget tracks real capital only. Needs a decision.
25. **Sequential target polling** — the monitor loop iterates targets sequentially. 10 targets at 2s per API call = 20s per tick with a 2s poll interval. Should targets be polled concurrently with `asyncio.gather`? Or is sequential acceptable for MVP?
26. **Signal deduplication across polls** — if the target makes two rapid changes within one poll interval, we see only the net change. This is probably fine (and unavoidable), but worth documenting as a known limitation.
27. **Retry policy details** — "retry on transient failure" with no definition of: max attempts, backoff strategy (linear? exponential?), which errors are transient vs fatal, timeout per attempt.

---

## store.md — Connection and Type Gaps

**Adequate:**
- SQL schema is complete and well-indexed
- Function signatures for all 7 store modules are listed
- DEFAULTS dict with all 10 settings is explicit
- Target validation rules (allocation sum, unique label/address) are clear

**Gaps:**
28. **Connection management pattern** — `init_db(path) → connection` and `get_connection() → connection` — is this a module-level singleton? How does the CLI (which may run while the bot is running) get a separate connection? Thread-safety?
29. **WAL mode not specified** — without WAL, concurrent reads (CLI) while the engine writes will block. With WAL, they're concurrent. Needs an explicit decision.
30. **`get_current()` return type** — returns a dict, but callers need typed numeric values. Either this returns a typed dataclass/TypedDict, or it returns `dict[str, str]` and callers cast. The coercion location must be specified.
31. **Transaction boundaries** — when the executor persists a trade + updates a position, is that atomic? If the process crashes between `insert_trade` and `upsert_position`, state is inconsistent. Need explicit transaction wrapping.
32. **`delete_stale_snapshots(older_than)`** — parameter type not specified (datetime? timedelta? seconds?). What defines "stale"? Who calls this and how often?
33. **`get_trade_summary` return shape** — "→ dict" with no key/value specification.
34. **`get_allocation_summary` inner dict** — "→ dict[str, dict]" but inner dict structure undefined. From dashboard.md we know it includes "label | allocation % | budget $ | deployed $ | available $" but that's in the view, not the store spec.
35. **Schema has no `pnl` tracking table** — the redeemer calculates P&L on resolved positions, but where is realized P&L persisted? `zero_out_position` removes the position, and there's no P&L column in executed_trades. Need either a P&L column on our_positions, a separate pnl_events table, or P&L in the trade record.
36. **`store/__init__.py` role** — other docs reference `store.settings`, `store.targets`. Is `store/__init__.py` a facade that re-exports all modules? Or does each caller import `from prediction_mirror.store import settings` directly?

---

## dashboard.md — Heavily Underspecified

**Adequate:**
- Module responsibilities are clear (listener receives events, renderer formats, views are pure)
- Allocation breakdown columns are listed

**Gaps:**
37. **No visual layout / mockup** — no description of what the dashboard actually looks like. How are sections arranged? What's the header? What's the order of sections?
38. **No column specifications** — `render_positions_table`, `render_recent_signals`, `render_recent_trades` have no column names, widths, or truncation rules.
39. **Dashboard rendering mechanism** — "clear_and_print" suggests ANSI escape codes, but no library chosen. Is this `\033[2J\033[H` + print? A library like `rich`? Plain text to stdout?
40. **Async interaction model** — `DashboardListener` queues updates and renders on interval. What queue type? How does the sync `on_signal()` callback (called from engine's event loop) interact with the async render loop? Is the render loop a separate asyncio task?
41. **Dry-run mode indicator** — where and how is dry-run status shown? In the header? Colored banner?
42. **Empty state** — what shows when there are no targets, no positions, or no recent activity?
43. **Terminal compatibility** — minimum terminal width? What if the terminal is too narrow for tables?

---

## Cross-Cutting Gaps

44. **Logging spec** — `utils/log.py` is in the file tree but has no spec. Log format? File path? Rotation size? Console vs file behavior? Which log levels for which events?
45. **CLI output format** — `docs/cli.md` says "Display all settings" and "Display all targets" but doesn't specify the format (table? key-value list? JSON?). No error message format specified.
46. **CLI graceful shutdown** — how does `python -m prediction_mirror run` handle Ctrl+C? SIGINT → engine.shutdown() → adapter cleanup → exit? What's the timeout before force-kill?
47. **Configuration validation on startup** — what if allocation sum > 100%? No targets configured? Invalid env vars (bad private key format)? Does the bot refuse to start or start with warnings?
48. **`pyproject.toml` has no runtime dependencies** — `dependencies = []`. The entire dependency list needs to be defined based on stack decisions.
49. **No `.env` validation** — what happens if `POLYMARKET_PRIVATE_KEY` is missing or malformed? Where and how is this validated? Before or after DB init?

---

## Summary: Blocking Gaps by Priority

### Must resolve before implementation (blocks code)
- **#11-13**: Polymarket API schemas, signing, contract addresses (blocks platform adapter)
- **#19**: pmxt SDK evaluation (may change adapter architecture entirely)
- **#6/17**: get_price side ambiguity (blocks strategy + executor)
- **#20**: Slippage check definition (blocks strategy)
- **#23**: Store param type for Engine (blocks engine/core)
- **#30**: Settings return type (blocks every module that reads settings)
- **#48**: Runtime dependencies (blocks any code that imports third-party libs)

### Should resolve before implementation (prevents rework)
- **#5**: Market-to-asset mapping (blocks redeemer)
- **#8**: Settings typed model (quality-of-life, affects many callers)
- **#21**: Aggregation window behavior (affects executor design)
- **#22/27**: Error handling + retry policy (affects engine resilience)
- **#24**: Portfolio value dry-run inclusion (affects strategy calculations)
- **#28-29**: Connection management + WAL (affects all store callers)
- **#31**: Transaction boundaries (affects data consistency)
- **#35**: P&L persistence (blocks redeemer persistence)
- **#36**: store/__init__.py facade pattern (affects all import paths)

### Can defer to implementation (nice-to-have specs)
- **#4**: Signal TargetConfig round-tripping (design choice, document it)
- **#25**: Sequential vs concurrent polling (MVP can be sequential)
- **#26**: Signal dedup limitation (document as known limitation)
- **#37-43**: Dashboard visual details (can iterate during implementation)
- **#44**: Logging spec details (sensible defaults, refine later)
