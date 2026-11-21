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

def stream_probe(name, base_url, key, model, timeout=60):
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
    first_content_at = None
    content_parts = []
    reasoning_parts = []
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
                    rc = delta.get("reasoning_content")
                    if rc:
                        reasoning_parts.append(rc)
                    if c:
                        if first_content_at is None:
                            first_content_at = time.time() - t0
                        content_parts.append(c)
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
        total = time.time() - t0
        content = "".join(content_parts)
        reasoning = "".join(reasoning_parts)
        return (f"[{name} {model}] => 200 total={total:.1f}s "
                f"first_content={('%.1fs' % first_content_at) if first_content_at is not None else 'N/A'} "
                f"content={content[:60]!r} reasoning_len={len(reasoning)}")
    except urllib.error.HTTPError as e:
        return f"[{name} {model}] => {e.code} :: {e.read().decode('utf-8','replace')[:140]}"
    except Exception as e:
        return f"[{name} {model}] => ERR :: {repr(e)[:160]}"

TENCENT_URL = env.get("TENCENT_MAAS_BASE_URL", "")
TENCENT_KEY = env.get("TENCENT_MAAS_API_KEY", "")
for m in ["deepseek-v4.1-flash", "deepseek-v4.1-flash-1017"]:
    print(stream_probe("tencent_maas", TENCENT_URL, TENCENT_KEY, m))