#!/usr/bin/env node
/**
 * 梗库查询（只做字面匹配，不做模糊/包含推断）
 *
 *   node memes.mjs list                         列出全部词条
 *   node memes.mjs lookup <词>                  精确查一个词
 *   node memes.mjs scan <文本>                  在一段文本里找出命中的词（长的优先）
 *   node memes.mjs scan --file <路径>           同上，从文件读
 *
 * 设计约束（来自 docs/human-voice.md 与社区反馈）：
 *   - 只收两字以上的词条，单字一律不收（「典」「急」这类误命中率太高）
 *   - 命中只当作「可以接」的候选，接不接由 agent 判断；拿不准就别接
 *   - private 组里 onlyWithOwner=true 的只对主人说，别在公开评论里用
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const DB = path.join(HERE, '..', 'memes', 'default.json');

let db;
try {
  db = JSON.parse(fs.readFileSync(DB, 'utf8'));
} catch (e) {
  console.log(JSON.stringify({ error: '梗库读取失败: ' + e.message }));
  process.exit(1);
}

const groups = ['builtin', 'tech', 'private'];
const minChars = (db.rules && db.rules.minChars) || 2;

function entries() {
  const out = [];
  for (const g of groups) {
    for (const [word, v] of Object.entries(db[g] || {})) {
      if ([...word].length < minChars) continue;
      out.push({ word, group: g, use: v.use || '', tone: v.tone || '', onlyWithOwner: !!v.onlyWithOwner });
    }
  }
  return out;
}

const cmd = (process.argv[2] || '').trim();

if (cmd === 'list') {
  const all = entries();
  console.log(JSON.stringify({ count: all.length, groups: { builtin: Object.keys(db.builtin||{}).length, tech: Object.keys(db.tech||{}).length, private: Object.keys(db.private||{}).length }, words: all.map(e => e.word) }, null, 1));
  process.exit(0);
}

if (cmd === 'lookup') {
  const w = process.argv[3] || '';
  const hit = entries().filter(e => e.word === w);
  console.log(JSON.stringify(hit.length ? { hit: hit[0] } : { hit: null, note: '没有该词条；不要自己编解释' }, null, 1));
  process.exit(0);
}

if (cmd === 'scan') {
  let text = '';
  if (process.argv[3] === '--file') {
    try { text = fs.readFileSync(process.argv[4], 'utf8'); } catch (e) { console.log(JSON.stringify({ error: e.message })); process.exit(1); }
  } else {
    text = process.argv.slice(3).join(' ');
  }
  if (!text.trim()) { console.log(JSON.stringify({ hits: [], note: '空文本' })); process.exit(0); }

  // 长词优先，避免「典中典」被「典」抢（单字本来就不收，这条是保险）
  const hits = entries()
    .filter(e => text.includes(e.word))
    .sort((a, b) => [...b.word].length - [...a.word].length)
    .slice(0, 5)
    .map(e => ({ word: e.word, group: e.group, use: e.use, tone: e.tone, onlyWithOwner: e.onlyWithOwner }));

  console.log(JSON.stringify({
    hits,
    advice: hits.length
      ? '命中只是「可以接」的候选：挑最多 1 个，按 use 的方式接，别解释这个词本身。'
      : '没命中 —— 不接。硬接比不接更像机器人。'
  }, null, 1));
  process.exit(0);
}

console.log('用法: node memes.mjs list | lookup <词> | scan <文本> | scan --file <路径>');
process.exit(2);
