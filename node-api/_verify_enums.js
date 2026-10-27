const { PrismaClient } = require('@prisma/client');
const p = new PrismaClient();

const TEST_TASK_ID = '__verify_test_' + Date.now();

async function main() {
  console.log('=== StepType enum values (DB) ===');
  const stepTypes = await p.$queryRawUnsafe('SELECT unnest(enum_range(NULL::"StepType")) as step_type');
  stepTypes.forEach(r => console.log('  ', r.step_type));

  console.log('\n=== TaskStatus enum values (DB) ===');
  const statuses = await p.$queryRawUnsafe('SELECT unnest(enum_range(NULL::"TaskStatus")) as status');
  statuses.forEach(r => console.log('  ', r.status));

  console.log('\n=== Test: create Task + respond step + update with completed ===');
  try {
    await p.task.create({
      data: { id: TEST_TASK_ID, prompt: 'verify test', status: 'running' }
    });
    console.log('  1. Task created:', TEST_TASK_ID);

    const step = await p.taskStep.create({
      data: {
        task_id: TEST_TASK_ID,
        step_type: 'respond',
        status: 'pending',
        input: { test: true }
      }
    });
    console.log('  2. respond step created, id =', step.id);

    const updated = await p.taskStep.update({
      where: { id: step.id },
      data: { status: 'done', output: { text: 'verify ok' }, finished_at: new Date() }
    });
    console.log('  3. respond step updated to done, id =', updated.id);

    console.log('\n  ALL CHECKS PASSED');
  } catch (e) {
    console.log('  FAILED:', e.message.split('\n')[0]);
  } finally {
    await p.taskStep.deleteMany({ where: { task_id: TEST_TASK_ID } }).catch(() => {});
    await p.task.delete({ where: { id: TEST_TASK_ID } }).catch(() => {});
    await p.$disconnect();
  }
}

main().catch(e => { console.error(e); p.$disconnect(); });