# DroneV1 Technical Report (Concise)

## Service Definition
- Domain: Transportation / drone logistics.
- Service: dispatch and delivery prioritization with safety-aware autonomous operations.
- Stakeholders: logistics operators, dispatch managers, operations on-call.

## Architecture
- Telemetry producer: `drone_streamer.py`
- Order producer: `order_streamer.py`
- MCP Observability server: `mcp_observability_server.py`
- MCP Operations server: `mcp_operations_server.py`
- Agent roles:
  - `observer_agent.py`
  - `remediation_agent.py`
- Coordinator: `agent_demo.py`
- Dashboard + human approvals: `dashboard.py`

## Reliability and Scalability Mechanisms
- Bounded loops with max-step for both agents.
- Policy validation before operational actions.
- Idempotent assignment behavior.
- Graceful degradation path when operations MCP is unavailable.
- Full action audit in JSONL.

## Agent Roles and MCP Design
- Capability Group A (read-only): telemetry/observability.
- Capability Group B (write/controlled): remediation/approvals.
- Separation prevents unrestricted writes from observer role.

## Safety Policy
See `SAFETY_POLICY.md`.

## Failure Experiments
Use `failure_scenarios.sh` for:
- operations dependency outage
- malformed order input
- queue congestion
- LLM endpoint unavailability
- recovery check

## SLO Proposal
- Dispatch decision latency p95: <= 5s
- Approval queue visibility latency: <= 2s
- Data freshness in dashboard: <= 5s

## Cost and ROI (Estimate)
- Agent cost ceiling per run: 0.05 EUR (enforced in guardrail)
- Monthly ops estimate (local lab setup): 40-120 EUR equivalent infra/electricity/opportunity cost
- Downtime cost estimate (1h): 300 EUR equivalent (delayed urgent deliveries + manual triage)

## Trade-offs
- Cost vs reliability: limit agent steps/cost ceiling reduces exploration depth but protects budget.
- Automation vs safety: high-impact actions require approval, reducing speed but increasing safety.

## ROA (Return on Agent)
- Benefit: faster triage, fewer unsafe assignments, explicit approval workflow.
- Value source: reduced manual dispatch load and lower incident handling time.
- CAPEX/OPEX factors: model runtime resources, operator time, maintenance of policy and dashboards.
