exports.run = async function(context) {
    console.log('[step:finalize] finalize running...');
    return { status: 'done', output: { note: 'finalize done' } };
};
