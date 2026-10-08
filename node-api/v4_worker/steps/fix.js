exports.run = async function(context) {
    console.log('[step:fix] fix running...');
    return { status: 'done', output: { note: 'fix done' } };
};
