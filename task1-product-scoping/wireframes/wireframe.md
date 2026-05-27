# V1 Wireframe — Marketing Intelligence Digest

The wireframes below show different operational states of the dashboard.
The goal of the UI is operational visibility, not deep analytics exploration.

The dashboard screens were explored iteratively using Claude-assisted prompt
drafting before being refined into the final operational layouts shown below.

---

## State 1 — Normal run, no anomalies

Everything ran cleanly. All channels fresh. No flags. The analyst reads the
summary bar and moves on. This is the expected daily experience.

![State 1 - Normal run, no anomalies](./state-1-normal.png)

---

## State 2 — Anomaly detected

Something moved significantly. The anomaly strip surfaces above the channel
breakdown so the analyst sees the signal before reading individual numbers.
The flag states what moved and by how much — not what to do about it.

![State 2 - Anomaly detected on Meta Ads](./state-2-anomaly.png)

---

## State 3 — Partial data, channel stale

One channel failed to fetch. The digest delivers what it has. The failed
channel is marked explicitly — cross-channel totals show as incomplete rather
than silently wrong. Retry time is visible inline.

![State 3 - Partial data, HubSpot stale](./state-3-partial.png)

---

## UX decisions — documented

**Summary bar comes first**
The standing question is cross-channel. Three numbers answer it. Everything
below supports those three numbers. The layout reflects the question, not the
data structure.

**Anomaly strip appears above channel cards**
If something needs attention, the analyst should see it before reading channel
detail. The strip surfaces the signal before the noise.

**Freshness indicators are inline, not in a footer**
A footer timestamp is easy to ignore. Freshness sitting next to the channel
name means the analyst sees data age at the same moment they read the number.
They never mistake a stale number for a current one.

**Run log is visible in the main view**
Making it visible at the bottom means any team member can answer "did the
system run correctly today?" without needing a developer or an admin panel.

**Observations panel labelled "Rule-based · V1"**
Sets accurate expectations. The analyst knows this is threshold logic, not AI
interpretation. When V2 adds LLM narrative, the label changes. No confusion
about what the system is doing or how much confidence to place in its output.

**Three states, not one**
Most wireframes show the happy path. These three states cover normal operation,
anomaly detection, and partial failure — because the tool needs to be trusted
in all three situations, not just when everything works.