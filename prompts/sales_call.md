You are given the transcript of a sales / customer call recorded on the attendee's laptop.
"Me" is the seller (laptop owner); "Them" is the customer (and others when diarized as
"Them · Speaker A/B").

# Meeting
- Title: {{TITLE}}
- Date: {{DATE}}
- Duration: {{DURATION}}

# Seller's rough notes (may be empty)
{{NOTES}}

# Transcript
{{TRANSCRIPT}}

# Task
Write sales-call notes in Markdown with exactly these sections:

## Summary
2–3 bullets: who the prospect is, what they need, and where the deal stands.

## Pain points & needs
What problems the customer is trying to solve; quote specifics where possible.

## Requirements & criteria
Must-haves, evaluation criteria, budget/timeline signals mentioned.

## Objections & concerns
Pushback raised and how it was (or wasn't) addressed. If none, write "None."

## Next steps
- [ ] action — owner — due date (follow-ups, demos, proposals, intros)
If none, write "None."

## Deal signals
Buying signals, stakeholders, and (if stated) stage/likelihood. Else "Not stated."

Rules:
- Use only facts from the transcript and rough notes; never invent commitments or numbers.
- Fix obvious transcription errors silently using context.
- Output only the Markdown note. No preamble, no top-level title heading.
