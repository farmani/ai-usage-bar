# ai-usage-bar

A macOS menu bar plugin that shows your Claude Code and ChatGPT (Codex) plan limits. It shows the 5-hour window and the weekly window for each account.

```
CC 6%/81% · GPT 16%
```

`CC` is Claude Code and `GPT` is ChatGPT Codex. The first number is the 5-hour window, the second is the weekly window. A plan with only a weekly limit, like ChatGPT Pro, shows one number. The title turns yellow at 60% and red at 85%.

The dropdown shows used and remaining percent for every window, a progress bar, and when each window resets.

## Requirements

- macOS with [SwiftBar](https://github.com/swiftbar/SwiftBar). [xbar](https://xbarapp.com) works too.
- `python3`. It comes with the Xcode Command Line Tools.
- At least one of: [Claude Code](https://docs.claude.com/en/docs/claude-code) logged in with a Pro or Max plan, or the [Codex CLI](https://github.com/openai/codex) logged in with your ChatGPT account.

## Install

1. Install SwiftBar: `brew install --cask swiftbar`
2. Download `ai-usage.5m.py` from the [latest release](../../releases/latest) into your SwiftBar plugin folder.
3. Make it executable: `chmod +x ai-usage.5m.py`
4. On the first run, macOS asks to let the plugin read the "Claude Code-credentials" Keychain item. Choose **Always Allow**.

## Link your accounts

There's no separate login. The plugin reads the tokens that the official CLIs already saved.

- Claude Code: run `claude`, then `/login`. The token is in the Keychain under "Claude Code-credentials".
- ChatGPT: run `codex login`. The token is in `~/.codex/auth.json`.

The plugin only reads these tokens. It never refreshes them, because a refresh replaces the refresh token and logs the CLI out. If the menu says a token expired, open that CLI once and it refreshes the token itself.

## Settings

**Update interval.** Open the dropdown and pick a value under **Update every**, from 2 minutes to 1 hour. SwiftBar reads the interval from the filename, so the plugin renames its own file. For example, `ai-usage.5m.py` becomes `ai-usage.10m.py`. There's no option below 2 minutes because both services rate limit faster polling.

**Used or remaining.** The title shows percent used. To show percent left instead, change the default in the `SHOW` line near the top of the script to `"remaining"`.

**Config folders.** If you moved the CLI config folders, the plugin reads `CLAUDE_CONFIG_DIR` and `CODEX_HOME`.

## How it works

The plugin calls the same endpoints that `claude /usage` and `codex /status` use:

- `GET https://api.anthropic.com/api/oauth/usage`
- `GET https://chatgpt.com/backend-api/wham/usage`

Neither endpoint is documented. Either one can change without notice, and then the plugin needs an update.

Requests go through `/usr/bin/curl`, so TLS checks use the macOS Keychain trust store. The token goes to curl through stdin, so it never shows up in `ps`. The last good result is saved in `~/Library/Caches/ai-usage-bar/last.json`. When a request fails, the menu keeps showing that saved data and marks the title with `*`.

## What it can't show

- Token counts. Both services report only percent of the limit. Neither publishes how many tokens 100% means.
- Chat limits on chatgpt.com. "ChatGPT" here means Codex limits on a ChatGPT plan. Message caps for the web chat aren't available from any endpoint.
- A 5-hour window for ChatGPT Pro. As of October 2026, OpenAI applies the 5-hour Codex limit only to Plus. Pro has a weekly limit only.

## Errors

| Message | Fix |
|---|---|
| `HTTP 401` | The token expired. Open `claude` or `codex` once. |
| `HTTP 403` on ChatGPT while logged in | Cloudflare blocked the request. This often happens on a VPN. Switch the VPN server or turn it off. |
| `rate limited` | Pick a longer update interval. |
| `not linked` | Log in with the CLI, as described above. |
