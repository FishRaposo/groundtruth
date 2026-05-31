# Refusal Policy

## Overview

GroundTruth is designed to **refuse** when it cannot provide a grounded, evidence-backed answer. This is a feature, not a limitation — it builds user trust and prevents hallucination.

## When the System Refuses

The system will refuse to answer when any of the following conditions are met:

### 1. Insufficient Retrieval Results
- Zero chunks returned from both vector and keyword search
- Indicates the document corpus has no relevant content

### 2. Low Confidence Score
- Average relevance score of top chunks falls below `REFUSAL_CONFIDENCE_THRESHOLD` (default: 0.5)
- Indicates retrieved content is tangentially related but not sufficient for a reliable answer

### 3. Safety Concerns
- Query contains requests for harmful, illegal, or unethical content
- System detects prompt injection attempts

### 4. Out-of-Domain Queries
- Query is clearly unrelated to any uploaded documents
- e.g., asking about weather when the corpus contains company policies

## Confidence Thresholds

```
confidence >= 0.7  →  Proceed with answer (high confidence)
0.5 <= confidence < 0.7  →  Proceed with low-confidence warning
confidence < 0.5  →  Refuse (insufficient evidence)
```

## Refusal Message Format

When the system refuses, it returns:

```json
{
  "answer": null,
  "refused": true,
  "refusal_reason": "I couldn't find sufficient evidence in the uploaded documents to answer this question confidently.",
  "confidence": 0.32,
  "suggestion": "Try rephrasing your question or uploading additional documents related to this topic.",
  "retrieval_trace": { ... }
}
```

## Configurable Behavior

Refusal behavior can be configured via environment variables:

| Variable | Default | Description |
|---|---|---|
| `REFUSAL_CONFIDENCE_THRESHOLD` | 0.5 | Minimum confidence to proceed |
| `REFUSAL_ENABLED` | `true` | Enable/disable refusal logic |
| `REFUSAL_INCLUDE_SUGGESTION` | `true` | Include reformulation suggestions |

## Refusal Message Templates

The system uses predefined templates for different refusal scenarios:

| Scenario | Template |
|---|---|
| No results | "I couldn't find any relevant information in the uploaded documents for your question about {topic}." |
| Low confidence | "The information I found isn't detailed enough to give you a confident answer about {topic}." |
| Out of domain | "Your question appears to be outside the scope of the uploaded documents." |
| Safety concern | "I'm not able to assist with that type of request." |

## Design Philosophy

Refusal is preferable to hallucination. A system that says "I don't know" when appropriate is more trustworthy than one that always attempts an answer. The retrieval trace is always included with refusals so users can understand what the system found (or didn't find) and take corrective action.
