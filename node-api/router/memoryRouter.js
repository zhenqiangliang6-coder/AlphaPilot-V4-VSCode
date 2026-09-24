const express = require('express');
const router = express.Router();
const memoryService = require('../services/memoryService');

// GET /memory/context/:taskId - load context for worker
router.get('/context/:taskId', async (req, res) => {
  try {
    const { taskId } = req.params;
    const ctx = await memoryService.loadContextForWorker(taskId);
    res.json({ success: true, context: ctx });
  } catch (err) {
    console.error('[MemoryRouter] load context failed:', err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

// GET /memory/task/:taskId - get task details
router.get('/task/:taskId', async (req, res) => {
  try {
    const { taskId } = req.params;
    const task = await memoryService.getTask(taskId);
    if (!task) return res.status(404).json({ success: false, error: 'task not found' });
    res.json({ success: true, task });
  } catch (err) {
    console.error('[MemoryRouter] get task failed:', err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

// POST /memory/user - create or get user
router.post('/user', async (req, res) => {
  try {
    const { externalId, name, preferences } = req.body;
    if (!externalId) return res.status(400).json({ success: false, error: 'externalId required' });
    const user = await memoryService.getOrCreateUser(externalId, name, preferences || {});
    res.json({ success: true, user });
  } catch (err) {
    console.error('[MemoryRouter] create/get user failed:', err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

// POST /memory/project - create or get project
router.post('/project', async (req, res) => {
  try {
    const { userId, name, rootPath, techStack } = req.body;
    if (!userId || !name) return res.status(400).json({ success: false, error: 'userId and name required' });
    const project = await memoryService.getOrCreateProject(userId, name, rootPath || '', techStack || {});
    res.json({ success: true, project });
  } catch (err) {
    console.error('[MemoryRouter] create/get project failed:', err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

// POST /memory/memory - create a memory entry
router.post('/memory', async (req, res) => {
  try {
    const { ownerType, ownerId, memoryType, content, importance } = req.body;
    const mem = await memoryService.createMemory(ownerType, ownerId, memoryType, content, importance || 1);
    res.json({ success: true, memory: mem });
  } catch (err) {
    console.error('[MemoryRouter] create memory failed:', err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

module.exports = router;

