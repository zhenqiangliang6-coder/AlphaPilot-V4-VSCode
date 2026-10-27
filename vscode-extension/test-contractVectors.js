const assert = require('node:assert/strict');
const test = require('node:test');
const path = require('path');
const { resolveTaskStatus } = require('./out/taskModel');

const vectors = require(path.join(__dirname, '..', 'contract-test-vectors.json'));

const testName = `[TypeScript] Cross-language contract vectors (${vectors.vectors.length} total, ${vectors.summary.known_divergence_vectors} known divergences)`;
test(testName, () => {
  const failures = [];
  const divergence_failures = [];
  const passes = [];

  for (const vector of vectors.vectors) {
    const resolved = resolveTaskStatus(vector.input);
    const expected = vector.expected;

    let passed = true;
    const mismatches = [];

    if (resolved.valid !== expected.valid) {
      passed = false;
      mismatches.push(`valid: got ${resolved.valid}, expected ${expected.valid}`);
    }

    if (resolved.status !== expected.status) {
      passed = false;
      mismatches.push(`status: got ${JSON.stringify(resolved.status)}, expected ${JSON.stringify(expected.status)}`);
    }

    const isDivergence = vector.category === 'KNOWN_DIVERGENCE';

    if (passed) {
      passes.push(vector.id);
    } else if (isDivergence) {
      divergence_failures.push({ id: vector.id, mismatches, description: vector.description });
    } else {
      failures.push({ id: vector.id, mismatches, description: vector.description });
    }
  }

  if (failures.length > 0) {
    console.error(`\n❌ ${failures.length} UNEXPECTED failures:`);
    failures.forEach(f => {
      console.error(`   ${f.id}: ${f.mismatches.join('; ')}`);
      console.error(`      desc: ${f.description}`);
    });
  }

  if (divergence_failures.length > 0) {
    console.warn(`\n⚠️ ${divergence_failures.length} KNOWN DIVERGENCE failures (expected, will be fixed in G3.2-3):`);
    divergence_failures.forEach(f => {
      console.warn(`   ${f.id}: ${f.mismatches.join('; ')}`);
      console.warn(`      desc: ${f.description}`);
    });
  }

  console.log(`\n✅ ${passes.length}/${vectors.vectors.length} passed`);
  console.log(`⚠️ ${divergence_failures.length} known divergence failures`);
  console.log(`❌ ${failures.length} unexpected failures`);

  assert.equal(failures.length, 0, `${failures.length} unexpected failures in TypeScript cross-language contract vectors`);
});