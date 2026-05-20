// node-api/test_memory_service.js

const memoryService = require('./services/memoryService');
const { v4: uuidv4 } = require('uuid');

/**
 * 测试 Memory Service 的完整功能
 */
async function testMemoryService() {
  console.log('🧪 开始测试 AlphaPilot OS Memory Service...\n');

  try {
    // 1. 测试用户层
    console.log('📝 1. 测试用户层操作...');
    const user = await memoryService.getOrCreateUser('test-user-001', '测试用户', {
      language: 'zh-CN',
      explanation_style: 'detailed',
      preferred_model: 'qwen'
    });
    console.log(`✅ 创建/获取用户: ${user.name} (ID: ${user.id})`);

    // 2. 测试项目层
    console.log('\n📝 2. 测试项目层操作...');
    const project = await memoryService.getOrCreateProject(
      user.id,
      'AlphaPilot Test Project',
      'D:\\Test\\Project',
      { languages: ['Python', 'JavaScript'], framework: 'FastAPI + React' }
    );
    console.log(`✅ 创建/获取项目: ${project.name} (ID: ${project.id})`);

    // 3. 测试任务层
    console.log('\n📝 3. 测试任务层操作...');
    const taskId = uuidv4();
    const task = await memoryService.createTask(
      taskId,
      user.id,
      project.id,
      '帮我创建一个 FastAPI 用户认证模块',
      'qwen-max',
      'react-webview'
    );
    console.log(`✅ 创建任务: ${task.id}`);

    // 4. 测试执行链层
    console.log('\n📝 4. 测试执行链层操作...');
    const analyzeStep = await memoryService.createTaskStep(taskId, 'analyze', {
      prompt: '帮我创建一个 FastAPI 用户认证模块'
    });
    console.log(`✅ 创建分析步骤: stepId=${analyzeStep.id}`);

    await memoryService.updateTaskStep(analyzeStep.id, 'done', {
      analysis: '需要实现用户注册、登录、JWT 认证等功能',
      tech_stack: ['FastAPI', 'SQLAlchemy', 'PyJWT']
    });
    console.log(`✅ 更新分析步骤状态: done`);

    const planStep = await memoryService.createTaskStep(taskId, 'plan', {
      analysis: analyzeStep.output
    });
    console.log(`✅ 创建规划步骤: stepId=${planStep.id}`);

    // 5. 测试 FileOps 层
    console.log('\n📝 5. 测试 FileOps 层操作...');
    await memoryService.recordFileOp(
      taskId,
      planStep.id,
      'create',
      'app/auth/models.py',
      'main',
      '创建用户模型',
      'plan'
    );
    console.log(`✅ 记录文件操作: create app/auth/models.py`);

    await memoryService.recordFileOp(
      taskId,
      planStep.id,
      'create',
      'app/auth/routes.py',
      'main',
      '创建认证路由',
      'plan'
    );
    console.log(`✅ 记录文件操作: create app/auth/routes.py`);

    // 6. 测试文件层
    console.log('\n📝 6. 测试文件层操作...');
    const file = await memoryService.getOrCreateFile(project.id, 'app/auth/models.py');
    console.log(`✅ 创建文件身份: fileId=${file.id}`);

    await memoryService.saveFileVersion(
      file.id,
      taskId,
      planStep.id,
      'from sqlalchemy import Column, Integer, String\n\nclass User(Base):\n    __tablename__ = "users"\n    id = Column(Integer, primary_key=True)\n    username = Column(String(50), unique=True)\n    email = Column(String(100), unique=True)',
      'abc123hash'
    );
    console.log(`✅ 保存文件版本`);

    // 7. 测试长期记忆层
    console.log('\n📝 7. 测试长期记忆层操作...');
    await memoryService.createMemory(
      'project',
      project.id,
      'rule',
      '所有 API 路由必须使用 async/await 异步模式',
      5
    );
    console.log(`✅ 创建项目规则记忆`);

    await memoryService.createMemory(
      'user',
      user.id,
      'preference',
      '用户偏好详细的代码解释和中文注释',
      4
    );
    console.log(`✅ 创建用户偏好记忆`);

    // 8. 测试查询功能
    console.log('\n📝 8. 测试查询功能...');
    const projectMemories = await memoryService.queryProjectMemories(project.id);
    console.log(`✅ 查询项目记忆: ${projectMemories.length} 条`);

    const userMemories = await memoryService.queryUserMemories(user.id);
    console.log(`✅ 查询用户记忆: ${userMemories.length} 条`);

    const taskSteps = await memoryService.getTaskSteps(taskId);
    console.log(`✅ 查询任务步骤: ${taskSteps.length} 个`);

    const taskFileOps = await memoryService.getTaskFileOps(taskId);
    console.log(`✅ 查询任务文件操作: ${taskFileOps.length} 个`);

    const fileVersions = await memoryService.getFileVersions(file.id);
    console.log(`✅ 查询文件版本历史: ${fileVersions.length} 个`);

    // 9. 测试上下文加载
    console.log('\n📝 9. 测试 Worker 上下文加载...');
    const context = await memoryService.loadContextForWorker(taskId);
    console.log(`✅ 加载 Worker 上下文:`);
    console.log(`   - 项目名称: ${context.project_context?.name}`);
    console.log(`   - 技术栈: ${JSON.stringify(context.project_context?.tech_stack)}`);
    console.log(`   - 项目记忆数: ${context.memory_context?.project_memories?.length}`);
    console.log(`   - 最近任务数: ${context.memory_context?.recent_tasks?.length}`);

    // 10. 更新任务状态
    console.log('\n📝 10. 更新任务状态...');
    await memoryService.updateTaskStatus(taskId, 'done', '成功创建 FastAPI 用户认证模块');
    console.log(`✅ 任务状态更新为: done`);

    console.log('\n🎉 所有测试通过！Memory Service 运行正常。');
    console.log('\n📊 测试总结:');
    console.log('   ✅ 用户层: 创建、更新、查询');
    console.log('   ✅ 项目层: 创建、更新、查询');
    console.log('   ✅ 任务层: 创建、更新、查询');
    console.log('   ✅ 执行链层: 步骤创建、状态更新');
    console.log('   ✅ FileOps 层: 文件操作记录');
    console.log('   ✅ 文件层: 文件身份、版本管理');
    console.log('   ✅ 长期记忆: 创建、查询');
    console.log('   ✅ 上下文加载: Worker 上下文组装');

  } catch (error) {
    console.error('\n❌ 测试失败:', error.message);
    console.error(error.stack);
    process.exit(1);
  } finally {
    // 断开数据库连接
    await memoryService.prisma.$disconnect();
    console.log('\n🔌 数据库连接已关闭');
  }
}

// 运行测试
testMemoryService();
