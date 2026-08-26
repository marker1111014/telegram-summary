# Telegram Group Summarizer Bot(Vercel 版)

使用 Google Gemini AI 摘要 Telegram 群組最近訊息的機器人,部署於 Vercel serverless,快取存於 Upstash Redis。

## 功能

- `/summarize [N]`:摘要最近 N 則訊息(預設 25,上限 200)
- `/start` / `/help`:使用說明
- 自動快取群組文字訊息(每群最多 500 則,保留 7 天)
- 以對話主要語言產生主題式摘要

## 架構

```
Telegram ──webhook──▶ Vercel Function (api/webhook.py, FastAPI)
                          ▼
                      PTB process_update()
              ┌───────────┼────────────┐
        文字訊息 → Redis  /start     /summarize N → Gemini → 回覆
```

## 部署步驟

### 1. 推上 GitHub

```bash
git push origin vercel-deployment
```

### 2. Vercel 匯入專案

1. 到 [Vercel Dashboard](https://vercel.com/dashboard) → **Add New... → Project**
2. 匯入你的 repo(Python 會自動偵測)
3. 建議在 Settings → Environment Variables 加上 `PYTHON_VERSION=3.13`(與本地開發版本一致;python-telegram-bot 22.8 需 Python ≥3.9)

### 3. 加入 Upstash Redis

1. 專案的 **Storage** 分頁 → **Marketplace** → 選 **Upstash Redis**
2. 選方案(Free 即可)並連結到本專案
3. 完成後 `UPSTASH_REDIS_REST_URL` 與 `UPSTASH_REDIS_REST_TOKEN` 會自動注入

### 4. 設定環境變數

Settings → Environment Variables 加入:

| 變數 | 說明 |
|------|------|
| `TELEGRAM_BOT_TOKEN` | 向 [@BotFather](https://t.me/BotFather) 取得 |
| `GEMINI_API_KEY` | 向 [Google AI Studio](https://aistudio.google.com/app/apikey) 取得 |
| `WEBHOOK_SECRET` | 自行產生的隨機字串,例如 `openssl rand -hex 32` |

選填:`GEMINI_MODEL_NAME`(預設 `gemini-3.6-flash`)、`API_TIMEOUT_SECONDS`(預設 30)、`GEMINI_SAFETY_THRESHOLD`(預設 `BLOCK_ONLY_HIGH`,可設 `BLOCK_NONE`)、`SUMMARY_AUTO_DELETE_SECONDS`(預設 30,摘要自動刪除秒數)、`SUMMARIZE_COOLDOWN_SECONDS`(預設 60,每群 /summarize 冷卻與併發互斥秒數)。

加完後執行一次 **Redeploy**。

### 5. 註冊 Telegram Webhook

```bash
curl "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=https://<your-project>.vercel.app/api/webhook&secret_token=<WEBHOOK_SECRET>&allowed_updates=%5B%22message%22%5D"
```

成功的回應:`{"ok":true,"result":true,"description":"Webhook was set"}`

### 6. BotFather 設定

向 [@BotFather](https://t.me/BotFather):`/mybots` → 選你的 bot → **Bot Settings → Group Privacy → Turn off**(必須,否則收不到群組訊息)。

### 7. 測試

1. 把 bot 加進群組
2. 讓大家發幾則訊息
3. 送出 `/summarize`(或 `/summarize 100`)

## 本地開發

```bash
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env   # 填入實際值
python -m pytest       # 單元測試
vercel dev             # 本地跑 serverless(curl 打 http://localhost:3000/api/webhook 測試)
```

## 限制

- 只能摘要 bot 上線期間收到的訊息(快取存 Redis,保留 7 天)
- Hobby plan 函式上限 60 秒;Gemini 呼叫限時 30 秒
- 冷啟動時首次回應可能延遲數秒
