"""意图路由 + 临时记忆 覆盖度测试"""
import sys, os, tempfile
sys.path.insert(0, 'python_worker')

from intent_router import IntentRouter
from temp_session_memory import get_temp_memory

print('=' * 60)
print('当前 Intent Router 覆盖度测试')
print('=' * 60)

test_cases = [
    ('approval+execute', '很好就按照你所说的执行吧，但是一户一票/一人一票。选择一人一票这样才更民主'),
    ('confirm+run',      '对的，运行吧。'),
    ('continue',         '请继续进行。'),
    ('continue2',        '继续往下写'),
    ('ok_go',            '好的，开始吧'),
    ('ok_implement',     'OK，按这个方案实现代码'),
    ('modify',           '把上面那个投票规则改成一户一票'),
    ('approval_only',    '不错，这个方案可以'),
    ('simple_go',        '执行'),
    ('run_code',         '运行'),
    ('go_ahead',         '开始写代码吧'),
    ('lets_do_it',       '我们来实现吧'),
    ('yes_continue',     '是的，请继续'),
]

issues = []
for label, prompt in test_cases:
    intent, persona, chain = IntentRouter.detect_intent(prompt)
    status = 'OK' if intent == 'write_code' else 'MISS'
    if intent != 'write_code':
        issues.append((label, prompt, intent))
    print(f'  [{status:4s}] {label:18s} => intent={intent:20s} persona={persona:12s} | {prompt[:60]} ({chain[0] if chain else "none"})')

print()

print('=' * 60)
print('Intent Router MISS 列表')
print('=' * 60)
for label, prompt, intent in issues:
    print(f'  [{label}] "{prompt}" -> {intent}')

print()

print('=' * 60)
print('临时记忆搜索覆盖度测试')
print('=' * 60)

with tempfile.TemporaryDirectory() as tmpdir:
    os.environ['ALPHAPILOT_TEMP_MEMORY_DIR'] = tmpdir
    mem = get_temp_memory()
    store = mem.get_or_create_store('d:\\election_project')

    mem.append(store, 'task-1',
        prompt='帮我设计一个村民选举投票系统',
        summary='架构设计完成: domain/enums.py, models.py, policies.py...',
        intent='architecture',
        result_preview='village_election_system/domain/... 定义了ElectionStatus等枚举和模型')

    mem.append(store, 'task-2',
        prompt='请执行上面内容代码编写',
        summary='代码编写完成: 实现了voter票权管理模块',
        intent='write_code',
        result_preview='voter/service.py 实现了票权状态机和一人一票/一户一票策略')

    search_queries = [
        '很好就按照你所说的执行吧',
        '对的，运行吧',
        '请继续进行',
        '继续往下写',
        '把上面那个投票规则改成一户一票',
        '好的，开始吧',
        'OK，按这个方案实现代码',
        '执行',
        '运行',
    ]

    mem_issues = []
    for query in search_queries:
        results = mem.search(store, query, top_k=3)
        ok = "OK" if results else "MISS"
        if not results:
            mem_issues.append(query)
        print(f'  [{ok:4s}] "{query[:50]}" => {len(results)}条')

print()

print('=' * 60)
print('临时记忆 MISS 列表')
print('=' * 60)
for q in mem_issues:
    print(f'  "{q}" -> 0 results')

print()
total = len(issues) + len(mem_issues)
if total:
    print(f'共计 {total} 个覆盖盲区需要修复 (Intent: {len(issues)}, Memory: {len(mem_issues)})')
else:
    print('全部覆盖 OK')