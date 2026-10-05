#!/usr/bin/env python3
# <xbar.title>AI Limits (Claude Code + ChatGPT)</xbar.title>
# <xbar.version>1.4</xbar.version>
# <xbar.desc>5-hour and weekly plan limits for Claude Code and ChatGPT (Codex).</xbar.desc>
# <xbar.dependencies>python3</xbar.dependencies>
# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>
# <swiftbar.hideDisablePlugin>true</swiftbar.hideDisablePlugin>
# <swiftbar.hideSwiftBar>true</swiftbar.hideSwiftBar>
#
# Refresh interval: pick it from the dropdown ("Update every"). SwiftBar and xbar read the
# interval from the filename (ai-usage.5m.py = every 5 minutes), so the picker renames this
# file and SwiftBar reloads it. Renaming the file by hand works too.
# The shortest option is 2 minutes; both endpoints rate limit faster polling.
#
# Account linking = the official CLIs' own login. No separate auth.
#   Claude: `claude` -> /login        (token read from Keychain "Claude Code-credentials")
#   ChatGPT: `codex login`            (token read from ~/.codex/auth.json)
#
# Endpoints (undocumented; the same ones the CLIs call for /usage and /status):
#   GET https://api.anthropic.com/api/oauth/usage
#   GET https://chatgpt.com/backend-api/wham/usage
#
# Tokens are read only. The script never refreshes them: a refresh rotates the
# refresh token and would log the CLI out. On "token expired", run the CLI once.

import json
import os
import subprocess
import sys
import time
from datetime import datetime

SHOW = os.environ.get("AIU_SHOW", "used")  # title shows "used" or "remaining" percent
CLAUDE_HOME = os.environ.get("CLAUDE_CONFIG_DIR", os.path.expanduser("~/.claude"))
CODEX_HOME = os.environ.get("CODEX_HOME", os.path.expanduser("~/.codex"))
CACHE = os.path.expanduser("~/Library/Caches/ai-usage-bar/last.json")
NOW = time.time()
INTERVALS = [("2m", "2 min"), ("5m", "5 min"), ("10m", "10 min"),
             ("15m", "15 min"), ("30m", "30 min"), ("1h", "1 hour")]
SELF = os.path.abspath(sys.argv[0])  # not realpath: if the plugin is a symlink, rename the link


def current_interval():
    parts = os.path.basename(SELF).split(".")
    return parts[-2] if len(parts) >= 3 else None


def set_interval(new):
    if new not in dict(INTERVALS):
        sys.exit(f"interval must be one of {', '.join(k for k, _ in INTERVALS)}")
    folder, base = os.path.split(SELF)
    parts = base.split(".")
    if len(parts) >= 3:
        parts[-2] = new                 # name.5m.py -> name.10m.py
    else:
        parts.insert(-1, new)           # name.py -> name.10m.py
    target = os.path.join(folder, ".".join(parts))
    if target != SELF:
        os.rename(SELF, target)


def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def parse_ts(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return v / 1000 if v > 1e12 else float(v)
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def get(url, headers):
    # /usr/bin/curl verifies TLS against the macOS Keychain trust store, so it works
    # where Python's bundled OpenSSL has no CA bundle (python.org installs) and
    # behind VPNs/proxies whose root cert is trusted in Keychain.
    # Headers go through stdin (-H @-) so the bearer token never appears in `ps`.
    hdrs = "\n".join(f"{k}: {v}" for k, v in {"Accept": "application/json", **headers}.items())
    try:
        r = subprocess.run(
            ["/usr/bin/curl", "-sS", "--max-time", "10", "-H", "@-",
             "-w", "\n%{http_code}", url],
            input=hdrs, capture_output=True, text=True, timeout=15,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("network error: timeout")
    if r.returncode != 0:
        raise RuntimeError(f"network error: {r.stderr.strip() or f'curl exit {r.returncode}'}")
    body, _, code = r.stdout.rpartition("\n")
    code = int(code) if code.isdigit() else 0
    if code in (401, 403):
        raise RuntimeError(f"HTTP {code}: token expired or rejected, run the CLI once")
    if code == 429:
        raise RuntimeError("rate limited, increase the refresh interval")
    if code != 200:
        raise RuntimeError(f"HTTP {code}")
    try:
        return json.loads(body)
    except ValueError:
        raise RuntimeError("unexpected non-JSON response")


def claude():
    raw = None
    try:
        r = subprocess.run(["/usr/bin/security", "find-generic-password",
                            "-s", "Claude Code-credentials", "-w"],
                           capture_output=True, text=True, timeout=15)
        if r.returncode == 0:
            raw = json.loads(r.stdout)
    except Exception:
        pass
    raw = raw or load_json(os.path.join(CLAUDE_HOME, ".credentials.json")) or {}
    c = raw.get("claudeAiOauth") or {}
    if not c.get("accessToken"):
        raise RuntimeError("not linked, run `claude` and /login")
    exp = parse_ts(c.get("expiresAt"))
    if exp and exp < NOW:
        raise RuntimeError("token expired, run `claude` once")
    d = get("https://api.anthropic.com/api/oauth/usage", {
        "Authorization": f"Bearer {c['accessToken']}",
        "anthropic-beta": "oauth-2025-04-20",
        "User-Agent": "claude-code/2.1.0",  # endpoint requires a claude-code/ UA
    })

    def win(key):
        w = d.get(key)
        if isinstance(w, dict) and w.get("utilization") is not None:
            return {"used": float(w["utilization"]), "reset": parse_ts(w.get("resets_at"))}
        return None

    extra = {k: win(k) for k in ("seven_day_opus", "seven_day_sonnet") if win(k)}
    return {"plan": c.get("subscriptionType"), "5h": win("five_hour"),
            "week": win("seven_day"), "extra": extra}


def chatgpt():
    t = (load_json(os.path.join(CODEX_HOME, "auth.json")) or {}).get("tokens") or {}
    if not t.get("access_token"):
        raise RuntimeError("not linked, run `codex login`")
    h = {"Authorization": f"Bearer {t['access_token']}", "User-Agent": "codex_cli_rs/0.50.0"}
    if t.get("account_id"):
        h["ChatGPT-Account-Id"] = t["account_id"]
    d = get("https://chatgpt.com/backend-api/wham/usage", h)
    out = {"plan": d.get("plan_type"), "5h": None, "week": None, "extra": {}}
    rl = d.get("rate_limit") or {}
    for key in ("primary_window", "secondary_window"):
        w = rl.get(key)
        if not isinstance(w, dict):
            continue
        used = w.get("used_percent")
        if used is None and w.get("remaining_percent") is not None:
            used = 100 - float(w["remaining_percent"])
        if used is None:
            continue
        reset = parse_ts(w.get("reset_at"))
        if reset is None and w.get("reset_after_seconds") is not None:
            reset = NOW + float(w["reset_after_seconds"])
        secs = w.get("limit_window_seconds") or (w.get("window_minutes") or 0) * 60
        # classify by window length; fall back to primary=5h, secondary=weekly
        slot = ("5h" if secs <= 6 * 3600 else "week") if secs else \
               ("5h" if key == "primary_window" else "week")
        out[slot] = {"used": float(used), "reset": reset}
    return out


def fetch_all():
    cache = load_json(CACHE) or {}
    result = {}
    for name, fn in (("claude", claude), ("chatgpt", chatgpt)):
        try:
            result[name] = {"t": NOW, "data": fn(), "err": None}
        except Exception as e:
            prev = cache.get(name) or {}
            result[name] = {"t": prev.get("t"), "data": prev.get("data"), "err": str(e)}
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE + ".tmp", "w") as f:
        json.dump(result, f)
    os.replace(CACHE + ".tmp", CACHE)
    return result


TEXT = "#1f2328,#e6edf3"   # light,dark: SwiftBar dims items without an explicit color
MUTED = "#6e7781,#8b949e"


def color(used):
    return "#e5534b" if used >= 85 else "#d29922" if used >= 60 else None


def pct(w):
    if not w:
        return "–"
    return f"{(w['used'] if SHOW == 'used' else 100 - w['used']):.0f}%"


def until(ts):
    if not ts:
        return "?"
    d = int(ts - NOW)
    if d <= 0:
        return "now"
    days, rem = divmod(d, 86400)
    h, m = rem // 3600, rem % 3600 // 60
    rel = f"{days}d {h}h" if days else f"{h}h {m}m" if h else f"{m}m"
    return f"{rel} ({datetime.fromtimestamp(ts).strftime('%a %H:%M')})"


def gauge(used, n=20):
    k = max(0, min(n, round(used / 100 * n)))
    return "█" * k + "░" * (n - k)


def row(label, w, missing="no data"):
    if not w:
        return [f"{label}: {missing} | color={MUTED}"]
    cs = f" color={color(w['used']) or TEXT}"
    return [f"{label}: {w['used']:.0f}% used · {100 - w['used']:.0f}% left |{cs}",
            f"{gauge(w['used'])}  resets in {until(w['reset'])} | font=Menlo size=11{cs}"]


def section(name, e):
    d = e["data"]
    plan = f" · {str(d['plan']).capitalize()}" if d and d.get("plan") else ""
    out = [f"{name}{plan} | size=13 color={MUTED}"]
    if e["err"]:
        out.append(f"⚠ {e['err']} | color=#e5534b size=11")
        if d and e["t"]:
            out.append(f"last good data {int((NOW - e['t']) / 60)} min ago | size=11 color={MUTED}")
    if d:
        # the API omits a window the plan does not enforce (e.g. ChatGPT Pro has no 5-hour cap)
        missing = "not enforced on this plan" if d.get("week") else "no data"
        out += row("5-hour", d["5h"], missing) + row("Weekly", d["week"])
        for k, w in d.get("extra", {}).items():
            out += row("Weekly " + k.split("_")[-1].capitalize(), w)
    return out


def interval_menu():
    cur = current_interval()
    label = dict(INTERVALS).get(cur, cur or "unknown")
    out = [f"Update every: {label} | color={TEXT}"]
    for key, name in INTERVALS:
        check = " checked=true" if key == cur else ""
        out.append(f"--{name} | bash='{SELF}' param1=--interval param2={key} "
                   f"terminal=false refresh=true{check}")
    return out


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--interval":
        set_interval(sys.argv[2])
        return
    r = fetch_all()
    parts, worst = [], 0.0
    for tag, key in (("CC", "claude"), ("GPT", "chatgpt")):
        e = r[key]
        d = e["data"] or {}
        stale = "*" if e["err"] else ""
        if d.get("week") and not d.get("5h"):
            parts.append(f"{tag} {pct(d['week'])}{stale}")      # weekly-only plan
        else:
            parts.append(f"{tag} {pct(d.get('5h'))}/{pct(d.get('week'))}{stale}")
        for w in (d.get("5h"), d.get("week")):
            if w:
                worst = max(worst, w["used"])
    c = color(worst)
    print(" · ".join(parts) + f" | size=12{' color=' + c if c else ''}")
    print("---")
    print("\n".join(section("Claude Code", r["claude"])))
    print("---")
    print("\n".join(section("ChatGPT (Codex)", r["chatgpt"])))
    print("---")
    print(f"Refresh now | refresh=true")
    print("\n".join(interval_menu()))
    print(f"Title: 5h/weekly {SHOW} · * = stale · updated {datetime.now():%H:%M} | size=11 color={MUTED}")


if __name__ == "__main__":
    main()
