---
title: agent-output-tracer — AI Agent Session Forensic Debugger (設計版)
plugin_name: agent-output-tracer
target_repo: ~/work/agent-output-tracer/
intended_engines:
  - Claude Code (公式 plugin 機構 → 主軸実装)
  - Codex CLI (compatible 実装、Phase C で対応)
distribution_model: standalone plugin package（host repo に install されるが host repo の構造に依存しない汎用 plugin）
date: 2026-05-14
author: Claude (claude-opus-4-7, 1M context)
status: design draft (実装着手前、他セッションへ引継ぎ可能な粒度で記述)
primary_sources:
  - Claude Code Hooks 公式 docs: https://code.claude.com/docs/en/hooks.md
  - Claude Code Plugins 公式 docs: https://code.claude.com/docs/en/plugins.md
  - Claude Code Plugins Reference: https://code.claude.com/docs/en/plugins-reference.md
  - Claude Code Settings: https://code.claude.com/docs/en/settings.md
verification_dates:
  - Claude Code plugin / hooks 仕様: 2026-05-14 (claude-code-guide subagent 経由)
  - Codex hook event 構造: 2026-05-14 (host repo の既存実装からの実測)
  - Codex 公式 hooks docs verify: 2026-05-14 〜 2026-05-15 (general-purpose subagent 経由、OpenAI 公式 docs `developers.openai.com/codex/hooks` + generated schemas)
handoff_notes:
  - 本 doc は単独で読んで実装着手できる粒度を意図して書かれている
  - 他セッション・他 agent が引き継ぐ場合は §13 限界 + §11 実装計画を最初に確認
  - 主機能は §8 CLI コマンド一覧。implementation は §7 architecture と §6 config から
  - 設計判断の背景・経緯は §0.5（design rationale）と §修訂履歴 を参照
---

# ⚠ Historical baseline — Phase A–C design draft (2026-05-14)

This document is the **pre-implementation design** of the recorder
pipeline, hook contract, event schema, and CLI surface for Phase A–C.
It is preserved as the historical record of how the project was
scoped before code was written.

For the **current state**, refer to:

- [`README.md`](../README.md) — overview, screenshots, status table
- [`docs/TUI.md`](TUI.md) — TUI guide (the primary surface)
- [`CHANGELOG.md`](../CHANGELOG.md) — per-version diff

Implementation has evolved beyond this draft. Specifically:

- The engine detector (`hooks/_runner.py`) no longer keys off
  `permission_mode` — see CHANGELOG v0.16.1 / OBSERVATIONS for why.
- Timeline theme reads engine from events, not metadata — v0.16.2.
- Phase D shipped in full plus TUI Phase 1–4.A on top — see status
  table in README.

This document is not deleted because the §0.5 design rationale,
§1.2 non-goals, §2 design principles, and §9 safety guarantees are
still load-bearing for anyone reviewing PRs or contributing.

---

# 0. Executive Summary

## 0.1 一言で

**`agent-output-tracer`** は、AI agent (Claude Code / Codex 等) の session を完全に記録し、user が agent の出力に違和感を感じた時に「**何が、いつ、どの順序で、どの input から派生して agent の出力に至ったか**」を replay / query で追跡可能にする **issue-agnostic な forensic debugger plugin** である。

## 0.2 なぜ必要か

AI agent は誤った出力を出すことがある。原因は多岐に渡る：

- file の読み落とし / 読み過ぎ
- 別 namespace との混線
- 過去の routing 履歴に影響された誤判断
- Context Rot（attention 状態の劣化）
- skill / tool の誤選択
- user 指示の誤解
- hallucination (出力に source ない情報)

**user が違和感に気づいた時点で何が起きたか追跡できる仕組み**があれば、原因種別を事前に分類する必要はない。本 plugin は user の **「これおかしい、なぜ？」** に対する forensic 答えを提供する。

## 0.3 主機能（preview）

```bash
# 直近 session の timeline 再生
$ agent-output-tracer replay --session latest

# 違和感のある出力部分から逆引き
$ agent-output-tracer trace --session abc123 --output "DI コンテナを使い..."
# → 「DI コンテナ」という単語が初めて出現した event を特定
# → その前に agent が読了した files / user の prompts を表示

# 特定の tool 呼び出しの理由を query
$ agent-output-tracer why --session abc123 --event "Read(file_X) at 10:23:45"
# → 直前の user prompt / agent reasoning を表示

# user 指示 vs agent action の差分
$ agent-output-tracer diff --session abc123
# → user が指示していない action を強調

# session 内全文検索
$ agent-output-tracer grep --session abc123 --pattern "file X"

# 因果図 export
$ agent-output-tracer causal-graph --session abc123 --output ./graph.md
```

## 0.4 設計の特徴

1. **Issue-agnostic**: 違和感の種別（hallucination / rot / wrong tool / etc.）を事前分類しない。「**事実経路の再構築**」のみ提供
2. **User-driven**: plugin が proactive に「rot 起きてる」と判定しない。user が違和感を覚えた時点で query を投げる
3. **Mechanical record**: hook で session を完全記録、agent compliance に依存しない
4. **Read-only forensic**: agent 動作に介入せず、観測のみ
5. **Host repo 非汚染**: plugin data dir に閉じる、host repo を一切変更しない
6. **Engine-agnostic core**: Claude Code 主軸、Codex compatible

## 0.5 設計判断の rationale（なぜこの設計か）

本 plugin の主機能を「**自動検知**」ではなく「**forensic / debug**」に据えた判断には、棄却した代替案との比較がある。

| 観点 | 棄却された代替案（pattern 自動検知 plugin） | 本 doc の設計（forensic debugger） |
|---|---|---|
| 主機能 | 検知パターンで rot を自動検知 | session 完全記録 + 任意 query で原因 trace |
| 検知主体 | plugin が proxy で判定 | user が違和感に気づく、plugin は forensic data 提供 |
| issue 範囲 | Context Rot 限定 | 任意の agent 不具合（rot / hallucination / wrong tool / etc.）|
| 哲学的根拠 | rot の proxy detection | rot は内部状態で直接検知不可能、forensic recorder に徹する方が正直 |
| Pattern 検知（P-X 系）| main 機能 | **付録の副機能**（replay 時の anomaly hint として副次表示）|

棄却理由：**proxy 問題**。pattern 自動検知は「rot 兆候の proxy（同 file 重複 read 等）」を観測するが、proxy ≠ rot 本体（rot は LLM 内部の attention 状態）。proxy 単独では false positive / false negative を避けられず、「正確検知できる」とは謳えない。本 plugin は **「user の anomaly 検知 + plugin の forensic recorder」** に役割分担し、proxy の限界を受け入れた上で確かな価値（事実経路の再構築）を提供する設計に収束した。

## 0.6 完成形イメージ（user 視点）

```
[Day 1] $ claude plugin install ~/work/agent-output-tracer
✓ Installed agent-output-tracer v0.1.0

[Day 1 - Day N] user が agent を host repo で使う
  → plugin が裏で session を完全記録（user は意識しない）

[Day N+1] user: "今朝の agent 出力、なんか変だった..."
  $ agent-output-tracer replay --session 2026-05-15-am1
  
  [09:30:00] [user] "FooBar コンポーネントを実装して"
  [09:30:02] [agent] thinking...
  [09:30:03] [tool: Read] CLAUDE.md (12KB)
  [09:30:05] [tool: Glob] "src/**/*.tsx" → 23 files
  [09:30:08] [tool: Read] src/lib/di.ts (3KB)  ← ⚠️ user が指示してない file
  [09:30:12] [agent response] "FooBar.tsx を作成、DI コンテナで..."
  
  → user: "あー、DI を勝手に持ち出してきたのか。trace してみよう"
  
  $ agent-output-tracer trace --session 2026-05-15-am1 \
    --output "DI コンテナで"
  
  Output mentions "DI" first at 09:30:12
  Causal trail:
    - user prompt at 09:30:00: "FooBar コンポーネントを実装して" (no DI mention)
    - read CLAUDE.md at 09:30:03: ✗ no "DI" in content
    - read di.ts at 09:30:08: ✓ first source of "DI"
  
  Why was di.ts read?
    Glob "src/**/*.tsx" returned di.ts as result #14
    Agent picked it (reason not visible in hook data)
  
  Hypothesis: agent read di.ts speculatively after Glob, then 
              incorporated into design decision
  
  → user: "なるほど、Glob 結果から余計な file 読んだのか。CLAUDE.md
          に 'DI 使わない' を書こう、または agent prompt に明示しよう"
```

これが plugin の本質的価値。user は **「事実経路を見て自分で判断する」** ことができる。plugin は判断しない。

---

# 1. Plugin の目的と非目的

## 1.1 目的（Why this exists）

AI agent の出力に違和感を覚えた user が、**追加で agent と対話することなく**、**hook で記録された session データだけから** 何が起きたかを再構築できる仕組みを提供する。

具体的に：

| user の question | plugin が提供する答え |
|---|---|
| 「なぜ agent はこの file を読んだ？」 | その file が読まれた event、直前の user prompt / agent action、その file が Glob 結果か明示参照かを表示 |
| 「agent はいつこの情報を見た？」 | 該当 string を含む tool result の event timestamp、source file |
| 「user 指示と違うことをしているか？」 | user prompt 一覧と agent action 一覧の対照、user が触れていない対象への access を強調 |
| 「session のどこから挙動がおかしくなった？」 | session timeline の全体像、user が変な点を identify するための replay |
| 「この出力の根拠 file はどこ？」 | 出力に含まれる string の source（読了 file 内に存在するか、それとも hallucination 可能性）|

## 1.2 非目的（Out of scope）

| 非目的 | 理由 |
|---|---|
| 違和感の種類を自動分類する | user が違和感に気づいた時点で十分、種別は user の判断 |
| Context Rot などの特定 issue を自動検知する | proxy detection は不正確（§0.5 rationale 参照）。pattern 検知は **anomaly hint** として副次化 |
| agent 出力の正誤判定 | hook データだけでは「正しさ」は決定不能、人間判断に委ねる |
| agent 動作の block / modify | read-only forensic recorder。介入しない |
| host repo への書込 | plugin data dir に閉じる |
| LLM 内部状態の観測 | hook は外部 event のみ取得、attention 状態等は不可視 |
| session 跨ぎの長期挙動分析 | 各 session 内 forensic に focus、長期分析は外部 tool |
| 自動修正 / 推奨 | recorder であり advisor ではない |

## 1.3 想定 user

| user type | 利用シーン |
|---|---|
| 開発者 | agent が想定外の挙動 → debug |
| AI safety researcher | agent 挙動の経験的観察 |
| プロダクト team | agent-powered features の品質問題の root cause 調査 |
| OS / multi-skill repo 運用者 | 案件横断で agent を使う中での挙動追跡 |
| Audit / compliance | agent 出力の根拠 trace（regulatory 要件）|

## 1.4 何が plugin の強みか

本 plugin の強みは「**Context Rot を正確に検知できる**」ではない。proxy 検知の本質的限界により、それは原理的に不可能（§0.5 の rationale を参照）。本 plugin の強みは「**user が違和感を感じた瞬間、追加コストゼロで session 全体を mechanical に再生・query できる**」こと。

これは：

- **人間 = anomaly detector**（人間判断は any proxy より正確）
- **plugin = forensic recorder + query interface**（人間が知りたいことを mechanical に取り出す）

の役割分担で構成される。pattern 自動検知の proxy 問題（rot 兆候 ≠ rot）を回避し、user の判断力を活かす設計。

---

# 2. 設計原則

## 2.1 Issue-agnostic（種類分類しない）

| 原則 | 実装 |
|---|---|
| 違和感の事前分類しない | plugin に「hallucination 検知器」「rot 検知器」等の機能を main にしない |
| 全 event を均一に記録 | tool 呼び出し、user prompt、agent response すべて同 schema で保存 |
| query が user の語彙に合わせる | "なぜこの file を読んだ？" "いつこの情報を見た？" 等、自然言語的 query を CLI で expose |

## 2.2 User-driven（user の trigger で動作）

| 原則 | 実装 |
|---|---|
| plugin が proactive 通知しない | live alert は default off。plugin が「rot 起きてます」と能動通知しない |
| user の query 時にのみ分析 | hook は記録のみ、分析は CLI 経由で user 起動 |
| session list の dashboard を提供 | user が session を見つけやすくする `list` / `latest` コマンド |

## 2.3 Mechanical（agent compliance に依存しない）

| 原則 | 実装 |
|---|---|
| agent が emit する marker に依存しない | hook で得られる event のみで完結 |
| 全 tool call を捕捉 | matcher は全 tool 対応 (`Read|Glob|Grep|Edit|Write|MultiEdit|Bash`) |
| timestamp は plugin 側で打つ | agent self-reporting に依存しない |

## 2.4 Safe by default

| 原則 | 実装 |
|---|---|
| 例外 tolerant | 全 hook で try/except、agent 動作を絶対止めない |
| Read-only on observe | tool_input / tool_response を読むだけ、改変なし |
| Host repo 非汚染 | data write 先は `${CLAUDE_PLUGIN_DATA}` 配下のみ |
| Performance budget | PreToolUse < 10ms, PostToolUse < 15ms (content capture 含む) |
| Privacy / redaction | secret pattern (API key 等) を自動 mask、retention 期限切れで自動削除 |

## 2.5 Engine-agnostic core

| 原則 | 実装 |
|---|---|
| Hook event を normalized event に変換 | engine 別 adapter (`adapters/claude_code.py`, `adapters/codex.py`) |
| Detection / query は normalized event 上で動作 | engine 違いを isolation |
| 新 engine 追加は adapter 追加のみ | 将来の他 LLM tool 対応容易 |

---

# 3. 対応 engine と hook 仕様

## 3.1 Claude Code（主軸、公式仕様確認済）

Claude Code 公式 docs より（claude-code-guide subagent 経由で 2026-05-14 確認）：

### 3.1.1 全 hook event 共通 fields

> All hooks receive JSON with these fields:
> ```json
> {
>   "session_id": "abc123",
>   "transcript_path": "/path/to/transcript.jsonl",
>   "cwd": "/current/directory",
>   "permission_mode": "default|plan|acceptEdits|auto|dontAsk|bypassPermissions",
>   "hook_event_name": "EventName"
> }
> ```

### 3.1.2 採用する 5 hook 種別

forensic 完全記録のため以下を採用：

| hook | 役割 | キャプチャするもの |
|---|---|---|
| **`UserPromptSubmit`** | user 入力時 | user prompt 全文 + timestamp |
| **`PreToolUse`** | tool 呼び出し前 | tool_name + tool_input 全文 + timestamp |
| **`PostToolUse`** | tool 成功完了後 | tool_response + timestamp |
| **`Stop`** | agent 応答完了時 | response_text + stop_reason |
| **`SessionEnd`** | session 終了時 | session 統計の最終化 + GC trigger |

### 3.1.3 採用しない hook と理由

- `SessionStart`: 初の event を session start とみなす（独立 hook 不要）
- `StopFailure` / `PostToolUseFailure`: error 系は別 phase で対応
- `PermissionRequest`: 観測対象外（permission 自体は別仕組み）

### 3.1.4 hook の制御 flow

すべての hook で **exit 0 + 空 stdout** を返す（観測のみ、block しない）。例外時も silent exit 0。

## 3.2 Codex CLI（公式 spec 確認済、Phase C で実装）

### 3.2.1 公式 docs（一次資料）

- 公式 hooks docs: https://developers.openai.com/codex/hooks
- Plugin build docs: https://developers.openai.com/codex/plugins/build
- Changelog: https://developers.openai.com/codex/changelog
- Advanced config (feature flag): https://developers.openai.com/codex/config-advanced
- Generated schemas (ground truth wire format): https://github.com/openai/codex/tree/main/codex-rs/hooks/schema/generated

### 3.2.2 利用可能な hook event（公式 8 種）

公式 docs より：

| 階層 | event 名 | 発火タイミング | plugin 採用 |
|---|---|---|---|
| Session level | `SessionStart` | session 開始時（source enum: `startup` / `resume` / `clear`）| ◯（session 切替の検知に使用）|
| **(Session 終了 hook なし)** | — | — | 設計変更必要（後述）|
| Per-turn | `UserPromptSubmit` | user 入力時 | ◎（user prompt 全文取得可）|
| Per-turn | `Stop` | agent response 完了時 | ◎（agent response 取得 + session 単位グルーピング起点）|
| Per-tool | `PreToolUse` | tool 呼び出し前 | ◎（中核）|
| Per-tool | `PostToolUse` | tool 完了後（Bash / apply_patch / MCP のみ）| ◎（ただし制限あり、後述）|
| Per-tool | `PermissionRequest` | permission 要求時 | △（採用しない、観測対象外）|
| Compaction | `PreCompact` | session compaction 開始前（0.129+）| △（long-session 文脈で利用余地）|
| Compaction | `PostCompact` | session compaction 完了後（0.129+）| △（同上）|

> "`PreToolUse`, `PermissionRequest`, `PostToolUse`, `UserPromptSubmit`, and `Stop` run at turn scope." (公式 hooks docs)

### 3.2.3 共通 event input field（公式 generated schema より）

8 種すべての input が以下を required：

| field | 型 | 内容 |
|---|---|---|
| `hook_event_name` | string（snake_case、定数）| 各 event 識別 |
| `session_id` | string | session 識別子（format は公式仕様で「string」のみ規定、UUID は未明記）|
| `cwd` | string | 作業 directory |
| `model` | string | 使用モデル名 |
| `permission_mode` | enum | `default` / `acceptEdits` / `plan` / `dontAsk` / `bypassPermissions` |
| `transcript_path` | string \| null | session transcript |
| `turn_id`（turn-scoped 5 種のみ）| string | Codex 固有拡張 |

経験的観察との差異：

- **公式は `hook_event_name`（snake_case）のみ**。 `hookEventName`（camelCase）は **output 側**（`hookSpecificOutput.hookEventName`）でのみ使用。**`event` 単体表記は公式根拠なし** — defensive code の `event` 分岐は不要
- **`tool_input.command` が canonical**、**`tool_input.cmd` は公式根拠なし** — defensive 分岐は古い PR の名残

→ Codex adapter は **`hook_event_name` + `tool_input.command`** のみ前提で実装してよい。

### 3.2.4 PostToolUse の制限

> "`PostToolUse` runs after supported tools produce output, including Bash, `apply_patch`, and MCP tool calls. ... This doesn't intercept all shell calls yet... Similarly, this doesn't intercept `WebSearch` or other non-shell, non-MCP tool calls."

→ **Codex の Read 相当（内部の非 MCP 経路）は PostToolUse 発火しない可能性が高い**。Codex 側では tool_response 取得が Claude Code 比で **限定的**。設計上の影響：tool 結果 size 計測（Phase B 機能）は Codex 側で機能限定となる。

### 3.2.5 SessionEnd の不在 — 設計変更

公式 generated schema directory および公式 docs の event リストに **`SessionEnd` は存在しない**。Codex で session 終了 trigger は取れない。

**実装方針 (Phase C-5 着地点)**:

- `metadata.json` は `core/recorder.append_event` が **毎 event で再書き出し** するため、`ts_end` / `tool_calls_total` / counters は常に最新。明示的な session_end イベントが無くても、operator が `replay --session latest` した時点でその session の最終 state が見える。
- 「Stop + N 分 idle で擬似 session_end を合成する」 active な finalize loop は実装しない。recorder 側で十分 self-healing なため、追加コードの維持コストに見合わない。
- 必要なら下流で `metadata.ts_end` を観察すれば idle 判定はクライアント側で計算可能（query/state-at が既に提供）。

### 3.2.6 ask 未サポート（経験的観察と一致）

> "`permissionDecision: \"allow\"` and `\"ask\"`, legacy `decision: \"approve\"`, ... are parsed but not supported yet, so they fail open."

→ Codex side は **deny only**。本 plugin は read-only forensic なので ask/deny どちらも使わない（exit 0 + 空 stdout のみ）。本仕様は plugin 動作に直接影響しないが、host repo 側の他 Codex hook と並走する際の設計考慮事項。

### 3.2.7 Plugin 機構（公式仕様）

Codex 公式 plugin 機構：

```bash
# Marketplace plugin install
$ codex plugin marketplace add owner/repo
$ codex plugin marketplace add owner/repo --ref main
$ codex plugin marketplace add owner/repo --sparse PATH

# Local plugin
$ codex plugin marketplace add ./local-marketplace-root
```

**Plugin 構造**:
- `.codex-plugin/plugin.json` manifest（Claude Code の `.claude-plugin/plugin.json` 相当）
- `hooks` field で `./hooks/hooks.json` を指す
- `hooks` 省略時は `./hooks/hooks.json` が default で自動 load

**Plugin install 先**:
- `~/.codex/plugins/cache/$MARKETPLACE_NAME/$PLUGIN_NAME/$VERSION/`
- local plugin の `$VERSION` は `"local"`

**Marketplace 配置**:
- repo: `$REPO_ROOT/.agents/plugins/marketplace.json`
- personal: `~/.agents/plugins/marketplace.json`
- Claude 互換: `$REPO_ROOT/.claude-plugin/marketplace.json`

**Feature flag 必須**:

```toml
# ~/.codex/config.toml or project .codex/config.toml
[features]
codex_hooks = true   # 0.129+ は hooks = true でも可（alias）
```

→ これがないと hooks は **silently ignored**。Plugin install 手順で必須項目。

**Trusted project layer 制約**:

> "Project-local hooks load only when the project `.codex/` layer is trusted."

### 3.2.8 Codex native env var の確認状況

Claude Code の `${CLAUDE_PLUGIN_ROOT}` / `${CLAUDE_PLUGIN_DATA}` 完全相当の **Codex native 環境変数は公式 docs では未明示**。`openai/codex-plugin-cc` repo は `${CLAUDE_PLUGIN_ROOT}` を使うが、これは Claude 互換 layer 由来。

**plugin 実装方針**: 
- Codex install path `~/.codex/plugins/cache/$MARKETPLACE_NAME/$PLUGIN_NAME/$VERSION/` を直接使用、または `$HOME` + path 計算で plugin root を解決
- data 保存先は plugin root 配下の `data/` または `~/.codex/plugins/data/` 等（実機 verify 必要、Phase C-1 で確定）

### 3.2.9 version 依存性

- Hook 機構自体は 0.114 頃 merge
- 0.128: marketplace install / plugin-bundled hooks 整備
- 0.129: `PreCompact` / `PostCompact` 追加、`/hooks` TUI 追加、`hooks` feature flag alias
- 0.130: plugin details に bundled hooks 表示

**plugin の Codex version 要件**: 
- 推奨: **>= 0.128**（plugin-bundled hooks サポート）
- compaction 関連も使うなら: **>= 0.129**

### 3.2.10 経験的観察との差異 summary（Phase C 着手前 checklist）

| 項目 | 経験的観察 | 公式 spec | 対応 |
|---|---|---|---|
| `event` field 単体表記 | defensive 3 分岐 | **存在しない** | adapter で `hook_event_name` のみ前提に簡素化 |
| `tool_input.cmd` | defensive 2 分岐 | **存在しない** | adapter で `tool_input.command` のみ前提に簡素化 |
| `PreToolUse` 存在 | あり | あり ✓ | 一致 |
| `PermissionRequest` 存在 | あり | あり ✓ | 一致 |
| `PostToolUse` 存在 | 未確認 | あり（限定的）| Codex side は Bash / apply_patch / MCP のみ発火 |
| `Stop` 存在 | 未確認 | あり | 採用、turn 終了ごと発火 |
| `UserPromptSubmit` 存在 | 未確認 | あり（`prompt` field で全文取得可）| 採用 |
| `SessionStart` 存在 | 未確認 | あり（`source` enum）| 採用 |
| `SessionEnd` 存在 | 想定 | **なし** | Stop + session_id でグルーピング、または SessionStart `source="clear"` で擬似検知 |
| `session_id` field 存在 | 未確認 | あり（string、format 未規定）| 採用 |
| `turn_id` field | 未確認 | あり（Codex 固有、turn-scoped 5 種で required）| Codex adapter で normalized_event に optional `turn_id` として attach (Phase C-9 着地)。turn 単位 forensic を作る場合は events.jsonl から `turn_id` で groupBy する想定 |
| 両 engine の session_id 衝突 | 想定外 | spec は format 未規定 | 両 engine とも UUID 系を発行する慣例があり実衝突確率は事実上ゼロ。`sessions/<session_id>/` を engine prefix なしで共有する現行 layout を維持し、衝突時のみ operator が `--data-dir` を分けて運用すれば足りる（Phase C-8 着地） |
| Plugin 機構 | 未確認 | あり（`codex plugin marketplace add`）| 採用、§10.2 install 手順を更新 |
| `${CLAUDE_PLUGIN_ROOT}` 相当 env | 未確認 | **公式明示なし** | plugin root を path 計算で解決、Phase C-1 実機 verify |
| Feature flag `codex_hooks = true` | 未確認 | **必須**（無いと silently ignored） | install 手順で必須化 |
| ask 未サポート | 既知 | あり ✓（fail open）| 一致、影響なし（read-only forensic）|

## 3.3 Engine-agnostic interface

各 engine の event を統一 schema に正規化：

```python
normalized_event = {
    "engine": "claude-code" | "codex" | ...,
    "event_type": "user_prompt" | "pre_tool" | "post_tool" | "agent_response" | "session_end",
    "session_id": str,
    "ts": ISO 8601 with millisecond precision,
    "cwd": str,
    
    # event_type 別の主要 field
    "user_prompt_text": str | None,  # user_prompt
    "tool_name": str | None,         # pre_tool / post_tool
    "tool_input": dict | None,       # pre_tool
    "tool_response": str | None,     # post_tool
    "agent_response_text": str | None,  # agent_response
    "stop_reason": str | None,       # agent_response
    
    # 共通 derived
    "paths": list[str],              # tool_input から抽出
    "command": str | None,           # Bash 系
    
    "raw_event": dict,               # 元 event（debug 用）
}
```

各 engine adapter (`adapters/claude_code.py`, `adapters/codex.py`) が変換責任を負う。

---

# 4. Plugin パッケージ構造

```
~/work/agent-output-tracer/                         ← 独立 git repo
├── .claude-plugin/
│   └── plugin.json                                  ← manifest
├── hooks/
│   ├── hooks.json                                    ← hook registration (Claude Code 形式)
│   ├── user_prompt_submit.py
│   ├── pre_tool_use.py
│   ├── post_tool_use.py
│   ├── stop.py
│   └── session_end.py
├── adapters/
│   ├── __init__.py
│   ├── claude_code.py                                ← Claude Code event → normalized
│   └── codex.py                                       ← Codex event → normalized (Phase C)
├── core/
│   ├── __init__.py
│   ├── normalizer.py                                  ← normalized_event 生成
│   ├── recorder.py                                    ← session JSONL append
│   ├── indexer.py                                     ← per-session 検索 index 生成
│   ├── redactor.py                                    ← secret pattern mask
│   ├── path_utils.py
│   └── time_utils.py
├── query/                                              ← CLI 主機能
│   ├── __init__.py
│   ├── replay.py                                       ← timeline 再生
│   ├── trace.py                                        ← output から逆引き
│   ├── why.py                                          ← event の理由 query
│   ├── diff.py                                         ← user prompt vs agent action
│   ├── state_at.py                                     ← time T 時点の状態
│   ├── grep.py                                         ← 全文検索
│   ├── causal_graph.py                                 ← 因果図生成
│   ├── mentioned_but_not_read.py                       ← hallucination 候補抽出
│   └── list.py                                         ← session 一覧
├── analyzer/                                           ← 副次機能（anomaly hint patterns、replay 時に副次表示）
│   ├── __init__.py
│   ├── anomaly_hints.py                                ← replay 時の hint 出力
│   └── patterns.py                                     ← 汎用 anomaly patterns（同一 file 重複 read / long-session outlier / routing config thrash 等、§11 Phase B-8 参照）
├── cli/
│   ├── __init__.py
│   └── main.py                                         ← entry point dispatch
├── config/
│   ├── default.toml                                    ← default 設定
│   └── schema.json
├── codex/                                              ← Codex 用 setup (Phase C)
│   ├── config.toml.example
│   └── INSTALL_CODEX.md
├── tests/
│   ├── unit/
│   │   ├── test_normalizer.py
│   │   ├── test_recorder.py
│   │   ├── test_indexer.py
│   │   ├── test_redactor.py
│   │   ├── test_replay.py
│   │   ├── test_trace.py
│   │   ├── test_diff.py
│   │   └── test_grep.py
│   ├── integration/
│   │   ├── test_full_session_lifecycle.py
│   │   ├── test_trace_from_output.py
│   │   ├── test_diff_user_vs_agent.py
│   │   └── fixtures/
│   │       ├── claude_code_sessions/
│   │       └── codex_sessions/
│   └── conftest.py
├── data/                                                ← gitignored、${CLAUDE_PLUGIN_DATA} 連動
│   └── sessions/<session_id>/
│       ├── events.jsonl                                 ← append-only event 履歴
│       ├── metadata.json                                ← session metadata
│       └── index.json                                   ← 検索 index
├── docs/
│   ├── DESIGN.md                                        ← 本 doc を最終移植
│   ├── COMMANDS.md                                      ← CLI 詳細
│   ├── CONFIG.md                                        ← config の書き方
│   ├── INSTALL.md                                       ← install 手順
│   ├── PRIVACY.md                                       ← redaction / retention
│   └── EXAMPLES.md                                      ← debug workflow 例
├── README.md
├── LICENSE
├── CHANGELOG.md
├── pyproject.toml
├── .gitignore
└── .github/workflows/
    ├── test.yml
    └── lint.yml
```

## 4.1 `plugin.json` の最小例

```json
{
  "name": "agent-output-tracer",
  "version": "0.1.0",
  "description": "Universal AI agent session forensic debugger. Replay, trace, and query agent behavior when output looks wrong.",
  "author": {
    "name": "agent-output-tracer contributors"
  },
  "license": "MIT",
  "keywords": [
    "agent-debugging",
    "session-forensic",
    "ai-observability",
    "claude-code",
    "trace"
  ]
}
```

**`hooks` field を書いてはいけない**: Claude Code は `<plugin_root>/hooks/hooks.json` を自動 load する。`plugin.json` に `"hooks": "./hooks/hooks.json"` を明示すると "Duplicate hooks file detected" エラーで読み込み失敗する。`hooks` field は **標準位置以外の追加 hook ファイル**を参照する時にだけ使う（実機 verify 済、2026-05-15 dev mode 起動時に判明）。Codex 側も同じ規約と想定（Phase C で再 verify）。

## 4.2 `hooks/hooks.json` の例

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [{
          "type": "command",
          "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/user_prompt_submit.py\""
        }]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Read|Glob|Grep|Edit|Write|MultiEdit|Bash",
        "hooks": [{
          "type": "command",
          "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/pre_tool_use.py\""
        }]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Read|Glob|Grep|Edit|Write|MultiEdit|Bash",
        "hooks": [{
          "type": "command",
          "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/post_tool_use.py\""
        }]
      }
    ],
    "Stop": [
      {
        "hooks": [{
          "type": "command",
          "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/stop.py\""
        }]
      }
    ],
    "SessionEnd": [
      {
        "hooks": [{
          "type": "command",
          "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/session_end.py\""
        }]
      }
    ]
  }
}
```

---

# 5. データ schema

## 5.1 `events.jsonl` の event entry

各 hook が以下の形式で append（1 event = 1 行）：

```json
{
  "v": 1,
  "ts": "2026-05-14T10:23:45.123+09:00",
  "session_id": "abc123",
  "engine": "claude-code",
  "event_type": "pre_tool",
  "tool_name": "Read",
  "tool_input": {
    "file_path": "/Users/.../foo.md"
  },
  "paths": ["/Users/.../foo.md"],
  "cwd": "/Users/.../project"
}
```

event_type 別の追加 field：

```json
// user_prompt
{
  "event_type": "user_prompt",
  "user_prompt_text": "FooBar コンポーネントを実装して..."
}

// post_tool
{
  "event_type": "post_tool",
  "tool_name": "Read",
  "tool_response": "...",
  "result_bytes": 12345,
  "result_excerpt": "..."  // config で先頭 N 文字
}

// agent_response (Stop)
{
  "event_type": "agent_response",
  "stop_reason": "end_turn",
  "agent_response_text": "..."
}

// session_end
{
  "event_type": "session_end",
  "tool_calls_total": 42,
  "duration_seconds": 1234.5
}
```

## 5.2 `metadata.json`

```json
{
  "v": 1,
  "session_id": "abc123",
  "engine": "claude-code",
  "ts_start": "2026-05-14T10:20:00.000+09:00",
  "ts_end": "2026-05-14T10:45:30.000+09:00",
  "cwd": "/Users/.../project",
  "tool_calls_total": 42,
  "user_prompts_count": 3,
  "agent_responses_count": 5,
  "unique_files_read": 12,
  "total_bytes_read": 234567,
  "tags": []
}
```

## 5.3 `index.json`

検索高速化のための index：

```json
{
  "v": 1,
  "session_id": "abc123",
  "files_read": {
    "/Users/.../foo.md": [
      {"ts": "2026-05-14T10:23:45.123+09:00", "event_idx": 3},
      {"ts": "2026-05-14T10:30:12.456+09:00", "event_idx": 17}
    ]
  },
  "tools_used": {
    "Read": [3, 17, 21, 25],
    "Glob": [5, 8],
    "Bash": [11, 15]
  },
  "text_inverted_index": {
    // 簡易な keyword → event_idx mapping (Phase A は word level、Phase B で n-gram)
    "FooBar": [1, 12, 25],
    "DI": [17, 25]
  }
}
```

---

# 6. 設定（config）仕様

`${CLAUDE_PLUGIN_DATA}/config.toml`：

```toml
[plugin]
enabled = true
log_level = "info"

[capture]
# user_prompt の捕捉
user_prompt = "full"        # full | excerpt | off

# tool_input の捕捉粒度
tool_input = "full"          # full | excerpt | paths_only | off

# tool_response の捕捉粒度
tool_response = "excerpt"    # full | excerpt | size_only | off
tool_response_excerpt_chars = 2000  # excerpt 時の先頭文字数

# agent_response の捕捉
agent_response = "full"      # full | excerpt | off

# session_end の自動 GC
auto_gc_on_session_end = true

[retention]
# session JSONL の保持期間
sessions_full_days = 30      # full content 保持
sessions_metadata_days = 365 # metadata のみ保持
auto_archive_format = "gzip" # 30 日超は gz 圧縮

[redaction]
enabled = true
patterns = [
  # default: 一般的な secret pattern
  '(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*["\']?[\w\-]{16,}["\']?',
  'sk-[a-zA-Z0-9]{40,}',
  'ghp_[a-zA-Z0-9]{36,}',
  # user 追加
]
replacement = "[REDACTED]"

[anomaly_hints]
# replay 時の hint 表示（anomaly hint patterns、§11 Phase B-8 で実装）
enabled = true
show_repeated_read = true
repeated_read_threshold = 3
show_long_session = true
show_cross_namespace_bleed = false  # host-specific config
show_routing_thrash = true
routing_paths = ["CLAUDE.md", "AGENTS.md"]

[engine.claude_code]
enabled = true

[engine.codex]
enabled = false  # Phase C で enable
```

---

# 7. Architecture

## 7.1 Layer 1: Capture (hooks)

5 つの hook handler が各 event を normalize して `events.jsonl` に append：

```python
# hooks/user_prompt_submit.py の擬似コード
import json, sys, os
from adapters.claude_code import normalize_event
from core.recorder import append_event

def main():
    try:
        event = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    try:
        normalized = normalize_event(event, event_type="user_prompt")
        if normalized:
            append_event(normalized)
    except Exception:
        pass

    sys.exit(0)

if __name__ == "__main__":
    main()
```

その他 hook も同じ形（recorder.append_event に渡すだけ）。

## 7.2 Layer 2: Storage

`core/recorder.py`：

```python
import json
import os
from pathlib import Path

def append_event(normalized_event: dict) -> None:
    session_id = normalized_event["session_id"]
    data_dir = Path(os.environ["CLAUDE_PLUGIN_DATA"])
    session_dir = data_dir / "sessions" / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    
    events_file = session_dir / "events.jsonl"
    
    # redaction
    redacted = apply_redaction(normalized_event)
    
    # append
    with events_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(redacted, ensure_ascii=False) + "\n")
    
    # update metadata (best-effort)
    update_metadata(session_dir, redacted)
```

## 7.3 Layer 3: Query interface (CLI 主機能)

各 query は `events.jsonl` を load し、index で検索を高速化、結果を human-readable 形式で出力。

### 7.3.1 `replay` の擬似コード

```python
# query/replay.py
def replay(session_id: str, options: dict) -> None:
    events = load_events(session_id)
    metadata = load_metadata(session_id)
    
    print(f"Session: {session_id}")
    print(f"Started: {metadata['ts_start']}")
    print(f"Total events: {len(events)}")
    print()
    
    for event in events:
        ts = format_time(event["ts"])
        typ = event["event_type"]
        
        if typ == "user_prompt":
            print(f"[{ts}] [user] {truncate(event['user_prompt_text'], 80)}")
        elif typ == "pre_tool":
            print(f"[{ts}] [tool] {event['tool_name']}({format_input(event['tool_input'])})")
        elif typ == "post_tool":
            print(f"[{ts}]   ↳ result: {format_bytes(event['result_bytes'])}")
        elif typ == "agent_response":
            print(f"[{ts}] [agent] {truncate(event['agent_response_text'], 100)}")
        
        # anomaly hint (if enabled)
        if options.get("show_hints", True):
            hints = detect_hints(event, events)
            for hint in hints:
                print(f"          ⚠️ {hint}")
```

### 7.3.2 `trace` の擬似コード

```python
# query/trace.py
def trace(session_id: str, output_excerpt: str) -> None:
    events = load_events(session_id)
    
    # output_excerpt が初めて出現した agent_response を特定
    first_mention = find_first_event(events, lambda e: 
        e["event_type"] == "agent_response" and output_excerpt in e["agent_response_text"]
    )
    
    if not first_mention:
        print(f"Not found: '{output_excerpt}' in any agent response")
        return
    
    # その時点までに何が起きたかを表示
    prior_events = events[:events.index(first_mention)]
    
    print(f"Output '{output_excerpt}' first appeared at {first_mention['ts']}")
    print()
    print("Causal trail (prior events):")
    
    # 直前の user_prompt
    last_user_prompt = find_last_event(prior_events, lambda e: e["event_type"] == "user_prompt")
    if last_user_prompt:
        mentions = output_excerpt in last_user_prompt.get("user_prompt_text", "")
        print(f"  - user prompt: {last_user_prompt['ts']}: "
              f"{'✓ mentioned' if mentions else '✗ not mentioned'}")
    
    # 読了 file で output_excerpt を含むものを探す
    print("  - files read prior to this output:")
    for pe in prior_events:
        if pe["event_type"] == "post_tool" and pe["tool_name"] == "Read":
            response = pe.get("tool_response", "") or pe.get("result_excerpt", "")
            mentions = output_excerpt in response
            indicator = "✓ contains" if mentions else "✗ does not contain"
            path = pe.get("paths", [""])[0]
            print(f"      [{pe['ts']}] {path}: {indicator}")
    
    # hallucination 候補判定
    has_source = any(
        pe["event_type"] == "post_tool" and 
        output_excerpt in (pe.get("tool_response", "") or pe.get("result_excerpt", ""))
        for pe in prior_events
    )
    has_user_mention = last_user_prompt and output_excerpt in last_user_prompt.get("user_prompt_text", "")
    
    if not has_source and not has_user_mention:
        print()
        print(f"⚠️  HALLUCINATION CANDIDATE: '{output_excerpt}' has no source in "
              f"user prompts or tool results visible to agent")
```

### 7.3.3 `why` の擬似コード

```python
# query/why.py
def why(session_id: str, event_descriptor: str) -> None:
    """e.g., event_descriptor = 'Read(file_X) at 10:23:45'"""
    events = load_events(session_id)
    target = parse_event_descriptor(events, event_descriptor)
    
    if not target:
        print(f"Event not found: {event_descriptor}")
        return
    
    target_idx = events.index(target)
    prior = events[:target_idx]
    
    print(f"Event: {target['ts']} {target['tool_name']}({format_input(target['tool_input'])})")
    print()
    print("What came immediately before:")
    
    # 直前 3 event を表示
    for pe in prior[-3:]:
        print(f"  - [{pe['ts']}] {format_event_brief(pe)}")
    
    # 直前の user_prompt
    last_prompt = find_last_event(prior, lambda e: e["event_type"] == "user_prompt")
    print()
    print("Last user prompt before this event:")
    print(f"  [{last_prompt['ts']}] {last_prompt.get('user_prompt_text', '')[:200]}")
    
    # この path / target を含む直前 Glob 結果があれば
    target_path = (target.get("paths") or [""])[0]
    glob_origin = find_glob_that_returned(prior, target_path)
    if glob_origin:
        print()
        print(f"⚠️  This path appeared in a Glob result at {glob_origin['ts']}:")
        print(f"   {glob_origin['tool_input']}")
        print(f"   (agent picked this path from Glob results, no explicit user mention)")
```

### 7.3.4 `diff` の擬似コード

```python
# query/diff.py
def diff(session_id: str) -> None:
    events = load_events(session_id)
    
    user_prompts = [e for e in events if e["event_type"] == "user_prompt"]
    tool_calls = [e for e in events if e["event_type"] == "pre_tool"]
    
    # user prompt に含まれた reference (file path / 固有名詞) を抽出
    user_mentions = set()
    for up in user_prompts:
        text = up.get("user_prompt_text", "")
        user_mentions.update(extract_references(text))
    
    # tool call で agent が触った path を抽出
    agent_touches = set()
    for tc in tool_calls:
        agent_touches.update(tc.get("paths", []))
    
    # diff
    user_mentioned_but_agent_didnt = user_mentions - agent_touches
    agent_touched_without_user_mention = agent_touches - user_mentions
    
    print("User mentioned but agent did NOT access:")
    for ref in sorted(user_mentioned_but_agent_didnt):
        print(f"  - {ref}")
    
    print()
    print("Agent accessed without user mention:")
    for ref in sorted(agent_touched_without_user_mention):
        print(f"  - {ref}")
    
    print()
    print("(Note: agent may have legitimate reasons to read additional files, "
          "but each should be reviewable.)")
```

### 7.3.5 `state-at` の擬似コード

```python
# query/state_at.py
def state_at(session_id: str, time_str: str) -> None:
    target_ts = parse_time(time_str)
    events = load_events(session_id)
    events_until = [e for e in events if parse_time(e["ts"]) <= target_ts]
    
    # state 構築
    files_read = {}
    total_bytes = 0
    user_prompts = []
    
    for e in events_until:
        if e["event_type"] == "post_tool" and e.get("tool_name") == "Read":
            for p in e.get("paths", []):
                files_read[p] = files_read.get(p, 0) + 1
            total_bytes += e.get("result_bytes", 0)
        elif e["event_type"] == "user_prompt":
            user_prompts.append(e.get("user_prompt_text", ""))
    
    print(f"State at {time_str}:")
    print(f"  Files read so far: {len(files_read)} unique, "
          f"{sum(files_read.values())} total reads")
    print(f"  Total bytes from Read: {total_bytes:,}")
    print(f"  User prompts so far: {len(user_prompts)}")
    print()
    print("Top read files:")
    for path, count in sorted(files_read.items(), key=lambda x: -x[1])[:10]:
        marker = " ⚠️ repeated" if count >= 3 else ""
        print(f"  {count}x  {path}{marker}")
```

### 7.3.6 `grep` の擬似コード

```python
# query/grep.py
def grep(session_id: str, pattern: str, ignore_case: bool = False) -> None:
    events = load_events(session_id)
    flags = re.IGNORECASE if ignore_case else 0
    regex = re.compile(pattern, flags)
    
    for e in events:
        # event 内の文字列 fields を全部検索
        searchable = collect_searchable_text(e)
        for field_name, text in searchable.items():
            if regex.search(text):
                print(f"[{e['ts']}] {e['event_type']}.{field_name}: "
                      f"{highlight_match(text, regex)[:200]}")
```

### 7.3.7 `causal-graph` の擬似コード

```python
# query/causal_graph.py
def causal_graph(session_id: str, output_path: str) -> None:
    events = load_events(session_id)
    
    # mermaid graph 生成
    lines = ["```mermaid", "graph TD"]
    
    for i, e in enumerate(events):
        node_id = f"E{i}"
        label = format_event_short(e)
        lines.append(f"  {node_id}[\"{label}\"]")
    
    # 因果リンク (各 event はその直前 event に接続、特定パターンは別経路)
    for i in range(1, len(events)):
        lines.append(f"  E{i-1} --> E{i}")
        
        # 直前 Glob の結果から後の Read への link
        cur = events[i]
        if cur["event_type"] == "pre_tool" and cur.get("tool_name") == "Read":
            target_path = (cur.get("paths") or [""])[0]
            glob_origin_idx = find_glob_idx_that_returned(events[:i], target_path)
            if glob_origin_idx is not None:
                lines.append(f"  E{glob_origin_idx} -.->|returned this path| E{i}")
    
    lines.append("```")
    Path(output_path).write_text("\n".join(lines))
```

### 7.3.8 `mentioned-but-not-read` の擬似コード

```python
# query/mentioned_but_not_read.py
def mentioned_but_not_read(session_id: str) -> None:
    """agent response に含まれた言及で、read 履歴にも user prompt にも source が見当たらないものを抽出"""
    events = load_events(session_id)
    
    # agent response から固有名詞・file path 候補を抽出
    candidates = set()
    for e in events:
        if e["event_type"] == "agent_response":
            candidates.update(extract_references(e.get("agent_response_text", "")))
    
    # source が存在しない候補を抽出
    suspicious = []
    for candidate in candidates:
        has_user_source = any(
            candidate in e.get("user_prompt_text", "")
            for e in events if e["event_type"] == "user_prompt"
        )
        has_read_source = any(
            candidate in (e.get("tool_response", "") or e.get("result_excerpt", ""))
            for e in events if e["event_type"] == "post_tool"
        )
        if not has_user_source and not has_read_source:
            suspicious.append(candidate)
    
    print("Hallucination candidates (mentioned in agent response, no visible source):")
    for s in sorted(suspicious):
        print(f"  - {s}")
```

## 7.4 Layer 4: Export

```python
# query/export.py
def export_trace(session_id: str, output_path: str, format: str = "markdown") -> None:
    # replay + causal graph + diff + mentioned-but-not-read を統合した forensic report
    pass
```

---

# 8. CLI コマンド一覧（user-facing surface）

## 8.1 主要コマンド

| コマンド | 機能 | 出力 |
|---|---|---|
| `replay --session <id>` | session の完全 timeline を表示 | text、event 順 |
| `trace --session <id> --output <text>` | 出力 text の初出を逆引き、prior causal trail を表示 | text、causal trail |
| `why --session <id> --event <descriptor>` | 特定 event がなぜ起きたかを query | text、直前 events |
| `diff --session <id>` | user mention vs agent action の差分 | text、表形式 |
| `state-at --session <id> --time <ts>` | 指定時点での session state snapshot | text |
| `grep --session <id> --pattern <regex>` | session 内全文検索 | text、match list |
| `causal-graph --session <id> [--output <path>]` | mermaid 因果図生成 | markdown、mermaid |
| `mentioned-but-not-read --session <id>` | hallucination 候補抽出 | text |

## 8.2 補助コマンド

| コマンド | 機能 |
|---|---|
| `list [--last <N>]` | 最近の session 一覧 |
| `latest` | 最新 session の id を出力 |
| `status` | plugin 全体の status |
| `export-trace --session <id> --output <path>` | forensic report 一括 export |
| `gc` | 期限切れ session の手動 GC |
| `config` | 現在の config 表示 |
| `tag --session <id> --tag <name>` | session に手動 tag を付ける（後で見つけやすく）|

## 8.3 セッション指定の便利記法

すべてのコマンドで `--session` は以下を accept：

- `latest` — 最新 session
- `<session_id>` — 完全な ID
- `<short_id>` — 先頭 8 文字 prefix
- `<tag>` — `tag` コマンドで付けた名前
- `latest-N` — N 個前の session
- ISO date `2026-05-14` — その日の session（複数あれば最新）

## 8.4 出力 format

```bash
$ agent-output-tracer replay --session latest --format text       # default
$ agent-output-tracer replay --session latest --format json       # 機械処理用
$ agent-output-tracer replay --session latest --format markdown   # report 用
```

---

# 9. 安全設計

## 9.1 Failure tolerance

すべての hook で：

```python
def main():
    try:
        event = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # 例外時は silent exit、agent 動作を絶対止めない

    try:
        # 実処理
        ...
    except Exception:
        pass

    sys.exit(0)
```

## 9.2 Host repo 非汚染

| 制約 | 実装 |
|---|---|
| Write 先制限 | `${CLAUDE_PLUGIN_DATA}/sessions/` 配下のみ、code review で enforce |
| Host repo path への write 禁止 | unit test で assertion |
| Host repo content の read | observation のみ、再 open 禁止 |

## 9.3 Privacy / Redaction

`redactor.py` は以下を自動 mask：

- API key pattern: `sk-...`, `ghp_...`, `eyJh...` JWT 等
- Password / token / secret を含む key=value
- user 追加 pattern（config に regex 追加）

redaction は `events.jsonl` 書き込み前に実施。元データは plugin 内にも残さない。

## 9.4 Retention / Auto GC

```python
# SessionEnd hook で trigger される（または `gc` コマンドで手動）
def gc():
    cutoff_archive = now - 30 days
    cutoff_delete = now - 365 days
    
    for session_dir in sessions_dir.iterdir():
        meta = load_metadata(session_dir)
        if meta["ts_end"] < cutoff_archive:
            # full content (tool_response 等) を strip、metadata + index は残す
            strip_content(session_dir)
        if meta["ts_end"] < cutoff_delete:
            # 完全削除
            shutil.rmtree(session_dir)
```

## 9.5 Performance budget

| hook | budget |
|---|---|
| UserPromptSubmit | < 5ms（text append のみ）|
| PreToolUse | < 10ms（event append + index update）|
| PostToolUse | < 15ms（excerpt 抽出 + redaction + append）|
| Stop | < 10ms（agent response append）|
| SessionEnd | < 200ms（metadata 確定 + GC trigger）|

実装時は単体テストで実測、超過したら async 化検討。

## 9.6 Plugin 破損時の影響

| 状況 | 影響 |
|---|---|
| hook 例外 | silent fail、agent 動作影響なし |
| hook script 消失 | Claude Code が warning、agent 動作継続（hook 不在扱い）|
| data dir 破損 | 次 session 起動時に新規作成、過去 session log は失われるが新規 session 継続 |
| config.toml 壊れた | default 設定で fallback |
| storage 容量逼迫 | best-effort write で silent skip（agent 影響なし）、`status` で警告 |

致命時の最終手段: `claude plugin disable agent-output-tracer` で即無効化。

---

# 10. インストールとアンインストール

## 10.1 Claude Code 向け

### Local 開発 install

```bash
$ git clone <repo-url> ~/work/agent-output-tracer
$ cd ~/work/agent-output-tracer
$ python3 -m venv .venv && source .venv/bin/activate
$ pip install -e .

# 永続 install
$ claude plugin install ~/work/agent-output-tracer

# または local dev (hot reload 用)
$ claude --plugin-dir ~/work/agent-output-tracer
```

### Production install (marketplace)

```bash
$ claude plugin install agent-output-tracer
```

## 10.2 Codex 向け（Phase C、公式 plugin 機構を使用）

### Local 開発 install

```bash
# 1. plugin repo を clone
$ git clone <repo-url> ~/work/agent-output-tracer

# 2. host repo の .codex/config.toml で feature flag を有効化（必須）
# または ~/.codex/config.toml（user level）
$ cat >> .codex/config.toml <<'EOF'
[features]
codex_hooks = true   # 0.129+ は hooks = true でも可（alias）
EOF

# 3. local marketplace 経由で install
$ codex plugin marketplace add ~/work/agent-output-tracer

# Plugin は ~/.codex/plugins/cache/$MARKETPLACE_NAME/$PLUGIN_NAME/local/ に install される
```

### Marketplace install（将来）

```bash
$ codex plugin marketplace add owner/agent-output-tracer
```

### Plugin 構造の Codex 用追加

`.codex-plugin/plugin.json` を `.claude-plugin/plugin.json` と同じ内容で配置（Claude Code と Codex の dual-distribution 構成）:

```
~/work/agent-output-tracer/
├── .claude-plugin/
│   └── plugin.json
├── .codex-plugin/
│   └── plugin.json           ← Claude 版と同形、name/version/hooks field 共通
├── hooks/hooks.json          ← 両 engine 共通定義（PostToolUse 等は engine 側で対応 event のみ発火）
├── adapters/
│   ├── claude_code.py
│   └── codex.py              ← Phase C 実装
└── ...
```

### Trusted project 制約

> "Project-local hooks load only when the project `.codex/` layer is trusted."

→ user level (`~/.codex/`) install を推奨。project level も可だが、project trust 設定が必要。

## 10.3 Disable / uninstall

```bash
$ claude plugin disable agent-output-tracer          # 一時無効
$ claude plugin uninstall agent-output-tracer --keep-data  # data 保持 uninstall
$ claude plugin uninstall agent-output-tracer        # 完全削除
```

## 10.4 動作確認

```bash
$ agent-output-tracer status

agent-output-tracer v0.1.0
Status: enabled
Data dir: ~/.claude/plugins/data/agent-output-tracer/
Sessions captured: 23 (last 30 days)
Storage used: 14.2 MB
Latest session: 2026-05-14-pm3 (started 30 min ago)
```

---

# 11. 実装計画（Phase A / B / C）

## Phase A: Claude Code 基本 forensic（最小動作）

| Sub-phase | 内容 | 成果物 |
|---|---|---|
| A-0 | repo 初期化、Python 3.11+ skeleton、`pyproject.toml`、CI workflow | git repo 作成 |
| A-1 | `plugin.json` + `hooks/hooks.json`、空 hook script で plugin install できることを verify | install / hook 配線確認 |
| A-2 | `adapters/claude_code.py` + `core/normalizer.py` で normalized_event 確立、unit test | normalize TDD pass |
| A-3 | `core/recorder.py` で events.jsonl append、`hooks/pre_tool_use.py` 実装 | session JSONL 生成 |
| A-4 | `hooks/user_prompt_submit.py` / `stop.py` / `session_end.py` 追加 | user prompt + agent response 捕捉 |
| A-5 | `core/redactor.py` で secret pattern mask | redaction 動作 |
| A-6 | `query/replay.py` 実装、`agent-output-tracer replay` で session 時系列表示 | **主機能 1** |
| A-7 | `query/list.py` + `query/latest.py` + session id resolution（latest / short_id / tag）| session navigation |
| A-8 | `query/grep.py` 実装、全文検索 | **主機能 2** |
| A-9 | `query/state_at.py` 実装、time T の state snapshot | 主機能 3 |
| A-10 | integration test、performance 実測、README v0.1.0 | reproducible install + 基本 forensic |

期間目安: 3-4 週間

## Phase B: 高度 forensic query

| Sub-phase | 内容 |
|---|---|
| B-1 | `core/indexer.py` で per-session search index 構築、grep を高速化 |
| B-2 | `query/trace.py` 実装、output 逆引き + causal trail |
| B-3 | `query/why.py` 実装、event の理由 query |
| B-4 | `query/diff.py` 実装、user vs agent action の差分 |
| B-5 | `query/mentioned_but_not_read.py` 実装、hallucination 候補抽出 |
| B-6 | `query/causal_graph.py` 実装、mermaid 因果図生成 |
| B-7 | `query/export.py` で forensic report 一括 export |
| B-8 | `analyzer/anomaly_hints.py` 実装、replay 時の anomaly hint 表示。検知対象 pattern は以下（host repo 構造に依存しない汎用形、閾値は config 駆動）:<br>(a) 同一 file の session 内 read 回数 ≥ N（default 3）<br>(b) routing config（CLAUDE.md / AGENTS.md 等の config_paths 設定）の session 内 read ≥ N（default 3）<br>(c) session の tool_calls_total が直近 30 日 90 percentile 超（long-session outlier）<br>(d) wrapper 系 path と core 系 path の連続 read（time delta < 60s、config drift 兆候）<br>(e) namespace boundary 跨ぎ read（`boundary_paths` 設定の異なる prefix を同 session で複数 read）<br>(f) protected path への Bash 経由 read（`cat`/`less`/`head` 等が protected_globs と組合せ）<br>(g) same-domain skill 並列発火（`skill_groups` 設定経由）|
| B-9 | 自動 GC（30 日 / 365 日）+ archive 機能 |

期間目安: 3-4 週間

## Phase C: Codex 対応（spec 確定済、実装段階）

**C-0 は完了**（2026-05-14〜15、general-purpose subagent 経由で公式 docs verify 済、§3.2 に反映）

| Sub-phase | 内容 |
|---|---|
| ~~C-0~~ | ~~Codex 公式 hook docs verify~~ → **完了**、結果は §3.2 |
| C-1 | `adapters/codex.py` 実装：8 hook event の normalize（SessionStart / PreToolUse / PostToolUse / UserPromptSubmit / Stop / PermissionRequest / PreCompact / PostCompact） |
| C-2 | `.codex-plugin/plugin.json` 配置、`hooks/hooks.json` を両 engine 共通形式に調整 |
| C-3 | Codex `[features] codex_hooks = true` 必須 + `codex plugin marketplace add` 手順を `docs/INSTALL.md` に追加 |
| C-4 | Codex native env var の実機 verify（`${CLAUDE_PLUGIN_ROOT}` 相当の解決方法）、必要なら adapter で path 計算 fallback |
| C-5 | `SessionEnd` 不在対応：Stop event + session_id グルーピング + idle timeout で擬似 session 終了検知 |
| C-6 | PostToolUse の Codex 制限（Bash / apply_patch / MCP のみ発火）への対応：機能限定の明示 |
| C-7 | Codex integration test fixtures（公式 schema directory から取得した sample event を使用）|
| C-8 | 両 engine 並走時の session_id 整合確認 |
| C-9 | `turn_id` field の活用検討（Codex 固有 turn 識別子、turn-level forensic に有用）|
| C-10 | Codex version 要件明示（>= 0.128 推奨、compaction event 使うなら >= 0.129）|

期間目安: 2-3 週間（C-0 短縮済）

## Phase D: 発展機能（optional）

- web UI viewer（plugin data dir を browse）
- AI agent integration（query 結果を別 LLM に渡して summary）
- pattern 学習 / user 行動 fingerprint
- marketplace 公開準備

---

# 12. テスト戦略

## 12.1 単体テスト

| 対象 | カバー |
|---|---|
| `core/normalizer.py` | engine 別 event → normalized、edge case |
| `core/recorder.py` | append / 連続書込 / 失敗時 silent |
| `core/indexer.py` | index 整合性、検索精度 |
| `core/redactor.py` | secret pattern mask、誤検出抑制 |
| `query/replay.py` | event 順序、format 出力 |
| `query/trace.py` | 出力初出特定、causal trail 構築 |
| `query/diff.py` | mention / touch 集合演算 |
| `query/grep.py` | regex match、case sensitivity |
| `analyzer/anomaly_hints.py` | hint 閾値 |

## 12.2 統合テスト

| シナリオ | 検証 |
|---|---|
| Claude Code event 流入 → events.jsonl 完成 | end-to-end |
| user prompt + tool calls + agent response の完全 session | replay で全 event 再現 |
| hallucination scenario（read source なしの言及）| `mentioned-but-not-read` 検出 |
| cross-namespace bleed | anomaly hint 表示 |
| 1000 events / session | performance budget 内 |
| Hook 例外発生 | agent 動作影響なし |
| Plugin disable 時 | hook fire しない |
| Codex event 流入（Phase C）| Claude Code と同等の captured |

## 12.3 性能テスト

```python
def test_capture_overhead():
    avg_ms = bench_full_session(num_events=1000)
    assert avg_ms < 15  # per-call budget
```

## 12.4 安全テスト

- `${CLAUDE_PLUGIN_DATA}` 外への write 試行 → fail
- redaction 失敗時の動作（secret が log に残らないか）
- 巨大 event JSON (10MB) → skip
- 故意の壊れた config.toml → default fallback

---

# 13. 限界・未確認事項

## 13.1 実装着手前に verify が必要

| 項目 | 解消手段 | 状態 |
|---|---|---|
| Claude Code `${CLAUDE_PLUGIN_ROOT}` / `${CLAUDE_PLUGIN_DATA}` の実 path | Phase A-1 実機 verify | **✓ 完了** (2026-05-15、dev mode で `~/.claude/plugins/data/agent-output-tracer-inline/` を実測。永続 install での suffix 有無は Phase A-11 で再 verify) |
| Claude Code PostToolUse `tool_response` の Read 結果フォーマット | Phase A-3 実機 verify | **✓ 完了** (dict 型 `{"type":"text","file":{...}}`、付録 A.4 反映) |
| Claude Code Stop hook `response_text` の completeness | Phase A-4 実機 verify | **✓ 完了** (実 field 名は `last_assistant_message`、`stop_reason` は非到来、付録 A.5 反映) |
| Claude Code UserPromptSubmit event field | Phase A-4 実機 verify | **✓ 完了** (実 field 名は `prompt`、付録 A.2 反映) |
| Claude Code SessionEnd event の field | Phase A-3 実機 verify | **✓ 完了** (`reason` field あり、付録 A.6 反映。`SessionEnd` 単独 fire の可能性も観測) |
| Codex hook 仕様 | Phase C-0 公式 docs | **完了**（2026-05-14〜15、§3.2 に反映）|
| Codex `session_id` の format（UUID v4 or 独自）| Phase C-1 実機 verify | 未 |
| Codex native plugin data env var（`${CLAUDE_PLUGIN_ROOT}` 相当）| Phase C-4 実機 verify | 未 |
| Codex schema の minor version 間破壊的変更 | Phase C-10 changelog 再確認 | 未 |
| Codex の WebSearch / Read 相当 tool での PostToolUse 発火可否 | Phase C-6 実機 verify | 未（公式 docs では非発火明示）|

## 13.2 設計上の制限

- **hook は agent 内部 context を観測できない**: attention 状態 / token-level focus は不可視
- **rot を「正確検知」できない**: anomaly hints は proxy、user 判断の補助
- **session 跨ぎ挙動**: 各 session 独立 forensic、long-running stateful agent は別設計
- **agent 出力の正誤判定**: hook データでは「正しさ」は決定不能、user / 外部 reviewer に委ねる
- **tool_response の content 取得**: large content は excerpt のみ default、full mode はストレージ・性能 trade-off
- **hallucination 検知の精度**: source visible なら検出可、agent の implicit knowledge との区別は不可能

## 13.3 運用で調整が必要

- capture 粒度（excerpt 文字数、tool_response の full / off）
- retention 期間（業務性質依存）
- redaction pattern（host repo 固有 secret format 追加）
- anomaly hints 閾値
- 巨大 session 時の query 性能（index 設計）

---

# 14. 公開リリース戦略

## 14.1 当面（Phase A-B）

- 個人 / 小規模 team による local install + GitHub install
- public repo (`itosdad/agent-output-tracer`)、信頼 user に共有
- feedback 収集

## 14.2 公式 Marketplace 公開（Phase C 後の選択肢）

公式 Claude Code marketplace に「登録された marketplace」として収録される場合の要件（公式 docs 未確認の部分は Phase C-Late で再確認）:

1. `plugin.json` 必須 metadata 完備
2. README に screenshot + workflow 例
3. CHANGELOG.md
4. GitHub Actions CI（test / lint）
5. semantic versioning

## 14.3 配布チャネル（実機 verify 済 / 2026-05-15）

**正しい install フロー**（公式 docs 確認済、claude-code-guide subagent 経由）:

```
/plugin marketplace add itosdad/agent-output-tracer
/plugin install agent-output-tracer@itosdad-agent-output-tracer
```

つまり「GitHub repo を marketplace として登録 → その中の plugin を install」の **2 段階フロー**。「`claude plugin install <git-url>` の 1 行 install」は公式コマンドとして**存在しない** (旧版 §14.3 の記述は推測誤り、訂正済)。

この 2 段階を成立させるため、本 repo は同時に:

- `.claude-plugin/plugin.json` — plugin 本体定義
- `.claude-plugin/marketplace.json` — この repo が 1 plugin だけ収録する個人 marketplace である宣言

の **両方** を root に配置する（`marketplace.json` の `plugins[0].source = "./"` で同 repo の plugin を指す）。

### Update flow

公式 version 解決順:
1. `plugin.json` の `version` field
2. `marketplace.json` plugin entry の `version` field（plugin.json と齟齬したら plugin.json が silent に勝つので片方に集約）
3. git commit SHA

本 plugin は `plugin.json` の `version` を semver で明示 (`"0.1.0"` 等) し、release ごとに bump + git tag (`v0.1.0`) を打つ運用。user 側 update は `/plugin update agent-output-tracer@itosdad-agent-output-tracer`。

### dev mode との関係

dev mode (`claude --plugin-dir ~/work/agent-output-tracer`) は marketplace.json を経由せず source path 直参照。`/reload-plugins` で commit を即反映可能、version bump 不要。本番運用 (`/plugin marketplace add`) と排他。

---

# 付録 A: Claude Code hook event schema（実機 verify 済、2026-05-15）

実 event capture から確認した形（公式 docs の "想定 field" 名が一部実機と違っていたため、本付録は **実機 dump をベース** に書き換えてある。verify 元: `~/.claude/plugins/data/agent-output-tracer-inline/sessions/<UUID>/events.jsonl` で観測した raw_event）。

## A.1 共通 field

すべての hook で以下が来る:

```json
{
  "session_id": "ba640ad4-5982-4601-8bed-69164fd10851",   // UUID v4
  "transcript_path": "/Users/.../.claude/projects/-Users-...-<project-slug>/<session_id>.jsonl",
  "cwd": "/Users/...",                                       // absolute path
  "hook_event_name": "UserPromptSubmit|PreToolUse|PostToolUse|Stop|SessionEnd"
}
```

`permission_mode` は **turn-scoped hook (PreToolUse / PostToolUse / Stop) のみ** で来る (`"default"` 等)。SessionEnd には来ない。

## A.2 UserPromptSubmit

```json
{
  ...common,
  "hook_event_name": "UserPromptSubmit",
  "prompt": "..."                                           // ← Codex と同じ field 名
}
```

**重要**: 公式 docs での想定は `user_prompt` だったが、実 event は `prompt`。本 plugin の adapter は両方対応している（`user_prompt` → `prompt` fallback）。

## A.3 PreToolUse

```json
{
  ...common,
  "permission_mode": "default",
  "hook_event_name": "PreToolUse",
  "tool_name": "Read|Glob|Grep|Edit|Write|MultiEdit|Bash",
  "tool_input": {
    "file_path": "/path/..."                                // Read/Write/Edit/MultiEdit
    // または "pattern": "...", "path": "..."               // Glob/Grep
    // または "command": "...", "description": "..."        // Bash
  },
  "tool_use_id": "toolu_01EibVnnMzShRvxNPTPieM8y"           // ← 公式 docs に未記載
}
```

`tool_use_id` は Claude API の tool_use block id。本 plugin は raw_event に保持するのみで Phase A では未活用。Phase B の `trace` / `why` で pre↔post 厳密紐付けに利用できる。

## A.4 PostToolUse

```json
{
  ...common,
  "permission_mode": "default",
  "hook_event_name": "PostToolUse",
  "tool_name": "Read",
  "tool_input": {...},                                       // PreToolUse と同じ
  "tool_response": {                                         // ← **dict 型** (string ではない)
    "type": "text",
    "file": {
      "filePath": "/path/...",
      "content": "...",
      "numLines": 92,
      "startLine": 1,
      "totalLines": 92
    }
    // Bash の場合は {"stdout": "...", "stderr": "...", "interrupted": bool,
    //                "isImage": bool, "noOutputExpected": bool}
  },
  "tool_use_id": "toolu_01...",                              // PreToolUse と同 id
  "duration_ms": 24                                          // ← 公式 docs に未記載
}
```

`tool_response` は **dict** で来るため、本 plugin の `_coerce_response` で `json.dumps` 化してから記録する（downstream grep / index で string として扱えるように）。`duration_ms` は Phase B の anomaly hint (long-running tool 検知) で活用予定。

## A.5 Stop

```json
{
  ...common,
  "permission_mode": "default",
  "hook_event_name": "Stop",
  "stop_hook_active": false,                                 // ← bool。"Stop hook が現在 active か"
  "last_assistant_message": "..."                            // ← Codex と同じ field 名
}
```

**重要**: 公式 docs での想定は `response_text` / `stop_reason: "end_turn|tool_use|max_tokens"` だったが、実 event は `last_assistant_message` で、`stop_reason` は**来ない**。代わりに `stop_hook_active: bool` が来る（plugin が直接活用する意味は薄い）。本 plugin の adapter は `response_text` → `last_assistant_message` fallback で動作。`stop_reason` は normalized event 上で常に None。

## A.6 SessionEnd

```json
{
  ...common (session_id, transcript_path, cwd, hook_event_name),
  "hook_event_name": "SessionEnd",
  "reason": "prompt_input_exit"                              // ← 公式 docs に未記載
}
```

`reason` は session 終了種別。実機観測値:
- `"prompt_input_exit"` — `/exit` 等の正常終了
- （他に `"clear"`, `"logout"` 等がありそうだが Phase A では未観測。Phase B で追加 verify）

注意: **`SessionEnd` だけが単独で fire することがある** — `hooks/hooks.json` の load 失敗時、その他 hook (UserPromptSubmit / PreTool / PostTool / Stop) は発火しないが、SessionEnd は `/exit` で fire するケースを観測（events.jsonl に 1 行だけ残る空 session）。Claude Code の plugin loader が hook ごとに独立判定している可能性。

---

# 付録 A.7: dev mode (`--plugin-dir`) 固有の挙動

実機 verify 済の挙動:

- **data dir 名に `-inline` suffix が付く**: `~/.claude/plugins/data/agent-output-tracer-inline/`（永続 install では suffix なしになるはずだが Phase A-11 で実機再 verify）
- **`${CLAUDE_PLUGIN_DATA}` 解決パス**: `~/.claude/plugins/data/<plugin_name>[-inline]/`
- **session_id format**: UUID v4 (`ba640ad4-5982-4601-8bed-69164fd10851`) — Codex 側との互換考慮では「string とだけ仮定」が正しいまま
- **transcript_path 命名**: `~/.claude/projects/<cwd を slash→hyphen 変換した slug>/<session_id>.jsonl`

---

# 付録 B: Codex hook event schema（公式 spec 確認済、2026-05-14〜15 verify）

公式 generated schema（https://github.com/openai/codex/tree/main/codex-rs/hooks/schema/generated）と公式 docs（https://developers.openai.com/codex/hooks）より：

## B.1 共通 input fields（8 種すべての required）

```json
{
  "hook_event_name": "PreToolUse|PostToolUse|SessionStart|UserPromptSubmit|Stop|PermissionRequest|PreCompact|PostCompact",
  "session_id": "string",
  "cwd": "/path/...",
  "model": "model name",
  "permission_mode": "default|acceptEdits|plan|dontAsk|bypassPermissions",
  "transcript_path": "/path/... or null",
  "turn_id": "string"  // turn-scoped 5 種（PreToolUse / PostToolUse / UserPromptSubmit / Stop / PermissionRequest）のみ required
}
```

## B.2 event 別の追加 field

### PreToolUse

```json
{
  ...common,
  "tool_name": "Bash|apply_patch|...",
  "tool_input": {
    "command": "..."   // ← canonical、`cmd` は公式根拠なし
  }
}
```

### PostToolUse

```json
{
  ...common,
  "tool_name": "Bash|apply_patch|MCP_tool_name",
  "tool_input": {...},
  "tool_response": <JSON value>  // tool-specific output、MCP の場合は MCP call result
}
```

**重要な制限**: Codex の Read 相当 / WebSearch 等の non-shell, non-MCP tool は **PostToolUse 発火しない**:

> "This doesn't intercept all shell calls yet... Similarly, this doesn't intercept `WebSearch` or other non-shell, non-MCP tool calls." (公式 hooks docs)

### UserPromptSubmit

```json
{
  ...common,
  "prompt": "user prompt 全文"
}
```

### Stop

```json
{
  ...common,
  "stop_hook_active": bool,
  "last_assistant_message": "..."
}
```

### SessionStart

```json
{
  ...common,
  "source": "startup|resume|clear"
}
```

### PermissionRequest

complex schema、本 plugin では採用しないため省略。詳細は generated schema directory 参照。

### PreCompact / PostCompact (0.129+)

session compaction lifecycle event。本 plugin の Phase D で活用検討。

## B.3 plugin が使う defensive 読み取り（簡素化版）

公式 spec で `event` 表記 / `cmd` field は **存在しないと確定**したため、defensive code を以下に簡素化：

```python
# 簡素化（公式 spec 確認後の正しい形）
event_name = event.get("hook_event_name", "unknown")
command = tool_input.get("command", "")
```

経験的観察の `event` / `cmd` 分岐は **不要、削除推奨**。

## B.4 output（hook → Codex への返答）

current format（PreToolUse）：

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",   // ← output 側は camelCase
    "permissionDecision": "deny",
    "permissionDecisionReason": "..."
  }
}
```

`agent-output-tracer` は read-only forensic なので **exit 0 + 空 stdout** のみ使用、output 側 schema は使わない。

## B.5 multiple hooks の優先

> "Multiple matching command hooks for the same event are launched concurrently, so one hook cannot prevent another matching hook from starting."
> "If multiple matching hooks return decisions, any `deny` wins."

→ plugin は decision を返さないため、他 hook との並走で問題なし。

---

# 付録 C: Debug workflow 例

## C.1 Hallucination 調査

```
[user]: 「agent が "DI コンテナを使った設計" って言ってきたけど、
         うちのプロジェクトでは DI 使わない方針。なぜこう言った？」

$ agent-output-tracer trace --session latest --output "DI コンテナ"

Output 'DI コンテナ' first appeared at 2026-05-14T10:30:12.456+09:00
Causal trail (prior events):
  - user prompt at 10:30:00: ✗ no 'DI' mentioned
  - files read prior to this output:
      [10:30:03] CLAUDE.md: ✗ does not contain
      [10:30:08] src/lib/di.ts: ✓ contains  ← source!

→ user: "あー、di.ts を勝手に読んだのか。なぜ？"

$ agent-output-tracer why --session latest --event "Read(src/lib/di.ts)"

Event: 10:30:08 Read(file_path=src/lib/di.ts)
What came immediately before:
  - [10:30:05] Glob(pattern='src/**/*.tsx') returned 23 results
  - [10:30:08] (the Read above)

⚠️ This path appeared in a Glob result at 10:30:05:
   Glob pattern: src/**/*.tsx
   (agent picked this path from Glob results, no explicit user mention)

→ user: "Glob が無関係 file を返して、agent が読んじゃったのか。
         次回は Glob の pattern をもっと絞ろう。"
```

## C.2 Wrong tool 調査

```
[user]: 「SEO 案件で agent が search-console-interpreter を invoke したけど、
         本当は serp-reverse-engineer のはずでは？」

$ agent-output-tracer why --session today \
  --event "Skill(search-console-interpreter)"

Event: 14:22:30 Task tool invoked with subagent_type='search-console-interpreter'
What came immediately before:
  - [14:22:25] user_prompt: "新しいキーワードの SERP 分析をしたい"
  - [14:22:27] agent thinking (Read CLAUDE.md)
  - [14:22:30] (the invocation above)

⚠️ User prompt mentioned 'SERP 分析' but agent invoked 'search-console-interpreter'
   (interprets GSC data, not SERP results)

$ agent-output-tracer grep --session today --pattern "serp"

[14:22:25] user_prompt.text: "新しいキーワードの **SERP** 分析をしたい"
(no other 'serp' mentions in session)

→ user: "agent は SERP と GSC を取り違えた。routing rules が曖昧かも、
         CLAUDE.md に明示しよう。"
```

## C.3 Cross-namespace bleed 調査

```
[user]: 「Project A の作業をしてたはずなのに、agent が Project B の file を
         参照してきた」

$ agent-output-tracer diff --session latest

User mentioned but agent did NOT access:
  - projects/A/spec.md
  
Agent accessed without user mention:
  - projects/A/config.yaml          ← legitimate (near A/spec.md)
  - projects/B/utils.ts             ← ⚠️ unexpected
  - projects/B/types.ts             ← ⚠️ unexpected

→ user: "Project B を読んだ理由を確認"

$ agent-output-tracer why --session latest --event "Read(projects/B/utils.ts)"

Event: 11:45:30 Read(projects/B/utils.ts)
What came immediately before:
  - [11:45:25] Glob(pattern='projects/**/utils.ts')

⚠️ Glob pattern crosses project boundaries.
   Consider scoping Glob to projects/A/ to avoid cross-project bleed.
```

## C.4 Session quality drop 調査

```
[user]: 「session の最初は良い回答だったのに、後半から的外れになった」

$ agent-output-tracer replay --session latest --show-hints

[10:00:00] [user] "FooBar を実装して"
[10:00:05] [tool] Read CLAUDE.md (12KB)
[10:00:08] [tool] Read src/foo.ts (5KB)
[10:00:15] [agent] "実装案を提示します..."

[10:05:00] [user] "テストも書いて"
[10:05:03] [tool] Read CLAUDE.md (12KB)    ⚠️ 2nd read (30 sec ago)
[10:05:12] [agent] "テスト案..."

[10:10:00] [user] "ドキュメントも"
[10:10:01] [tool] Read CLAUDE.md (12KB)    ⚠️ 3rd read in 10 min (lost-in-middle hint)
[10:10:05] [tool] Read src/foo.ts (5KB)    ⚠️ 2nd read
[10:10:18] [agent] "ドキュメント案..."  ← user's "後半から的外れ" starts here?

→ user: "確かにこの時点から context が肥大してる。
         CLAUDE.md を 3 回読んでる時点で attention budget 圧迫してたかも。
         次は long task では session 分割しよう。"
```

---

# 付録 D: 用語集

| 用語 | 定義 |
|---|---|
| **Session** | agent の 1 起動から終了までの単位。session_id で識別 |
| **Event** | session 内の 1 つの行為（user prompt / tool call / agent response 等）|
| **Normalized event** | engine 固有の event JSON を plugin 内部の統一 schema に変換した dict |
| **Forensic recorder** | session を完全記録する仕組み、原因 trace のための data 提供 |
| **Causal trail** | ある event に至るまでの直前 event 系列、因果連鎖の trace |
| **Anomaly hint** | replay 時に表示される注意喚起。pattern 自動検知の副次出力 |
| **Hallucination candidate** | agent response に出現したが、user prompt にも read 履歴にも source が見当たらない言及 |
| **Redaction** | secret pattern を log 書込前に mask する処理 |
| **Issue-agnostic** | 違和感の種類を事前分類しないアプローチ |
| **Engine adapter** | engine 別の event 形式を統一 schema に変換する変換層 |
| **Excerpt** | tool_response 等の長文を先頭 N 文字に切り詰めた断片 |

---

# 引継ぎメモ（次セッション・他 agent 向け）

## このセッションで決まったこと

1. **plugin 名**: `agent-output-tracer`（issue-agnostic な debugger 機能を name で表現）
2. **配置**: `~/work/agent-output-tracer/`（独立 git repo）
3. **主機能**: 検知ではなく **forensic / debug 機能**。user が違和感を感じた時に session を replay / trace / query 可能
4. **issue-agnostic**: 違和感の種別を分類しない、debug capability のみ提供
5. **agent compliance に依存しない mechanical recorder**
6. **Anomaly hint patterns**: 副次として replay 時に表示、main 機能ではない（具体 pattern は §11 Phase B-8 参照）
7. **host repo 非汚染**: plugin data dir に閉じる
8. **engine 対応**: Claude Code 主軸、Codex は Phase C
9. **5 hook 採用**: UserPromptSubmit / PreToolUse / PostToolUse / Stop / SessionEnd
10. **content capture**: default は excerpt + paths、full mode は opt-in

## 実装着手時に最初にやること

1. `~/work/agent-output-tracer/` git init
2. `pyproject.toml` draft（Python 3.11+、最小依存）
3. **Phase A-1** から開始：`plugin.json` + 空 `hooks/hooks.json` で plugin install を成功させる
4. Phase A-2 から TDD で進める：単体 test 駆動で `core/normalizer.py` を構築
5. Phase A-3 〜 A-6 は逐次（recorder → user prompt / stop → redactor → replay）
6. Phase A 完了したら **`replay` コマンドが動く** ことが必須 milestone（最重要主機能）

## 注意点

- 本 doc 内で「host repo」「OS」「Director OS」のような特定 repo 固有概念は **plugin 本体から排除**。すべて config 駆動
- `${CLAUDE_PLUGIN_ROOT}` / `${CLAUDE_PLUGIN_DATA}` の挙動は Phase A-1 で実機 verify
- Codex 公式 docs は本 doc 作成時に未確認、Phase C-0 で先行 verify 必要
- **「rot を検知できる」と謳わない**: 検知 ≠ 提供。本 plugin は forensic recorder、判断は user
- `replay` の出力品質が plugin の価値の大半を決める。Phase A-6 に時間をかける
- redaction を初期から有効化（secret 漏れ事故予防）

## 既に verify 済の primary sources

| Source | URL | 確認日 | 確認手段 |
|---|---|---|---|
| Claude Code hooks 公式 | https://code.claude.com/docs/en/hooks.md | 2026-05-14 | claude-code-guide subagent |
| Claude Code plugins 公式 | https://code.claude.com/docs/en/plugins.md | 2026-05-14 | 同上 |
| Claude Code plugins reference | https://code.claude.com/docs/en/plugins-reference.md | 2026-05-14 | 同上 |
| Claude Code settings | https://code.claude.com/docs/en/settings.md | 2026-05-14 | 同上 |

## 未 verify、Phase A-1 / C-0 で確認すべき

| 項目 | 重要度 |
|---|---|
| `${CLAUDE_PLUGIN_ROOT}` / `${CLAUDE_PLUGIN_DATA}` の解決経路 | 高（Phase A-1）|
| PostToolUse `tool_response` の Read 結果 format | 高（Phase A-3）|
| Stop hook `response_text` の completeness | 中（Phase A-4）|
| UserPromptSubmit event の prompt field 名 | 中（Phase A-4）|
| SessionEnd event の field 詳細 | 中（Phase A-3）|
| Codex CLI hooks 公式 docs | 中（Phase C-0）|
| Codex UserPromptSubmit 相当の有無 | 中（同上）|

---

# 修訂履歴

## 2026-05-14（初版）

- issue-agnostic forensic debugger plugin として設計成立（plugin 名 `agent-output-tracer`）
- 検討段階で proxy 検知方式（pattern 自動検知）を棄却し、forensic recorder + user-driven query の役割分担に収束（rationale は §0.5 参照）
- 5 hook 採用: UserPromptSubmit / PreToolUse / PostToolUse / Stop / SessionEnd
- 8 主要 CLI コマンド定義: replay / trace / why / diff / state-at / grep / causal-graph / mentioned-but-not-read
- Pattern 検知（P-X 系）は anomaly hint として副次化
- Phase A / B / C の段階実装計画
- 安全設計（failure tolerance / host 非汚染 / privacy redaction / 自動 GC / performance budget）

## 2026-05-14〜15（Phase C-0 完了）— Codex 公式 hook docs verify

**契機**: 「Codex 公式 hook docs verify とは何か」「今 verify」という user 指示。

**実施**: general-purpose subagent 経由で OpenAI Codex CLI 公式 docs を一次資料 verify。defuddle で公式 docs を取得保存（`shared-assets/temporary/defuddle-openai-codex-hooks.md` 等）。

**主な発見**:

1. **Codex 公式 hooks docs 存在**: https://developers.openai.com/codex/hooks（および config-advanced / changelog / plugins/build / generated schemas）
2. **利用可能な hook event は 8 種**: SessionStart / PreToolUse / PermissionRequest / PostToolUse / UserPromptSubmit / Stop / PreCompact / PostCompact（**SessionEnd は存在しない**）
3. **`session_id` field 確認済**（全 event の required）
4. **`turn_id` field 存在**: turn-scoped 5 event で required（Codex 固有拡張、Claude Code にはない）
5. **経験的観察と矛盾した項目**:
   - `event` 単体表記は **公式根拠なし**（defensive code 不要）
   - `tool_input.cmd` は **公式根拠なし**（`command` のみ）
6. **`SessionEnd` 不在 → 設計変更**: Codex では Stop event + session_id グルーピングで擬似的に session 完結を扱う、または SessionStart `source="clear"` で切替検知
7. **PostToolUse 制限**: Bash / apply_patch / MCP のみ発火、Read / WebSearch 相当は非発火（公式明示）
8. **Plugin 機構公式確認**: `codex plugin marketplace add <path or repo>` で install、`~/.codex/plugins/cache/...` に配置
9. **Feature flag `[features] codex_hooks = true` 必須**（無いと silently ignored、install 手順で必須化）
10. **version 推奨**: >= 0.128（plugin-bundled hooks）、compaction event 使うなら >= 0.129

**doc 修正内容**:

| 箇所 | Before | After |
|---|---|---|
| frontmatter `verification_dates` | Codex 公式 docs は未 verify | Codex 公式 hooks docs verify 完了（2026-05-14〜15）追加 |
| §3.2 Codex CLI section | 経験的観察ベースの薄い記述 | 公式 spec 確認済の詳細（8 event、共通 fields、PostToolUse 制限、SessionEnd 不在対応、plugin 機構、feature flag、version 要件、経験的観察との差異 summary）|
| §10.2 Codex install | sample `config.toml.example` のみ | `codex plugin marketplace add` 公式手順 + feature flag 必須 + trusted project 制約 |
| §11 Phase C | C-0〜C-5、verify 未完成として記述 | **C-0 完了**、残り C-1〜C-10 を spec 確定済として展開 |
| §13.1 verify 状態 | Codex hook 仕様: Phase C-0 公式 docs | **完了** + 残課題（session_id format / native env var / version 互換）を列挙 |
| 付録 B | 実測ベースの 1 schema 例 + defensive code | **公式 spec 確認済**: B.1〜B.5 で共通 fields / event 別 schema / 簡素化された defensive code / output format / multiple hooks 優先順位 |

**残課題（Phase C 着手前に実機 verify が必要）**:

- Codex `session_id` の正確な format（UUID v4 or 独自）
- Codex native plugin data env var（`${CLAUDE_PLUGIN_ROOT}` 相当）の解決
- Codex schema の minor version 間破壊的変更履歴

**取得した公式 docs（gitignored `shared-assets/temporary/`）**:

- `defuddle-openai-codex-hooks.md` (486 lines, wordCount 2188)
- `defuddle-openai-codex-hooks.json`
- `defuddle-openai-codex-plugins-build.md`
- `defuddle-openai-codex-changelog.md`

これらは保管期限内に plugin repo (`~/work/agent-output-tracer/`) 着手時に移植可能。

## 経緯（5 段階の設計収束 + Codex 公式 verify 完了）

本 plugin に至るまでの設計判断の進化を要約として記録する（具体的な棄却案 doc は本 doc 完成時点で削除済、本 doc が単独で完結する形に再整理されている）：

1. 初期：host repo 側の predictive guard（hard deny / 章分割等）案 → 設計意図の不一致で撤回
2. 予防系の soft signal（pragma）案 → 既存 permissions deny で hard enforcement 可能と判明し置換
3. 予防中心から検知中心へ方針切替（host repo 結合型の検知設計を draft）
4. host repo 結合型 → 完全分離 plugin 設計に再転換（pattern 自動検知 plugin として draft）
5. **検知設計の本質的限界（proxy 問題：proxy ≠ rot 本体）を踏まえ、forensic debugger に再再転換（本 doc 初版）**
6. **Phase C-0 完了**: Codex 公式 hooks docs verify、§3.2 / 付録 B / §10.2 / §11 / §13.1 を公式 spec ベースに書き換え

各段階は建設的レビューを起点とした self-correction の積み重ね。誇大主張（「正確検知できる」「pattern で rot を判定できる」等）を一つずつ排除し、honest capability に削ぎ落とした結果として現設計に到達。本 doc が最も成熟した形。
