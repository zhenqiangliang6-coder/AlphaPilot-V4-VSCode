exports.run = async function(context) {
    console.log('[step:docstring] docstring running...');
    return { status: 'done', output: { note: 'docstring done' } };
};
