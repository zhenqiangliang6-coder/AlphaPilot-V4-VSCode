// node-api/logGovernance.js
// ---------------------------------------------------------
// Node API 日志治理：结构化摘要代替全量 JSON.stringify。
//
// 真实问题（2026-11-14 ShopFlow 跟测）：index.js 用
// `console.log(JSON.stringify(result, null, 2))` 打印 Worker 回传的完整结果，
// 其中含所有步骤的完整 prompt、记忆上下文和模型生成的全部源码。
// 实测单行 509,268 字符，node_api_run9.log 累计 11 MB。
//
// 治理原则（与 python_worker/log_governance.py 对齐）：
//   * 默认输出结构化摘要：身份字段、状态、数量、路径列表；大文本折叠为
//     {len, preview}；任何输出都有硬上界。
//   * 完整数据不丢失 —— 仍在 Redis / HTTP 响应里，只是不重复倾倒到日志。
//   * ALPHAPILOT_VERBOSE_LOG=1 可开全量（本地调试用），全量同样受限。
// ---------------------------------------------------------

'use strict';

const MAX_LINE_CHARS = 400;
const MAX_PREVIEW_CHARS = 120;
const MAX_TOTAL_CHARS = 6000;
const MAX_LIST_ITEMS = 20;
const MAX_DEPTH = 4;

const HEAVY_KEYS = new Set([
  'prompt', 'content', 'code', 'text', 'result', 'input', 'output',
  'response', 'raw', 'memory_context', 'context', 'messages',
  'file_ops', 'final_file_ops', 'steps', 'events', 'traceback',
  'baseline_errors', 'detail', 'payload', 'source_code', 'diff',
]);

const IDENTITY_KEYS = new Set([
  'task_id', 'trace_id', 'status', 'task_state', 'type', 'task_type',
  'version', 'protocol_version', 'sequence', 'event', 'step_id',
  'phase', 'path', 'op', 'model', 'intent', 'persona', 'provider',
  'error', 'success', 'from_step', 'file_type', 'language',
]);

function clip(text, limit) {
  const s = String(text);
  if (s.length <= limit) return s;
  // 硬截断：连截断标记本身也计入上界，保证返回值长度 <= limit
  const suffix = `… [已截断 ${s.length - limit} 字符]`;
  return s.slice(0, Math.max(0, limit - suffix.length)) + suffix;
}

function summarizeValue(value, depth = 0, key = '') {
  if (depth >= MAX_DEPTH) return `<深度>${MAX_DEPTH}`;

  if (value === null || ['boolean', 'number'].includes(typeof value)) return value;

  if (typeof value === 'string') {
    if (IDENTITY_KEYS.has(key) && value.length <= MAX_LINE_CHARS) return value;
    if (value.length <= MAX_PREVIEW_CHARS) return value;
    return {
      _type: 'str',
      len: value.length,
      preview: clip(value.replace(/\n/g, '⏎'), MAX_PREVIEW_CHARS),
    };
  }

  if (Array.isArray(value)) {
    const out = value.slice(0, MAX_LIST_ITEMS).map(v => summarizeValue(v, depth + 1));
    if (value.length > MAX_LIST_ITEMS) out.push(`… 另有 ${value.length - MAX_LIST_ITEMS} 项`);
    return out;
  }

  if (typeof value === 'object') {
    const out = {};
    for (const [k, v] of Object.entries(value)) {
      if (HEAVY_KEYS.has(k) && (typeof v === 'string' || Array.isArray(v) || (v && typeof v === 'object'))) {
        if (typeof v === 'string') {
          out[k] = summarizeValue(v, depth + 1, k);
        } else if (Array.isArray(v)) {
          out[k] = {
            _type: 'array',
            len: v.length,
            items: v.slice(0, MAX_LIST_ITEMS).map(x => summarizeValue(x, depth + 1)),
          };
        } else {
          const fields = Object.keys(v);
          out[k] = { _type: 'object', len: fields.length, fields: fields.slice(0, 6) };
        }
      } else {
        out[k] = summarizeValue(v, depth + 1, k);
      }
    }
    return out;
  }

  return clip(String(value), MAX_PREVIEW_CHARS);
}

function summarize(obj) {
  try {
    return clip(JSON.stringify(summarizeValue(obj), null, 2), MAX_TOTAL_CHARS);
  } catch (e) {
    return `<日志摘要生成失败: ${e.name}: ${e.message}>`;
  }
}

function logObject(label, obj) {
  const verbose = (process.env.ALPHAPILOT_VERBOSE_LOG || '0').trim() === '1';
  console.log(`\n${label}`);
  if (verbose) {
    try {
      console.log(clip(JSON.stringify(obj, null, 2), MAX_TOTAL_CHARS));
    } catch (e) {
      console.log(clip(String(e), MAX_LINE_CHARS));
    }
    console.log('(VERBOSE 模式：完整数据仍以 Redis / HTTP 响应为准)');
  } else {
    console.log(summarize(obj));
    console.log('(摘要模式：完整数据见 Redis；需全量请设 ALPHAPILOT_VERBOSE_LOG=1)');
  }
}

function logLine(text) {
  return clip(text, MAX_LINE_CHARS);
}

module.exports = { summarize, logObject, logLine, MAX_TOTAL_CHARS, MAX_LINE_CHARS };
