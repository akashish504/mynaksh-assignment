# Sample API Requests and Responses

A request and a response for every endpoint, plus the error responses.

Back to the [README](../README.md).

**About these samples.** Every response below is real. They were captured on 8 October 2026 by running the calls against the application with a real model (the local Docker stack, which runs the same code as the deployed one). Nothing was edited except the login token, shown as `<JWT>` or `<token>`. Because a real model wrote the replies, running the calls again gives different wording but the same structure.

Interactive documentation for all endpoints is served by the API itself at `/docs`.

## Contents

1. [Quick walkthrough with curl](#1-quick-walkthrough-with-curl)
2. [Health](#2-health)
3. [Signup and login](#3-signup-and-login)
4. [Profile](#4-profile)
5. [Chat sessions](#5-chat-sessions)
6. [Chat: the assignment's conversation](#6-chat-the-assignments-conversation)
7. [Memory updates (polling)](#7-memory-updates-polling)
8. [Memory page](#8-memory-page)
9. [A new user who gives their profile in chat](#9-a-new-user-who-gives-their-profile-in-chat)
10. [Error responses](#10-error-responses)

---

## 1. Quick walkthrough with curl

This runs the assignment's example conversation from a terminal. It needs `curl` and `jq`.

```bash
API=http://localhost:8000        # or the deployed API address

# 1. Sign up and keep the token
TOKEN=$(curl -s -X POST $API/auth/signup -H 'Content-Type: application/json' \
  -d '{"email":"rahul@example.com","password":"correct-horse-battery"}' | jq -r .access_token)
AUTH="Authorization: Bearer $TOKEN"

# 2. Save the profile
curl -s -X PUT $API/users/me/profile -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"name":"Rahul","dob":"1995-08-15","birth_time":"14:30:00","birth_time_known":true,"birth_place":"Delhi"}' | jq

# 3. Start a chat
SESSION=$(curl -s -X POST $API/sessions -H "$AUTH" | jq -r .id)

# 4. State a lasting fact
MSG=$(curl -s -X POST $API/chat -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"session_id\":\"$SESSION\",\"message\":\"I'm planning to switch jobs next year.\"}" | jq -r .message_id)

# 5. See what was remembered (wait a second or two first)
sleep 3; curl -s $API/messages/$MSG/memory-updates -H "$AUTH" | jq

# 6. Ask a question that should use it, then a follow-up
curl -s -X POST $API/chat -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"session_id\":\"$SESSION\",\"message\":\"What should I focus on for my career?\"}" | jq
curl -s -X POST $API/chat -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"session_id\":\"$SESSION\",\"message\":\"Why do you say that?\"}" | jq

# 7. New chat: the memory is still there
SESSION2=$(curl -s -X POST $API/sessions -H "$AUTH" | jq -r .id)
curl -s -X POST $API/chat -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"session_id\":\"$SESSION2\",\"message\":\"What do you remember about my career goals?\"}" | jq

# 8. Everything stored about the user
curl -s $API/users/me/memory -H "$AUTH" | jq
```

## 2. Health

No login needed. Returns 503 when either database is down, with the same body shape and `"down"` for that store.

```http
GET /health
```

Response `200`:

```json
{
  "status": "ok",
  "postgres": "up",
  "neo4j": "up"
}
```

## 3. Signup and login

### Sign up

```http
POST /auth/signup
Content-Type: application/json

{
  "email": "rahul.demo@example.com",
  "password": "correct-horse-battery"
}
```

Response `201`:

```json
{
  "access_token": "<JWT>",
  "token_type": "bearer",
  "profile_complete": false
}
```

`profile_complete` is false until the birth details are known. The token is valid for 7 days and is sent as `Authorization: Bearer <token>` on every other call.

### Log in

```http
POST /auth/login
Content-Type: application/json

{
  "email": "rahul.demo@example.com",
  "password": "correct-horse-battery"
}
```

Response `200`:

```json
{
  "access_token": "<JWT>",
  "token_type": "bearer",
  "profile_complete": false
}
```

## 4. Profile

### Who am I (before the profile is saved)

```http
GET /users/me
Authorization: Bearer <token>
```

Response `200`:

```json
{
  "email": "rahul.demo@example.com",
  "profile_complete": false,
  "profile": null
}
```

### Save the profile

The sun sign is computed from the date of birth. It is never accepted from the user.

```http
PUT /users/me/profile
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "Rahul",
  "dob": "1995-08-15",
  "birth_time": "14:30:00",
  "birth_time_known": true,
  "birth_place": "Delhi"
}
```

Response `200`:

```json
{
  "email": "rahul.demo@example.com",
  "profile_complete": true,
  "profile": {
    "name": "Rahul",
    "dob": "1995-08-15",
    "birth_time": "14:30:00",
    "birth_time_known": true,
    "birth_place": "Delhi",
    "language": "en",
    "profile_updated_via": "form",
    "zodiac": {
      "name": "Leo",
      "element": "Fire",
      "traits": [
        "confident",
        "generous",
        "expressive"
      ]
    }
  }
}
```

When the birth time is not known, send `"birth_time_known": false` and leave `birth_time` out.

## 5. Chat sessions

### Start a chat

```http
POST /sessions
Authorization: Bearer <token>
```

Response `201`:

```json
{
  "id": "f16280a1-9023-4f0a-93e3-02cd6c04f7af",
  "title": "New chat",
  "created_at": "2026-10-08T15:51:28.243760Z",
  "updated_at": "2026-10-08T15:51:28.243760Z"
}
```

The title changes to the first message (up to 60 characters) once the chat is used.

### List chats

Most recently used first.

```http
GET /sessions
Authorization: Bearer <token>
```

Response `200`:

```json
[
  {
    "id": "6a5ce702-e5eb-43c0-b4ef-5ccf527ea356",
    "title": "What do you remember about my career goals?",
    "created_at": "2026-10-08T15:51:43.838277Z",
    "updated_at": "2026-10-08T15:51:55.058435Z"
  },
  {
    "id": "f16280a1-9023-4f0a-93e3-02cd6c04f7af",
    "title": "I'm planning to switch jobs next year.",
    "created_at": "2026-10-08T15:51:28.243760Z",
    "updated_at": "2026-10-08T15:51:43.828977Z"
  }
]
```

### Messages of one chat

The first two of the ten messages are shown. Assistant messages carry `context_used`; user messages carry `memory_status`.

```http
GET /sessions/f16280a1-9023-4f0a-93e3-02cd6c04f7af/messages
Authorization: Bearer <token>
```

Response `200`:

```json
[
  {
    "id": "36626b76-bae4-4240-81a0-86dabd2b9bb9",
    "role": "user",
    "content": "I'm planning to switch jobs next year.",
    "created_at": "2026-10-08T15:51:28.249576Z",
    "type": null,
    "context_used": null,
    "memory_status": "done"
  },
  {
    "id": "dbbf4cd8-4425-45bc-a1a3-203062265a90",
    "role": "assistant",
    "content": "Based on what you’ve told me: you’re a Leo (Fire) type—confident, generous, expressive. That usually favors bold career moves, especially when you can take a visible role, lead, or build something with recognition. Next year, a job switch tends to go best when you choose opportunities where your strengths show (communication, initiative, energizing a team) rather than where you’d feel stuck or unheard. \n\nPractical tip: aim for a transition with a clear pitch—what you’ll improve, how you’ll add value, and how you’ll “own the spotlight” in the new role.",
    "created_at": "2026-10-08T15:51:31.555021Z",
    "type": "answer",
    "context_used": [
      "user_profile",
      "zodiac"
    ],
    "memory_status": null
  }
]
```

## 6. Chat: the assignment's conversation

All turns below belong to one user, Rahul (Leo), whose profile was saved in section 4.

Fields of the response:

| Field | Meaning |
|---|---|
| `response` | The reply |
| `user_id`, `session_id` | As in the assignment's sample |
| `message_id` | The id of the **user's** message, used to poll for memory updates |
| `type` | Always `answer` today. `clarification` is reserved for a planned feature |
| `options` | Always `null` today. Reserved for the same feature |
| `context_used` | Exactly what was put into the prompt: `user_profile`, `zodiac`, `history`, and one `kind:id` per memory |

### 6.1 A lasting fact

No memory exists yet, so only the profile and sun sign are used. The goal is stored after the reply (see section 7).

```http
POST /chat
Authorization: Bearer <token>
Content-Type: application/json

{
  "session_id": "f16280a1-9023-4f0a-93e3-02cd6c04f7af",
  "message": "I'm planning to switch jobs next year."
}
```

Response `200`:

```json
{
  "response": "Based on what you’ve told me: you’re a Leo (Fire) type—confident, generous, expressive. That usually favors bold career moves, especially when you can take a visible role, lead, or build something with recognition. Next year, a job switch tends to go best when you choose opportunities where your strengths show (communication, initiative, energizing a team) rather than where you’d feel stuck or unheard. \n\nPractical tip: aim for a transition with a clear pitch—what you’ll improve, how you’ll add value, and how you’ll “own the spotlight” in the new role.",
  "user_id": "3be409bf-c9b2-4022-a03e-360eb8882b19",
  "session_id": "f16280a1-9023-4f0a-93e3-02cd6c04f7af",
  "message_id": "36626b76-bae4-4240-81a0-86dabd2b9bb9",
  "type": "answer",
  "options": null,
  "context_used": [
    "user_profile",
    "zodiac"
  ]
}
```

### 6.2 Later in the same conversation

The goal stored a moment ago is now in `context_used`, and the reply mentions the 2027 switch.

```http
POST /chat
Authorization: Bearer <token>
Content-Type: application/json

{
  "session_id": "f16280a1-9023-4f0a-93e3-02cd6c04f7af",
  "message": "What should I focus on for my career?"
}
```

Response `200`:

```json
{
  "response": "From what you’ve told me: you’re a Leo (Fire) type—confident, generous, expressive. For your career, focus on roles where your visibility and leadership can shine: leading projects, pitching ideas, training/mentoring, or stepping into client-facing or decision-making work.\n\nFor your job switch in 2027, prepare a simple “spotlight pitch”: 1) what problem you solve, 2) a concrete win you’ve driven, and 3) how you’ll make the new team better within 60–90 days.\n\nAlso, stay generous but selective—don’t overcommit. Choose teams where your initiative is welcomed and your voice matters.",
  "user_id": "3be409bf-c9b2-4022-a03e-360eb8882b19",
  "session_id": "f16280a1-9023-4f0a-93e3-02cd6c04f7af",
  "message_id": "af7f96f4-642a-4db1-98fa-ae12b077e0f6",
  "type": "answer",
  "options": null,
  "context_used": [
    "user_profile",
    "zodiac",
    "history",
    "goal:13201797-1284-44ee-a88a-453f563fdd2b"
  ]
}
```

### 6.3 Follow-up

The same goal is reused, together with the history.

```http
POST /chat
Authorization: Bearer <token>
Content-Type: application/json

{
  "session_id": "f16280a1-9023-4f0a-93e3-02cd6c04f7af",
  "message": "Why do you say that?"
}
```

Response `200`:

```json
{
  "response": "I’m saying that because what you’ve shared points to a classic Leo (Fire) style at work: confident, generous, and expressive. That typically means you do best when your energy is used for leadership, clear communication, and taking ownership—things like leading projects, presenting ideas, guiding others, or working where you can be seen for your impact. \n\nAnd since you’re planning a job switch next year, the practical angle is: you’ll likely gain the most by choosing roles that let you “show your value” quickly—through a strong pitch, visible responsibilities, and early wins—rather than quiet back-end work where your strengths may not be noticed.",
  "user_id": "3be409bf-c9b2-4022-a03e-360eb8882b19",
  "session_id": "f16280a1-9023-4f0a-93e3-02cd6c04f7af",
  "message_id": "fb3f0f2f-3fde-44e5-bba1-92e323fef7e6",
  "type": "answer",
  "options": null,
  "context_used": [
    "user_profile",
    "zodiac",
    "history",
    "goal:13201797-1284-44ee-a88a-453f563fdd2b"
  ]
}
```

### 6.4 An unrelated question

The career goal is **not** sent: there is no `goal:` entry.

```http
POST /chat
Authorization: Bearer <token>
Content-Type: application/json

{
  "session_id": "f16280a1-9023-4f0a-93e3-02cd6c04f7af",
  "message": "Any advice for my health this month?"
}
```

Response `200`:

```json
{
  "response": "Based on what you’ve told me, you’re a Leo (Fire) type—confident, generous, expressive—so this month your health focus should support “fire energy” without burning out.\n\n1) Channel energy: aim for workouts that feel expressive and motivating (group classes, sports, brisk movement, strength + cardio mix).\n2) Watch heat habits: be mindful of overdoing caffeine, late nights, and sugary “reward” eating—those can turn energy into inflammation/low mood.\n3) Consistent schedule: keep sleep and meal timing steady to avoid mood/energy swings.\n4) Hydrate and stretch: add water plus a short daily stretch/mobility session to release tension.\n\nIf you want, tell me your main health goal (sleep, weight, stress, fitness).",
  "user_id": "3be409bf-c9b2-4022-a03e-360eb8882b19",
  "session_id": "f16280a1-9023-4f0a-93e3-02cd6c04f7af",
  "message_id": "085bfde1-2059-478b-8da3-52405c8efd27",
  "type": "answer",
  "options": null,
  "context_used": [
    "user_profile",
    "zodiac",
    "history"
  ]
}
```

### 6.5 Small talk

Only the name (`user_profile`) and the last two messages are sent. No sun sign, no memories.

```http
POST /chat
Authorization: Bearer <token>
Content-Type: application/json

{
  "session_id": "f16280a1-9023-4f0a-93e3-02cd6c04f7af",
  "message": "Thanks!"
}
```

Response `200`:

```json
{
  "response": "You’re welcome, Rahul. This month, the simplest health support is to “keep your fire controlled”: move regularly in a way that feels fun or expressive (even a short session), but avoid over-pushing—especially late nights and heavy caffeine/sugary “treat” cycles. Try to keep sleep and meal timing steady so your energy and mood don’t swing. Add hydration plus a quick daily stretch/mobility routine to prevent stiffness and help recovery. If you’ve been stressed, prioritize gentle movement and earlier wind-down rather than intensity.",
  "user_id": "3be409bf-c9b2-4022-a03e-360eb8882b19",
  "session_id": "f16280a1-9023-4f0a-93e3-02cd6c04f7af",
  "message_id": "7fb67052-f00b-4c07-a98c-b25feb0a0bcb",
  "type": "answer",
  "options": null,
  "context_used": [
    "user_profile",
    "history"
  ]
}
```

### 6.6 New conversation

A new session, so there is no `history`. The goal comes from the Shared Brain.

```http
POST /chat
Authorization: Bearer <token>
Content-Type: application/json

{
  "session_id": "6a5ce702-e5eb-43c0-b4ef-5ccf527ea356",
  "message": "What do you remember about my career goals?"
}
```

Response `200`:

```json
{
  "response": "You’ve told me that your career goal is to switch jobs in 2027. That’s the only career-goal detail I have saved so far.",
  "user_id": "3be409bf-c9b2-4022-a03e-360eb8882b19",
  "session_id": "6a5ce702-e5eb-43c0-b4ef-5ccf527ea356",
  "message_id": "e5be7289-91cf-4abf-a077-62e384d2eff9",
  "type": "answer",
  "options": null,
  "context_used": [
    "user_profile",
    "zodiac",
    "goal:13201797-1284-44ee-a88a-453f563fdd2b"
  ]
}
```

### 6.7 A question about the profile

```http
POST /chat
Authorization: Bearer <token>
Content-Type: application/json

{
  "session_id": "6a5ce702-e5eb-43c0-b4ef-5ccf527ea356",
  "message": "What is my zodiac sign?"
}
```

Response `200`:

```json
{
  "response": "Based on what you’ve told me, your zodiac sign is Leo (Fire). Your Leo traits are confident, generous, and expressive.",
  "user_id": "3be409bf-c9b2-4022-a03e-360eb8882b19",
  "session_id": "6a5ce702-e5eb-43c0-b4ef-5ccf527ea356",
  "message_id": "3b2dff03-719f-48b9-9044-fab964fcb861",
  "type": "answer",
  "options": null,
  "context_used": [
    "user_profile",
    "zodiac",
    "history"
  ]
}
```

### 6.8 Correcting a memory

At the moment of this reply the old goal is still the active one, so it is what `context_used` shows. The correction is applied right after (see section 7).

```http
POST /chat
Authorization: Bearer <token>
Content-Type: application/json

{
  "session_id": "6a5ce702-e5eb-43c0-b4ef-5ccf527ea356",
  "message": "Actually, I've pushed the job switch to 2028."
}
```

Response `200`:

```json
{
  "response": "Got it—what you’ve told me now is that you’re planning to switch jobs in 2028 (instead of 2027).\n\nAs a Leo (Fire), you’re naturally confident, generous, and expressive, so this kind of career shift often works best when you:\n1) lead with your strengths (confidence),\n2) build visibility/relationships (expressive, generous approach),\n3) choose a role where your personality can be seen, not just measured.\n\nIf you want, you can treat 2028 as your “launch window” and start positioning yourself now through skills and networking.",
  "user_id": "3be409bf-c9b2-4022-a03e-360eb8882b19",
  "session_id": "6a5ce702-e5eb-43c0-b4ef-5ccf527ea356",
  "message_id": "2ea25376-e064-4a03-bed9-b7992d3e4cff",
  "type": "answer",
  "options": null,
  "context_used": [
    "user_profile",
    "zodiac",
    "history",
    "goal:13201797-1284-44ee-a88a-453f563fdd2b"
  ]
}
```

### 6.9 After the correction

A different goal id: the corrected memory. The 2027 version is no longer selected.

```http
POST /chat
Authorization: Bearer <token>
Content-Type: application/json

{
  "session_id": "6a5ce702-e5eb-43c0-b4ef-5ccf527ea356",
  "message": "What do you remember about my career goals?"
}
```

Response `200`:

```json
{
  "response": "What you’ve told me about your career goals: you’re planning to switch jobs in 2028. That’s the only career-goal detail I have saved so far.",
  "user_id": "3be409bf-c9b2-4022-a03e-360eb8882b19",
  "session_id": "6a5ce702-e5eb-43c0-b4ef-5ccf527ea356",
  "message_id": "5a4a39b3-da62-403e-994c-f0af6ee82a14",
  "type": "answer",
  "options": null,
  "context_used": [
    "user_profile",
    "zodiac",
    "history",
    "goal:402dabe9-61a8-4633-8959-dedc71006bc1"
  ]
}
```

## 7. Memory updates (polling)

The frontend calls this once a second after each reply, for up to 8 seconds, to show the "Memory updated" chip.

| `status` | Meaning |
|---|---|
| `pending` | The background step has not finished yet |
| `done` | Finished. `updates` lists what was stored (it can be empty) |
| `skipped` | The memory gate decided the message held nothing lasting. No LLM call was made |
| `failed` | The step failed. The chat reply was not affected |

### A memory was created

For "I'm planning to switch jobs next year."

```http
GET /messages/36626b76-bae4-4240-81a0-86dabd2b9bb9/memory-updates
Authorization: Bearer <token>
```

Response `200`:

```json
{
  "status": "done",
  "updates": [
    {
      "action": "created",
      "kind": "goal",
      "title": "Job switch next year",
      "life_area": "career",
      "memory_id": "13201797-1284-44ee-a88a-453f563fdd2b"
    }
  ]
}
```

### Skipped by the gate

For "What should I focus on for my career?"

```http
GET /messages/af7f96f4-642a-4db1-98fa-ae12b077e0f6/memory-updates
Authorization: Bearer <token>
```

Response `200`:

```json
{
  "status": "skipped",
  "updates": []
}
```

### A memory was updated

For "Actually, I've pushed the job switch to 2028." The `memory_id` is the new node.

```http
GET /messages/2ea25376-e064-4a03-bed9-b7992d3e4cff/memory-updates
Authorization: Bearer <token>
```

Response `200`:

```json
{
  "status": "done",
  "updates": [
    {
      "action": "updated",
      "kind": "goal",
      "title": "Job switch timing updated",
      "life_area": "career",
      "memory_id": "402dabe9-61a8-4633-8959-dedc71006bc1"
    }
  ]
}
```

### The assignment's second example

For "I'm preparing for a product management interview next month."

```http
GET /messages/ccf88096-3d20-4405-aac8-51972dffefa7/memory-updates
Authorization: Bearer <token>
```

Response `200`:

```json
{
  "status": "done",
  "updates": [
    {
      "action": "created",
      "kind": "goal",
      "title": "Prepare for PM interview",
      "life_area": "career",
      "memory_id": "47db5722-7e9b-498e-9ef1-ade3bbbccb76"
    }
  ]
}
```

## 8. Memory page

### Everything stored about the user

Active memories only, grouped by life area, newest first. The superseded 2027 goal is not listed.

```http
GET /users/me/memory
Authorization: Bearer <token>
```

Response `200`:

```json
{
  "profile": {
    "name": "Rahul",
    "dob": "1995-08-15",
    "birth_time": "14:30:00",
    "birth_time_known": true,
    "birth_place": "Delhi",
    "language": "en",
    "profile_updated_via": "form",
    "zodiac": {
      "name": "Leo",
      "element": "Fire",
      "traits": [
        "confident",
        "generous",
        "expressive"
      ]
    }
  },
  "memories": {
    "career": [
      {
        "id": "47db5722-7e9b-498e-9ef1-ade3bbbccb76",
        "kind": "goal",
        "title": "Prepare for PM interview",
        "text": "Goal: prepare for a product management interview next month.",
        "life_area": "career",
        "attributes": {
          "timeframe": "next month (relative)"
        },
        "created_at": "2026-10-08T15:51:56.568228Z"
      },
      {
        "id": "402dabe9-61a8-4633-8959-dedc71006bc1",
        "kind": "goal",
        "title": "Job switch timing updated",
        "text": "Career goal: plans to switch jobs in 2028.",
        "life_area": "career",
        "attributes": {
          "target_year": 2028
        },
        "created_at": "2026-10-08T15:51:51.318047Z"
      }
    ]
  }
}
```

### Delete one memory

```http
DELETE /users/me/memory/402dabe9-61a8-4633-8959-dedc71006bc1
Authorization: Bearer <token>
```

Response `204 No Content` (empty body).

Deleting it again:

```http
DELETE /users/me/memory/402dabe9-61a8-4633-8959-dedc71006bc1
Authorization: Bearer <token>
```

Response `404`:

```json
{
  "detail": "Memory not found."
}
```

## 9. A new user who gives their profile in chat

A second account that never filled the form.

### 9.1 Before anything is known

`context_used` is empty, and the reply suggests completing the profile.

```http
POST /chat
Authorization: Bearer <token>
Content-Type: application/json

{
  "session_id": "f72e85f8-3dac-4c6e-b65f-e9f65391aee2",
  "message": "What should I focus on for my career?"
}
```

Response `200`:

```json
{
  "response": "From what you’ve shared, I only know your general personality approach: you’re practical and steady (grounded element) and you tend to build things through consistency, responsibility, and reliable effort. For career, your best focus is: 1) long-term skill-building (one craft, deepen it), 2) dependable execution (show up, meet deadlines, keep quality steady), 3) roles where process and problem-solving matter, and 4) taking ownership of outcomes rather than just tasks. \n\nSince your birth details aren’t complete yet, I can’t tailor this to your deeper timing or strengths. If you finish your profile, I’ll personalize your career themes.",
  "user_id": "b0a7881a-85c8-4ec0-9c8a-4f2a472fecc5",
  "session_id": "f72e85f8-3dac-4c6e-b65f-e9f65391aee2",
  "message_id": "0346be29-f324-4773-9089-810205fba546",
  "type": "answer",
  "options": null,
  "context_used": []
}
```

### 9.2 The assignment's first message

```http
POST /chat
Authorization: Bearer <token>
Content-Type: application/json

{
  "session_id": "f72e85f8-3dac-4c6e-b65f-e9f65391aee2",
  "message": "My name is Rahul. I was born on 15 August 1995 in Delhi. I'm planning to switch jobs next year."
}
```

Response `200`:

```json
{
  "response": "Rahul, from what you’ve shared, you’re likely at your best in careers that reward consistency, responsibility, and reliable output. For your job switch next year, focus on:\n\n1) Choose a path to deepen: pick one core skill/role and go deeper, not wider.  \n2) Prove dependable execution: highlight reliability, quality, and meeting deadlines.  \n3) Look for “process + problem-solving” roles: jobs where structure, troubleshooting, and continuous improvement matter.  \n4) Target ownership: show you can take charge of outcomes, not just tasks.\n\nIf you complete your full birth details (especially birth time) in your profile, I can personalize the timing and the best career themes for your switch.",
  "user_id": "b0a7881a-85c8-4ec0-9c8a-4f2a472fecc5",
  "session_id": "f72e85f8-3dac-4c6e-b65f-e9f65391aee2",
  "message_id": "c65c9649-dfa4-474a-89de-d2f507c31b72",
  "type": "answer",
  "options": null,
  "context_used": [
    "history"
  ]
}
```

At the moment of this reply nothing is stored yet, so only the history is used.

### 9.3 What the memory step did with it

Three profile updates and one goal, from one message.

```http
GET /messages/c65c9649-dfa4-474a-89de-d2f507c31b72/memory-updates
Authorization: Bearer <token>
```

Response `200`:

```json
{
  "status": "done",
  "updates": [
    {
      "action": "profile_corrected",
      "kind": "profile_correction",
      "title": "Name updated",
      "life_area": "general",
      "memory_id": null
    },
    {
      "action": "profile_corrected",
      "kind": "profile_correction",
      "title": "Date of birth updated",
      "life_area": "general",
      "memory_id": null
    },
    {
      "action": "profile_corrected",
      "kind": "profile_correction",
      "title": "Birth place updated",
      "life_area": "general",
      "memory_id": null
    },
    {
      "action": "created",
      "kind": "goal",
      "title": "Job switch next year",
      "life_area": "career",
      "memory_id": "40014d1e-18b3-4b27-a2f1-8c05752e1b99"
    }
  ]
}
```

### 9.4 The profile is now complete

The sun sign was computed from the date of birth. `profile_updated_via` is `chat`. The birth time is still unknown.

```http
GET /users/me
Authorization: Bearer <token>
```

Response `200`:

```json
{
  "email": "priya.demo@example.com",
  "profile_complete": true,
  "profile": {
    "name": "Rahul",
    "dob": "1995-08-15",
    "birth_time": null,
    "birth_time_known": false,
    "birth_place": "Delhi",
    "language": "en",
    "profile_updated_via": "chat",
    "zodiac": {
      "name": "Leo",
      "element": "Fire",
      "traits": [
        "confident",
        "generous",
        "expressive"
      ]
    }
  }
}
```

### 9.5 What is stored

```http
GET /users/me/memory
Authorization: Bearer <token>
```

Response `200`:

```json
{
  "profile": {
    "name": "Rahul",
    "dob": "1995-08-15",
    "birth_time": null,
    "birth_time_known": false,
    "birth_place": "Delhi",
    "language": "en",
    "profile_updated_via": "chat",
    "zodiac": {
      "name": "Leo",
      "element": "Fire",
      "traits": [
        "confident",
        "generous",
        "expressive"
      ]
    }
  },
  "memories": {
    "career": [
      {
        "id": "40014d1e-18b3-4b27-a2f1-8c05752e1b99",
        "kind": "goal",
        "title": "Job switch next year",
        "text": "Career goal: plans to switch jobs next year (2027).",
        "life_area": "career",
        "attributes": {
          "target_year": 2027,
          "timeframe": "next year"
        },
        "created_at": "2026-10-08T15:52:03.931801Z"
      }
    ]
  }
}
```

### 9.6 The same question as 9.1, now personalised

```http
POST /chat
Authorization: Bearer <token>
Content-Type: application/json

{
  "session_id": "f72e85f8-3dac-4c6e-b65f-e9f65391aee2",
  "message": "What should I focus on for my career?"
}
```

Response `200`:

```json
{
  "response": "Rahul, based on what you’ve shared (your Leo-style strengths: confident, generous, expressive, plus a practical/grounded approach), focus on career moves that let you lead through your voice and results.\n\n1) Pick one direction to go deep on before you switch (a core skill or domain).  \n2) Build a “reliability proof”: measurable outcomes, consistent delivery, strong quality.  \n3) Choose roles with problem-solving and process improvement, where ownership is rewarded.  \n4) During the job switch next year (2027), communicate your impact confidently—your expression is an advantage.\n\nIf you share your birth time, I can tailor this even more.",
  "user_id": "b0a7881a-85c8-4ec0-9c8a-4f2a472fecc5",
  "session_id": "f72e85f8-3dac-4c6e-b65f-e9f65391aee2",
  "message_id": "c494d923-f185-4caa-be57-9002bea46412",
  "type": "answer",
  "options": null,
  "context_used": [
    "user_profile",
    "zodiac",
    "history",
    "goal:40014d1e-18b3-4b27-a2f1-8c05752e1b99"
  ]
}
```

## 10. Error responses

Every error has a `detail` field. For validation errors (422) it is a list with one entry per problem; for everything else it is one sentence.

| Status | When |
|---|---|
| 401 | No token, or an invalid or expired one; wrong email or password at login |
| 404 | The chat, message or memory does not exist or belongs to someone else |
| 409 | The email is already registered |
| 422 | The request body is invalid |
| 429 | More than 20 chat messages in a minute |
| 503 | A database is unreachable |

### 401: no token

```http
POST /chat
Content-Type: application/json

{
  "session_id": "f16280a1-9023-4f0a-93e3-02cd6c04f7af",
  "message": "hi"
}
```

Response `401`:

```json
{
  "detail": "Please log in to continue."
}
```

### 401: wrong password

The same message is returned for an unknown email.

```http
POST /auth/login
Content-Type: application/json

{
  "email": "rahul.demo@example.com",
  "password": "wrong-password"
}
```

Response `401`:

```json
{
  "detail": "Incorrect email or password."
}
```

### 404: a session that does not exist

```http
POST /chat
Authorization: Bearer <token>
Content-Type: application/json

{
  "session_id": "00000000-0000-0000-0000-000000000000",
  "message": "hi"
}
```

Response `404`:

```json
{
  "detail": "Chat not found."
}
```

### 404: another user's chat

The second user asks for the first user's messages. The answer is the same as for a chat that does not exist.

```http
GET /sessions/f16280a1-9023-4f0a-93e3-02cd6c04f7af/messages
Authorization: Bearer <token>
```

Response `404`:

```json
{
  "detail": "Chat not found."
}
```

### 409: email already registered

```http
POST /auth/signup
Content-Type: application/json

{
  "email": "rahul.demo@example.com",
  "password": "correct-horse-battery"
}
```

Response `409`:

```json
{
  "detail": "An account with this email already exists. Try logging in instead."
}
```

### 422: empty message

```http
POST /chat
Authorization: Bearer <token>
Content-Type: application/json

{
  "session_id": "f16280a1-9023-4f0a-93e3-02cd6c04f7af",
  "message": "   "
}
```

Response `422`:

```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": [
        "body",
        "message"
      ],
      "msg": "Value error, Message cannot be empty.",
      "input": "   ",
      "ctx": {
        "error": {}
      }
    }
  ]
}
```

### 422: a session id that is not a valid id

```http
POST /chat
Authorization: Bearer <token>
Content-Type: application/json

{
  "session_id": "session-456",
  "message": "hi"
}
```

Response `422`:

```json
{
  "detail": [
    {
      "type": "uuid_parsing",
      "loc": [
        "body",
        "session_id"
      ],
      "msg": "Input should be a valid UUID, invalid character: found `s` at 1",
      "input": "session-456",
      "ctx": {
        "error": "invalid character: found `s` at 1"
      }
    }
  ]
}
```

### 422: invalid signup

Two problems, two entries.

```http
POST /auth/signup
Content-Type: application/json

{
  "email": "not-an-email",
  "password": "short"
}
```

Response `422`:

```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": [
        "body",
        "email"
      ],
      "msg": "value is not a valid email address: An email address must have an @-sign.",
      "input": "not-an-email",
      "ctx": {
        "reason": "An email address must have an @-sign."
      }
    },
    {
      "type": "string_too_short",
      "loc": [
        "body",
        "password"
      ],
      "msg": "String should have at least 8 characters",
      "input": "short",
      "ctx": {
        "min_length": 8
      }
    }
  ]
}
```

### 422: date of birth in the future

```http
PUT /users/me/profile
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "Rahul",
  "dob": "2999-01-01",
  "birth_time_known": false,
  "birth_place": "Delhi"
}
```

Response `422`:

```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": [
        "body",
        "dob"
      ],
      "msg": "Value error, Date of birth cannot be in the future.",
      "input": "2999-01-01",
      "ctx": {
        "error": {}
      }
    }
  ]
}
```

### 429: rate limit

Not captured in the run above; this is the fixed body the API returns.

```json
{
  "detail": "You're sending messages too quickly. Please wait a moment and try again."
}
```

### 503: a database is unreachable

Not captured in the run above; these are the fixed bodies the API returns.

```json
{
  "detail": "The service is temporarily unavailable. Please try again in a moment."
}
```

```json
{
  "detail": "Your profile is temporarily unavailable. Please try again in a moment."
}
```

### 200: every model failed

Not an error status. The chat answers with a fixed sentence, the turn is saved, and `context_used` is empty. Not captured in the run above; the automated test `test_llm_failure_returns_a_friendly_reply_and_still_saves_the_turn` checks it.

```json
{
  "response": "I'm having trouble answering right now. Please try again in a moment.",
  "user_id": "...",
  "session_id": "...",
  "message_id": "...",
  "type": "answer",
  "options": null,
  "context_used": []
}
```
