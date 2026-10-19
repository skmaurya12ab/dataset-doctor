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
    return postRaw(JSON.stringify(body))
  }
  function postRaw(raw) {
    return JSON.parse(context.doPost({ postData: { contents: raw } }).getContent())
  }
  function postEvent(event) {
    return JSON.parse(context.doPost(event).getContent())
  }
  return {
    context,
    payload,
    post,
    postRaw,
    postEvent,
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

test('classifies request-envelope, size, JSON, and payload-shape failures safely', () => {
  const relay = createRelay()
  const oversized = JSON.stringify({ body: 'x'.repeat(9000) })
  const malformed = '{"status":'
  const missingKey = relay.payload()
  delete missingKey.signature
  const extraKey = { ...relay.payload(), unexpected: true }
  const invalidType = relay.payload({ timestamp: 'not-an-integer' })

  assert.equal(relay.postEvent(undefined).status, 'invalid_envelope')
  assert.equal(relay.postEvent({}).status, 'invalid_envelope')
  assert.equal(relay.postEvent({ postData: {} }).status, 'invalid_envelope')
  assert.equal(relay.postEvent({ postData: { contents: null } }).status, 'invalid_envelope')
  assert.equal(relay.postRaw(oversized).status, 'body_too_large')
  assert.equal(relay.postRaw(malformed).status, 'invalid_json')
  assert.equal(relay.post(missingKey).status, 'invalid_payload')
  assert.equal(relay.post(extraKey).status, 'invalid_payload')
  assert.equal(relay.post(invalidType).status, 'invalid_payload')
  assert.equal(relay.sent.length, 0)

  const records = relay.diagnostics.map((line) => JSON.parse(line.slice('DD_RELAY_STAGE '.length)))
  const statuses = records.filter((record) => record.stage === 'response_returned').map((record) => record.status)
  assert.deepEqual(statuses, [
    'invalid_envelope', 'invalid_envelope', 'invalid_envelope', 'invalid_envelope',
    'body_too_large', 'invalid_json', 'invalid_payload', 'invalid_payload', 'invalid_payload',
  ])
  for (const record of records) {
    assert.ok(Number.isInteger(record.elapsed_ms) && record.elapsed_ms >= 0)
    assert.ok(Object.keys(record).every((key) => ['stage', 'elapsed_ms', 'status'].includes(key)))
  }
  const diagnosticText = relay.diagnostics.join('\n')
  for (const sensitiveValue of [secret, malformed, oversized, missingKey.recipient, missingKey.action_url, token]) {
    assert.equal(diagnosticText.includes(sensitiveValue), false)
  }
})

test('classifies recipient and action URL validation failures separately', () => {
  const relay = createRelay()
  const invalidRecipient = relay.payload({ recipient: 'not-an-email' })
  const invalidActionUrl = relay.payload({ action_url: `https://attacker.example/verify-email?token=${token}` })

  assert.equal(relay.post(invalidRecipient).status, 'invalid_recipient')
  const rejected = relay.post(invalidActionUrl)
  assert.equal(rejected.status, 'invalid_action_url')
  assert.equal(rejected.reason, 'origin_mismatch')
  assert.equal(relay.sent.length, 0)

  const statuses = relay.diagnostics
    .map((line) => JSON.parse(line.slice('DD_RELAY_STAGE '.length)))
    .filter((record) => record.stage === 'response_returned')
    .map((record) => record.status)
  assert.deepEqual(statuses, ['invalid_recipient', 'invalid_action_url'])
})

test('reports only allowlisted action URL validation reasons', () => {
  const relay = createRelay()
  assert.equal(typeof relay.context.URL, 'undefined')
  assert.equal(typeof relay.context.URLSearchParams, 'undefined')
  const validUrl = `https://dataset.example/verify-email?token=${token}`
  const cases = [
    ['https://dataset.example/verify-email?token=' + token, 'http://dataset.example', 'verification', 'base_protocol'],
    [validUrl, 'https://user:private@dataset.example', 'verification', 'base_credentials'],
    [validUrl, 'https://dataset.example/base', 'verification', 'base_path'],
    [validUrl, 'https://dataset.example/?mode=demo', 'verification', 'base_query'],
    [validUrl, 'https://dataset.example?', 'verification', 'base_query'],
    [validUrl, 'https://dataset.example/#demo', 'verification', 'base_fragment'],
    [validUrl, 'https://dataset.example#', 'verification', 'base_fragment'],
    [`http://dataset.example/verify-email?token=${token}`, 'https://dataset.example', 'verification', 'link_protocol'],
    [`https://attacker.example/verify-email?token=${token}`, 'https://dataset.example', 'verification', 'origin_mismatch'],
    [`https://dataset.example/other?token=${token}`, 'https://dataset.example', 'verification', 'path_mismatch'],
    [`https://user:private@dataset.example/verify-email?token=${token}`, 'https://dataset.example', 'verification', 'link_credentials'],
    [`${validUrl}#demo`, 'https://dataset.example', 'verification', 'link_fragment'],
    ['https://dataset.example/verify-email', 'https://dataset.example', 'verification', 'token_count'],
    [`${validUrl}&token=${token}`, 'https://dataset.example', 'verification', 'token_count'],
    [`${validUrl}&source=demo`, 'https://dataset.example', 'verification', 'unexpected_query'],
    ['https://dataset.example/verify-email?token=short', 'https://dataset.example', 'verification', 'token_format'],
    ['https://[', 'https://dataset.example', 'verification', 'url_parse_error'],
    [validUrl, 'https://dataset.example ', 'verification', 'base_whitespace'],
    [`https://dataset.example /verify-email?token=${token}`, 'https://dataset.example', 'verification', 'link_whitespace'],
  ]

  for (const [actionUrl, actionBase, messageType, expectedReason] of cases) {
    assert.equal(relay.context.actionUrlValidationReason_(actionUrl, actionBase, messageType), expectedReason)
  }

  const normalizedOrigin = `https://DATASET.EXAMPLE:443/verify-email?token=${token}`
  assert.equal(relay.context.actionUrlValidationReason_(normalizedOrigin, 'https://dataset.example', 'verification'), null)
  const emptyPortOrigin = `https://DATASET.EXAMPLE:/verify-email?token=${token}`
  assert.equal(relay.context.actionUrlValidationReason_(emptyPortOrigin, 'https://dataset.example:000443', 'verification'), null)
  const normalizedIpv6Origin = 'https://[2001:0db8:0:0:0:0:0:1]:443/verify-email?token=' + token
  assert.equal(
    relay.context.actionUrlValidationReason_(normalizedIpv6Origin, 'https://[2001:db8::1]', 'verification'),
    null,
  )
  const safeFallback = relay.context.relayResponse_(0, 'action_url_rejected', 'invalid_action_url', 'untrusted-provider-value')
  assert.equal(JSON.parse(safeFallback.getContent()).reason, 'url_parse_error')
  assert.equal(relay.sent.length, 0)
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
  assert.equal(relay.post(badLink).status, 'invalid_action_url')

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
  const response = relay.post(relay.payload())
  assert.equal(response.status, 'invalid_action_url')
  assert.equal(response.reason, 'base_credentials')
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
