# OccamDraft MVP

第一版提供：

- 驗證 `profile.json`。
- 使用 `playwright-cli` named session 登入 SUT。
- 對登入後頁面執行同 origin、有界 BFS。
- 保存原始 snapshot、頁面 metadata 與 `route-manifest.json`。
- 使用 Gemini API 從頁面證據產生新增、修改、刪除任務草稿。

## 安裝

```powershell
py -3.12 -m pip install -e ".[dev]"
playwright-cli install-browser
```

## 驗證 Profile

此命令只驗證結構，不要求環境變數已設定：

```powershell
occamdraft validate --profiles profiles/profile.example.json
```

## 探索

先設定 profile 引用的帳號密碼，再執行：

```powershell
$env:TIMEOFF_ADMIN_USERNAME = "admin@example.com"
$env:TIMEOFF_ADMIN_PASSWORD = "password"
occamdraft explore --profiles profiles/profile.example.json --sut timeoff --profile admin
```

輸出位於：

```text
artifacts/<run_id>/
  route-manifest.json
  .auth/<profile_id>.json
  evidence/<evidence_id>/
    snapshot.yml
    metadata.json
```

探索以 profile 的第一個 `start_routes` 登入後 final URL 作為首頁 root。每個 Route
與對應 `metadata.json` 都保存從首頁開始的完整 `navigation_path`。

Dropdown 路徑會拆成「點擊 menu toggle」與「點擊 menu item」兩步，例如：

```text
Click Settings in header
Click Reports in Settings menu
Click Allowance usage by time
```

每個 step 同時保存結構化 target/context 與可直接提供給 Gherkin draft 的
`instruction`。

Crawler 不會實際點擊新增、修改、刪除或提交按鈕。`logout`、刪除、核准、拒絕、
下載與備份等 URL 會被安全政策阻擋。

Route 以 redirect 後的 final canonical URL 去重。Query parameter 預設全部移除；只有
`exploration.include_query_keys` 明確列出的 key 會保留。原始 `snapshot.yml` 不改寫，
因此仍可追溯頁面當時實際顯示的連結。

## 產生 Gherkin 草稿

在 `.env` 放入 Gemini API key：

```text
GEMINI_API=...
```

針對探索結果產生草稿：

```powershell
occamdraft draft artifacts/<run_id>
```

輸出位於：

```text
artifacts/<run_id>/drafts/
  task01.json
  task02.json
  draft-tasks.json
  review.json
```

每個 task 會使用 OccamQA JSON-based Gherkin 格式，並優先產生新增、修改與刪除情境。

`review.json` 是人工審查工作單，格式如下：

```json
{
  "version": 1,
  "run_id": "timeoff-navigation-final",
  "sut_id": "timeoff",
  "items": [
    {
      "task_file": "task01.json",
      "task_id": "timeoff_draft_001",
      "type": "",
      "feedback": "",
      "draft": {
        "require_login": true,
        "page_url": "http://localhost:3102/users/add",
        "gherkin": {
          "feature": "...",
          "scenario": "...",
          "given": ["..."],
          "when": ["..."],
          "then": ["..."]
        }
      }
    }
  ]
}
```

`type` 可填 `accept`、`revise` 或 `remove`。若填 `revise`，請在 `feedback`
描述要如何修改草稿。

## 套用人工回饋

填完 `review.json` 後執行：

```powershell
occamdraft revise artifacts/<run_id>
```

輸出位於：

```text
artifacts/<run_id>/drafts/
  accepted/
    task01.json
    draft-tasks.json
  revised/
    task02.json
    draft-tasks.json
    review.json
    review-result.json
```

`accepted/` 是已通過審查的可用任務集合；`revised/` 是下一輪仍需審查的任務 queue。
若 `revised/` 沒有 `task*.json`，代表迭代流程結束。`remove` 的任務不會再輸出。

## 使用 ADK Agent

ADK agent 位於：

```text
agents/occamdraft_agent/
```

啟動 CLI 對話：

```powershell
adk run agents/occamdraft_agent
```

或啟動 Web UI：

```powershell
adk web --port 8000
```

可對 agent 說：

```text
幫我檢查 artifacts/timeoff-navigation-final 的狀態
幫我產生 artifacts/timeoff-navigation-final 的 draft
我已經填好 artifacts/timeoff-navigation-final/drafts/review.json，幫我套用 review
我已經填好 artifacts/timeoff-navigation-final/drafts/revised/review.json，幫我繼續套用
```

Agent 不會替你修改 `review.json`。你仍需自行打開 JSON，填入 `accept`、`revise`
或 `remove`；若填 `revise`，也要填 `feedback`。Agent 會在你填完後讀取並套用。
