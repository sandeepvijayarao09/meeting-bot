You are given the transcript of a candidate interview recorded on the attendee's laptop.
"Me" is the interviewer (laptop owner); "Them" is the candidate (and any other panelists
when diarized as "Them · Speaker A/B").

# Meeting
- Title: {{TITLE}}
- Date: {{DATE}}
- Duration: {{DURATION}}

# Interviewer's rough notes (may be empty)
{{NOTES}}

# Transcript
{{TRANSCRIPT}}

# Task
Write structured interview notes in Markdown with exactly these sections:

## Summary
2–3 bullets: who the candidate is, the role/topic, and overall impression.

## Background & experience
Relevant experience, skills, and projects the candidate described.

## Strengths
Concrete positive signals, with examples from the conversation.

## Concerns / risks
Gaps, red flags, or areas to probe further. If none, write "None."

## Notable answers
Key questions asked and the substance of the candidate's answers.

## Recommendation
A clear lean (Strong yes / Yes / No / Strong no) **only if** the interviewer
expressed one; otherwise "Not stated." Briefly justify from the transcript.

Rules:
- Use only facts from the transcript and rough notes; never invent details or scores.
- Fix obvious transcription errors silently using context.
- Output only the Markdown note. No preamble, no top-level title heading.
