import psycopg2
import sys

def clear_project_tasks(project_name_pattern="shopflow"):
    """清除指定项目的所有历史任务和记忆，确保测试从零开始"""
    conn = psycopg2.connect(
        host='localhost', port=5433,
        dbname='alphapilot_copilot_memory',
        user='alphapilot', password='alphapilot_memory_2026'
    )
    cur = conn.cursor()

    # 1. 找到目标项目
    cur.execute('SELECT id, name FROM "Project" WHERE LOWER(name) LIKE %s', (f'%{project_name_pattern}%',))
    projects = cur.fetchall()

    if not projects:
        print(f"[MEMORY_CLEAN] 未找到匹配 '{project_name_pattern}' 的项目")
        conn.close()
        return

    for pid, pname in projects:
        print(f"[MEMORY_CLEAN] 项目: {pname} (id={pid})")

        # 2. 删除所有任务
        cur.execute('DELETE FROM "Task" WHERE project_id = %s', (pid,))
        task_count = cur.rowcount
        print(f"  - 已清除 {task_count} 个任务")

        # 3. 删除项目记忆
        cur.execute('DELETE FROM "Memory" WHERE project_id = %s', (pid,))
        mem_count = cur.rowcount
        print(f"  - 已清除 {mem_count} 条项目记忆")

        # 4. 清除 memory_items（使用项目路径 hash 作为 user_id）
        #    MEMORY 模块的 user_id 是从项目路径 hash 而来
        #    这里按 project name 模糊匹配清除
        #    不删除 entire memory_items，因为可能跨项目共享

        conn.commit()

    print(f"[MEMORY_CLEAN] 完成：已清除 {sum(1 for _ in projects)} 个项目的数据")
    conn.close()
    return True


if __name__ == "__main__":
    pattern = sys.argv[1] if len(sys.argv) > 1 else "shopflow"
    clear_project_tasks(pattern)