You are given the transcript of a meeting recorded on the attendee's laptop.
"Me" is the laptop owner; "Them" is everyone else on the call.

# Meeting
- Title: {{TITLE}}
- Date: {{DATE}}
- Duration: {{DURATION}}

# Attendee's rough notes (may be empty)
{{NOTES}}

# Transcript
{{TRANSCRIPT}}

# Task
Write polished meeting notes in Markdown with exactly these sections:

## Summary
2–4 bullets capturing what the meeting was about and where it landed.

## Key points
The substantive discussion points, grouped by topic. Be specific: numbers, names, dates.

## Decisions
What was agreed or decided. If nothing was decided, write "None."

## Action items
- [ ] task — owner — due date (only if an owner/date was actually mentioned)
If there are none, write "None."

## Open questions
Unresolved issues or things deferred to a later conversation. If none, write "None."

Rules:
- Use ONLY facts from the transcript and rough notes; never invent details, names,
  numbers, owners, or dates. It is better to omit than to guess.
- Be specific and concise — prefer concrete facts (figures, names, dates) over vague
  paraphrase, and don't pad. Every bullet should carry information.
- Capture EVERY decision and EVERY action item — these are the most important output.
  Attribute each action item to an owner only if one was actually named.
- If the rough notes exist, treat them as what the attendee cared about: expand and
  correct them against the transcript and keep their emphasis.
- Transcription may contain errors; silently fix obvious mis-transcriptions using context.
- If the transcript is too short or empty to support a section, write "None." for that
  section rather than inventing content.
- Output only the Markdown note. No preamble, no top-level title heading.
