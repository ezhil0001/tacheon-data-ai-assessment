# System Overview

These diagrams show the operational flow and failure handling behaviour for the
marketing intelligence digest workflow.

The diagrams were drafted using Excalidraw for quick system visualisation.

---

## Scheduled system flow

![Scheduled System Flow](./images/system-flow.png)

The scheduled workflow starts with the scheduler triggering parallel API fetches
across marketing channels. The processing layer normalises the responses, calculates
week-over-week deltas, checks for anomalies, and stores the final snapshots before
delivery surfaces are refreshed.

---

## Failure handling flow

![Failure Handling Flow](./images/failure-flow.png)

If a channel fetch fails, the system retries automatically before marking the
channel as stale for that run. Rather than failing the entire workflow silently,
the digest still gets delivered with a visible warning so analysts know the data
is partial.