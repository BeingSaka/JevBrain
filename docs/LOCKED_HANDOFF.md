# JEV AI EVALUATION & DECISION ENGINE

## Master Handoff Specification for ChatGPT Work

**Status:** APPROVED\
**Purpose:** Authoritative project context\
**Current scope:** V1 --- Universal AI Output Evaluator\
**Priority:** Minimize manual checking, repeated prompting, and
unnecessary token/time expenditure.

------------------------------------------------------------------------

## 1. Project Goal

Build a reusable **Jev-powered AI Evaluation & Decision Engine**.

The system must automatically evaluate outputs produced by: - ChatGPT -
Codex - Gemini - Future AI agents/models

The engine answers:

> **Is this AI output ready to use? If not, what failed, and what should
> happen next?**

Target pipeline:

``` text
USER REQUEST
     ↓
AI WORKER
ChatGPT / Codex / Gemini
     ↓
CANDIDATE OUTPUT
     ↓
JEV EVALUATION ENGINE
     ↓
PASS / REVISE / HUMAN REVIEW
     ↓
If REVISE:
AI repairs failed areas only
     ↓
JEV RECHECK
     ↓
FINAL OUTPUT
```

## 2. Core Problem Being Solved

Current repetitive workflow:

``` text
Generate output
    ↓
Manually inspect
    ↓
"Find mistakes"
    ↓
"Correct mistakes"
    ↓
"Rate out of 5"
    ↓
Rewrite
    ↓
Inspect again
```

This consumes substantial human time, AI tokens, repeated prompts,
attention, and manual copy/paste.

The system should automate as much of this QA loop as practical.

## 3. Correct Mental Model of Jev

Do **NOT** treat Jev as: - Chatbot - Content generator - Research
engine - Search engine - Vision model - Generic "rate this answer"
system - Source of absolute truth

Treat Jev as:

> **A probabilistic evaluation and decision primitive.**

Conceptually:

``` text
STATE
  ↓
QUESTION + EXPLICIT CRITERIA
  ↓
JEV
  ↓
PROBABILITY / STRUCTURED JUDGMENT
  ↓
OUR POLICY ENGINE
  ↓
ACTION
```

A Jev result such as `TRUE = 0.77` does **not** mean 77% objectively
true, 77% model accuracy, or 77/100 deterministic score. It represents
the model's probabilistic judgment given the supplied state, question
and criteria.

## 4. Three Jev Primitives

Do **not** create three separate skills for these. They are evaluation
primitives used by the **same engine**.

### NOUL --- Binary Judgment

Use for: - Are all hard requirements satisfied? - Is a critical
requirement missing? - Does the output contradict supplied evidence? -
Are unsupported claims present? - Is the output ready for delivery?

Expected output: `P(TRUE)`.

### CHOICE --- Classification / Routing

Example primary failure classes: - missing_requirement - contradiction -
unsupported_claim - insufficient_evidence - generic_output -
format_violation - instruction_violation - none

This should help determine the repair strategy.

### SCORE --- Ordered Evaluation

Example: - 0 = unusable - 1 = major revision required - 2 = acceptable -
3 = strong - 4 = production ready

Do not rely on Score alone for acceptance. **Hard requirements outrank
an attractive overall score.**

## 5. V1 Evaluation State

Normalize each evaluation into a structured state resembling:

``` json
{
  "original_request": "...",
  "locked_requirements": ["...", "..."],
  "candidate_output": "...",
  "output_type": "...",
  "available_evidence": "...",
  "known_constraints": ["...", "..."]
}
```

Do not send irrelevant conversation history to Jev. State should contain
only information necessary to make the requested judgments.

## 6. V1 Evaluation Questions

### NOUL

-   requirements_met
-   critical_requirement_missing
-   instruction_violation_present
-   internal_contradiction_present
-   unsupported_claim_present
-   evidence_sufficient
-   ready_to_deliver

Each question must have explicit positive/negative decision criteria.
Avoid vague questions such as `"Is this answer good?"`

### CHOICE

Primary failure classification: - none - missing_requirement -
instruction_violation - contradiction - unsupported_claim -
insufficient_evidence - generic_output - format_violation - other

### SCORE

Production readiness: - 0 --- unusable - 1 --- major revision - 2 ---
acceptable with issues - 3 --- strong - 4 --- production ready

The exact rubric should be explicit.

## 7. Policy Engine

Jev provides probabilistic judgments. **Our application code makes the
final routing decision.**

``` text
JEV RESULTS
     ↓
POLICY ENGINE
     ↓
PASS / REVISE / HUMAN REVIEW
```

Initial thresholds may be used as configuration, but must NOT be
represented as scientifically validated.

Example starting policy:

``` text
requirements_met >= high threshold
AND
critical_requirement_missing <= low threshold
AND
unsupported_claim_present <= low threshold
AND
ready_to_deliver >= acceptance threshold
AND
production_readiness >= required level
```

Thresholds must live in configuration rather than being scattered
through code, e.g. `config/thresholds.json`.

## 8. Automatic Repair Loop

If policy returns `REVISE`, send the candidate back to the worker AI.

The repair instruction should contain only: - Original request - Locked
requirements - Previous candidate - Failed dimensions - Primary
failure - Required correction

Do **not** regenerate everything unnecessarily. Prefer: **Repair only
the identified failures while preserving correct portions.**

Then run the revised output through **JEV RECHECK**.

## 9. Retry Limit

Hard requirement:

``` text
MAX_RETRIES = 2
```

After two unsuccessful repair attempts: **HUMAN REVIEW**.

Never allow an unlimited AI → Jev → AI → Jev loop.

## 10. Logging

Every evaluation should automatically record useful metadata, e.g.:

``` json
{
  "timestamp": "...",
  "task_type": "...",
  "worker": "...",
  "evaluation_profile": "universal",
  "jev_results": {},
  "policy_decision": "PASS",
  "retry_count": 1,
  "primary_failure": "none"
}
```

Prefer JSONL or another lightweight structured format initially.

Real production usage should become the future calibration dataset.

We explicitly decided **not to delay V1 for a manual 30--50-case
benchmark**. Instead, accumulate real usage and calibrate progressively.

## 11. Cost / Efficiency Rules

Optimize for: **Human time \> unnecessary architecture**

Requirements: - Batch compatible Jev judgments where supported. - Avoid
redundant Jev calls. - Avoid sending unnecessary context. - Do not
evaluate unchanged content repeatedly. - Do not use Jev when
deterministic validation is available. - Log cost/usage information when
API data makes it available. - Prefer free/open-source dependencies. -
Use existing Jev credits before introducing additional paid
dependencies.

## 12. When Jev SHOULD Be Used

Typical target use cases: - AI-output requirement compliance - Prompt
validation - SKILL.md workflow validation - Research-output evidence
checking - USHA content constraint validation - Video-prompt requirement
validation - Agent routing - Failure classification - Revision
decision - Production-readiness evaluation

## 13. When Jev SHOULD NOT Be Used

Do not substitute Jev for: - Web research - Current-information
retrieval - Content generation - Image generation - Image/video
understanding - Audio analysis - Web scraping - Exact mathematics -
Deterministic code tests - SQL execution - Static-schema validation -
Authoritative factual databases

Core rule:

> **Use deterministic verification whenever deterministic verification
> can answer the question reliably. Use Jev for judgments containing
> genuine semantic uncertainty.**

## 14. Multimedia Rule

Jev is not the primary perception layer.

``` text
IMAGE / VIDEO / AUDIO
          ↓
Vision / multimodal model
          ↓
Structured observations
          ↓
JEV
          ↓
Evaluation / decision
```

Conceptually: - Vision model = eyes - Worker AI = creator/reasoner - Jev
= probabilistic judge - Policy code = decision authority

## 15. Modular Architecture

Target structure:

``` text
jev-ai-evaluation-engine/
│
├── README.md
├── config/
│   └── thresholds.json
│
├── evaluators/
│   └── universal.json
│
├── src/
│   ├── normalize.*
│   ├── jev_client.*
│   ├── evaluate.*
│   ├── policy.*
│   ├── repair.*
│   └── logging.*
│
├── logs/
│   └── evaluations.jsonl
│
└── tests/
```

Exact language/layout may change if implementation research identifies a
better minimal architecture. Avoid unnecessary frameworks.

## 16. Future Evaluator Profiles --- NOT V1

Architecture should permit: - Prompt Evaluator - SKILL.md Evaluator -
Research Evaluator - Code Evaluator - Video-Prompt Evaluator - USHA
Product-Fidelity Evaluator

But **do not build these during V1.** First prove the Universal
Evaluator works end-to-end.

## 17. Advanced Developer Principle

Do not merely ask `"Rate this output 0–100."`

Instead decompose quality into atomic decisions:

``` text
NOUL   → Hard requirements satisfied?
NOUL   → Critical error present?
NOUL   → Evidence sufficient?
CHOICE → What failed?
SCORE  → How production-ready is it?
              ↓
         POLICY ENGINE
              ↓
    PASS / REVISE / REVIEW
```

The value comes from engineering:

``` text
State design
+ Question decomposition
+ Explicit criteria
+ Probabilities
+ Decision policy
+ Repair routing
+ Logging
+ Progressive calibration
```

## 18. V1 Success Condition

V1 is successful when this works automatically:

``` text
INPUT
  ↓
AI generates candidate
  ↓
Candidate automatically evaluated by Jev
  ↓
Policy determines action
  ↓
PASS
   OR
REVISE → automatic targeted repair → Jev recheck
   OR
HUMAN REVIEW
  ↓
FINAL RESULT
```

There should be **no routine manual copy/paste between the worker AI and
Jev**.

## 19. Explicit Anti-Patterns

Do **NOT**: - Build three separate skills for Noul, Choice and Score. -
Treat Jev probability as ground truth. - Create arbitrary "AI quality =
97/100" vanity scores. - Hard-code thresholds throughout source files. -
Build every domain evaluator immediately. - Add a database before one is
necessary. - Add complex multi-agent infrastructure prematurely. - Allow
infinite revision loops. - Ask Jev questions that deterministic code can
answer. - Feed huge conversation histories when concise structured state
is sufficient. - Change locked project scope without explicit approval.

## 20. Execution Order for ChatGPT Work

Execute in this order:

1.  Verify current official Jev API/documentation.
2.  Determine the smallest supported integration method.
3.  Finalize Universal Evaluator schema.
4.  Finalize Noul / Choice / Score questions and criteria.
5.  Implement Jev client.
6.  Implement configurable policy engine.
7.  Implement targeted repair loop.
8.  Implement `MAX_RETRIES = 2`.
9.  Implement structured logging.
10. Add minimal tests.
11. Run an end-to-end demonstration.
12. Document setup and usage.
13. Report architecture, files created, dependencies, API configuration,
    limitations, cost implications, and next recommended version.

## 21. Constraints for Work

### Mandatory

-   Research **current** Jev documentation before implementation.
-   Prefer official Jev/TypeSafe documentation and repositories.
-   Never invent unsupported API behavior.
-   Keep architecture minimal.
-   Prefer Python unless current Jev tooling materially favors another
    implementation.
-   No unnecessary paid service.
-   Never expose API keys in source code.
-   Use environment variables for secrets.
-   Preserve modularity for future evaluator profiles.
-   Optimize primarily for **reducing repetitive human QA work**.

### Stop Condition

If current Jev capabilities fundamentally prevent the approved
architecture:

> Stop implementation, identify the exact blocker with evidence, and
> propose the smallest correction to the architecture.

Do **not** silently replace Jev or redesign the objective.

# FINAL LOCK

> **Build an AI Evaluation & Decision Engine powered by Jev---not a
> generic Jev checker.**

The first deliverable is:

> **V1 Universal AI Output Evaluator with automatic PASS / REVISE /
> HUMAN REVIEW routing and maximum two automated repair/re-evaluation
> cycles.**

Everything else is future expansion.
