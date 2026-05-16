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

---

## 2026-05-15 — Phase A-11 GitHub 公開準備時の install フロー verify

### コンテキスト

GitHub repo `itosdad/agent-output-tracer` 公開準備中。設計 doc §14.3 に「GitHub repo 直接 (`claude plugin install <git-url>`)」と書いてあったが、公式 docs verify で**そのコマンドは存在しないこと**が判明。claude-code-guide subagent 経由で公式 docs 引用を取得。

### 一次資料

- https://code.claude.com/docs/en/discover-plugins.md §Install plugins
- https://code.claude.com/docs/en/plugin-marketplaces.md §Marketplace schema / Plugin sources / Version resolution
- https://code.claude.com/docs/en/plugins-reference.md §Version management

### 観察

1. **`claude plugin install <git-url>` は存在しない**
   - 公式 install フローは **2 段階**: `/plugin marketplace add owner/repo` → `/plugin install plugin-name@marketplace-name`
   - 反映: `docs/DESIGN.md` §14.3 を訂正、`docs/INSTALL.md` の GitHub install 節を marketplace flow に書き換え

2. **同 repo 内 plugin への source 指定は相対パス `"./"` でよい**
   - `marketplace.json` の `plugins[].source` は `string | object` の union
   - 同 repo の plugin を指す最小形は `"source": "./"` （repo root 解決、`.claude-plugin/` 配下ではない点に注意）
   - 反映: `.claude-plugin/marketplace.json` 新規追加

3. **marketplace.json の最小必須 fields**
   - top-level: `name` (kebab-case) / `owner` (object with `name` required) / `plugins` (array)
   - plugins entry 必須: `name` / `source`
   - 反映: `.claude-plugin/marketplace.json`

4. **version 解決順は `plugin.json` > `marketplace.json` > git SHA**
   - 両方に version を書くと plugin.json が silent に勝つ（公式 docs に warning あり）
   - 本 plugin は `plugin.json` のみで version 管理する方針
   - 反映: `docs/DESIGN.md` §14.3 Update flow

### 未決

- **marketplace-less 直接 install (`/plugin add owner/repo` 等) があるか** — 公式 docs 上未確認。Phase A-11 実機 verify 推奨だが現状の marketplace flow で目的達成できるので低優先

---

## 2026-05-16 — Claude Code が `permission_mode` を全イベントに送るようになり engine 誤判定

### コンテキスト

v0.7.0 で導入した `hooks/_runner.py::_detect_engine` は「`permission_mode` フィールドが
ある = Codex」というヒューリスティクスを使っていた。当時 Codex 側 schema にだけ存在
していたフィールドだったため。しかし v0.16.x 期間に Claude Code も全イベントに
`permission_mode: "auto"` を載せるようになり、すべての Claude Code event が
**Codex engine と誤判定 → codex adapter で正規化**されるようになっていた。

### 一次資料

- `~/.claude/plugins/data/agent-output-tracer-itosdad-agent-output-tracer/sessions/781ff3fa-9a21-4107-ad31-d089ecd1ee56/events.jsonl`
- 40 件すべての `agent_response` event の `raw_event` keys:
  `['cwd', 'hook_event_name', 'last_assistant_message', 'permission_mode', 'session_id', 'stop_hook_active', 'transcript_path']`
- `hook_event_name` は CamelCase の `Stop` → Claude Code、それでも `permission_mode` 持ち

### 観察

1. **見かけ上は壊れていないが engine field が全件 codex に固定されていた**
   - 両 adapter が `last_assistant_message` を読むため `agent_response_text` は populate されていた
   - しかし `metadata.engine = "codex"` が初回イベント時に焼き付き、theme auto-detect、
     anomaly counters、tool mix の engine 別集計が全部壊れていた

2. **真に堅牢な discriminator は `hook_event_name` の casing**
   - Codex: snake_case (`stop`, `pre_tool_use`)
   - Claude Code: CamelCase (`Stop`, `PreToolUse`)
   - フィールドの有無で判定すると engine 側仕様変更で誤判定が起きるが、casing は
     両 engine とも歴史的に動かしていない

3. **反映: v0.16.1 で casing を一次シグナルに変更、`permission_mode` は tail fallback に降格**
   - `hooks/_runner.py::_detect_engine`
   - `tests/integration/test_codex_hook_scripts.py::test_engine_detection_claude_payload_with_permission_mode`

---

## 2026-05-16 — Stale `metadata.engine` が Timeline theme を狂わせる

### コンテキスト

v0.16.1 の engine detector 修正後も、それ以前に記録された session の
`metadata.json` には誤判定の名残で `engine: "codex"` が焼き付いたまま。
`core/recorder.py` は metadata.engine を初回イベント時に一度だけ書き、以後更新しない
仕様なので、修正後も古い session の metadata.engine は永久に間違ったまま残る。

`tui/screens/timeline.py::_sync_theme_to_engine` が metadata.engine を読んでいたため、
Claude Code session の Timeline を開くたびに毎 reload で theme が Codex に強制
切替され、user が `t` で salmon を選んでいても上書きされていた。

### 観察

1. **metadata は first-write-wins。誤った値は永続化する**
   - 後から rebuilt したり migration したりする経路は現状ない
   - 同等の問題は engine 以外のフィールドにも潜在しうる

2. **theme 判定は metadata でなく events から行うのが正しい**
   - `tui/screens/timeline.py::_majority_engine(events)` を新設、events 配列から
     多数決で engine を決定。stale metadata の影響を受けない
   - 反映: v0.16.2

3. **`user_theme_override` flag は別の話**
   - 手動 `t` 切替の保護のために v0.15.0 で導入済。今回の修正と直交

---

## 2026-05-16 — TUI alignment が画面中央寄せになる症状

### コンテキスト

Stats / Doctor / Trace / Search / Config のような短い content を持つ screen で、
body 部分が viewport の縦中央に寄って表示されていた。Timeline のような full-height
screen は問題なし。

### 観察

1. **Textual の Container default は短い content の場合に縦中央寄せになる**
   - 明示的に `align: left top` を指定しないと viewport の中央に置かれる
   - long content では `height: 1fr` が効くので問題が表面化しない

2. **反映: v0.16.2 で `tui/themes/base.tcss` の `AOTScreen > .body` と nested
   `Vertical` wrapper に `align: left top; content-align: left top;` を明示**

---

### 運用ルール

- 実機検証で「設計 doc / コードと違った」ことがあれば、ここに 1 ブロック追加する
- 反映先 (doc / code path) を明記する。後から「この観察はどこに反映されている？」を辿れるように
- 一次資料 (events.jsonl, metadata.json, session_id 等) を必ず書く。再現性のため
- 「未決」項目は次の verify trigger を書く（Phase 番号 or 条件）
- ここは log であって正本ではない。正本は `README.md` / `docs/TUI.md` / コード本体
  （`docs/DESIGN.md` / `docs/DESIGN_FORENSIC_UX.md` は historical baseline）
