// Minimal V4 state machine skeleton
const steps = require('./steps');
/**
 * Run the V4 step pipeline sequentially.
 * Each step receives a context and may return { status, output, ops }
 */
async function runStateMachine(task) {
    const context = { task, results: {}, ops: [] };

    const order = ['analyze','plan','write','test','fix','doc','docstring','finalize'];

    for (const name of order) {
        if (!steps[name] || typeof steps[name].run !== 'function') continue;
        try {
            console.log(`[V4 Worker] 运行步骤: ${name}`);
            const res = await steps[name].run(context);
            context.results[name] = res || {};
            if (res?.ops && Array.isArray(res.ops)) {
                context.ops.push(...res.ops);
            }
            if (res?.status === 'error') {
                console.warn(`[V4 Worker] 步骤 ${name} 返回错误，停止后续步骤`);
                break;
            }
        } catch (err) {
            console.error(`[V4 Worker] 步骤 ${name} 执行异常:`, err.message);
            break;
        }
    }

    return context;
}

module.exports = { runStateMachine };
