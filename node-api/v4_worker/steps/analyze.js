exports.run = async function(context) {
    console.log('[step:analyze] analyze running...');
    // minimal analyze: produce a plan outline
    return { status: 'done', output: { note: 'analyze done' } };
};
