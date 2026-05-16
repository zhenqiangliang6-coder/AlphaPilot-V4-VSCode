// clear_redis_queues.js
// 使用Node.js清理Redis队列

require('dotenv').config();
const https = require('https');

const UPSTASH_URL = process.env.UPSTASH_REDIS_REST_URL;
const UPSTASH_TOKEN = process.env.UPSTASH_REDIS_REST_TOKEN;

if (!UPSTASH_URL || !UPSTASH_TOKEN) {
    console.error('❌ Upstash环境变量未配置');
    console.error('   UPSTASH_REDIS_REST_URL:', UPSTASH_URL ? '已设置' : '未设置');
    console.error('   UPSTASH_REDIS_REST_TOKEN:', UPSTASH_TOKEN ? '已设置' : '未设置');
    process.exit(1);
}

const queues = [
    'task_queue:qwen',
    'task_queue:deepseek',
    'task_queue:doubao',
    'task_queue:local',
    'task_queue:openai',
    'task_queue:claude',
    'task_queue:gemini'
];

async function executeCommand(command, args) {
    return new Promise((resolve, reject) => {
        const data = JSON.stringify([[command, ...args]]);
        
        const options = {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${UPSTASH_TOKEN}`,
                'Content-Type': 'application/json'
            }
        };

        const req = https.request(UPSTASH_URL, options, (res) => {
            let body = '';
            res.on('data', chunk => body += chunk);
            res.on('end', () => {
                try {
                    resolve(JSON.parse(body));
                } catch (e) {
                    reject(e);
                }
            });
        });

        req.on('error', reject);
        req.write(data);
        req.end();
    });
}

async function main() {
    console.log('\n========================================');
    console.log('AlphaPilot Redis队列清理工具');
    console.log('========================================\n');
    console.log('🧹 开始清理队列...\n');

    for (const queue of queues) {
        try {
            // 获取队列长度
            const lenResult = await executeCommand('LLEN', [queue]);
            const length = lenResult[0];

            if (length > 0) {
                console.log(`🗑️  ${queue}: ${length} 个任务`);
                
                // 清空队列
                const delResult = await executeCommand('DEL', [queue]);
                console.log(`   ✅ 已清空 (删除了 ${delResult[0]} 个key)\n`);
            } else {
                console.log(`✓ ${queue}: 空\n`);
            }
        } catch (error) {
            console.error(`❌ ${queue}: 清理失败 - ${error.message}\n`);
        }
    }

    console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
    console.log('✅ 队列清理完成!\n');
    console.log('提示: 请重新启动所有Worker以确保它们从干净的状态开始监听\n');
}

main().catch(console.error);
