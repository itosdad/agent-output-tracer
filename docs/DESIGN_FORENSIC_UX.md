---
title: agent-output-tracer — Phase D Power-Up 設計（Forensic UX 強化）
plugin_name: agent-output-tracer
target_repo: ~/work/agent-output-tracer/
phase: D（Phase A-C 完了を前提とした次世代設計）
intended_engines:
  - Claude Code（主軸、Phase A-B で実装済とみなす）
  - Codex CLI（Phase C で実装済とみなす）
date: 2026-05-15
author: Claude (claude-opus-4-7, 1M context)
status: design draft（実装着手前、他セッションへ引継ぎ可能な粒度で記述）
companion_doc: docs/DESIGN.md（Phase A-C 設計の baseline、本書はその拡張）
primary_sources:
  - Claude Code 公式 docs: https://code.claude.com/docs/en/
  - Codex 公式 docs: https://developers.openai.com/codex/
  - Codex generated schemas: https://github.com/openai/codex/tree/main/codex-rs/hooks/schema/generated
  - 本 repo の DESIGN.md（特に §0.5 design rationale, §1.2 非目的, §2 設計原則）
verification_dates:
  - CC / Codex debug モード機能ギャップ調査: 2026-05-15（claude-code-guide / general-purpose subagent 経由）
handoff_notes:
  - 本書は DESIGN.md の差分・拡張のみを記す。Phase A-C の baseline は DESIGN.md を一次資料とする
  - cold-read で D-1 実装着手可能な粒度を意図。実装着手時は §9 Phased rollout を起点に
  - 哲学衝突を疑った時は §1 思想軸 → DESIGN.md §0.5 / §1.2 / §2 を参照
  - 未検証項目は §11 に集約、実装着手前に一次資料 verify を済ませること
---

# ⚠ Historical baseline — Phase D design draft (2026-05-15)

This document is the **pre-implementation design** of Phase D
(forensic UX power-up + TUI side-channel). It is preserved as the
historical record of how Phase D was scoped before code was written.

For the **current state**, refer to:

- [`README.md`](../README.md) — overview, screenshots, current
  status table covering Phase D + TUI Phase 1–4.A as shipped
- [`docs/TUI.md`](TUI.md) — comprehensive TUI guide
- [`CHANGELOG.md`](../CHANGELOG.md) — per-version diff

Implementation has shipped Phase D in full plus the TUI Phase 1–4.A
that wasn't in the original draft (engine themes, OhMyZsh-style
banner, menu preview pane, clipboard yank, sticky defaults, etc.).
This document is not deleted because the §1 思想軸 / §2 design
principles are still load-bearing for PR review.

---

# 0. Executive Summary

## 0.1 一言で

Phase A-C で完成した forensic recorder + post-hoc query CLI の上に、**「セッションを一切中断せずに forensic 分析できる side-channel UI」** と **「user 判断を支援する unique workflow（bisect / note / find vocabulary / content-address）」** を加え、Claude Code / Codex の標準 debug モードの良所を **AOT 哲学に翻訳して取り入れる**全面パワーアップ。

## 0.2 解く課題

| 課題 | 既存（Phase C 完了時点）| Phase D での解決 |
|---|---|---|
| CC TUI 内で forensic を打つと観測対象を汚染する | slash command / Bash 経由しか手段なし、context tokens を消費 | side-channel `aot tui` を別 pane に常駐、CC と完全切断 |
| 「どこから狂ったか」を探す手段が目視 replay のみ | replay を上下スクロール | git-bisect 流の `bisect` ワークフロー |
| 結論や仮説を session に紐づけて残せない | 外部 doc / memo に転記するしかない | `note` で session metadata に永続化 |
| anomaly hint が「個別 hint 出力」止まり | replay 中の inline 表示のみ | `find` 語彙化、検索 / 集計可能に |
| 同じ tool_response が他 session でも出ているか分からない | session 単独 forensic 設計 | content-addressable（SHA256）で session 跨ぎ照合（opt-in） |
| 料金 / token / latency / engine 側 permission decision が見えない | hook 経路では取れないものが多い | OTel sidecar export と engine-log overlay の **片方向 bridge** で補完 |
| CLI が長く typing が重い | `agent-output-tracer ...` の絶対形しかない | `aot` alias、引数なし既定、tab 補完、密度切替 |

## 0.3 設計の 3 本柱

| 柱 | 役割 | 主な deliverable |
|---|---|---|
| **Pillar 1: Forensic UX 層** | user の指先と目に直接触れる | CLI 動詞再編・alias・色・密度切替・エラー UX・slash command 政策 |
| **Pillar 2: Causal Core 深化** | AOT 独自性が宿る本丸 | Schema v2・bisect・note・find 語彙・content-address・trace 双方向化 |
| **Pillar 3: Interop Bridges** | 既存 debug モードの良所を哲学に翻訳して取り入れる | engine-log overlay・OTel sidecar・cross-session index（全 opt-in） |

## 0.4 段階化

| Phase | 目的 | 依存 |
|---|---|---|
| D-1 | UX 基盤（alias / 密度 / 色 / エラー / doctor / config） | なし |
| D-2 | Schema v2（純加算、reader が v1/v2 両対応） | なし |
| D-3 | Causal Core 強化（find 語彙 / trace 拡張 / bisect / note / stats） | D-2 |
| D-4 | Live UX（tail / replay --watch / stream-json） | D-2 |
| D-5 | aot tui（side-channel TUI、非中断 UI のプライマリ） | D-3, D-4 |
| D-6 | Bridges（engine-log overlay / OTel sidecar / cross-session） | D-2, D-3 |
| D-7 | Safe-share Export | D-2 |

---

# 1. 思想軸

## 1.1 憲法（DESIGN.md §2 から再宣言、Phase D で**一切緩めない**）

| 原則 | 進化なし |
|---|---|
| Issue-agnostic | 違和感の自動分類は行わない、anomaly は hint に止める |
| User-driven | proactive alert は default off、dispatch は user 起動 |
| Mechanical | agent self-report 非依存、hook payload のみ |
| Observation-only | 全 hook `exit 0`、絶対介入しない |
| Host repo 非汚染 | 書込は `${CLAUDE_PLUGIN_DATA}` 配下のみ、`<host>/tasks/` 等にも書かない |
| Engine-agnostic | normalized event schema が単一の真実 |

## 1.2 Phase D で加わる原則

| 新原則 | 意図 | 適用される対象 |
|---|---|---|
| **Defaults that just work** | 引数なしで最頻動作（`aot` 単独 = `replay latest --brief`） | CLI 全体 |
| **Bridges are explicit and one-way** | OTel / engine-log / cross-session は常に opt-in、AOT → 外向きのみ | Pillar 3 全体 |
| **Composable exit codes & --json everywhere** | あらゆる query が `--json` を持ち、shell pipeline / CI に組み込める | 全 subcommand |
| **Schema additive evolution** | v1 → v2 → v3 は加算のみ、reader は古い v でも読める | events / metadata / index 全て |
| **Color & density honor the user's terminal** | `NO_COLOR` / `--color {auto,always,never}` / TTY 判定、密度は brief / full / raw / json の 4 段 | CLI / TUI 両方 |
| **Errors carry next-action** | エラーは「何が起きたか / 原因 / 次に打つコマンド」3 行を保証 | 全 subcommand |

## 1.3 哲学衝突の検知ルール

Phase D 実装中に以下の signals が出たら設計判断を見直す:

- 「proactive に warn する」案 → §1.1 user-driven と衝突、却下
- 「agent に注入する slash command」案 → §1.1 observation-only と衝突、即却下（Phase D では slash command 自体を出荷しない / OQ6 決裁 2026-05-15）
- 「host repo に書く」案 → §1.1 host repo 非汚染と衝突、即却下
- 「OTel collector を内蔵する」案 → §0.3 Pillar 3 の "bridges are one-way" と衝突、sidecar exporter に留める

---

# 2. アーキテクチャ全体図

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                        Pillar 1: Forensic UX 層                              │
│  CLI verbs (17) ─ alias `aot` ─ 密度 4 段 ─ 色 ─ エラー 3 行 ─ doctor / config │
│  aot tui (side-channel TUI、非中断 UI のプライマリ)                            │
└──────────┬──────────────────────────────────────────────────────────┬────────┘
           │                                                          │
           ▼                                                          ▼
┌──────────────────────────────┐                ┌─────────────────────────────────┐
│   Pillar 2: Causal Core      │                │   Pillar 3: Interop Bridges     │
│                              │                │   (全 opt-in、片方向)           │
│  events.jsonl v2             │                │                                 │
│   - SHA256 / tool_use_id     │                │  engine-log overlay             │
│   - correlation_id / tokens  │   (read-only   │   (~/.claude/debug/* を merge)  │
│   - parent_session_id        │    consumer)   │                                 │
│                              │ ──────────────▶│  OTel sidecar export            │
│  index.json v2               │                │   (aot.session/turn/tool span)  │
│   - bigram_inverted          │                │                                 │
│   - content_hash_to_events   │                │  cross-session global_index     │
│   - phrase_to_first_agent    │                │   (review / --since 用)         │
│                              │                │                                 │
│  metadata.json v2            │                │  (slash command は不出荷:       │
│   - notes / findings         │                │    OQ6 決裁、aot tui が唯一の   │
│   - anomaly_counters         │                │    非中断 UI)                   │
│                              │                └─────────────────────────────────┘
│  query: trace±/bisect/note   │
│         find/stats/review    │
└──────────────────────────────┘
           ▲
           │ hook payload（変更なし、Phase A-C のまま）
           │
┌──────────────────────────────────────────────────────────────────────────────┐
│           hooks/ (5 種) ─ adapters/{claude_code,codex}.py ─ recorder         │
│                                                                              │
│           Phase D で hooks 自体は変更しない（observation-only 維持）           │
│           hooks payload に新 field（tokens 等）が来れば adapter 経由で v2 へ  │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

# 3. CLI 動詞正規表

## 3.1 動詞一覧（17 verb）

| グループ | 動詞 | alias | 状態 | 役割 |
|---|---|---|---|---|
| Browse | `replay` | `r` | 拡張 | timeline 再生、`--brief/--full/--raw`、`--watch`、`--overlay engine-log` |
| Browse | `list` | `ls` | 拡張 | session 一覧、`--filter`（engine, has-hallucination, has-notes, prefix）|
| Browse | `latest` | `l` | 拡張 | 最新 session id、`--n N` で末尾 N 件 |
| Browse | `tail` | `t*`| **新規** | 進行中 session の events.jsonl follow、`--format stream-json` |
| Browse | `tui` | — | **新規** | side-channel TUI（非中断 UI、§5 詳細）|
| Search | `grep` | `g` | 拡張 | 全文 regex 検索、`-C N`（context）、色付きマッチ |
| Search | `find` | `f` | **新規** | anomaly 語彙検索（§7.4）|
| Trace | `trace` | `tr` | 拡張 | 出力句逆引き、`--missing` / `--by-sha`（§7.1）|
| Trace | `why` | `w` | 既存 | 個別 event の理由 query |
| Trace | `diff` | `d` | 既存 | user 指示 vs agent action 差分 |
| Trace | `graph` | `gr` | rename | 既存 `causal-graph` を短縮命名 |
| State | `state-at` | `s` | 拡張 | 任意時刻の累積 state、`--since-prompt` / `--before-event` 追加 |
| State | `stats` | — | **新規** | session 単位 forensic 統計（cost ではなく anomaly / bytes / unique paths）|
| Workflow | `bisect` | — | **新規** | git bisect 流の二分捜索（§7.2）|
| Workflow | `note` | `n` | **新規** | session に人間 curate 注釈を attach（§7.3）|
| Workflow | `review` | — | **新規** | `--since DATE` で user-explicit な cross-session summary（§7.6）|
| Meta | `doctor` | — | **新規** | 自己診断（§7.7）|
| Meta | `config` | — | **新規** | TOML を直接編集せずに設定操作（§7.8）|
| Meta | `export` | `x` | **新規** | 安全共有 export（`--safe-share`、§7.9）|
| Meta | `purge` | — | **新規** | session 削除（doctor の `fix:` から呼ばれる）|

`t*` = `tail` の alias は `t` だが §1.1 の "trace" 動詞 `tr` と衝突回避のため `tail` には alias を付けない選択肢もある。実装時に決定。

## 3.2 サブサブコマンドを作らない理由

`browse / search / trace / state / workflow / meta` のグループは概念整理のみで、CLI 上はフラット。`aot trace search foo` のような階層は typing 速度を損なうため作らない。代わりに **alias + 強い `--help` + tab 補完** で操作性を担保。

## 3.3 Exit code 規約

| code | 意味 | 使う subcommand |
|---|---|---|
| 0 | 成功 / マッチあり | 全般 |
| 1 | マッチなし | `grep` / `find` (grep 規約踏襲) |
| 2 | ユーザエラー（session not found / regex 不正 / 時刻 parse 失敗 / 引数不正） | 全般 |
| 3 | 特殊 finding | `trace`: hallucination_candidate / `bisect`: aborted |
| 4 | I/O エラー | データ dir 不在 / 権限不足 |
| ≥10 | 予約（将来拡張） | — |

## 3.4 `--json` 全 subcommand 対応

全 subcommand は `--json` を持ち、構造化出力 schema は **subcommand ごとに版数 v** を持つ。例:

```json
{"$schema": "aot/trace/v1", "session_id": "...", "phrase": "...", "verdict": "grounded|hallucination_candidate|not_found", "sources": [...], "...": ...}
```

CI 用途。

---

# 4. 出力 UX

## 4.1 密度 4 段

| 密度 | 用途 | 既定の subcommand |
|---|---|---|
| `--brief` | 1 行 1 event、固有名詞省略形 | `replay`, `list` |
| `--full` | 既存標準出力 | `trace`, `why`, `state-at` |
| `--raw` | 内部 JSON ほぼそのまま | 機械読み |
| `--json` | subcommand ごと固定 schema | スクリプト |

`aot config set defaults.density brief|full` でユーザ既定上書き可。

## 4.2 色と記号（ASCII のみ、emoji 不使用）

| event / state | 記号 | 色 |
|---|---|---|
| user_prompt | `>>` | cyan |
| pre_tool | `..` | dim |
| post_tool | `↪` | normal |
| agent_response | `<<` | green |
| session_end | `==` | dim |
| hint | `!` | yellow |
| hallucination_candidate | `?` | red |
| note (human-attached) | `*` | magenta |
| engine overlay 行 | `@engine` | dim cyan |

色 OFF 条件: `NO_COLOR` env / `--color never` / `not isatty(stdout)`。

## 4.3 エラー 3 行構造

```
error: <短い宣言>
  cause: <一次原因、可能ならデータ込み>
  try:   <次に打つコマンド 1〜3 個>
```

例:

```
$ aot trace --session abc --output "JWT"
error: session 'abc' is ambiguous
  cause: 3 sessions match prefix 'abc' in your data dir
           abc94a3e-...  2026-05-12-pm3
           abc12f70-...  2026-05-08-am2
           abcd8e21-...  2026-04-30-pm5
  try:   aot list --filter prefix=abc
         aot trace --session abc94a3e --output "JWT"
```

エラー全種で同型を保証。`aot doctor` でも `fix:` 行が同役割。

## 4.4 タブ補完

`aot --install-completion {bash,zsh,fish}` で補完スクリプト出力。session spec も補完対象（recent 20 session を提示）。

---

# 5. `aot tui` 詳細設計

## 5.1 役割

**非中断 forensic UI のプライマリ**。CC と一切通信せず、`${CLAUDE_PLUGIN_DATA}/sessions/` の events.jsonl を fsevents/inotify で follow する独立プロセス。tmux split / iTerm pane / 別ウィンドウで常駐させる前提。

## 5.2 レイアウト

```
┌─ aot tui ─────────────────────────────────────────────────────────────────┐
│ Status bar: session id / live・past / engine / hint count / cand / notes  │
├──────────────────────────┬────────────────────────────────────────────────┤
│ Session list (28 cols)   │ Main pane                                      │
│  ● current               │  Timeline / overlay (why/trace/bisect/note/   │
│  ○ recent N              │   find/grep) を mode 切替で 1 pane に描画       │
│                          │                                                │
│  [filter]  [search]      │                                                │
├──────────────────────────┴────────────────────────────────────────────────┤
│ Keybinding hint bar (mode に応じて変化)                                    │
└───────────────────────────────────────────────────────────────────────────┘
```

詳細な mode 別画面は本書外の `docs/wireframes/`（実装着手時に追加）または会話の wireframe 出力を参照。

## 5.3 キーバインド

| キー | 動作 | 状態遷移 |
|---|---|---|
| `j` / `k` | event カーソル移動 | timeline mode |
| `↑` / `↓` | session カーソル移動 | session list focus |
| `Tab` | pane focus 切替（session list ⇄ main）| 任意 |
| `Enter` | event 詳細 / session 選択確定 | mode 依存 |
| `t` | trace（cursor の agent_response 起点）| timeline → trace overlay |
| `w` | why（cursor の event 起点）| timeline → why overlay |
| `b` | bisect 開始 | timeline → bisect mode |
| `n` | note 入力 | timeline → note form |
| `f` | find 語彙 picker | timeline → find mode |
| `/` | grep 入力 | timeline → grep mode |
| `s` | session 切替 picker | 任意 |
| `o` | engine-log overlay toggle | timeline |
| `x` | export 現在 view | 任意 |
| `?` | help overlay | 任意 |
| `Esc` | overlay 閉じる / mode 戻り | 任意 |
| `q` | quit | 任意 |

## 5.4 File watch 戦略

| platform | 1st choice | fallback | 検証要否 |
|---|---|---|---|
| macOS | fsevents (watchdog) | polling 500ms | §11 で計測 |
| Linux | inotify (watchdog) | polling 500ms | §11 で計測 |
| Windows | ReadDirectoryChangesW (watchdog) | polling 500ms | 公式 support 範囲外、polling のみ可 |

events.jsonl は append-only なので「最終 inode 位置」だけ保持し、watch event を受けたら追記分を読み込み tail buffer に push する。

## 5.5 依存パッケージ選定

| ライブラリ | 役割 | 採否 |
|---|---|---|
| `textual` | TUI framework（rich 上に layout / event loop） | **第一候補**（modern、layout が宣言的） |
| `urwid` | TUI framework（古典）| 代替候補（Python 3.9 互換性が確実） |
| `curses` (stdlib) | 最小 fallback | 万一上記が使えない場合のみ |
| `watchdog` | クロスプラットフォーム file watch | 採用候補（fsevents / inotify / 各 OS 統合） |

**方針**: core CLI は依存ゼロを維持。TUI は `pip install agent-output-tracer[tui]` の **optional dependency** に隔離する。`aot tui` 起動時に未 install なら以下を表示:

```
error: 'aot tui' requires optional dependencies
  cause: textual / watchdog not installed
  try:   pip install 'agent-output-tracer[tui]'
```

## 5.6 起動オプション

```
aot tui [--session SPEC] [--data-dir PATH] [--no-color] [--polling]
```

- `--session SPEC` で初期 session 指定（無指定 = `latest`）
- `--polling` で fsevents/inotify を強制 OFF（CI / 仮想環境向け）

## 5.7 非中断保証

- CC とのプロセス通信なし
- CC が触る state（`~/.claude/projects/...`）は **read のみ**、引数 `--overlay engine-log` 時に CC debug log を read するのみ
- AOT 自身の events.jsonl は append-only、読みは inode 追跡で衝突しない

---

# 6. Schema v2 仕様

## 6.1 設計方針

**純加算**。v1 reader は v2 event の追加 field を ignore できる。v2 reader は v1 event を `None` フォールバックで読める。`v` field が欠落していたら v1 とみなす。

## 6.2 events.jsonl v2（v1 から追加される field）

| field | 入る event | 型 | 役割 | 欠落時 |
|---|---|---|---|---|
| `v` | 全 | int | schema 版数（v2） | reader は v1 とみなす |
| `response_sha256` | post_tool | str (hex 64) | tool_response 本文の SHA256 | content-address 不可、それ以外影響なし |
| `response_size_bytes` | post_tool | int | excerpt と独立した full size | size 統計に不参加 |
| `tool_use_id` | pre_tool / post_tool | str | engine 由来（CC: `toolu_01...`）、pre↔post 厳密紐付け | pre/post の紐付けは ts 近接で fallback |
| `correlation_id` | 全 | str (uuid) | 同一 turn 内 event を束ねる、subagent lineage の起点（AOT 生成）| trace / why の精度低下 |
| `parent_session_id` | session_start 相当 | str / null | subagent / Task spawn の親 session | lineage 復元不可、独立 session として扱う |
| `tokens` | agent_response | object: `{input, output, cache_read, cache_creation}` (各 int / null) | hook payload に来た範囲のみ | stats / review で skip |
| `duration_ms` | post_tool / agent_response | int / null | engine reported（来れば） | profile 統計に不参加 |
| `hook_self_ms` | 全 | int | AOT hook 自身の処理時間 | self-instrument 不参加 |
| `engine_version` | 全 | str | CC / Codex のバージョン | 不明として表示 |
| `permission_mode` | 全 | str | CC / Codex 共通必須 field を正規化 | 不明として表示 |

## 6.3 metadata.json v2（v1 から追加）

| field | 型 | 役割 |
|---|---|---|
| `v` | int | schema 版数（2） |
| `notes_count` | int | `note` 数 |
| `findings` | array of object | `bisect` 結論等。`{kind, event_idx?, ts, by}` |
| `anomaly_counters` | object | `{unmentioned_reads, repeated_reads, hallucination_candidates, glob_burst, routing_thrash, large_read}` |
| `tokens_total` | object | `{input, output, cache_read, cache_creation}` |
| `cwd_hash` | str (hex 64) | cwd の SHA256（safe-share export 時の identity 隠蔽用） |
| `engine_version` | str | session 最初の event のもの |

## 6.4 index.json v2（v1 から追加 / 進化）

| field | 役割 |
|---|---|
| `v` | schema 版数（2） |
| `bigram_inverted` | grep prefix 検索高速化。v1 word-level → bigram に進化 |
| `content_hash_to_events` | SHA256 → event idx 群。同 tool_response 発生回数を O(1) |
| `path_first_seen` | path → 初出 event idx |
| `phrase_to_first_agent_event` | n-gram (length 3-5) → 初めて agent_response に出た event idx。`trace` 高速化 |

## 6.5 global_index.json（新規、opt-in）

`${CLAUDE_PLUGIN_DATA}/global_index.json` に作成。**`aot review` / `--cross-session` flag 時のみ生成・更新**。proactive には触らない（§1.1 user-driven）。

| field | 役割 |
|---|---|
| `v` | schema 版数（1） |
| `built_at` | 最終 build 時刻 |
| `retention_days` | 30（既定、config で変更可） |
| `sessions` | array `{session_id, ts_start, ts_end, engine, anomaly_counters, notes_tags}` |
| `phrase_cross_index` | n-gram → array `{session_id, event_idx}` |
| `path_cross_index` | path → array `{session_id, event_count}` |
| `sha_cross_index` | SHA256 → array `{session_id, event_idx, ts}` |

`aot review` 起動時に最新 events.jsonl 群との差分で incremental build。

## 6.6 v1 → v2 migration policy

| 行動 | 方針 |
|---|---|
| 既存 v1 events.jsonl を変換 | しない。v1 のまま保持、reader が両対応 |
| 新 hook write は v2 | D-2 完了以降は v2 で write |
| 古い session を mix で扱える | yes、reader は v ごとに dispatch |
| `aot doctor` が schema 版数を表示 | yes、`schema v1: N, v2: M` |
| 強制 migration コマンド | 提供しない（過剰設計回避）|

---

# 7. 新規 query 機能仕様

## 7.1 `trace` 拡張

### 7.1.1 既存（Phase B-2、CHANGELOG Unreleased で実装）

```
aot trace --session SPEC --output PHRASE
```

agent_response 中の PHRASE 初出 event を特定 → prior user_prompts / Reads / tool_responses を辿り、grounded / hallucination_candidate を判定。exit 3 で candidate flag。

### 7.1.2 Phase D 拡張

#### `--missing` （inverse hallucination）

```
aot trace --session SPEC --missing PHRASE --reference-paths PATH1,PATH2,...
```

意図: 「user が読ませた前提で質問したが、agent_response に該当キーワードが出ていない」検出。

| 入力 | 内容 |
|---|---|
| `--missing PHRASE` | 期待される phrase |
| `--reference-paths` | user 期待の参照 path 群 |

出力: 「reference path の tool_response 中に phrase 由来 token があったが agent が言及していない」event 列挙。

哲学整合: user 期待を明示的に与えるので、AOT は判定せず照合のみ。

#### `--by-sha`（content-address）

```
aot trace --by-sha SHA256_HEX [--since DATE]
```

意図: ある tool_response（SHA256）が他に何回、どの session で出たかを集計。session 跨ぎは `--since` 指定時のみ global_index 経由（opt-in）。

哲学整合: cross-session は user-explicit な opt-in、proactive ではない。

## 7.2 `bisect`

```
aot bisect start --session SPEC [--from EVENT_IDX] [--to EVENT_IDX]
aot bisect (good|bad|skip|view|quit)
aot bisect status
aot bisect log
```

### 7.2.1 動作

1. `start` で範囲 [from, to] を決定（既定: 1 ～ 最終 event）
2. 中点 event を提示、user が `good/bad/skip` で判定
3. log₂(N) 回繰り返して first-bad event を特定
4. 結論を `metadata.findings[]` に append、`{kind: "bisect_first_bad", event_idx, steps, ts, by}` 形式

### 7.2.2 非対話モード（CI 用）

```
aot bisect run --session SPEC --predicate 'jq ...'
```

予測関数（shell command が exit 0/1 で判定）を用意できれば自動 bisect 可能。設計上の余地として用意するが D-3 では非対話モードを **未実装** とし、D-5 以降に判断。

### 7.2.3 永続化

- `metadata.findings[]` は append-only（上書き禁止、再 bisect しても旧 finding は残る）
- `aot bisect log --session SPEC` で履歴閲覧

## 7.3 `note`

```
aot note add --session SPEC [--event IDX] [--tag TAG] [--finding FINDING_IDX] BODY
aot note list --session SPEC [--tag TAG]
aot note rm --session SPEC --id NOTE_ID
```

### 7.3.1 格納

- `<session_dir>/notes.jsonl`、append-only
- 1 行 = 1 note: `{id, ts, by, tag, body, links: {event_idx?, finding_idx?}}`
- `by` は OS user / `aot config set user.name "X"` で上書き

### 7.3.2 タグ語彙（既定）

`root-cause` / `observation` / `question` / `false-positive` / `followup` / `custom:<freeform>`

### 7.3.3 検索

`aot list --filter has-note[=TAG]` で note 付き session 列挙。

## 7.4 `find`（anomaly 語彙化）

### 7.4.1 既定の語彙

| 語彙 | 定義（厳密） | 既定パラメータ |
|---|---|---|
| `unmentioned-reads` | path tokens が直前まで全 user_prompts のいずれの token 集合とも素 | — |
| `repeated-reads N` | 同 path が N 回以上 post_tool に出る | N=3 |
| `glob-burst` | 直前 Glob 結果に含まれる path への Read が連続 K 回 | K=2 |
| `routing-thrash` | `CLAUDE.md` / `AGENTS.md` 等が同 session で M 回以上 read | M=2, 対象 path は config 可 |
| `large-read N` | 単一 Read の result_bytes が N KB 超 | N=50 (KB) |
| `hallucinations` | trace の hallucination_candidate flag が立った agent_response | — |
| `denied-permission` | engine-log overlay 由来、permission_mode で deny された tool（D-6 以降） | — |
| `empty-glob` | Glob / Grep が 0 件返却した直後、agent_response が「見つけた」体で言及 | — |
| `stale-cache` | 同 path を同 SHA256 で連続 read（無駄な context budget 消費を可視化） | — |
| `silent-failure` | post_tool が error / 空 result、直後 agent_response が言及しない | — |
| `abandoned-write` | Write / Edit 直後に同 path を Read せず再 Write / Edit（review なし上書き） | — |

### 7.4.2 ユーザ拡張

```toml
# config.toml
[find.custom]
my_pattern = { description = "...", regex = "...", target = "tool_response" }
```

### 7.4.3 出力

```
aot find VOCAB [--session SPEC] [--since DATE] [--json]
```

`--since` は global_index 経由（opt-in）。

## 7.5 `stats`

```
aot stats --session SPEC [--baseline 30d]
```

session 単位 forensic 統計を出力（CC `/usage` の cost 軸を **forensic 軸に翻訳**）:

| 指標 | 内容 |
|---|---|
| `events_total` | 全 event 数 |
| `tool_mix` | tool 別比率 |
| `unique_paths_read` | unique path 数 |
| `total_bytes_read` | total bytes |
| `anomaly_counters` | metadata 由来 |
| `tokens` | metadata 由来（取得できれば） |
| `vs baseline` | 当該ユーザ過去 N 日平均との偏差（opt-in） |

cost は **計上しない**（API 層、AOT hook では取れない）。OTel sidecar 経由で組織監査側に流す責務。

## 7.6 `review`

```
aot review --since DATE [--until DATE] [--json]
```

意図: user-explicit な cross-session summary。CC `/insights` を **user-driven に翻訳**。proactive にはならない。

出力（§4.1 brief 既定）:

- 期間内 session 数 / engine 別 / median duration
- anomaly counter 集計
- hallucination_candidate 一覧
- 上位 read paths
- note 付き session 一覧

global_index.json を build / consult する唯一の subcommand。

## 7.7 `doctor`

```
aot doctor [--json]
```

自己診断:

| 検査項目 | 出力 |
|---|---|
| runtime | Python version / hook runtime |
| data dir | path / size / session count / oldest |
| hooks | engine 別の hook 登録状況 |
| schema | 直近 5 session の v1/v2 比、parse 失敗 / 失敗-load remnant 警告 |
| redaction | enable 状況、dry-run scan |
| bridges | otel / overlay / cross-session の on/off 状況 |
| recent activity | 過去 7 日 session 数と anomaly counters |

各項目に `fix:` 行で次に打つコマンドを提示（§4.3 エラー UX と同型）。

## 7.8 `config`

```
aot config get KEY
aot config set KEY VALUE
aot config unset KEY
aot config list [--diagnose]
aot config schema [--json]
```

`config.toml` を user に編集させない（precedence を見える化）。`--diagnose` で値が **どの source 由来か**（default / user config / env / CLI flag）を表示。Codex `/debug-config` 取入。

`config schema` で JSON Schema を出力（IDE 補完用）。

## 7.9 `export --safe-share`

```
aot export --session SPEC [--safe-share] [--format markdown|json|archive] [--keep-excerpt N]
```

意図: team Slack / incident report に貼れる安全な形で session を export。

`--safe-share` で自動適用される変換:

| 変換 | 内容 |
|---|---|
| Path 抽象化 | `/Users/work/...` → `<HOME>/...`、`/proj/foo/bar.ts` → `<repo>/foo/bar.ts` |
| cwd 隠蔽 | `cwd_hash` のみ残す、実 path 削除 |
| tool_response 削除 | 本文削除、size / sha / excerpt のみ残す（`--keep-excerpt N` 文字、既定 0） |
| user_prompt 強化マスク | export-only secret pattern セット（mail / phone / 固有名詞オプション） |
| session_id 短縮 | 先頭 8 文字 prefix |

`--format archive` で zip 化（events.jsonl / metadata.json / notes.jsonl / 添付 markdown を同梱）。

## 7.10 `tail`

```
aot tail --session SPEC [--format text|stream-json] [--polling]
```

進行中 session の events.jsonl を follow。`stream-json` は JSON Lines、各行 1 event。CI / log forwarder 直結。CC `--output-format stream-json` の役割を AOT 側で持つ。

## 7.11 `tui`

§5 詳細参照。

---

# 8. Bridges 仕様

## 8.1 共通方針

| 原則 | 適用 |
|---|---|
| 既定 OFF | 全 bridge は `aot config set bridges.<x>.enabled true` で明示 enable |
| 片方向 | AOT → 外（read のみ / write のみ）、双方向通信は禁止 |
| Schema 安定性は AOT 側が保証 | 外側 schema 変動は AOT が吸収 |

## 8.2 engine-log overlay

```toml
[bridges.engine_log]
enabled = "auto"   # auto | true | false
claude_code_path = "~/.claude/debug/"     # auto-detect; CLAUDE_CODE_DEBUG_LOGS_DIR honor
codex_log_path = "$CODEX_HOME/log/"       # Phase C 完了後
```

### 8.2.1 動作

1. `replay --overlay engine-log` または TUI で `o` キー
2. `~/.claude/debug/<session_id>.txt` 等が存在すれば read
3. 時刻 anchor で events.jsonl と merge し `@engine` 行として描画

### 8.2.2 取れる情報（CC）

- matcher の評価結果
- permission decision の source（config / hook / user_permanent / user_temporary）
- auto-mode classifier の response
- hook 実行 timing / exit code

§A4 ギャップ（permission decision 監査）を実機経路で埋める。AOT は **read のみ**、debug log の場所 / 内容に影響を与えない。

## 8.3 OTel sidecar export

```toml
[bridges.otel]
enabled = false
exporter = "otlp-http"             # otlp-http | otlp-grpc | console | none
endpoint = "https://otel.example.com/v1/traces"
headers = { "x-otlp-api-key" = "$OTLP_TOKEN" }
log_user_prompt = false            # default false (redaction 強化)
log_raw_tool_response = false      # default false
```

### 8.3.1 emit する span

| span | 親 | attributes |
|---|---|---|
| `aot.session` | (root) | session_id (short hash), engine, engine_version, ts_start, ts_end, anomaly_counters |
| `aot.turn` | aot.session | correlation_id, user_prompt_present, agent_response_present |
| `aot.tool` | aot.turn | tool_name, paths_count, response_size_bytes, response_sha256, duration_ms, permission_mode |
| `aot.finding` | aot.session | kind (bisect_first_bad / hallucination_candidate), event_idx, ts |
| `aot.note` | aot.session | tag, links |

`tokens` が events に含まれていれば span attribute に追加（CC OTel `claude_code.llm_request` と並走可能）。

### 8.3.2 動作モード

- **batch**: session_end 時に全 span を flush
- **streaming**: hook 後段で逐次 emit（D-6 後段、要 perf 計測）

D-6 では batch のみ。streaming は Phase E 候補。

## 8.4 cross-session index

§6.5 で定義。`aot review` / `find --since` / `trace --by-sha --since` が触れる唯一の cross-session 機構。**proactive build はしない**、user 起動時に incremental build。

```toml
[bridges.cross_session]
enabled = false             # default off
retention_days = 30
auto_purge_on_doctor = true
```

`aot doctor --fix` で retention 超過 session を purge 候補に提示。

---

# 9. Phased rollout

各 phase は **independently shippable**（途中で止めても既存機能は壊れない）。Goal / Deliverable / Verification の 3 点セットで定義。

## 9.1 D-1: UX 基盤

| 項目 | 内容 |
|---|---|
| Goal | `aot` alias、密度 4 段、色、エラー 3 行、`doctor`、`config`、tab 補完 |
| Deliverable | `cli/main.py` 拡張、`cli/colors.py`（新規）、`cli/errors.py`（新規）、`query/doctor.py`、`query/config.py`、`completion/_aot.{bash,zsh,fish}` |
| Verification | (1) 既存 query 全部に `--brief/--full/--raw/--json` のテスト追加  (2) `NO_COLOR` honor のテスト  (3) `aot doctor` の各検査が green / warn / fail を実際に出すスナップショット  (4) tab 補完が `aot t<TAB>` で `trace tail tui` を返すスクリプトテスト |
| 依存 | なし |
| 影響 schema | なし |

## 9.2 D-2: Schema v2

| 項目 | 内容 |
|---|---|
| Goal | events.jsonl / metadata / index に v2 field 加算、v1/v2 両対応 reader、`v` 欠落 fallback |
| Deliverable | `core/recorder.py` 拡張、`core/session_io.py` 両対応化、`core/normalizer.py` v2 field 生成、`core/indexer.py`（新規、bigram / content_hash / phrase_to_first） |
| Verification | (1) v1 で書かれた既存 fixture が v2 reader で壊れない snapshot test  (2) v2 で書いた event を v1 reader が ignore できる test  (3) hook self_ms / correlation_id が必ず付く test  (4) `aot doctor` の schema integrity が v1/v2 比を表示する |
| 依存 | D-1（doctor 拡張で版数表示） |
| 影響 schema | events.jsonl, metadata.json, index.json |

## 9.3 D-3: Causal Core 強化

| 項目 | 内容 |
|---|---|
| Goal | `find` 語彙、`trace --missing` / `--by-sha`、`bisect`、`note`、`stats` |
| Deliverable | `query/find.py`、`query/trace.py` 拡張、`query/bisect.py`、`query/note.py`、`query/stats.py`、`analyzer/anomaly_vocab.py` |
| Verification | (1) 各 find 語彙に 3 つ以上の fixture session で true positive / false positive を網羅  (2) `bisect run --predicate` 非対話モードを CI でテスト（D-3 では実装せず、D-5 以降）  (3) `note add` → `note list` → `list --filter has-note` の round-trip  (4) `trace --by-sha` の single-session round-trip（cross-session は D-6） |
| 依存 | D-2 |
| 影響 schema | metadata（findings / anomaly_counters）|

## 9.4 D-4: Live UX

| 項目 | 内容 |
|---|---|
| Goal | `tail` follow、`replay --watch`、stream-json |
| Deliverable | `query/tail.py`、`core/follower.py`（新規、watchdog ベース）、`replay --watch` flag |
| Verification | (1) 進行中 events.jsonl を mock 追記してテストが follow を確認  (2) `--polling` fallback が watchdog OFF でも動く  (3) stream-json の各行が `aot/<command>/v1` schema に合致 |
| 依存 | D-2 |
| 影響 schema | なし |

## 9.5 D-5: `aot tui`

| 項目 | 内容 |
|---|---|
| Goal | side-channel TUI、§5 仕様 |
| Deliverable | `tui/` パッケージ（新規）、optional dependency `[tui]`、起動 entry `aot tui`、各 mode（timeline / why / trace / bisect / note / find / grep / overlay）|
| Verification | (1) 全 keybinding の手動 verify（macOS / Linux）  (2) live follow が D-4 follower を経由して動く  (3) 巨大 session（events 10000+）で navigation が遅延しない（< 100ms）  (4) optional dep 未 install 時のエラー UX |
| 依存 | D-3, D-4 |
| 影響 schema | なし |

## 9.6 D-6: Bridges

| 項目 | 内容 |
|---|---|
| Goal | engine-log overlay、OTel sidecar、cross-session index |
| Deliverable | `bridges/engine_log.py`、`bridges/otel_export.py`、`core/global_index.py`、`query/review.py` |
| Verification | (1) bridges 全て default off を assert  (2) engine-log auto-detect が `CLAUDE_CODE_DEBUG_LOGS_DIR` を honor  (3) OTel export を `console` exporter で smoke、prompt redaction 既定 ON を verify  (4) cross-session index を 30 session で build、`review` が 1s 以内 |
| 依存 | D-2, D-3 |
| 影響 schema | global_index.json |

## 9.7 D-7: Safe-share Export

| 項目 | 内容 |
|---|---|
| Goal | `export --safe-share`、JSON Schema 出力 |
| Deliverable | `query/export.py`、`core/sanitiser.py`、`schemas/` ディレクトリ |
| Verification | (1) snapshot test で path / cwd / tool_response が export に残らないこと  (2) markdown / json / archive 3 format の round-trip  (3) `--keep-excerpt N` で excerpt 長制御 |
| 依存 | D-2 |
| 影響 schema | なし |

---

# 10. 非目的（line in the sand、Phase D で明示的にやらない）

| 項目 | 理由 |
|---|---|
| Anomaly の自動通知 / proactive alert | §1.1 user-driven、§DESIGN.md §0.5 proxy 問題 |
| Session resume / fork（生きた conversation 復元） | engine の責務、AOT は post-hoc forensic |
| Agent への介入（deny / approve / modify） | §1.1 observation-only |
| OTel collector 内蔵 | bridges are one-way、sidecar exporter のみ |
| 自動修正 / リファクタ提案 / LLM-based summarisation | recorder は advisor ではない |
| host repo / `<repo>/tasks/` / `<repo>/.claude/` への書込 | §1.1 host repo 非汚染 |
| 全 session 自動 cross-index | proactive 振舞禁止、`review` で user-explicit 時のみ |
| Web UI dashboard | CLI + TUI + OTel で十分、メンテコスト過大 |
| events.jsonl の SQLite 化 | per-session JSONL のシンプルさを維持、index で速度確保 |
| Anomaly score 自動重み付け | proxy on proxy で false が悪化、語彙化に止める |
| Plugin auto-update | host 側機構に委譲 |
| token / cost の AOT 内蔵集計（hook 経路で取れない範囲） | OTel sidecar 経由で組織監査側に委譲、AOT は取れる範囲のみ表示 |

---

# 11. 未検証項目（実装着手前に一次資料 verify が必要）

| # | 項目 | 影響する設計箇所 | verify 手段 | verify 不可時の fallback |
|---|---|---|---|---|
| V1 | `textual` の Python 3.9 互換性 | §5.5 TUI dep 選定 | PyPI の `python_requires` / 公式 docs + 実機 import（D-5 着手前に必ず） | `urwid` または stdlib `curses` に切替、`[tui]` extras は Python 3.10+ 限定 |
| V2 | fsevents / inotify による events.jsonl 追記の遅延 | §5.4 file watch 戦略 | macOS / Linux で実機計測（D-5 着手時） | 100ms 超なら polling 500ms 既定に変更、watchdog OFF flag を default |
| V3 | CC `Stop` event payload に token usage が来るか | §6.2 `tokens` field、§7.5 stats | 実機 dump で確認（OBSERVATIONS.md 2026-05-15 で `last_assistant_message` 確認済、`usage` は未確認） | tokens は OTel sidecar 経由で組織監査側のみに委譲、AOT 内では omit |
| V4 | CC hook payload に `parent_session_id` 相当 field が来るか（subagent / Task 関連） | §6.2 `parent_session_id`、subagent lineage 復元 | CC `Agent` ツール起動時の hook event を実機 dump | subagent lineage 復元を諦め、独立 session として扱う |
| V5 | Codex 側 `~/.codex/sessions/` を AOT plugin として watch 可能か | §5.7 `aot tui` の Codex 対応（Phase C 完了後） | Codex dev mode で実機 verify | Codex は当面 `tail` / CLI 経由のみ、TUI は CC 専用 |
| V6 | events.jsonl への append 中に reader が読むときの race | §5.4 file watch | 実機計測、`fcntl.flock` または read 側で部分行 skip | reader 側で最終行が改行終端でなければ skip、次の watch event で再読 |
| V7 | `watchdog` パッケージの Windows サポート品質 | §5.4 cross-platform | 公式 docs + 実機 | Windows は polling 限定、`aot tui` Windows サポートは best-effort |

---

# 12. リスクと migration

| リスク | レベル | 対処 |
|---|---|---|
| Schema v2 で v1 session が壊れる | 高 | reader 両対応、`v` 欠落 fallback、snapshot test を D-2 で必須 |
| `bisect` 結論が後から間違いと判明 | 中 | findings は append-only、上書き禁止、再 bisect 履歴保持 |
| `--overlay engine-log` で CC debug log location が変わる | 中 | `CLAUDE_CODE_DEBUG_LOGS_DIR` env honor、見つからなければ skip + warn |
| OTel sidecar export で機微情報漏洩 | 高 | `log_user_prompt = false` / `log_raw_tool_response = false` を default、export 時の redaction を強化版で常時適用、export 内容を `aot doctor` で dry-run |
| `aot review` の cross-session index 肥大 | 中 | 30 日 retention、`aot purge` 手動、`doctor --fix` 提案 |
| `note` / `findings` が host repo に染み出す | 低 | 全 file は `${CLAUDE_PLUGIN_DATA}/sessions/<id>/` 限定、host write を技術的に不可能化 |
| TUI optional dep の install 摩擦 | 中 | `aot tui` 起動時のエラーで `pip install` コマンドを提示、`aot doctor` で TUI dep 状態表示 |
| watchdog の OS 差で挙動不安定 | 中 | `--polling` で常に強制 polling 可能、TUI は polling fallback を内蔵 |
| 既存 hook の post_tool 処理時間が D-2 で増える（SHA256 計算） | 中 | tool_response 100KB 超は SHA 計算を後段 indexer に deferred（hook 内では size のみ確定、SHA は index build 時に算出）|

---

# 13. Open Questions（決裁ログ）

Phase D の Open Questions は **2026-05-15 に全 6 件決裁完了**（詳細は §14 修訂履歴）。

| # | 結論 | 反映先 |
|---|---|---|
| OQ1 | TUI dep は `textual` 第一候補。Python 3.9 互換性は D-5 着手前に実機 verify、不可なら `urwid` に切替 | §5.5 / §11 V1 |
| OQ2 | `bisect --predicate` 非対話モードは D-3 では未実装、Phase E 以降に実需を見て判断 | §7.2.2 |
| OQ3 | OTel sidecar は D-6 では batch のみ、streaming は Phase E 候補（hook perf budget 防衛） | §8.3.2 |
| OQ4 | `find` 既定語彙に `empty-glob` / `stale-cache` / `silent-failure` / `abandoned-write` を追加 | §7.4.1 |
| OQ5 | global_index retention 既定 30 日、`config.toml` で可変化 | §6.5 / §8.4 |
| OQ6 | slash command は一切出荷しない（`/aot-note` 含む）。`aot tui` を非中断 UI の唯一手段とする | §8（旧 §8.4 削除）/ §11（V1 削除） |

新規 Open Question が生じた場合は本節に追記する。

---

# 14. 修訂履歴

| 日付 | 内容 | author |
|---|---|---|
| 2026-05-15 | 初版作成。Phase D 設計を会話履歴（review → power-up → 非中断補正 → wireframe）から固定化 | Claude (claude-opus-4-7, 1M context) |
| 2026-05-15 | OQ1〜OQ6 全 6 件決裁完了（user 全推奨採用）。OQ1 textual / OQ2 bisect predicate 保留 / OQ3 OTel batch のみ / OQ4 find 語彙 4 追加 / OQ5 retention 30 日 / OQ6 slash command 全削除。§1.3 / §2 / §7.4 / §8（旧 §8.4 削除、§8.5 → §8.4 改番）/ §11（V1 削除、V2-V8 → V1-V7 改番）/ §12（slash 衝突 row 削除）/ §13（決裁ログ化）を整合更新 | Claude |
