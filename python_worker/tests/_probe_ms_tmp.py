import os, json, urllib.request, urllib.error, time

def load_env(path):
    d = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            d[k.strip()] = v.strip()
    return d

env = load_env(os.path.join(os.path.dirname(__file__), "..", ".env"))

def probe(base_url, key, model, timeout=60):
    url = base_url.rstrip("/") + "/chat/completions"
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": "用一句话回答：1+1=?"}],
        "stream": True,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {key}")
    t0 = time.time()
    first = None
    parts = []
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            for line in r:
                line = line.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    delta = chunk["choices"][0].get("delta", {})
                    c = delta.get("content")
                    if c:
                        if first is None:
                            first = time.time() - t0
                        parts.append(c)
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
        total = time.time() - t0
        return f"[OK {model}] 200 total={total:.1f}s first={first and ('%.1fs' % first)} content={''.join(parts)[:50]!r}"
    except urllib.error.HTTPError as e:
        return f"[FAIL {model}] {e.code} :: {e.read().decode('utf-8','replace')[:120]}"
    except Exception as e:
        return f"[ERR {model}] {repr(e)[:120]}"

BASE = env.get("MODELSCOPE_BASE_URL", "")
KEY = env.get("MODELSCOPE_API_KEY", "")
models = [
    "Qwen/Qwen3.8-Flash-Next",
    "Qwen/Qwen3.8-27B",
    "Qwen/Qwen3.5-27B",
    "Qwen/Qwen3.5-35B-A3B",
]
for m in models:
    print(probe(BASE, KEY, m))