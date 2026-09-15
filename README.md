# Intern Selection Task: From Operation Logs to an Automation Proposal

**Duration:** 7 days
**Submission:** Full repository (including Git history) + final report

---

## Background

You have been assigned as an FDE (Forward Deployed Engineer) to a client company.

In this company's back-office departments (HR, Finance, Logistics, and others), staff
spend their days moving back and forth between internal business systems and desktop
applications such as Excel and Word, processing routine paperwork. For these employees,
this kind of work continues all day long.

The company already runs a desktop agent that collects PC operation logs from its staff.
Every keystroke, click, and application switch is recorded in chronological order.

Management has one request:

> **"Use these logs to tell us where automation would have the greatest impact on our
> operations. And show us something that actually works."**

However, what is recorded is only **operations**. Nothing in the log says
"this person is now processing an expense claim" or "this is an onboarding procedure."
The logs have been piling up untouched. Right now, nobody knows what work is being done,
by whom, or how much time it takes.

---

## Goal

**Produce a proposal that maximizes the client's ROI, and demonstrate it with something
that actually runs.**

Technical accuracy is not the objective in itself. Your judgment is what is being
assessed — including how you choose to spend your 7 days.

---

## Provided Data

See **`DATA_SCHEMA.md`** for the full data specification.

### Dataset A (with ground truth / 63 sessions / ~162,000 events)

```
dataset_a/
  ses_<date>-<time>-<machine>/
    chunk_<date>-<time>-<machine>/
      events.jsonl        <- raw operation log
      manifest.json       <- chunk metadata
      screenshots/        <- screen captures referenced by screenshot events
    gt.jsonl              <- ground truth
    gt_manifest.json      <- ground truth summary (per session)
```

`gt.jsonl` records when each business process started and ended.
Use this dataset to build and validate your approach.

Note that a single session may be split across multiple chunks. This is a property of
how the agent records data — it is not an anomaly.

### Dataset B (no ground truth / 15 sessions / ~20,000 events)

```
dataset_b/
  ses_<date>-<time>-<machine>/
    chunk_<date>-<time>-<machine>/
      events.jsonl        <- raw operation log
      manifest.json       <- chunk metadata
      screenshots/        <- screen captures referenced by screenshot events
```

**This is the production data you are asked to analyze.** There is no ground truth.
It comes from different departments performing different work than Dataset A,
and the applications in use are also different.

---

## Tasks

### Step 1 — Recover units of work from the logs

`events.jsonl` is simply a list of keystrokes, clicks, and application switches
**in the order they occurred.** There are no markers saying "an expense claim started here"
or "it ended here."

Your task is to recover "one coherent unit of work" from this stream.
In other words, **the goal of Step 1 is to segment a continuous sequence of events into
individual executions of business processes.**

#### What makes this difficult

Real office workers do not behave the way a textbook would suggest.

- **Work is not contiguous.** A person switches to a different task partway through one,
  then returns to it later
- **The same process appears many times a day.** Different cases are processed
  using the same procedure, over and over
- **The same process does not always follow the same steps.** Depending on the case
  and the conditions, the systems visited and the items checked will differ
- **Operations unrelated to any business process are mixed in**

#### How to proceed

Start with Dataset A. Because A includes ground truth (`gt.jsonl`), **you can measure
how correct your approach is.** How far you push accuracy — and what you consider
"good enough" — is left to your judgment.

For the output format, see the Deliverables section.

### Step 2 — Analyze the work and identify automation candidates

Apply your Step 1 approach to Dataset B, and analyze the operations based on its output.

- What processes are performed, how often, and how much time do they consume?
- How many people are involved?
- Are there different handling patterns within the same process?

Then, **propose which processes should be automated, in priority order.**
Explain the reasoning behind that ordering.

### Step 3 — Build an automation tool

From the candidates identified in Step 2, build the one (or ones) you judge to have
the greatest impact.

The form your "automation tool" takes is up to you. Any of the following is acceptable,
as are approaches not listed here:

- An AI agent (for example, something like Copilot given a set of procedure definitions)
- A workflow definition (n8n, Power Automate, etc.)
- A deterministic script (Python, PowerShell, etc.)
- A desktop application
- A web application

#### Consider feasibility when choosing

An idea with large potential impact is worthless if it cannot be built. Before deciding
what to target, assess the **overall development difficulty**. For example:

- How would you access the data in the target system?
- How complex is the business logic? How many decision branches are there?
- What operational and governance constraints apply?
- What risks would only surface once implementation begins?

The information you can extract from the provided logs is limited.
**We are looking at how well you can anticipate realistic risks from that limited
information.** Proposals built purely on optimistic assumptions will not score well.

#### Decide the number and scope yourself

**We do not specify how many tools to build.** Whether you build one thing specialized
for a single process, or a general mechanism that can be extended across several processes
(for example, a shared foundation with per-process definitions) — **that decision is itself
part of the ROI question.**

A broadly applicable design has a higher ceiling, but delivers zero value if you cannot
finish it. State clearly what you chose to cover, what you deferred to a later phase,
and why.

#### What your report must explain

A working prototype is sufficient. Polish itself is not evaluated; judgment is.
Your report must address the following four points:

1. **Why you chose that process, and why that scope**
2. **Why you chose that implementation form** — including why you rejected the alternatives
3. **What manual work remains after deployment**, and what impact can realistically be expected
4. **What risks you anticipate in implementation and rollout, and how you would address them**
   — including what evidence led you to anticipate each risk

---

## Deliverables

1. **Step 1 output** — the result of applying your approach to Dataset B,
   submitted as `segments.jsonl`

   One JSON object per line:

   ```json
   {"session_id": "ses_20260701-183232-LAPTOP-76QMG9DE", "start": "2026-07-01T18:32:32Z", "end": "2026-07-01T18:35:41Z", "label": "expense_processing"}
   ```

   | Field | Description |
   |---|---|
   | `session_id` | The session directory name |
   | `start` / `end` | Segment start and end time (ISO 8601, UTC) |
   | `label` | Your own name for the process. **Use the same label for the same process** |

   The label text itself is not evaluated — name them however you like.
   What is evaluated is whether the boundaries between units of work are correct,
   and whether the same process consistently receives the same label.

2. **Full repository** — include your Git history (we review how the work progressed)

3. **Final report** — must include:
   - Your Step 2 analysis, the prioritized automation candidates, and the reasoning
   - A description of what you built in Step 3, **why that process and scope**,
     and **why that implementation form**
   - **What manual work remains after deployment, and the impact you realistically expect**
   - **Anticipated implementation and rollout risks, with your mitigation approach**
   - How you allocated the 7 days, and why

4. **Work log** — what you were thinking each day, what you tried, and what did not work

---

## Notes and Constraints

- **No ground truth is provided for Dataset B.** We will score your submission
  after you submit it.
- **The logs come from a Japanese company.** Screen text, business process names, and
  application UI content are in Japanese. You are free to use translation tools or LLMs.
- These logs were recorded in a test environment, so the waiting time within each
  operation is shorter than in real production use. Judge candidates by comparing
  processes against each other rather than by absolute figures.
- Some events in `events.jsonl` (`text_input_complete`) are unreliably recorded.
  Reconstruct from other events if you need that information.
- **You are free to use generative AI.** Please record how you used it in your work log.
- Any programming language or library is acceptable.

---

## FAQ

**Q. How accurate does Step 1 need to be?**
A. We will not give you a threshold. Deciding what counts as "good enough" is part of
the task.

**Q. Does the Step 3 tool need to be production-ready?**
A. No. A working prototype is sufficient.

**Q. Will I score higher by building something technically sophisticated?**
A. No. We evaluate the client's ROI. What matters is whether your technical choices
fit the objective.

**Q. I could not complete all three steps.**
A. Record in your work log why you did not, and how you arrived at the decisions you made
along the way.
