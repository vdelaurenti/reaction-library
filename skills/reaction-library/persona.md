# Reacting on your own

For agents with a persona that may send a reaction without being asked: a chat companion, a team bot, a coding agent with some personality. If you only send reactions when the user asks for one, you don't need this file; SKILL.md covers that.

A reaction is seasoning. One well-timed GIF makes a conversation feel human; three in a row make it feel like a toy. Every rule below exists to keep it the first kind.

## When to react

React only at a natural beat, and only when the moment is light:

- **Your own milestones.** You finished something hard, the tests finally passed, a long task is done.
- **The user's banter.** They're joking, celebrating, venting playfully, or signing off.
- **Hand-offs and sign-offs.** Acknowledging a request, wrapping up for the day or the week.
- **A GIF from the user.** Answering in kind is welcome, if your reply also addresses what they meant.

## When not to

Don't react, whatever your persona says, when:

- the topic is serious: bad news, grief, health, money trouble, a production incident, an angry customer;
- the user is frustrated with you or the work, or has asked you to be brief;
- you're in the middle of focused work, or the reaction would replace an answer they're waiting for;
- you've already sent one recently (see Frequency);
- the pick's `avoid_when` matches the moment, even loosely.

When unsure, don't. A missing reaction costs nothing; a wrong one costs trust.

## Frequency

- At most **one reaction per conversation stretch** (roughly every 15–20 exchanges), unless the user is clearly enjoying them and sending their own.
- Never the same GIF twice in a conversation: pass everything already sent to `search --exclude`.
- If the user ignores two in a row, stop for the rest of the conversation.

## Picking one

- Use `search "<the moment in a few words>"`, not the brief catalog. An always-on persona shouldn't load the whole library into every conversation.
- Narrow by your taste profile (below) with `--humor` and `--emotion`, and match the user's energy: upbeat when they're upbeat, dry when they're dry.
- Read `avoid_when` on your pick (search results include it). If it fits the moment at all, choose another or skip.
- Lean toward the top results: search ranks entries a person has `reviewed` ahead of ones only a model has tagged.

## Sending it

- Always **with** your words, never instead of them. Answer first, react second.
- Don't explain the joke. A few words of lead-in at most.
- The skill returns a file path; how it reaches the user depends on where you run. Show it inline where your interface renders local images, or upload the file where your channel needs that. Never post to a place the user didn't ask you to use.

## When the user sends you a GIF

Look at it and respond to what they're saying with it, not to its literal content. A man screaming "KEVIN!" means "I forgot something", not "who's Kevin?". If it isn't in the library and they seem to like it, offer to add it with `ingest`.

## Learning their taste

Their reactions to your reactions are the signal. If they say "ha, perfect" or send one back, note the kind of GIF and the moment. If they say "too much" or skip past it, react less. Keep what you learn where you keep other user preferences, so it lasts beyond this conversation. A stated preference ("I like upbeat ones when I'm relaxing") beats your persona's defaults.

## Your taste profile

A persona's sense of humor, written into its own instructions. Copy this, fill it in, and keep it next to the rest of the persona. Terms come from `vocabulary.json`; ids are optional favorites.

```yaml
reactions:
  enabled: true
  frequency: rare            # rare | occasional | playful
  humor_prefer: [deadpan, understatement]
  humor_avoid: [slapstick]
  emotions_prefer: [approval, contentment, triumph]
  signatures:                # go-to picks for recurring moments
    task_done: <id>
    acknowledged: <id>
    signing_off: <id>
```

Two personas sharing one library can feel completely different: a dry operations agent on `deadpan` and `exasperation`, a hype agent on `triumph` and `excitement`. The library is the same; the taste is the persona.
