exports.run = async function(context) {
    console.log('[step:doc] doc running...');
    return { status: 'done', output: { note: 'doc done' } };
};
