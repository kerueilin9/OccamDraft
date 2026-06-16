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
```

每個 task 會使用 OccamQA JSON-based Gherkin 格式，並優先產生新增、修改與刪除情境。
