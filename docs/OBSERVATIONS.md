# OBSERVATIONS

実機検証で得た知見の蓄積場所。設計 doc / コード / docs に反映済みの観察を、
- いつ
- 何を確認したか
- 一次資料（raw event の保存先や verify セッションの session_id 等）
- どの doc / file に反映したか

の 4 項目で残す。reproducible に追跡したい時の起点。

---

## 2026-05-15 — Phase A dev mode 実機 verify

### コンテキスト

`claude --plugin-dir ~/work/agent-output-tracer` で初回起動。`plugin.json` の `hooks` field 明示が
"Duplicate hooks file detected" を引き起こし最初は load 失敗、修正 commit 後に reload で全 hook 発火を確認。

### 一次資料

- `~/.claude/plugins/data/agent-output-tracer-inline/sessions/ba640ad4-5982-4601-8bed-69164fd10851/events.jsonl` (9 events、Read + Bash の 2 ターン session)
- 同 `metadata.json`
- `~/.claude/plugins/data/agent-output-tracer-inline/sessions/9afc8a3e-db72-4381-9d67-393f8fdcbf27/events.jsonl` (1 event のみ、load 失敗時の SessionEnd 単独)

### 観察

1. **UserPromptSubmit の field 名は `prompt` (NOT `user_prompt`)**
   - 設計 doc 付録 A の旧記述は推測ベース、実機と差異
   - 反映: `docs/DESIGN.md` 付録 A.2、`adapters/claude_code.py` UserPromptSubmit 分岐のコメント

2. **Stop の field 名は `last_assistant_message` (NOT `response_text`)**
   - `stop_reason` は来ない。代わりに `stop_hook_active: bool`
   - 反映: `docs/DESIGN.md` 付録 A.5、`adapters/claude_code.py` agent_response 分岐のコメント
   - 結果として replay 出力で `(end_turn)` ラベルは Claude Code では出ない（None になる）

3. **PostToolUse の `tool_response` は dict**
   - 例: `{"type": "text", "file": {"filePath": ..., "content": ..., "numLines": ...}}`
   - Bash の場合は `{"stdout": ..., "stderr": ..., "interrupted": bool, ...}`
   - 既に `_coerce_response` が dict → JSON.dumps 化対応していたので動作問題なし
   - 反映: `docs/DESIGN.md` 付録 A.4

4. **PostToolUse に `tool_use_id` / `duration_ms` あり**
   - 設計 doc に未記載だった
   - `tool_use_id` は `toolu_01...` 形式（Claude API tool_use block id）
   - Phase B の `trace` / `why` で pre↔post 厳密紐付けに活用予定
   - 反映: `docs/DESIGN.md` 付録 A.3 / A.4

5. **SessionEnd に `reason` field**
   - 観測値: `"prompt_input_exit"` (`/exit` での正常終了)
   - 他に `clear` / `logout` 等の enum がありそう（未観測）
   - 反映: `docs/DESIGN.md` 付録 A.6

6. **dev mode の data dir に `-inline` suffix**
   - `~/.claude/plugins/data/agent-output-tracer-inline/`
   - 永続 install 時の suffix 有無は Phase A-11 で再 verify
   - 反映: `docs/INSTALL.md` Verify 節、`docs/DESIGN.md` 付録 A.7

7. **session_id は UUID v4**
   - `ba640ad4-5982-4601-8bed-69164fd10851` 形式
   - Codex 側との互換考慮では「string とだけ仮定」を維持
   - 反映: `docs/INSTALL.md` Session id format 節

8. **`plugin.json` の `"hooks"` field は明示してはいけない**
   - Claude Code は `hooks/hooks.json` を auto-load する
   - 明示すると "Duplicate hooks file detected" で manifest load 失敗
   - 反映: `docs/DESIGN.md` §4.1、`.claude-plugin/plugin.json` / `.codex-plugin/plugin.json` から field 削除

9. **plugin load 失敗時でも SessionEnd 単独 fire の可能性あり**
   - hooks.json load エラーで他 hook 不発火だったが、`/exit` 時に SessionEnd だけ fire し空 session dir を残した
   - Claude Code の plugin loader が hook ごとに独立判定している可能性
   - 反映: `docs/DESIGN.md` 付録 A.6 末尾の注意書き

10. **adapter の forgiving 設計が救った**
    - `user_prompt` || `prompt`、`response_text` || `last_assistant_message` の両対応を「Codex 互換のため」と書いていたが、Claude Code 本体も同じ field 名だった
    - 結果として実機 verify 不足を吸収。lucky shot だが、Phase A-2 の TDD で偶発的に正しいガードを持てていた
    - 反映: `adapters/claude_code.py` の該当 fallback 箇所のコメントを「Codex 互換」→「Claude Code 本来の field 名」に書き換え

### 未決

- 永続 install (`claude plugin install <path>`) 時の data dir に `-inline` suffix が付くかどうか — Phase A-11 で `claude plugin install ~/work/agent-output-tracer` を実行して再 verify
- SessionEnd の `reason` 取りうる値の完全な enum — `clear` / `logout` 等の発生条件を別セッションで再現
- `permission_mode` が SessionEnd / UserPromptSubmit でも来るか — 実機 dump で SessionEnd / UserPromptSubmit に欠落していたが、別 permission_mode 時に再 verify

---

## 運用ルール

- 実機検証で「設計 doc / コードと違った」ことがあれば、ここに 1 ブロック追加する
- 反映先 (doc / code path) を明記する。後から「この観察はどこに反映されている？」を辿れるように
- 一次資料 (events.jsonl, metadata.json, session_id 等) を必ず書く。再現性のため
- 「未決」項目は次の verify trigger を書く（Phase 番号 or 条件）
- ここは log であって正本ではない。正本は `docs/DESIGN.md` / コード本体
