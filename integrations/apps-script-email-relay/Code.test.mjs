import assert from 'node:assert/strict'
import { createHmac, createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import vm from 'node:vm'

const source = readFileSync(new URL('./Code.gs', import.meta.url), 'utf8')
const secret = '0123456789abcdef0123456789abcdef0123456789abcdef'
const validId = '123e4567-e89b-42d3-a456-426614174000'
const validId2 = '123e4567-e89b-42d3-a456-426614174001'
const token = 'x'.repeat(43)

function createRelay({
  dailyCap = 2,
  remainingQuota = 10,
  actionBase = 'https://dataset.example',
  timestampTolerance = 300,
  failSentStatePersistence = false,
} = {}) {
  let now = Date.UTC(2026, 9, 16, 12, 0, 0)
  let quota = remainingQuota
  const properties = new Map([
    ['HMAC_SECRET', secret],
    ['ACTION_BASE_URL', actionBase],
    ['TIMESTAMP_TOLERANCE_SECONDS', String(timestampTolerance)],
    ['DAILY_SEND_CAP', String(dailyCap)],
    ['RECIPIENT_COOLDOWN_SECONDS', '900'],
  ])
  const sent = []
  const diagnostics = []
  const propertyApi = {
    getProperty(key) { return properties.has(key) ? properties.get(key) : null },
    setProperty(key, value) {
      const parsed = key.startsWith('request_') ? JSON.parse(String(value)) : null
      if (failSentStatePersistence && parsed?.status === 'sent') {
        throw new Error('private property failure detail')
      }
      properties.set(key, String(value))
      return this
    },
    deleteProperty(key) { properties.delete(key); return this },
    getProperties() { return Object.fromEntries(properties) },
  }
  class FakeDate extends Date {
    constructor(...args) { super(...(args.length ? args : [now])) }
    static now() { return now }
  }
  const context = vm.createContext({
    Date: FakeDate,
    URL,
    Math,
    Number,
    Object,
    Array,
    String,
    JSON,
    RegExp,
    isFinite,
    console: { log(message) { diagnostics.push(String(message)) } },
    PropertiesService: { getScriptProperties: () => propertyApi },
    LockService: { getScriptLock: () => ({ tryLock: () => true, releaseLock: () => {} }) },
    MailApp: {
      getRemainingDailyQuota: () => quota,
      sendEmail(message) { sent.push(message); quota -= 1 },
    },
    ContentService: {
      MimeType: { JSON: 'application/json' },
      createTextOutput(content) {
        return { content, setMimeType() { return this }, getContent() { return this.content } }
      },
    },
    Utilities: {
      Charset: { UTF_8: 'UTF-8' },
      DigestAlgorithm: { SHA_256: 'SHA-256' },
      newBlob(value) { return { getBytes: () => [...Buffer.from(value, 'utf8')] } },
      computeHmacSha256Signature(message, key) {
        return [...createHmac('sha256', key).update(message, 'utf8').digest()].map((byte) => byte > 127 ? byte - 256 : byte)
      },
      computeDigest(_algorithm, message) {
        return [...createHash('sha256').update(message, 'utf8').digest()].map((byte) => byte > 127 ? byte - 256 : byte)
      },
    },
  })
  vm.runInContext(source, context)

  function payload(overrides = {}) {
    const request = {
      schema_version: 1,
      timestamp: Math.floor(now / 1000),
      nonce: 'a'.repeat(32),
      request_id: validId,
      message_type: 'verification',
      recipient: 'user@example.net',
      action_url: `https://dataset.example/verify-email?token=${token}`,
      signature: '',
      ...overrides,
    }
    const canonical = context.canonicalMessage_(request)
    request.signature = createHmac('sha256', secret).update(canonical, 'utf8').digest('hex')
    return request
  }
  function post(body) {
    return JSON.parse(context.doPost({ postData: { contents: JSON.stringify(body) } }).getContent())
  }
  return {
    context,
    payload,
    post,
    sent,
    properties,
    diagnostics,
    setNow(value) { now = value },
    setQuota(value) { quota = value },
  }
}

test('accepts a signed fixed template and makes same request id idempotent', () => {
  const relay = createRelay()
  const request = relay.payload()
  assert.equal(relay.post(request).status, 'sent')
  assert.equal(relay.post(request).status, 'duplicate_sent')
  assert.equal(relay.sent.length, 1)
  assert.match(relay.sent[0].body, /https:\/\/dataset\.example\/verify-email\?token=/)
  assert.equal(relay.sent[0].from, undefined)
})

test('emits safe timing stages for a successful delivery path', () => {
  const relay = createRelay()
  const request = relay.payload()
  assert.equal(relay.post(request).status, 'sent')

  const records = relay.diagnostics.map((line) => {
    assert.ok(line.startsWith('DD_RELAY_STAGE '))
    return JSON.parse(line.slice('DD_RELAY_STAGE '.length))
  })
  assert.deepEqual(records.map((record) => record.stage), [
    'request_received',
    'payload_validated',
    'configuration_validated',
    'timestamp_validated',
    'recipient_and_action_validated',
    'signature_validated',
    'lock_acquired',
    'request_reserved',
    'mail_send_started',
    'mail_app_accepted',
    'final_state_persisted',
    'relay_completed',
    'response_returned',
  ])
  for (const record of records) {
    assert.ok(Number.isInteger(record.elapsed_ms) && record.elapsed_ms >= 0)
    assert.ok(Object.keys(record).every((key) => ['stage', 'elapsed_ms', 'status'].includes(key)))
  }
  assert.equal(records.at(-1).status, 'sent')
  const diagnosticText = relay.diagnostics.join('\n')
  for (const sensitiveValue of [secret, request.recipient, request.action_url, request.signature, token]) {
    assert.equal(diagnosticText.includes(sensitiveValue), false)
  }
})

test('rejects invalid signatures and stale timestamps', () => {
  const relay = createRelay()
  const invalid = relay.payload({ request_id: validId2, nonce: 'b'.repeat(32) })
  invalid.signature = '0'.repeat(64)
  assert.equal(relay.post(invalid).status, 'unauthorized')
  const expired = relay.payload({ request_id: validId2, nonce: 'c'.repeat(32), timestamp: 1 })
  // Re-sign stale request so expiry, rather than HMAC, is the failed check.
  expired.signature = createHmac('sha256', secret).update(relay.context.canonicalMessage_(expired), 'utf8').digest('hex')
  assert.equal(relay.post(expired).status, 'expired')
  assert.equal(relay.sent.length, 0)
})

test('returns a sanitized misconfigured status for invalid timestamp tolerance', () => {
  const relay = createRelay({ timestampTolerance: 'invalid' })
  assert.equal(relay.post(relay.payload()).status, 'misconfigured')
  assert.equal(relay.sent.length, 0)
})

test('rejects nonce replay and changed payload for an existing request id', () => {
  const relay = createRelay()
  const first = relay.payload()
  assert.equal(relay.post(first).status, 'sent')

  const replay = relay.payload({ request_id: validId2 })
  assert.equal(relay.post(replay).status, 'replay')

  const changed = relay.payload({
    recipient: 'other@example.net',
    nonce: 'd'.repeat(32),
  })
  assert.equal(relay.post(changed).status, 'idempotency_conflict')
  assert.equal(relay.sent.length, 1)
})

test('rejects unsupported routes and enforces recipient and daily caps', () => {
  const relay = createRelay({ dailyCap: 2 })
  const badLink = relay.payload({
    action_url: `https://attacker.example/verify-email?token=${token}`,
    nonce: 'b'.repeat(32),
  })
  badLink.signature = createHmac('sha256', secret).update(relay.context.canonicalMessage_(badLink), 'utf8').digest('hex')
  assert.equal(relay.post(badLink).status, 'invalid_request')

  const first = relay.payload({ recipient: 'one@example.net', nonce: 'c'.repeat(32) })
  assert.equal(relay.post(first).status, 'sent')
  const cooldown = relay.payload({ request_id: validId2, recipient: 'one@example.net', nonce: 'd'.repeat(32) })
  assert.equal(relay.post(cooldown).status, 'cooldown')
  const second = relay.payload({ request_id: validId2, recipient: 'two@example.net', nonce: 'e'.repeat(32) })
  assert.equal(relay.post(second).status, 'sent')
  const overCap = relay.payload({ request_id: '123e4567-e89b-42d3-a456-426614174002', recipient: 'three@example.net', nonce: 'f'.repeat(32) })
  assert.equal(relay.post(overCap).status, 'daily_cap')
  assert.equal(relay.sent.length, 2)
})

test('rejects action base URLs containing credentials', () => {
  const relay = createRelay({ actionBase: 'https://user:password@dataset.example' })
  assert.equal(relay.post(relay.payload()).status, 'invalid_request')
  assert.equal(relay.sent.length, 0)
})

test('keeps sent requests uncertain when final state persistence fails', () => {
  const relay = createRelay({ failSentStatePersistence: true })
  const request = relay.payload()

  assert.equal(relay.post(request).status, 'delivery_unknown')
  assert.equal(relay.post(request).status, 'delivery_unknown')
  assert.equal(relay.sent.length, 1)
})

test('fails closed when the account quota is exhausted', () => {
  const relay = createRelay({ remainingQuota: 0 })
  assert.equal(relay.post(relay.payload()).status, 'quota_exhausted')
  assert.equal(relay.sent.length, 0)
})

test('sends only the fixed password-reset template with the approved reset route', () => {
  const relay = createRelay()
  const request = relay.payload({
    request_id: '123e4567-e89b-42d3-a456-426614174002',
    nonce: 'f'.repeat(32),
    message_type: 'password_reset',
    action_url: `https://dataset.example/reset-password?token=${token}`,
  })
  request.signature = createHmac('sha256', secret).update(relay.context.canonicalMessage_(request), 'utf8').digest('hex')
  assert.equal(relay.post(request).status, 'sent')
  assert.match(relay.sent[0].subject, /Password reset/)
  assert.match(relay.sent[0].body, /\/reset-password\?token=/)
  assert.doesNotMatch(relay.sent[0].body, /<html|<script/i)
})
