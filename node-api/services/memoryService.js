// node-api/services/memoryService.js

const { PrismaClient } = require('@prisma/client');

// 创建 Prisma 客户端实例（Prisma 7.x 需要传入配置对象）
const prisma = new PrismaClient({});

/**
 * Memory Service - AlphaPilot OS 的记忆大脑
 * 
 * 负责：
 * - 写入任务记忆
 * - 写入项目记忆
 * - 写入用户偏好
 * - 写入文件版本
 * - 查询项目/用户/语义记忆
 */

// =======================
// 用户层操作
// =======================

/**
 * 创建或获取用户
 * @param {string} externalId - VSCode/GitHub 用户标识
 * @param {string} name - 用户名
 * @param {object} preferences - 用户偏好
 */
async function getOrCreateUser(externalId, name = null, preferences = {}) {
  try {
    let user = await prisma.user.findUnique({
      where: { external_id: externalId }
    });

    if (!user) {
      user = await prisma.user.create({
        data: {
          external_id: externalId,
          name: name || externalId,
          preferences: preferences
        }
      });
      console.log(`[Memory] 创建新用户: ${externalId}`);
    }

    return user;
  } catch (error) {
    console.error('[Memory] 获取用户失败:', error);
    throw error;
  }
}

/**
 * 更新用户偏好
 * @param {number} userId - 用户ID
 * @param {object} preferences - 新的偏好设置
 */
async function updateUserPreferences(userId, preferences) {
  try {
    const user = await prisma.user.update({
      where: { id: userId },
      data: { preferences }
    });
    console.log(`[Memory] 更新用户偏好: userId=${userId}`);
    return user;
  } catch (error) {
    console.error('[Memory] 更新用户偏好失败:', error);
    throw error;
  }
}

/**
 * 获取用户偏好
 * @param {number} userId - 用户ID
 */
async function getUserPreferences(userId) {
  try {
    const user = await prisma.user.findUnique({
      where: { id: userId },
      select: { preferences: true }
    });
    return user?.preferences || {};
  } catch (error) {
    console.error('[Memory] 获取用户偏好失败:', error);
    return {};
  }
}

// =======================
// 项目层操作
// =======================

/**
 * 创建或获取项目
 * @param {number} userId - 用户ID
 * @param {string} name - 项目名称
 * @param {string} rootPath - 项目根路径
 * @param {object} techStack - 技术栈
 */
async function getOrCreateProject(userId, name, rootPath, techStack = {}) {
  try {
    let project = await prisma.project.findFirst({
      where: {
        user_id: userId,
        root_path: rootPath
      }
    });

    if (!project) {
      project = await prisma.project.create({
        data: {
          user_id: userId,
          name: name,
          root_path: rootPath,
          tech_stack: techStack
        }
      });
      console.log(`[Memory] 创建新项目: ${name} (${rootPath})`);
    }

    return project;
  } catch (error) {
    console.error('[Memory] 获取项目失败:', error);
    throw error;
  }
}

/**
 * 更新项目元数据
 * @param {number} projectId - 项目ID
 * @param {object} metadata - 项目元数据（代码规范、目录约定等）
 */
async function updateProjectMetadata(projectId, metadata) {
  try {
    const project = await prisma.project.update({
      where: { id: projectId },
      data: { metadata }
    });
    console.log(`[Memory] 更新项目元数据: projectId=${projectId}`);
    return project;
  } catch (error) {
    console.error('[Memory] 更新项目元数据失败:', error);
    throw error;
  }
}

/**
 * 获取项目记忆
 * @param {number} projectId - 项目ID
 */
async function getProjectMemory(projectId) {
  try {
    const project = await prisma.project.findUnique({
      where: { id: projectId },
      include: {
        memories: {
          orderBy: { created_at: 'desc' },
          take: 20
        }
      }
    });

    return {
      project,
      memories: project?.memories || []
    };
  } catch (error) {
    console.error('[Memory] 获取项目记忆失败:', error);
    return { project: null, memories: [] };
  }
}

// =======================
// 任务层操作
// =======================

/**
 * 创建任务
 * @param {string} taskId - 任务ID (UUID)
 * @param {number} userId - 用户ID
 * @param {number} projectId - 项目ID
 * @param {string} prompt - 用户提示
 * @param {string} model - 使用的模型
 * @param {string} source - 任务来源 (react-webview / api / cli)
 */
async function createTask(taskId, userId, projectId, prompt, model, source = 'react-webview') {
  try {
    const task = await prisma.task.create({
      data: {
        id: taskId,
        user_id: userId,
        project_id: projectId,
        prompt: prompt,
        model: model,
        source: source,
        status: 'pending'
      }
    });
    console.log(`[Memory] 创建任务: ${taskId}`);
    return task;
  } catch (error) {
    console.error('[Memory] 创建任务失败:', error);
    throw error;
  }
}

/**
 * 更新任务状态
 * @param {string} taskId - 任务ID
 * @param {string} status - 任务状态 (pending/running/done/failed)
 * @param {string} resultSummary - 任务结果摘要
 */
async function updateTaskStatus(taskId, status, resultSummary = null) {
  try {
    const task = await prisma.task.update({
      where: { id: taskId },
      data: {
        status: status,
        result_summary: resultSummary,
        finished_at: status === 'done' || status === 'failed' ? new Date() : null
      }
    });
    console.log(`[Memory] 更新任务状态: ${taskId} -> ${status}`);
    return task;
  } catch (error) {
    console.error('[Memory] 更新任务状态失败:', error);
    throw error;
  }
}

/**
 * 获取任务详情
 * @param {string} taskId - 任务ID
 */
async function getTask(taskId) {
  try {
    const task = await prisma.task.findUnique({
      where: { id: taskId },
      include: {
        steps: {
          orderBy: { created_at: 'asc' }
        },
        file_ops: {
          orderBy: { created_at: 'asc' }
        },
        user: true,
        project: true
      }
    });
    return task;
  } catch (error) {
    console.error('[Memory] 获取任务失败:', error);
    return null;
  }
}

/**
 * 获取用户的任务历史
 * @param {number} userId - 用户ID
 * @param {number} limit - 限制数量
 */
async function getUserTasks(userId, limit = 50) {
  try {
    const tasks = await prisma.task.findMany({
      where: { user_id: userId },
      orderBy: { created_at: 'desc' },
      take: limit,
      include: {
        project: {
          select: { name: true }
        }
      }
    });
    return tasks;
  } catch (error) {
    console.error('[Memory] 获取用户任务历史失败:', error);
    return [];
  }
}

// =======================
// 执行链层操作 (Steps)
// =======================

/**
 * 创建任务步骤
 * @param {string} taskId - 任务ID
 * @param {string} stepType - 步骤类型 (analyze/plan/write/refine/test/fix/doc/docstring)
 * @param {object} input - 步骤输入
 */
async function createTaskStep(taskId, stepType, input = {}) {
  try {
    const step = await prisma.taskStep.create({
      data: {
        task_id: taskId,
        step_type: stepType,
        status: 'pending',
        input: input
      }
    });
    console.log(`[Memory] 创建步骤: ${taskId} -> ${stepType}`);
    return step;
  } catch (error) {
    console.error('[Memory] 创建步骤失败:', error);
    throw error;
  }
}

/**
 * 更新步骤状态和输出
 * @param {number} stepId - 步骤ID
 * @param {string} status - 步骤状态
 * @param {object} output - 步骤输出（结构化 JSON）
 */
async function updateTaskStep(stepId, status, output = {}) {
  try {
    const step = await prisma.taskStep.update({
      where: { id: stepId },
      data: {
        status: status,
        output: output,
        finished_at: status === 'done' || status === 'failed' ? new Date() : null
      }
    });
    console.log(`[Memory] 更新步骤状态: stepId=${stepId} -> ${status}`);
    return step;
  } catch (error) {
    console.error('[Memory] 更新步骤状态失败:', error);
    throw error;
  }
}

/**
 * 获取任务的步骤列表
 * @param {string} taskId - 任务ID
 */
async function getTaskSteps(taskId) {
  try {
    const steps = await prisma.taskStep.findMany({
      where: { task_id: taskId },
      orderBy: { created_at: 'asc' }
    });
    return steps;
  } catch (error) {
    console.error('[Memory] 获取任务步骤失败:', error);
    return [];
  }
}

// =======================
// FileOps 层操作
// =======================

/**
 * 记录文件操作
 * @param {string} taskId - 任务ID
 * @param {number} stepId - 步骤ID
 * @param {string} op - 操作类型 (create/update/delete)
 * @param {string} path - 文件路径
 * @param {string} role - 文件角色 (main/test/doc/config/meta)
 * @param {string} reason - 操作原因
 * @param {string} fromStep - 来源步骤
 */
async function recordFileOp(taskId, stepId, op, path, role = null, reason = null, fromStep = null) {
  try {
    const fileOp = await prisma.taskFileOp.create({
      data: {
        task_id: taskId,
        step_id: stepId,
        op: op,
        path: path,
        role: role,
        reason: reason,
        from_step: fromStep
      }
    });
    console.log(`[Memory] 记录文件操作: ${op} ${path}`);
    return fileOp;
  } catch (error) {
    console.error('[Memory] 记录文件操作失败:', error);
    throw error;
  }
}

/**
 * 获取任务的文件操作列表
 * @param {string} taskId - 任务ID
 */
async function getTaskFileOps(taskId) {
  try {
    const fileOps = await prisma.taskFileOp.findMany({
      where: { task_id: taskId },
      orderBy: { created_at: 'asc' }
    });
    return fileOps;
  } catch (error) {
    console.error('[Memory] 获取任务文件操作失败:', error);
    return [];
  }
}

// =======================
// 文件层操作
// =======================

/**
 * 创建或获取文件身份
 * @param {number} projectId - 项目ID
 * @param {string} filePath - 文件路径
 */
async function getOrCreateFile(projectId, filePath) {
  try {
    let file = await prisma.file.findFirst({
      where: {
        project_id: projectId,
        path: filePath
      }
    });

    if (!file) {
      file = await prisma.file.create({
        data: {
          project_id: projectId,
          path: filePath
        }
      });
      console.log(`[Memory] 创建文件身份: ${filePath}`);
    }

    return file;
  } catch (error) {
    console.error('[Memory] 获取文件身份失败:', error);
    throw error;
  }
}

/**
 * 保存文件版本
 * @param {number} fileId - 文件ID
 * @param {string} taskId - 任务ID
 * @param {number} stepId - 步骤ID
 * @param {string} content - 文件内容
 * @param {string} hash - 内容哈希值
 */
async function saveFileVersion(fileId, taskId, stepId, content, hash = null) {
  try {
    const version = await prisma.fileVersion.create({
      data: {
        file_id: fileId,
        task_id: taskId,
        step_id: stepId,
        content: content,
        hash: hash
      }
    });

    // 更新文件的当前版本
    await prisma.file.update({
      where: { id: fileId },
      data: { current_version_id: version.id }
    });

    console.log(`[Memory] 保存文件版本: fileId=${fileId}, versionId=${version.id}`);
    return version;
  } catch (error) {
    console.error('[Memory] 保存文件版本失败:', error);
    throw error;
  }
}

/**
 * 获取文件版本历史
 * @param {number} fileId - 文件ID
 * @param {number} limit - 限制数量
 */
async function getFileVersions(fileId, limit = 10) {
  try {
    const versions = await prisma.fileVersion.findMany({
      where: { file_id: fileId },
      orderBy: { created_at: 'desc' },
      take: limit
    });
    return versions;
  } catch (error) {
    console.error('[Memory] 获取文件版本历史失败:', error);
    return [];
  }
}

// =======================
// 长期记忆层操作
// =======================

/**
 * 创建记忆
 * @param {string} ownerType - 所有者类型 (user/project/task)
 * @param {number|string} ownerId - 所有者ID
 * @param {string} memoryType - 记忆类型 (preference/rule/summary/pattern)
 * @param {string} content - 记忆内容
 * @param {number} importance - 重要性 (1-5)
 */
async function createMemory(ownerType, ownerId, memoryType, content, importance = 1) {
  try {
    const data = {
      owner_type: ownerType,
      memory_type: memoryType,
      content: content,
      importance: importance
    };

    // 根据 owner_type 设置对应的 ID 字段
    if (ownerType === 'user') {
      data.user_id = ownerId;
    } else if (ownerType === 'project') {
      data.project_id = ownerId;
    } else if (ownerType === 'task') {
      data.task_id = ownerId;
    }

    const memory = await prisma.memory.create({
      data: data
    });

    console.log(`[Memory] 创建记忆: ${ownerType}/${ownerId} -> ${memoryType}`);
    return memory;
  } catch (error) {
    console.error('[Memory] 创建记忆失败:', error);
    throw error;
  }
}

/**
 * 查询项目记忆
 * @param {number} projectId - 项目ID
 * @param {string} memoryType - 记忆类型（可选）
 * @param {number} limit - 限制数量
 */
async function queryProjectMemories(projectId, memoryType = null, limit = 20) {
  try {
    const where = {
      project_id: projectId
    };

    if (memoryType) {
      where.memory_type = memoryType;
    }

    const memories = await prisma.memory.findMany({
      where: where,
      orderBy: [
        { importance: 'desc' },
        { created_at: 'desc' }
      ],
      take: limit
    });

    return memories;
  } catch (error) {
    console.error('[Memory] 查询项目记忆失败:', error);
    return [];
  }
}

/**
 * 查询用户记忆
 * @param {number} userId - 用户ID
 * @param {string} memoryType - 记忆类型（可选）
 * @param {number} limit - 限制数量
 */
async function queryUserMemories(userId, memoryType = null, limit = 20) {
  try {
    const where = {
      user_id: userId
    };

    if (memoryType) {
      where.memory_type = memoryType;
    }

    const memories = await prisma.memory.findMany({
      where: where,
      orderBy: [
        { importance: 'desc' },
        { created_at: 'desc' }
      ],
      take: limit
    });

    return memories;
  } catch (error) {
    console.error('[Memory] 查询用户记忆失败:', error);
    return [];
  }
}

/**
 * 查询任务相关记忆
 * @param {string} taskId - 任务ID
 */
async function queryTaskMemories(taskId) {
  try {
    const memories = await prisma.memory.findMany({
      where: { task_id: taskId },
      orderBy: { created_at: 'desc' }
    });
    return memories;
  } catch (error) {
    console.error('[Memory] 查询任务记忆失败:', error);
    return [];
  }
}

// =======================
// 上下文加载器（供 Worker 使用）
// =======================

/**
 * 为 Worker 加载完整的上下文
 * @param {string} taskId - 任务ID
 */
async function loadContextForWorker(taskId) {
  try {
    const task = await prisma.task.findUnique({
      where: { id: taskId },
      include: {
        user: true,
        project: {
          include: {
            memories: {
              orderBy: { importance: 'desc' },
              take: 10
            }
          }
        }
      }
    });

    if (!task) {
      throw new Error(`任务不存在: ${taskId}`);
    }

    // 获取用户偏好
    const userPreferences = task.user?.preferences || {};

    // 获取项目记忆
    const projectMemories = task.project?.memories || [];

    // 获取最近的任务历史
    const recentTasks = await prisma.task.findMany({
      where: {
        project_id: task.project_id,
        id: { not: taskId }
      },
      orderBy: { created_at: 'desc' },
      take: 5,
      select: {
        prompt: true,
        result_summary: true,
        model: true
      }
    });

    // ⭐ v3.5 新增：智能检索相似任务
    let similarTasks = [];
    if (task.prompt && task.project_id) {
      similarTasks = await findSimilarTasks(task.prompt, task.project_id, 3);
    }

    return {
      system_context: "你是 AlphaPilot，一个专业的 AI 编程助手。",
      project_context: {
        name: task.project?.name,
        tech_stack: task.project?.tech_stack,
        metadata: task.project?.metadata
      },
      memory_context: {
        user_preferences: userPreferences,
        project_memories: projectMemories.map(m => ({
          type: m.memory_type,
          content: m.content,
          importance: m.importance
        })),
        recent_tasks: recentTasks,
        similar_tasks: similarTasks  // ⭐ v3.5 新增：相似任务
      },
      semantic_context: {} // 待 pgvector 安装后启用
    };
  } catch (error) {
    console.error('[Memory] 加载 Worker 上下文失败:', error);
    throw error;
  }
}

// =======================
// 10. 智能检索相似任务（v3.5 新增）⭐
// =======================

/**
 * 根据 prompt 检索相似的历史任务
 * @param {string} prompt - 当前任务的 prompt
 * @param {number} projectId - 项目 ID（可选，限定在项目内搜索）
 * @param {number} limit - 返回数量限制
 * @returns {Promise<Array>} 相似任务列表
 */
async function findSimilarTasks(prompt, projectId = null, limit = 5) {
  try {
    // 提取关键词（简单实现：分词后取前 5 个关键词）
    const keywords = extractKeywords(prompt);
    
    console.log(`[Memory] 检索相似任务，关键词: ${keywords.join(', ')}`);
    
    // 构建查询条件
    const where = {
      status: 'done', // 只检索已完成的任务
      OR: keywords.map(keyword => ({
        prompt: {
          contains: keyword,
          mode: 'insensitive' // 不区分大小写
        }
      }))
    };
    
    // 如果指定了项目 ID，限定在项目内搜索
    if (projectId) {
      where.project_id = projectId;
    }
    
    const similarTasks = await prisma.task.findMany({
      where,
      orderBy: { created_at: 'desc' },
      take: limit,
      select: {
        id: true,
        prompt: true,
        result_summary: true,
        model: true,
        created_at: true,
        steps: {
          take: 3,
          select: {
            step_type: true,
            output: true
          }
        }
      }
    });
    
    console.log(`[Memory] 找到 ${similarTasks.length} 个相似任务`);
    
    return similarTasks;
  } catch (error) {
    console.error('[Memory] 检索相似任务失败:', error);
    return [];
  }
}

/**
 * 从 prompt 中提取关键词（简单实现）
 * @param {string} prompt 
 * @returns {string[]} 关键词数组
 */
function extractKeywords(prompt) {
  // 移除常见停用词
  const stopWords = ['的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这', '他', '她', '它', '们', '那', '些', '什么', '怎么', '如何', '请', '帮', '帮我', 'create', 'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'can', 'shall', 'to', 'for', 'of', 'with', 'at', 'by', 'from', 'as', 'into', 'through', 'during', 'before', 'after', 'above', 'below', 'between', 'out', 'off', 'over', 'under', 'again', 'further', 'then', 'once'];
  
  // 分词（简单实现：按空格和标点分割）
  const words = prompt.toLowerCase()
    .replace(/[^\w\s\u4e00-\u9fa5]/g, ' ') // 保留中文和英文单词
    .split(/\s+/)
    .filter(word => word.length > 1 && !stopWords.includes(word));
  
  // 去重并取前 5 个
  return [...new Set(words)].slice(0, 5);
}

// =======================
// 导出所有方法
// =======================

module.exports = {
  // 用户层
  getOrCreateUser,
  updateUserPreferences,
  getUserPreferences,

  // 项目层
  getOrCreateProject,
  updateProjectMetadata,
  getProjectMemory,

  // 任务层
  createTask,
  updateTaskStatus,
  getTask,
  getUserTasks,

  // 执行链层
  createTaskStep,
  updateTaskStep,
  getTaskSteps,

  // FileOps 层
  recordFileOp,
  getTaskFileOps,

  // 文件层
  getOrCreateFile,
  saveFileVersion,
  getFileVersions,

  // 长期记忆层
  createMemory,
  queryProjectMemories,
  queryUserMemories,
  queryTaskMemories,

  // 上下文加载
  loadContextForWorker,

  // ⭐ v3.5 新增：智能检索
  findSimilarTasks,

  // Prisma 实例（用于高级查询）
  prisma
};
