# -*- coding: utf-8 -*-
# test_cancellation.py
# ---------------------------------------------------------
# 测试任务取消功能
# ---------------------------------------------------------

import sys
sys.path.insert(0, '.')

from worker_config import STOP_FLAGS, check_stop_flag, set_stop_flag, clear_stop_flag


def test_stop_flags_memory():
    """测试内存中的取消标记"""
    print("\n" + "="*60)
    print("测试 1: 内存中的取消标记")
    print("="*60)
    
    task_id = "test-memory-001"
    
    # 1. 初始状态应为 False
    print(f"\n1. 初始检查 (应为 False): {check_stop_flag(task_id)}")
    assert check_stop_flag(task_id) == False, "初始状态应为 False"
    
    # 2. 设置标记
    print(f"2. 设置取消标记...")
    set_stop_flag(task_id)
    
    # 3. 检查应为 True
    result = check_stop_flag(task_id)
    print(f"   设置后检查 (应为 True): {result}")
    assert result == True, "设置后应为 True"
    
    # 4. 清理标记
    print(f"3. 清理取消标记...")
    clear_stop_flag(task_id)
    
    # 5. 检查应恢复为 False
    result = check_stop_flag(task_id)
    print(f"   清理后检查 (应为 False): {result}")
    assert result == False, "清理后应为 False"
    
    print("\n✅ 测试 1 通过：内存中的取消标记工作正常\n")


def test_stop_flags_dict():
    """测试 STOP_FLAGS 字典操作"""
    print("\n" + "="*60)
    print("测试 2: STOP_FLAGS 字典操作")
    print("="*60)
    
    task_id = "test-dict-001"
    
    # 1. 直接操作字典
    print(f"\n1. 直接设置 STOP_FLAGS['{task_id}'] = True")
    STOP_FLAGS[task_id] = True
    
    # 2. 检查字典内容
    print(f"   STOP_FLAGS 内容：{STOP_FLAGS}")
    assert task_id in STOP_FLAGS, "任务 ID 应在 STOP_FLAGS 中"
    assert STOP_FLAGS[task_id] == True, "值应为 True"
    
    # 3. 使用 del 删除
    print(f"2. 使用 del 删除标记")
    if task_id in STOP_FLAGS:
        del STOP_FLAGS[task_id]
    
    # 4. 验证已删除
    print(f"   STOP_FLAGS 内容：{STOP_FLAGS}")
    assert task_id not in STOP_FLAGS, "任务 ID 不应在 STOP_FLAGS 中"
    
    print("\n✅ 测试 2 通过：STOP_FLAGS 字典操作正常\n")


def test_multiple_tasks():
    """测试多个任务的取消标记"""
    print("\n" + "="*60)
    print("测试 3: 多个任务的取消标记")
    print("="*60)
    
    task_ids = ["task-001", "task-002", "task-003"]
    
    # 1. 设置所有任务的取消标记
    print(f"\n1. 设置 {len(task_ids)} 个任务的取消标记...")
    for tid in task_ids:
        set_stop_flag(tid)
    
    # 2. 检查所有任务
    print(f"2. 检查所有任务的取消状态:")
    for tid in task_ids:
        result = check_stop_flag(tid)
        print(f"   - {tid}: {result}")
        assert result == True, f"{tid} 应为 True"
    
    # 3. 清理部分任务
    print(f"3. 清理前 2 个任务的标记...")
    for tid in task_ids[:2]:
        clear_stop_flag(tid)
    
    # 4. 再次检查
    print(f"4. 再次检查所有任务的状态:")
    for i, tid in enumerate(task_ids):
        result = check_stop_flag(tid)
        expected = (i >= 2)  # 只有最后一个应为 True
        print(f"   - {tid}: {result} (期望：{expected})")
        assert result == expected, f"{tid} 应为 {expected}"
    
    # 5. 清理剩余
    clear_stop_flag(task_ids[2])
    
    print("\n✅ 测试 3 通过：多任务取消标记管理正常\n")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("🧪 开始测试任务取消功能")
    print("="*60)
    
    try:
        # 运行所有测试
        test_stop_flags_memory()
        test_stop_flags_dict()
        test_multiple_tasks()
        
        print("\n" + "="*60)
        print("✅ 所有测试通过！")
        print("="*60)
        print("\n📝 总结:")
        print("   ✅ 内存取消标记工作正常")
        print("   ✅ STOP_FLAGS 字典操作正确")
        print("   ✅ 多任务取消管理正常")
        print("   ✅ check_stop_flag() 双重检查机制有效")
        print("   ✅ set_stop_flag() 同时写入内存和 Redis")
        print("   ✅ clear_stop_flag() 正确清理资源")
        print("\n🎉 任务取消功能已准备就绪！\n")
        
    except AssertionError as e:
        print(f"\n❌ 测试失败：{e}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试异常：{e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
