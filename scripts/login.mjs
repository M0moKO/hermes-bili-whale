#!/usr/bin/env node
/**
 * 扫码登录（两段式，不依赖 TTY，可在后台跑）。
 *   node login.mjs --qr     只生成二维码：写 qr-login.png + ~/.bili-ai/qr-session.json
 *   node login.mjs --poll   轮询上次生成的二维码，成功后写 ~/.bili-ai/credentials.json
 *
 * 凭据由 createCredentialStore 原子写入并收紧权限；全程不打印 cookie / qrcode_key。
 */
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import QRCode from 'qrcode'
import { verifyAccount } from './lib/auth.js'
import { createCredentialStore } from './lib/credentials.js'

const HOME = process.env.USERPROFILE || process.env.HOME || os.homedir()
const DIR = path.join(HOME, '.bili-ai')
const CRED = path.join(DIR, 'credentials.json')
const PENDING = path.join(DIR, 'pending-replies.json')
const SESSION = path.join(DIR, 'qr-session.json')
const QR_PNG = path.join(path.dirname(fileURLToPath(import.meta.url)), 'qr-login.png')

const PASSPORT = 'https://passport.bilibili.com'
const HEADERS = { 'user-agent': 'Mozilla/5.0', referer: PASSPORT + '/login' }
const TTL_MS = 175000

async function gen() {
  const res = await fetch(PASSPORT + '/x/passport-login/web/qrcode/generate', { headers: HEADERS })
  const body = await res.json()
  if (body.code !== 0 || !body.data?.qrcode_key) throw new Error('二维码生成失败 code=' + body.code)
  const { url, qrcode_key } = body.data
  fs.mkdirSync(DIR, { recursive: true })
  fs.writeFileSync(SESSION, JSON.stringify({ qrcode_key, url, createdAt: Date.now() }, null, 2))
  const dataUrl = await QRCode.toDataURL(url, { width: 260, margin: 2 })
  fs.writeFileSync(QR_PNG, Buffer.from(dataUrl.split(',')[1], 'base64'))
  console.log('QR_READY ' + QR_PNG)
}

async function pollOnce() {
  const s = JSON.parse(fs.readFileSync(SESSION, 'utf8'))
  if (Date.now() - s.createdAt > TTL_MS) return 'expired'
  const u = new URL(PASSPORT + '/x/passport-login/web/qrcode/poll')
  u.searchParams.set('qrcode_key', s.qrcode_key)
  const res = await fetch(u, { headers: HEADERS, redirect: 'error' })
  const body = await res.json()
  const code = body?.data?.code
  if (code === 86101) return 'waiting'
  if (code === 86090) return 'scanned'
  if (code === 86038) return 'expired'
  if (code === 0) {
    const raw = typeof res.headers.getSetCookie === 'function' ? res.headers.getSetCookie() : []
    const vals = {}
    for (const c of raw) {
      const pair = c.split(';')[0]
      const i = pair.indexOf('=')
      const n = pair.slice(0, i).trim()
      if (['SESSDATA', 'bili_jct', 'buvid3'].includes(n)) vals[n] = pair.slice(i + 1).trim()
    }
    const { save } = createCredentialStore({ file: CRED, pending: PENDING, verify: verifyAccount })
    const account = await save({ sessdata: vals.SESSDATA, bili_jct: vals.bili_jct, buvid3: vals.buvid3 })
    try { fs.unlinkSync(SESSION) } catch {}
    console.log('ACCOUNT ' + JSON.stringify(account))
    return 'success'
  }
  return 'unknown:' + JSON.stringify(body).slice(0, 120)
}

if (process.argv.includes('--qr')) {
  await gen()
} else if (process.argv.includes('--poll')) {
  for (let i = 0; i < 88; i++) {
    const st = await pollOnce()
    if (st !== 'waiting') console.log('STATUS ' + st)
    if (st === 'success') process.exit(0)
    if (st === 'expired' || st.startsWith('unknown')) process.exit(1)
    await new Promise((r) => setTimeout(r, 2000))
  }
  console.log('FAILED timeout')
  process.exit(1)
} else if (process.argv.includes('--poll-once')) {
  // 面板用：只查一次扫码状态，立即返回 JSON（不阻塞）
  const st = await pollOnce()
  console.log(JSON.stringify({ status: st }))
  process.exit(0)
} else {
  console.log('用法：node login.mjs --qr | --poll | --poll-once')
  process.exit(2)
}
