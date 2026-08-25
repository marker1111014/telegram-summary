# 設計文件:Telegram 群組摘要機器人 Vercel 部署版

- 日期:2026-08-26
- 原始碼:https://github.com/moalimir/Telegram-Group-Chat-Summarizer-Bot
- 狀態:已核准

## 1. 目標與背景

原版機器人使用 python-telegram-bot(PTB)的 `run_polling()` 常駐輪詢,並將訊息快取存在進程記憶體,無法部署到 Vercel serverless 環境。本專案將其改造為可部署到 Vercel 的 webhook 版本。

### 精簡範圍(使用者決定)

**保留:**
- `/summarize [N]` 指令(N 為要摘要的最近訊息數,預設 25、上限 200)
- `/start` / `/help` 說明文字
- 群組文字訊息快取(每聊天 500 則)
- Gemini AI 摘要(含安全設定)

**移除:**
- 60 秒使用者冷卻限速
- langdetect 語言偵測與 en/fa 雙語模板(改由 prompt 指示「以對話主要語言回覆」)
- 公開超級群組的訊息連結生成
- ADMIN_CHAT_ID 錯誤通知
- psutil 記憶體監控
- 快取清理排程(Redis TTL 取代)

## 2. 架構

```
Telegram ──webhook──▶ Vercel Function (api/webhook.py, FastAPI)
                          │ 驗證 X-Telegram-Bot-Api-Secret-Token header
                          ▼
                      PTB Application.process_update()
                          │
            ┌─────────────┼──────────────┐
            ▼             ▼              ▼
      一般群組文字訊息   /start        /summarize N
            │             │              │
            ▼             ▼              ▼
      寫入 Redis       說明文字     LRANGE 讀最後 N 則
                                    → Gemini 摘要 → 回覆群組
```

執行模式:**純 Webhook**(無本地 polling 模式;本地測試用 `vercel dev`)。

## 3. 專案結構(方案 A:模組化)

```
telegram_summary/
├── api/
│   └── webhook.py          # Vercel 進入點(FastAPI app + PTB 接線)
├── bot_core/
│   ├── __init__.py
│   ├── config.py           # 環境變數讀取與驗證
│   ├── cache.py            # Upstash Redis 訊息快取操作
│   ├── summarizer.py       # Gemini prompt 建構與 API 呼叫
│   └── handlers.py         # PTB handlers(/start、/summarize、訊息快取)
├── tests/
│   ├── test_cache.py       # mock Redis
│   ├── test_summarizer.py  # mock Gemini
│   └── test_handlers.py    # mock cache/summarizer
├── requirements.txt
├── vercel.json
├── .env.example
└── README.md               # 部署步驟文件
```

原版 `bot.py` 刪除(功能拆分至 `bot_core/` 各模組)。

## 4. 元件設計

### 4.1 api/webhook.py(Vercel 進入點)

- 模組層建立 PTB `Application` 單例:`ApplicationBuilder().token(TOKEN).updater(None).build()`,並註冊 handlers。
- 以 lazy flag 在首次請求時執行 `await app.initialize()` + `await app.start()`;warm instance 重複使用。
- FastAPI `POST /api/webhook`:
  1. 比對 `X-Telegram-Bot-Api-Secret-Token` header 與 `WEBHOOK_SECRET`,不符回 403。
  2. `Update.de_json(payload, app.bot)` 後交給 `app.process_update()`。
  3. 回 200(`{"ok": true}`)。
- Gemini 呼叫以 `asyncio.wait_for` 限時(預設 30 秒),逾時回覆使用者錯誤訊息。

### 4.2 bot_core/cache.py(Redis 快取)

| 項目 | 內容 |
|------|------|
| Client | `upstash_redis.Redis(url, token)` — HTTP-based,serverless 官方建議 |
| Key | `chat:{chat_id}:messages`(LIST) |
| 值 | JSON 字串:`{"message_id", "user_name", "username", "user_id", "text", "ts"}` |
| 寫入 | `RPUSH` → `LTRIM -500 -1` → `EXPIRE 604800`(每次寫入刷新 TTL) |
| 讀取 | `LRANGE chat:{id}:messages -N -1` |
| 清空 | 不需要(TTL 自然過期) |

函式介面:
- `cache_message(chat_id: int, msg: dict) -> None`
- `get_recent_messages(chat_id: int, n: int) -> list[dict]`

### 4.3 bot_core/summarizer.py(Gemini 摘要)

- SDK:`google-generativeai==0.8.5`(維持原版,降低改動風險),同步呼叫包在 `asyncio.to_thread`。
- 預設模型改為 **`gemini-2.0-flash`**(原版 `gemini-1.5-flash` 已被 Google 淘汰),可用 `GEMINI_MODEL_NAME` 覆蓋。
- 安全設定沿用原版四類 `HARM_CATEGORY_*`,`BLOCK_MEDIUM_AND_ABOVE`。
- 單一通用 prompt:
  - 角色:Telegram 群組對話摘要助理
  - 要求:主題式摘要(重點討論、決議、問題、待辦)、粗體標題與強調、提及貢獻者用 `@username`、不引用 message ID
  - 指示「以對話的主要語言撰寫摘要」(取代 langdetect)
- 處理 `BlockedPromptException`、API 錯誤、逾時,回覆友善錯誤文字。

### 4.4 bot_core/handlers.py(PTB handlers)

- `start_command`:說明 `/summarize [N]` 用法與限制。
- `summarize_command`:解析參數(預設 25、上限 200)→ 讀 Redis → 呼叫 summarizer → 先送「處理中」訊息再編輯為摘要。摘要長度超過 4096 字元時截斷加刪節號。
- `handle_message`:過濾條件同原版(`filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS & ~filters.VIA_BOT`),組 dict 後寫入 Redis;寫入失敗僅記 log,不影響使用者。
- `error_handler`:記 log。

## 5. 環境變數

| 變數 | 必填 | 預設 | 來源 |
|------|------|------|------|
| `TELEGRAM_BOT_TOKEN` | ✓ | — | 手動加入 Vercel |
| `GEMINI_API_KEY` | ✓ | — | 手動加入 Vercel |
| `UPSTASH_REDIS_REST_URL` | ✓ | — | Marketplace 整合自動注入 |
| `UPSTASH_REDIS_REST_TOKEN` | ✓ | — | Marketplace 整合自動注入 |
| `WEBHOOK_SECRET` | ✓ | — | 自行產生隨機字串 |
| `GEMINI_MODEL_NAME` | ✗ | `gemini-2.0-flash` | 選填 |
| `API_TIMEOUT_SECONDS` | ✗ | `30` | 選填 |

缺少必填變數時,config 模組在 import 階段即 raise 明確錯誤訊息(Vercel function log 可見)。

## 6. vercel.json

```json
{
  "functions": {
    "api/webhook.py": { "maxDuration": 60 }
  }
}
```

Python runtime 由 requirements.txt 自動偵測,不需額外 build 設定。

## 7. 依賴異動(requirements.txt)

**保留:** `python-telegram-bot==21.2`(移除 `[ext]`,JobQueue 已不需要)、`google-generativeai==0.8.5`、`python-dotenv==1.0.1`(本地 `.env` 用)、`httpx`(PTB 傳遞依賴)

**新增:** `upstash-redis`、`fastapi`

**移除:** `langdetect`、`psutil`、明確釘選的 `google-api-core`

**開發用(dev):** `pytest`、`pytest-asyncio`

## 8. 部署流程(寫入新 README)

1. 推上 GitHub 儲存庫。
2. Vercel → Add New Project → 匯入該 repo(Python 自動偵測)。
3. 專案 Storage 頁 → 加入 Upstash Redis(Marketplace)並連結 → 環境變數自動注入。
4. Settings → Environment Variables 加入 `TELEGRAM_BOT_TOKEN`、`GEMINI_API_KEY`、`WEBHOOK_SECRET` → Redeploy。
5. 註冊 webhook:
   ```
   https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<project>.vercel.app/api/webhook&secret_token=<WEBHOOK_SECRET>&allowed_updates=["message"]
   ```
6. BotFather 關閉 Group Privacy(原版需求不變)。
7. 測試:邀請 bot 入群 → 發數則訊息 → `/summarize`。

## 9. 測試策略

- 單元測試(pytest + mock):cache 操作、prompt 建構、handler 參數解析與錯誤路徑。不打真實 Redis/Gemini/Telegram API。
- 本地整合:`vercel dev` 載入 `.env`,以 curl 模擬 Telegram update(帶 secret token header)確認 403/200 行為。
- 端對端(部署後):真實群組發訊息 → `/summarize` 驗證摘要回覆。

## 10. 已知限制

- Vercel Hobby plan `maxDuration` 上限 60 秒;Gemini 回應逾時設 30 秒,留有餘裕。
- Serverless 冷啟動(PTB + Gemini SDK import)可能造成首次回應延遲數秒。
- 快取只涵蓋 bot 收到 webhook 期間的訊息;Vercel 函式閒置回收不影響 Redis 資料,但 Telegram 端若取消 webhook 則收不到訊息。
- 摘要品質取決於 Gemini 模型與對話內容,與原版相同。
