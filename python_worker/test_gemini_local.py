# -*- coding: utf-8 -*-
import sys, time
sys.path.insert(0, '.')
from intent_router import IntentRouter

print('=' * 70)
print('  Gemini + Local LLM 语义分类实测')
print('=' * 70)

# Test 1: Gemini
t0 = time.time()
print('\n[1] Gemini (gemini-3.5-flash via Proxy)')
print('    prompt: 把代码里console.log全清掉')
r = IntentRouter._llm_classify('把代码里console.log全清掉', model_name='gemini')
t1 = time.time()
if r:
    print(f'    PASS  {t1-t0:.1f}s  intent={r["intent"]:16s} type={r["target_type"]:8s} conf={r["confidence"]:.2f}')
    print(f'         reason: {r["reasoning"]}')
else:
    print(f'    FAIL  {t1-t0:.1f}s  不可用（降级Regex）')

# Test 2: Local LLM  
t0 = time.time()
print('\n[2] Local LLM (via LM Studio)')
print('    prompt: docker-compose.yml 里没配 Redis，加一个')
r = IntentRouter._llm_classify('docker-compose.yml 里没配 Redis，加一个', model_name='local')
t1 = time.time()
if r:
    print(f'    PASS  {t1-t0:.1f}s  intent={r["intent"]:16s} type={r["target_type"]:8s} conf={r["confidence"]:.2f}')
    print(f'         reason: {r["reasoning"]}')
else:
    print(f'    FAIL  {t1-t0:.1f}s  不可用（降级Regex）')

# Test 3: detect_intent with Gemini
print('\n[3] detect_intent via Gemini')
i, p, c = IntentRouter.detect_intent('把代码里console.log全清掉', model_name='gemini')
print(f'    intent={i}')

# Test 4: detect_intent with Local
print('\n[4] detect_intent via Local')
i, p, c = IntentRouter.detect_intent('docker-compose.yml 里没配 Redis，加一个', model_name='local')
print(f'    intent={i}')