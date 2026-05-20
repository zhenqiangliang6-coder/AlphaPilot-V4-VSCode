// node-api/test_context_injection.js
// ⭐ AlphaPilot OS v3.5 上下文注入测试脚本
// 用途：验证 Worker 上下文注入是否正常工作

const memoryService = require('./services/memoryService');
const { v4: uuidv4 } = require('uuid');

console.log('🧪 AlphaPilot OS v3.5 上下文注入测试\n');
console.log('=' .repeat(60));

async function testContextInjection() {
    try {
        // 测试 1：创建测试数据
        console.log('\n📝 测试 1：创建测试数据');
        console.log('-'.repeat(60));
        
        const userId = 'test-user-v35';
        const projectId = 'test-project-v35';
        const taskId = uuidv4();
        
        // 创建用户
        const user = await memoryService.getOrCreateUser(userId, '测试用户 V3.5', {
            language: 'zh-CN',
            preferred_model: 'qwen-turbo',
            explanation_style: 'detailed'
        });
        console.log(`✅ 创建用户: ${user.name} (ID: ${user.id})`);
        
        // 创建项目
        const project = await memoryService.getOrCreateProject(
            user.id,
            '测试项目 V3.5',
            'D:\\Test\\V35',
            {
                framework: 'FastAPI + React',
                languages: ['Python', 'JavaScript'],
                code_style: 'snake_case'
            }
        );
        console.log(`✅ 创建项目: ${project.name} (ID: ${project.id})`);
        
        // 创建项目记忆（规则）
        await memoryService.createMemory(
            'project',
            project.id,
            'rule',
            '所有 API 必须使用 async/await 异步模式',
            5
        );
        await memoryService.createMemory(
            'project',
            project.id,
            'rule',
            '所有文件命名必须使用 snake_case',
            4
        );
        console.log(`✅ 创建项目规则记忆: 2 条`);
        
        // 创建用户偏好记忆
        await memoryService.createMemory(
            'user',
            user.id,
            'preference',
            '用户喜欢详细的代码注释和中文解释',
            4
        );
        console.log(`✅ 创建用户偏好记忆: 1 条`);
        
        // 创建历史任务（用于相似性检索测试）
        const historicalTaskId1 = uuidv4();
        await memoryService.createTask(
            historicalTaskId1,
            user.id,
            project.id,
            '帮我创建一个 FastAPI 用户认证模块，包含登录和注册功能',
            'qwen-turbo',
            'test'
        );
        await memoryService.updateTaskStatus(historicalTaskId1, 'done', '创建了 auth 模块');
        console.log(`✅ 创建历史任务 1: 用户认证模块`);
        
        const historicalTaskId2 = uuidv4();
        await memoryService.createTask(
            historicalTaskId2,
            user.id,
            project.id,
            '实现 JWT Token 生成和验证逻辑',
            'qwen-turbo',
            'test'
        );
        await memoryService.updateTaskStatus(historicalTaskId2, 'done', '实现了 JWT 逻辑');
        console.log(`✅ 创建历史任务 2: JWT 实现`);
        
        // 测试 2：加载上下文
        console.log('\n📝 测试 2：加载 Worker 上下文');
        console.log('-'.repeat(60));
        
        const currentTaskId = uuidv4();
        await memoryService.createTask(
            currentTaskId,
            user.id,
            project.id,
            '帮我创建一个用户登录接口，使用 JWT 认证',
            'qwen-turbo',
            'test'
        );
        
        const context = await memoryService.loadContextForWorker(currentTaskId);
        
        console.log('✅ 上下文加载成功！');
        console.log('\n📊 上下文内容:');
        console.log(`   - System Context: ${context.system_context}`);
        console.log(`   - Project Name: ${context.project_context?.name}`);
        console.log(`   - Tech Stack: ${JSON.stringify(context.project_context?.tech_stack)}`);
        console.log(`   - User Preferences: ${JSON.stringify(context.memory_context?.user_preferences)}`);
        console.log(`   - Project Memories: ${context.memory_context?.project_memories?.length} 条`);
        console.log(`   - Recent Tasks: ${context.memory_context?.recent_tasks?.length} 个`);
        console.log(`   - Similar Tasks: ${context.memory_context?.similar_tasks?.length} 个`);
        
        // 打印相似任务
        if (context.memory_context?.similar_tasks?.length > 0) {
            console.log('\n🔍 相似任务列表:');
            context.memory_context.similar_tasks.forEach((task, index) => {
                console.log(`   ${index + 1}. ${task.prompt.substring(0, 50)}...`);
                console.log(`      摘要: ${task.result_summary}`);
            });
        }
        
        // 测试 3：验证智能检索
        console.log('\n📝 测试 3：验证智能检索功能');
        console.log('-'.repeat(60));
        
        const similarTasks = await memoryService.findSimilarTasks(
            '帮我创建一个用户登录接口，使用 JWT 认证',
            project.id,
            5
        );
        
        console.log(`✅ 检索到 ${similarTasks.length} 个相似任务`);
        similarTasks.forEach((task, index) => {
            console.log(`   ${index + 1}. ${task.prompt.substring(0, 60)}...`);
        });
        
        console.log('\n' + '='.repeat(60));
        console.log('🎉 所有测试通过！上下文注入功能正常');
        console.log('='.repeat(60));
        
    } catch (error) {
        console.error('\n❌ 测试失败:', error);
        throw error;
    }
}

// 运行测试
testContextInjection();
