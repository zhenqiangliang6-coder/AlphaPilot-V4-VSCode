// node-api/test_memory_integration.js
// ⭐ AlphaPilot OS v3.1 Memory Service 集成测试脚本
// 用途：验证 Node API 与 Memory Service 的集成是否正常

const http = require('http');
const { v4: uuidv4 } = require('uuid');

const BASE_URL = 'http://localhost:3000';

console.log('🧪 AlphaPilot OS v3.1 Memory Service 集成测试\n');
console.log('=' .repeat(60));

// 测试 1：提交任务并验证记忆记录
async function testTaskSubmission() {
    console.log('\n📝 测试 1：提交任务并验证记忆记录');
    console.log('-'.repeat(60));
    
    const taskId = uuidv4();
    const taskData = {
        type: "qwen_generate",
        payload: {
            prompt: "帮我创建一个 FastAPI 用户认证模块"
        },
        source: "test-script",
        meta: {
            user_id: "test-user-001",
            project_id: "test-project-001",
            model: "qwen-turbo"
        }
    };
    
    try {
        const response = await makeRequest('/task/submit', 'POST', taskData);
        
        if (response.status === 'submitted') {
            console.log('✅ 任务提交成功');
            console.log(`   Task ID: ${response.task_id}`);
            console.log(`   Model: ${response.model}`);
            return response.task_id;
        } else {
            console.log('❌ 任务提交失败:', response);
            return null;
        }
    } catch (error) {
        console.error('❌ 请求失败:', error.message);
        return null;
    }
}

// 测试 2：模拟任务完成通知
async function testTaskCompletion(taskId) {
    if (!taskId) {
        console.log('⚠️  跳过测试 2：没有有效的 Task ID');
        return;
    }
    
    console.log('\n📝 测试 2：模拟任务完成通知');
    console.log('-'.repeat(60));
    
    const completionData = {
        status: "done",
        summary: "成功创建了用户认证模块，包含 models.py 和 routes.py",
        steps: [
            {
                step_type: "analyze",
                type: "analyze",
                status: "done",
                input: { prompt: "帮我创建一个 FastAPI 用户认证模块" },
                output: { analysis: "需要实现用户注册、登录、JWT 认证" }
            },
            {
                step_type: "write",
                type: "write",
                status: "done",
                input: {},
                output: { files_created: ["app/auth/models.py", "app/auth/routes.py"] }
            }
        ],
        context: {
            final_file_ops: [
                {
                    op: "create",
                    path: "app/auth/models.py",
                    role: "main",
                    reason: "创建用户模型",
                    from_step: "write"
                },
                {
                    op: "create",
                    path: "app/auth/routes.py",
                    role: "main",
                    reason: "创建路由文件",
                    from_step: "write"
                }
            ]
        }
    };
    
    try {
        const response = await makeRequest(`/task/notify/${taskId}`, 'POST', completionData);
        
        if (response.status === 'notified') {
            console.log('✅ 任务完成通知成功');
        } else {
            console.log('❌ 任务完成通知失败:', response);
        }
    } catch (error) {
        console.error('❌ 请求失败:', error.message);
    }
}

// 测试 3：查询数据库验证记录
async function testDatabaseRecords() {
    console.log('\n📝 测试 3：查询数据库验证记录');
    console.log('-'.repeat(60));
    
    const memoryService = require('./services/memoryService');
    
    try {
        // 查询用户
        const users = await memoryService.prisma.user.findMany({ take: 5 });
        console.log(`✅ 用户记录数: ${users.length}`);
        if (users.length > 0) {
            console.log(`   最新用户: ${users[0].name} (ID: ${users[0].id})`);
        }
        
        // 查询项目
        const projects = await memoryService.prisma.project.findMany({ take: 5 });
        console.log(`✅ 项目记录数: ${projects.length}`);
        if (projects.length > 0) {
            console.log(`   最新项目: ${projects[0].name} (ID: ${projects[0].id})`);
        }
        
        // 查询任务
        const tasks = await memoryService.prisma.task.findMany({ take: 5, orderBy: { created_at: 'desc' } });
        console.log(`✅ 任务记录数: ${tasks.length}`);
        if (tasks.length > 0) {
            console.log(`   最新任务: ${tasks[0].prompt.substring(0, 50)}...`);
            console.log(`   状态: ${tasks[0].status}`);
        }
        
        // 查询步骤
        if (tasks.length > 0) {
            const steps = await memoryService.getTaskSteps(tasks[0].id);
            console.log(`✅ 步骤记录数: ${steps.length}`);
        }
        
        // 查询 FileOps
        if (tasks.length > 0) {
            const fileOps = await memoryService.getTaskFileOps(tasks[0].id);
            console.log(`✅ FileOps 记录数: ${fileOps.length}`);
        }
        
        await memoryService.prisma.$disconnect();
        
    } catch (error) {
        console.error('❌ 数据库查询失败:', error.message);
    }
}

// 辅助函数：发送 HTTP 请求
function makeRequest(path, method, data) {
    return new Promise((resolve, reject) => {
        const url = new URL(path, BASE_URL);
        const options = {
            hostname: url.hostname,
            port: url.port,
            path: url.pathname,
            method: method,
            headers: {
                'Content-Type': 'application/json'
            }
        };
        
        const req = http.request(options, (res) => {
            let body = '';
            res.on('data', chunk => body += chunk);
            res.on('end', () => {
                try {
                    resolve(JSON.parse(body));
                } catch (e) {
                    resolve(body);
                }
            });
        });
        
        req.on('error', reject);
        
        if (data) {
            req.write(JSON.stringify(data));
        }
        
        req.end();
    });
}

// 主测试流程
async function runTests() {
    try {
        // 测试 1：提交任务
        const taskId = await testTaskSubmission();
        
        // 等待 1 秒，确保数据库写入完成
        await new Promise(resolve => setTimeout(resolve, 1000));
        
        // 测试 2：任务完成通知
        await testTaskCompletion(taskId);
        
        // 等待 1 秒，确保数据库更新完成
        await new Promise(resolve => setTimeout(resolve, 1000));
        
        // 测试 3：验证数据库记录
        await testDatabaseRecords();
        
        console.log('\n' + '='.repeat(60));
        console.log('🎉 所有集成测试完成！');
        console.log('='.repeat(60));
        
    } catch (error) {
        console.error('\n❌ 测试过程中发生错误:', error);
    }
}

// 运行测试
runTests();
