# תכנון: סוכן סיכום לוגים (LogSum)

> סוכן אחד, שני harnesses: `API/` (Messages API גולמי) ו-`SDK/` (Claude Agent SDK).
> שם התיקייה: `logsum-<השם-שלך>/`

---

## 1. רעיון הסוכן

**הבעיה:** כשמשהו נשבר, צריך לקרוא אלפי שורות לוג כדי להבין מה קרה. רוב השורות רעש, חלק מהשגיאות "ידועות" ולא מעניינות, והשאלה האמיתית היא בדרך כלל: *מה חדש? מה חמור? מאיזה שירות?*

**הסוכן:** מקבל בקשה בשפה חופשית ("מה קרה ב-worker בשעה האחרונה?"), קורא קובצי לוג דרך כלים, מקבץ שגיאות לפי חתימה, ומחזיר סיכום קצר. הוא **זוכר** בין סשנים:
- אילו שגיאות ידועות ולמה (למשל "DB timeout בלילה = backup").
- אילו דפוסים להתעלם מהם (למשל healthcheck).
- העדפות פורמט ושפה של הסיכום.
- היסטוריית אירועים (incidents) שכבר סוכמו.

### ארבעת הנושאים

| נושא | איך זה מתבטא בסוכן |
|---|---|
| **Tools** | 5 כלים משלי (פירוט בסעיף 2). הכלי החיצוני: קריאת קבצים מהדיסק (`read_log`), ואופציונלית `fetch_remote_log` מ-URL. |
| **Memory** | `shared/data/memory.json`: known issues, ignore patterns, preferences, incidents. נשמר בין סשנים ונטען במופע חדש. |
| **Context engineering** | הלוג הגולמי **אף פעם** לא נכנס לקונטקסט. הכלים מחזירים אגרגציות. מהזיכרון נכנס רק מה שרלוונטי לשירות/לקובץ שהבקשה עוסקת בו + ה-preferences. |
| **Token optimization** | פלט כלים קומפקטי (חתימה + ספירה + דוגמה אחת מקוצרת, עד N שורות), תקרת תווים לכל tool_result, מדידת טוקנים ועלות לכל תור. |

---

## 2. קוד הדומיין — `shared/`

```
shared/
  log_tools.py      # הלוגיקה של הכלים (פונקציות Python טהורות)
  memory_store.py   # קריאה/כתיבה של memory.json
  schemas.py        # תיאורי הכלים (שם, תיאור, פרמטרים) – מקור אחד לשתי הגרסאות
  data/
    logs/
      app.log       # לוג אפליקציה סינתטי עם שגיאות מתוכננות
      nginx.log     # access log עם 5xx
      worker.log    # לוג worker עם DB timeout + healthcheck
    memory.json     # נוצר בזמן ריצה (מתאפס בתחילת כל ריצה)
  checks.py         # הבדיקות pass/fail של התרחיש
```

### הכלים

| כלי | קלט | פלט (קומפקטי) | הערות |
|---|---|---|---|
| `list_logs` | — | `[{"file":"app.log","lines":4210,"from":"..","to":".."}]` | זול, נותן למודל מפה בלי לקרוא תוכן |
| `read_log` **(חיצוני – קבצים)** | `file`, `level?`, `since?`, `until?`, `limit=20` | שורות מסוננות, כל שורה חתוכה ל-160 תווים | `limit` מקסימלי 50 |
| `group_errors` | `file`, `since?`, `apply_ignore=true` | `[{"sig":"DBTimeout: pool exhausted","count":37,"first":"..","last":"..","sample":".."}]` | נרמול: מספרים/UUID/IP → `<N>`; מסנן ignore patterns מהזיכרון |
| `search_logs` | `pattern` (regex), `file?`, `limit=10` | `{"matches":12,"shown":[...]}` | |
| `remember` | `kind` (`known_issue`/`ignore`/`preference`/`incident`), `key`, `value` | `{"ok":true,"replaced":old?}` | **upsert** – ערך חדש דורס ישן, ומחזיר מה נדרס (חשוב לבקשה הסותרת) |
| `forget` | `kind`, `key` | `{"ok":true}` | להסרת ignore pattern |
| `recall` | `query?`, `kind?` | רק רשומות תואמות | שליפה לפי מילות מפתח / שם שירות |

שגיאות (קובץ לא קיים, regex לא תקין, `since` לא תקין) נזרקות כ-`ToolError` ב-shared, וכל harness ממיר אותן ל-`is_error` בדרכו.

### מבנה memory.json

```json
{
  "preferences": {"format": "bullets", "language": "en"},
  "ignore": {"healthcheck": "GET /health"},
  "known_issues": {"DBTimeout": "nightly backup 02:00-02:30, not actionable"},
  "incidents": [{"date": "2026-10-22", "file": "nginx.log", "summary": "..."}],
  "updated_at": "..."
}
```

### נתוני הלוג הסינתטיים
סקריפט `shared/data/make_logs.py` (deterministic, עם seed) שמייצר:
- `app.log`: INFO רגיל + `NullPointerException in OrderService` ×12 + `PaymentGateway 502` ×5.
- `nginx.log`: access log, 5xx בחלון זמן אחד על `/api/checkout`.
- `worker.log`: `DBTimeout` בין 02:00–02:30, הרבה `GET /health`, ושגיאה **חדשה** `S3 AccessDenied` שמופיעה רק בסשן 2.

---

## 3. גרסת API — `API/`

```
API/
  main.py      # CLI: --scenario --out, מריץ סשנים, כותב results/api.json
  agent.py     # class Agent: מחבר את כל ה-harness, פונקציה turn(user_text)
  harness/
    loop.py        # לולאת הסוכן
    tools.py       # סכמות JSON, dispatch, is_error
    history.py     # שיחה לדיסק, append-only (JSONL)
    memory.py      # עטיפה על shared/memory_store + בחירת רשומות רלוונטיות
    context.py     # בניית system + messages לכל תור
    compaction.py  # סיכום שיחה מעבר לסף
    caching.py     # נקודות cache_control
    tokens.py      # usage ועלות לכל קריאה ולכל תור
```

**דרישת הדפסה:** כל פעולה בזמן ריצה מודפסת עם שם הקובץ, דרך helper אחד:
```
[loop.py] call #2 → stop_reason=tool_use
[tools.py] dispatch group_errors(file=worker.log) → 4 sigs, 312 chars
[memory.py] selected 2/7 entries for context (service=worker)
[caching.py] cache_control on: system, tools[-1], messages[-1]
[tokens.py] turn 3: in=812 cache_r=3100 cache_w=0 out=240 $0.0123
```

### פירוט לכל קובץ

**loop.py**
- `while True`: קריאה ל-`client.messages.create(...)`; אם `stop_reason != "tool_use"` → יוצאים.
- אוספים **את כל** בלוקי `tool_use` בתשובה, מריצים, ומחזירים את כל ה-`tool_result` ב**הודעת user אחת**.
- תקרת בטיחות: `max_iterations=8`.
- מחזיר: טקסט סופי, מספר קריאות, רשימת כלים שהופעלו.

**tools.py**
- `TOOL_SCHEMAS` נבנה מ-`shared/schemas.py` (JSON Schema).
- `dispatch(name, input) → (content_str, is_error)`. שם לא מוכר / `ToolError` / exception → `is_error: true` עם הודעה קצרה, כדי שהמודל יתקן את עצמו.
- תקרת אורך לפלט (למשל 1,500 תווים) + `"truncated": true`.

**history.py**
- `history/<session_id>.jsonl`, שורה לכל הודעה (`role`, `content`, `ts`). רק append, אף פעם לא כתיבה מחדש.
- compaction **לא** מוחקת היסטוריה: היא כותבת רשומת `{"type":"compaction","summary":...,"upto":N}`, ו-context.py משתמש בה.
- `load(session_id)` לשחזור.

**memory.py**
- `relevant(user_text)` → תמיד `preferences` + `ignore`; `known_issues` ו-`incidents` רק אם מילת מפתח / שם קובץ / שירות מופיעים בבקשה. השאר זמין דרך הכלי `recall`.
- מדפיס כמה רשומות נבחרו מתוך כמה.

**context.py**
- system = הנחיות קבועות בלבד, שלא משתנות לאורך הסשן (שינוי ב-system שובר את ה-cache ופוסל thinking blocks קודמים ב-Opus 5.5).
- בלוק `<memory>` דינמי נשלח **בתוך הודעת ה-user** של התור ונשאר בהיסטוריה (append-only).
- messages = (סיכום compaction אם קיים) + ההודעות שאחריו.
- לא מכניס לוגים, לא מכניס את כל הזיכרון.

**compaction.py**
- סף: אם `input_tokens` של הקריאה האחרונה > `COMPACT_AT` (למשל 8,000 – נמוך בכוונה כדי שזה יקרה בתרחיש, או flag `--compact-at`).
- קריאה נפרדת למודל: "סכם את השיחה עד כה: החלטות, ממצאים, שאלות פתוחות". שומרים כרשומת compaction ב-history.
- הקריאה הזו נספרת ב-tokens.py.

**caching.py**
- `cache_control: {"type":"ephemeral"}` על: בלוק ה-system הסטטי, הכלי האחרון ב-`tools`, וההודעה האחרונה ב-messages (cache מצטבר לאורך הלולאה).
- עד 4 breakpoints.

**tokens.py**
- מכל `response.usage`: `input_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`, `output_tokens`.
- טבלת מחירים בקובץ אחד (לאמת מול התיעוד בזמן הכתיבה) → עלות לכל קריאה ולכל תור.
- אחוז cache = `cache_read / (input + cache_read + cache_write)`.

**הגדרות:** `model="claude-opus-5-5"`, effort `medium` (לאמת את שם הפרמטר המדויק ב-Messages API בזמן המימוש), `max_tokens` קבוע.

---

## 4. גרסת SDK — `SDK/`

```
SDK/
  main.py      # CLI זהה: --scenario --out, כותב results/sdk.json
  agent.py     # ClaudeAgentOptions + ClaudeSDKClient
  tools.py     # @tool wrappers על shared/log_tools + create_sdk_mcp_server
  CLAUDE.md    # הנחיות קבועות + "לפני סיכום – קרא recall"
```

### מיפוי – כל שורה מסומנת `# replaces: <קובץ>`

```python
options = ClaudeAgentOptions(
    model="claude-opus-5-5",                         # same as API
    system_prompt=SYSTEM_PROMPT,                     # replaces: context.py
    mcp_servers={"logsum": logsum_server},           # replaces: tools.py
    allowed_tools=[                                  # replaces: tools.py
        "mcp__logsum__list_logs", "mcp__logsum__read_log",
        "mcp__logsum__group_errors", "mcp__logsum__search_logs",
        "mcp__logsum__remember", "mcp__logsum__forget", "mcp__logsum__recall",
    ],
    strict_mcp_config=True,                          # רק השרת שלי
    setting_sources=["project"],                     # replaces: memory.py (CLAUDE.md)
    resume=session_id,                               # replaces: history.py
    cwd=PROJECT_DIR,
)
# client.query(...) + receive_response()          # replaces: loop.py
# compaction אוטומטי                             # replaces: compaction.py
# caching אוטומטי                                # replaces: caching.py
# ResultMessage.usage / total_cost_usd            # replaces: tokens.py
```

- **אין כלים מובנים** (Bash/Read/Write) ברשימה – רשימה מצומצמת, כדי שההשוואה תהיה הוגנת וכדי שהמודל לא יקרא לוגים גולמיים עם Read.
- **זיכרון:** אותו `memory.json` דרך אותם כלים (כדי שהבדיקות על המצב יהיו זהות), ו-`CLAUDE.md` להנחיות קבועות. בדוח: להסביר את ההבדל מול הזרקת זיכרון רלוונטי ב-context.py.
- **סשן 2:** `ClaudeSDKClient` חדש. השאלה היא אם להשתמש ב-`resume` – לפי ההנחיות סשן 2 הוא "מופע חדש שטוען מצב מהדיסק", לכן: סשן חדש **בלי** resume, והזיכרון מגיע מ-memory.json + CLAUDE.md. את `resume` מדגימים בתוך סשן (בין תורות) / מתעדים ב-agent.py.
- כלים: `ToolError` → מחזירים `{"content":[...], "is_error": True}`.
- **הרשאות:** לוודא ש-`ANTHROPIC_API_KEY` **לא** מוגדר כשמריצים את ה-SDK (main.py מדפיס אזהרה אם כן).

---

## 5. תרחיש — `scenario.json`

8 פניות, 2 סשנים. לפני ריצה: מחיקת `memory.json`, `history/`, ויצירת הלוגים מחדש.

```json
{
  "model": "claude-opus-5-5",
  "effort": "medium",
  "sessions": [
    {
      "id": "s1",
      "turns": [
        {"id": "t1", "user": "Which log files do I have, and what are the main errors in app.log?"},
        {"id": "t2", "user": "Check nginx.log for 5xx errors. Which endpoint and when? Save this as an incident."},
        {"id": "t3", "user": "The DBTimeout errors in worker.log are known – they're caused by the nightly backup. Remember that. Also always ignore healthcheck lines."},
        {"id": "t4", "user": "From now on, give me summaries as short bullets, in English."}
      ]
    },
    {
      "id": "s2",
      "new_instance": true,
      "pre": "append_new_errors_to_worker_log",
      "turns": [
        {"id": "t5", "user": "What's new in worker.log? Only things I don't already know about."},
        {"id": "t6", "user": "Did we already have an incident on checkout? What was it?"},
        {"id": "t7", "user": "Actually, stop ignoring healthcheck – I want to see it. And switch summaries to Hebrew."},
        {"id": "t8", "user": "Summarize worker.log again."}
      ]
    }
  ]
}
```

| דרישה | איפה |
|---|---|
| שימוש בכלים | t1, t2, t5, t8 |
| כלי חיצוני (קבצים) | t1, t2, t5, t8 (`read_log` / `group_errors`) |
| שמירה לזיכרון | t2 (incident), t3 (known_issue + ignore), t4 (preference) |
| שליפה מהזיכרון בסשן 2 | t5 (known issue + ignore), t6 (incident) |
| בקשה סותרת | t7 (ignore → לא להתעלם; en → he) |

### בדיקות pass/fail (`shared/checks.py`)

רובן על **המצב שנשמר**:

| # | בדיקה | סוג |
|---|---|---|
| C1 | אחרי s1: `memory.known_issues` מכיל מפתח עם `DBTimeout` והערך מכיל `backup` | state |
| C2 | אחרי s1: `memory.incidents` מכיל רשומה עם `nginx`/`checkout` | state |
| C3 | אחרי s1: `memory.preferences.format == "bullets"` | state |
| C4 | אחרי s2: `healthcheck` **לא** נמצא ב-`memory.ignore` (הסתירה נפתרה, לא נוספה רשומה כפולה) | state |
| C5 | אחרי s2: `memory.preferences.language == "he"` ויש רק ערך שפה אחד | state |
| C6 | t5: התשובה מזכירה `S3`/`AccessDenied` ו**לא** מציגה את DBTimeout כחדש | text + tools |
| C7 | t5 או t6: הופעל `recall`/זיכרון הוזרק, ו-t6 מזכיר `checkout` | tools + text |
| C8 | t8: התשובה בעברית (יחס תווים עבריים > 50%) | text |
| C9 | `history/` מכיל קובץ לכל סשן, ומספר השורות רק עולה (API בלבד) | state |

---

## 6. מדידה — `results/{api,sdk}.json`

```json
{
  "harness": "api",
  "model": "claude-opus-5-5",
  "effort": "medium",
  "turns": [
    {
      "session": "s1", "turn": "t1",
      "tokens": {"input": 812, "cache_read": 3100, "cache_write": 0, "output": 240},
      "model_calls": 3,
      "tools": ["list_logs", "group_errors"],
      "cost_usd": 0.0123,
      "seconds": 6.4,
      "response": "..."
    }
  ],
  "totals": {"input": 0, "cache_read": 0, "cache_write": 0, "output": 0,
             "cache_pct": 0.0, "model_calls": 0, "cost_usd": 0.0, "seconds": 0.0},
  "checks": [{"id": "C1", "pass": true, "detail": "..."}],
  "loc": {"loop": 0, "tools": 0, "history": 0, "memory": 0, "context": 0,
          "compaction": 0, "caching": 0, "tokens": 0, "total": 0}
}
```

- **API:** הטוקנים מ-tokens.py; מספר קריאות מ-loop.py.
- **SDK:** טוקנים מ-`ResultMessage.usage`, עלות מ-`total_cost_usd`, מספר קריאות = `num_turns` / ספירת `AssistantMessage`, כלים מבלוקי `ToolUseBlock`.
- **LOC:** `tools/count_loc.py` – שורות לא ריקות ולא הערות. ב-API לפי קובץ ב-`harness/`; ב-SDK לפי תגיות `# replaces: <x>`.

### כללי השוואה
- אותו מודל ואותו effort, מוגדרים ב-`scenario.json` ונקראים משם בשתי הגרסאות.
- `requirements.txt` עם גרסאות נעולות (`anthropic==…`, `claude-agent-sdk==…`) – מתוך `pip freeze` אחרי ההתקנה.
- `main.py` מאפס מצב בתחילת כל ריצה (`--fresh` כברירת מחדל).

---

## 7. בדיקות offline — `tests/`

ללא מפתח, עם `FakeClient` שמחזיר תשובות מתוסרטות.

| קובץ | מה נבדק |
|---|---|
| `test_shared_tools.py` | `group_errors` מנרמל ומקבץ נכון; ignore מסנן; פלט מתחת לתקרה; `ToolError` על קובץ חסר |
| `test_memory.py` | upsert דורס ומחזיר `replaced`; `forget`; שמירה וטעינה מהדיסק |
| `test_loop.py` | FakeClient: תשובה עם **2** tool_use → הודעת user אחת עם 2 tool_result; עצירה ב-`end_turn`; `max_iterations` |
| `test_tools_errors.py` | כלי לא מוכר / exception → `is_error: true` |
| `test_history.py` | append-only: טעינה מחדש מחזירה אותן הודעות; compaction מוסיף רשומה ולא מוחק |
| `test_context.py` | memory.py בוחר רק רשומות רלוונטיות; אין לוג גולמי ב-messages |
| `test_caching.py` | cache_control במקומות הנכונים, ≤ 4 |
| `test_tokens.py` | חישוב עלות ואחוז cache מ-usage מדומה |
| `test_checks.py` | הבדיקות C1–C9 על memory.json מדומה (pass וגם fail) |
| `test_sdk_tools.py` | ה-wrappers של `@tool` קוראים ל-shared ומחזירים is_error (בלי להריץ את Claude Code) |

הרצה: `python -m pytest tests -q`

---

## 8. מבנה סופי

```
logsum-<השם-שלך>/
  shared/        log_tools.py memory_store.py schemas.py checks.py data/
  API/           main.py agent.py harness/{loop,tools,history,memory,context,compaction,caching,tokens}.py
  SDK/           main.py agent.py tools.py CLAUDE.md
  tests/
  tools/count_loc.py
  scenario.json
  results/       api.json sdk.json
  requirements.txt
  .gitignore     # history/, memory.json, .env
  REPORT.md
```

---

## 9. סדר עבודה

1. **shared/**: יצירת לוגים סינתטיים, הכלים, memory_store, checks + בדיקות offline שלהם.
2. **API/harness**: tools → loop (עם FakeClient) → history → tokens → memory/context → caching → compaction.
3. **API/main.py**: הרצת התרחיש מול ה-API האמיתי, תיקון עד שהבדיקות עוברות.
4. **SDK/**: tools.py (@tool) → agent.py → main.py, אותו פורמט תוצאות.
5. **מדידה**: הרצה נקייה של שתי הגרסאות → `results/`.
6. **REPORT.md**.

---

## 10. שלד ל-REPORT.md

1. **תיאור הסוכן** וארבעת הנושאים (פסקה לכל אחד).
2. **טבלת השוואה:** API מול SDK – input / cache read / cache write / output, אחוז cache, קריאות למודל, עלות, זמן, בדיקות שעברו.
3. **שורות קוד** לכל חלק ב-harness (loop, tools, history, memory, context, compaction, caching, tokens), API מול SDK.
4. **איפה ה-SDK עלה יותר/פחות טוקנים ולמה** – השערות לבדוק: system prompt ותוספות של Claude Code מגדילים את ה-input הבסיסי; caching אוטומטי עשוי להיות טוב יותר; בלי הזרקת זיכרון רלוונטי המודל צריך לקרוא `recall` → קריאות נוספות.
5. **שליטה שאבדה ב-SDK** – מה בדיוק נכנס לקונטקסט, מיקום נקודות ה-cache, מתי ואיך compaction קורה, פורמט ההיסטוריה, ספירת טוקנים ברמת קריאה בודדת.
6. **מה הייתי בוחרת ולמה** – לסוכן הזה (כלים מעטים, זיכרון מובנה, הרבה דגש על קונטקסט קומפקטי) – לנמק לפי התוצאות בפועל.

---

## 11. הרשאות ואבטחה

- **API:** `ANTHROPIC_API_KEY` רק כמשתנה סביבה בטרמינל (`$env:ANTHROPIC_API_KEY="..."` ב-PowerShell). לא בקוד, לא ב-`.env` שנכנס ל-git.
- **SDK:** רץ על ה-login של Claude Code. לפני ההרצה: `Remove-Item Env:ANTHROPIC_API_KEY`, אחרת החיוב עובר למפתח.
- `.gitignore` כולל `memory.json`, `history/`, `.env`.
