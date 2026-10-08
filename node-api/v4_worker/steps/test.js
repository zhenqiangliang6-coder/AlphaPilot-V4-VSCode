exports.run = async function(context) {
    console.log('[step:test] test running...');
    return { status: 'done', output: { note: 'test done' } };
};
