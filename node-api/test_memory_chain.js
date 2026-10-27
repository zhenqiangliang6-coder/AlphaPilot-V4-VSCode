/**
 * AlphaPilot 生产记忆链路冒烟验证（独立 Prisma 脚本）
 *
 * 用途：被 Python run_smoke_e2e.py --full 通过 subprocess 调用，
 *       验证 Node.js → Prisma → PostgreSQL 真实生产链路。
 *
 * 不依赖 Express / Redis / WebSocket，仅测试 Prisma ORM 层。
 *
 * 输出：
 *   stdout: JSON { ok: true } 或 { ok: false, step: "...", error: "..." }
 *   退出码: 0=成功, 1=失败
 */

const path = require("path");
require("dotenv").config({ path: path.resolve(__dirname, ".env"), quiet: true });

const { PrismaClient } = require("@prisma/client");
const { v4: uuidv4 } = require("uuid");

const PRISMA = new PrismaClient({});

const TEST_PREFIX = "smoke_e2e_test";
const TEST_EXTERNAL_ID = `${TEST_PREFIX}_${Date.now()}`;

async function main() {
  // ==========================================
  // Step 1: 创建测试用户
  // ==========================================
  /** @type {import('@prisma/client').User} */
  let user;
  try {
    user = await PRISMA.user.create({
      data: {
        external_id: TEST_EXTERNAL_ID,
        name: "Smoke Test User",
        preferences: { language: "zh-CN", editor: "vscode" },
      },
    });
    console.error(`[smoke-memory] ✅ 用户已创建: id=${user.id}`);
  } catch (err) {
    return fail("create_user", err);
  }

  // ==========================================
  // Step 2: 创建测试项目
  // ==========================================
  /** @type {import('@prisma/client').Project} */
  let project;
  try {
    project = await PRISMA.project.create({
      data: {
        user_id: user.id,
        name: "Smoke Test Project",
        root_path: "/tmp/smoke_project",
        tech_stack: { language: "python", framework: "fastapi" },
      },
    });
    console.error(`[smoke-memory] ✅ 项目已创建: id=${project.id}`);
  } catch (err) {
    await cleanup(user.id, null, null);
    return fail("create_project", err);
  }

  // ==========================================
  // Step 3: 创建项目记忆
  // ==========================================
  try {
    await PRISMA.memory.create({
      data: {
        owner_type: "project",
        project_id: project.id,
        memory_type: "rule",
        content: "项目使用 FastAPI + SQLAlchemy，禁止裸 except",
        importance: 4,
      },
    });
    console.error(`[smoke-memory] ✅ 项目记忆已创建`);
  } catch (err) {
    await cleanup(user.id, project.id, null);
    return fail("create_memory", err);
  }

  // ==========================================
  // Step 4: 创建测试任务
  // ==========================================
  const taskId = uuidv4();
  /** @type {import('@prisma/client').Task} */
  let task;
  try {
    task = await PRISMA.task.create({
      data: {
        id: taskId,
        user_id: user.id,
        project_id: project.id,
        source: "smoke_test",
        model: "qwen-turbo",
        prompt: "帮我实现一个 FastAPI 的用户注册接口",
        status: "done",
        result_summary: "已创建 POST /register 端点，包含邮箱验证",
      },
    });
    console.error(`[smoke-memory] ✅ 任务已创建: id=${taskId}`);
  } catch (err) {
    await cleanup(user.id, project.id, null);
    return fail("create_task", err);
  }

  // ==========================================
  // Step 5: 创建任务步骤
  // ==========================================
  try {
    await PRISMA.taskStep.create({
      data: {
        task_id: taskId,
        step_type: "write",
        status: "done",
        input: { prompt: task.prompt },
        output: { files: ["src/routes.py"] },
      },
    });
    console.error(`[smoke-memory] ✅ 任务步骤已创建`);
  } catch (err) {
    await cleanup(user.id, project.id, taskId);
    return fail("create_step", err);
  }

  // ==========================================
  // Step 6: loadContextForWorker — 验证跨轮检索
  // ==========================================
  try {
    const ctx = await loadContextForWorker(taskId);

    if (!ctx) {
      await cleanup(user.id, project.id, taskId);
      return fail("load_context", new Error("loadContextForWorker 返回空"));
    }

    if (!ctx.project_context || !ctx.project_context.name) {
      await cleanup(user.id, project.id, taskId);
      return fail("load_context", new Error("project_context 缺失 name 字段"));
    }

    if (
      !ctx.memory_context ||
      !Array.isArray(ctx.memory_context.project_memories) ||
      ctx.memory_context.project_memories.length === 0
    ) {
      await cleanup(user.id, project.id, taskId);
      return fail(
        "load_context",
        new Error("project_memories 为空，项目记忆检索失败")
      );
    }

    const mem = ctx.memory_context.project_memories[0];
    console.error(
      `[smoke-memory] ✅ loadContextForWorker 通过: project=${ctx.project_context.name}, ` +
        `memories=${ctx.memory_context.project_memories.length}, ` +
        `top_memory="${(mem.content || "").slice(0, 40)}..."`
    );
  } catch (err) {
    await cleanup(user.id, project.id, taskId);
    return fail("load_context", err);
  }

  // ==========================================
  // Step 7: 查询任务历史（验证持久化）
  // ==========================================
  try {
    const tasks = await PRISMA.task.findMany({
      where: { project_id: project.id },
      orderBy: { created_at: "desc" },
    });

    if (tasks.length === 0) {
      await cleanup(user.id, project.id, taskId);
      return fail("query_history", new Error("按项目查询任务为空"));
    }

    const found = tasks.find((t) => t.id === taskId);
    if (!found) {
      await cleanup(user.id, project.id, taskId);
      return fail("query_history", new Error("按 ID 未找到已创建的任务"));
    }

    console.error(
      `[smoke-memory] ✅ 任务历史查询通过: ${tasks.length} 条记录`
    );
  } catch (err) {
    await cleanup(user.id, project.id, taskId);
    return fail("query_history", err);
  }

  // ==========================================
  // Step 8: 清理
  // ==========================================
  await cleanup(user.id, project.id, taskId);

  console.error(`[smoke-memory] 🎉 生产记忆链路全部通过`);
  process.stdout.write(JSON.stringify({ ok: true }) + "\n");
  process.exit(0);
}

// ==========================================
// loadContextForWorker（精简版，与 memoryService.js 逻辑一致）
// ==========================================
async function loadContextForWorker(taskId) {
  const task = await PRISMA.task.findUnique({
    where: { id: taskId },
    include: {
      user: true,
      project: {
        include: {
          memories: {
            orderBy: { importance: "desc" },
            take: 10,
          },
        },
      },
    },
  });

  if (!task) {
    throw new Error(`任务不存在: ${taskId}`);
  }

  const userPreferences = task.user?.preferences || {};
  const projectMemories = task.project?.memories || [];

  const recentTasks = await PRISMA.task.findMany({
    where: {
      project_id: task.project_id,
      id: { not: taskId },
    },
    orderBy: { created_at: "desc" },
    take: 5,
    select: {
      prompt: true,
      result_summary: true,
      model: true,
    },
  });

  return {
    system_context: "你是 AlphaPilot，一个专业的 AI 编程助手。",
    project_context: {
      name: task.project?.name,
      tech_stack: task.project?.tech_stack,
      metadata: task.project?.metadata,
    },
    memory_context: {
      user_preferences: userPreferences,
      project_memories: projectMemories.map((m) => ({
        type: m.memory_type,
        content: m.content,
        importance: m.importance,
      })),
      recent_tasks: recentTasks,
      similar_tasks: [],
    },
    semantic_context: {},
  };
}

// ==========================================
// 清理
// ==========================================
async function cleanup(userId, projectId, taskId) {
  const errors = [];

  if (taskId) {
    try {
      await PRISMA.taskStep.deleteMany({ where: { task_id: taskId } });
    } catch (e) {
      errors.push("taskStep: " + e.message);
    }
    try {
      await PRISMA.taskFileOp.deleteMany({ where: { task_id: taskId } });
    } catch (e) {
      errors.push("taskFileOp: " + e.message);
    }
    try {
      await PRISMA.fileVersion.deleteMany({ where: { task_id: taskId } });
    } catch (e) {
      errors.push("fileVersion: " + e.message);
    }
    try {
      await PRISMA.memory.deleteMany({ where: { task_id: taskId } });
    } catch (e) {
      errors.push("memory(task): " + e.message);
    }
    try {
      await PRISMA.task.deleteMany({ where: { id: taskId } });
    } catch (e) {
      errors.push("task: " + e.message);
    }
  }

  if (projectId) {
    try {
      await PRISMA.memory.deleteMany({ where: { project_id: projectId } });
    } catch (e) {
      errors.push("memory(project): " + e.message);
    }
    try {
      await PRISMA.file.deleteMany({ where: { project_id: projectId } });
    } catch (e) {
      errors.push("file: " + e.message);
    }
    try {
      await PRISMA.project.deleteMany({ where: { id: projectId } });
    } catch (e) {
      errors.push("project: " + e.message);
    }
  }

  if (userId) {
    try {
      await PRISMA.memory.deleteMany({ where: { user_id: userId } });
    } catch (e) {
      errors.push("memory(user): " + e.message);
    }
    try {
      await PRISMA.user.deleteMany({ where: { id: userId } });
    } catch (e) {
      errors.push("user: " + e.message);
    }
  }

  try {
    await PRISMA.$disconnect();
  } catch (_) {
    // ignore
  }

  if (errors.length > 0) {
    console.error(`[smoke-memory] ⚠️ 清理警告: ${errors.join("; ")}`);
  } else {
    console.error(`[smoke-memory] 🧹 清理完成`);
  }
}

// ==========================================
// 失败处理
// ==========================================
function fail(step, err) {
  console.error(`[smoke-memory] ❌ 失败于 ${step}: ${err.message}`);
  process.stdout.write(
    JSON.stringify({ ok: false, step, error: err.message }) + "\n"
  );
  process.exit(1);
}

// ==========================================
// 启动
// ==========================================
main().catch(async (err) => {
  console.error(`[smoke-memory] ❌ 未预期错误: ${err.message}`);
  process.stdout.write(
    JSON.stringify({ ok: false, step: "fatal", error: err.message }) + "\n"
  );
  try {
    await PRISMA.$disconnect();
  } catch (_) {}
  process.exit(1);
});