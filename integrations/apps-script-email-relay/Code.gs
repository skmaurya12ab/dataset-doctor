/**
 * Dataset Doctor fixed-template mail relay.
 * Deploy as a web app executing as the deploying account. See docs/email-delivery.md.
 * No request headers, arbitrary sender, or caller-supplied message body is trusted.
 */
var RELAY = {
  maxBodyBytes: 8192,
  defaultDailyCap: 20,
  maxDailyCap: 80,
  defaultCooldownSeconds: 900,
  defaultTimestampWindowSeconds: 300,
  defaultNonceTtlSeconds: 900,
  defaultIdempotencyTtlSeconds: 86400
};

var SAFE_RELAY_STATUSES = [
  "sent", "duplicate_sent", "misconfigured", "expired", "invalid_request", "unauthorized",
  "busy", "cooldown", "daily_cap", "quota_exhausted", "relay_error", "delivery_unknown",
  "delivery_failed", "idempotency_conflict", "replay"
];

function logRelayStage_(startedAt, stage, status) {
  var record = {
    stage: stage,
    elapsed_ms: Math.max(0, Date.now() - startedAt)
  };
  if (status) {
    record.status = SAFE_RELAY_STATUSES.indexOf(status) >= 0 ? status : "relay_error";
  }
  try {
    console.log("DD_RELAY_STAGE " + JSON.stringify(record));
  } catch (_error) {
    // Diagnostics must never prevent a relay response or email send.
  }
}

function relayResponse_(startedAt, stage, status) {
  logRelayStage_(startedAt, stage);
  logRelayStage_(startedAt, "response_returned", status);
  return output_({ status: status });
}

function doPost(event) {
  var startedAt = Date.now();
  logRelayStage_(startedAt, "request_received");
  if (!event || !event.postData || typeof event.postData.contents !== "string") {
    return relayResponse_(startedAt, "request_rejected", "invalid_request");
  }
  var raw = event.postData.contents;
  if (Utilities.newBlob(raw).getBytes().length > RELAY.maxBodyBytes) {
    return relayResponse_(startedAt, "request_rejected", "invalid_request");
  }

  var payload;
  try {
    payload = JSON.parse(raw);
  } catch (_error) {
    return relayResponse_(startedAt, "request_rejected", "invalid_request");
  }
  if (!validPayloadShape_(payload)) return relayResponse_(startedAt, "request_rejected", "invalid_request");
  logRelayStage_(startedAt, "payload_validated");

  var properties = PropertiesService.getScriptProperties();
  var secret = properties.getProperty("HMAC_SECRET");
  var actionBase = properties.getProperty("ACTION_BASE_URL");
  if (!secret || secret.length < 32 || !actionBase) {
    return relayResponse_(startedAt, "configuration_rejected", "misconfigured");
  }
  logRelayStage_(startedAt, "configuration_validated");

  var now = Date.now();
  var timestampWindow;
  try {
    timestampWindow = boundedIntegerProperty_(properties, "TIMESTAMP_TOLERANCE_SECONDS", 1, 600,
      RELAY.defaultTimestampWindowSeconds);
  } catch (_error) {
    return relayResponse_(startedAt, "configuration_rejected", "misconfigured");
  }
  if (Math.abs(Math.floor(now / 1000) - payload.timestamp) > timestampWindow) {
    return relayResponse_(startedAt, "timestamp_rejected", "expired");
  }
  logRelayStage_(startedAt, "timestamp_validated");
  if (!validRecipient_(payload.recipient) || !validActionUrl_(payload.action_url, actionBase, payload.message_type)) {
    return relayResponse_(startedAt, "recipient_or_action_rejected", "invalid_request");
  }
  logRelayStage_(startedAt, "recipient_and_action_validated");

  var canonical = canonicalMessage_(payload);
  var expectedSignature = hmacHex_(canonical, secret);
  if (!constantTimeEqual_(expectedSignature, payload.signature)) {
    return relayResponse_(startedAt, "signature_rejected", "unauthorized");
  }
  logRelayStage_(startedAt, "signature_validated");

  var requestHash = sha256Hex_([
    payload.request_id,
    payload.message_type,
    payload.recipient.toLowerCase(),
    payload.action_url
  ].join("\n"));
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(5000)) return relayResponse_(startedAt, "lock_busy", "busy");
  logRelayStage_(startedAt, "lock_acquired");

  var requestKey = "request_" + payload.request_id;
  var reserved;
  try {
    cleanupExpiredRecords_(properties, now);
    var existing = parseRecord_(properties.getProperty(requestKey));
    if (existing) {
      if (existing.hash !== requestHash) {
        return relayResponse_(startedAt, "idempotency_conflict", "idempotency_conflict");
      }
      if (existing.status === "sent") {
        return relayResponse_(startedAt, "duplicate_request", "duplicate_sent");
      }
      // A reserved/failed call is never resent automatically: sendEmail may have
      // succeeded immediately before an execution or response failure.
      var existingStatus = existing.status === "processing" || existing.status === "delivery_unknown"
        ? "delivery_unknown"
        : "delivery_failed";
      return relayResponse_(startedAt, "duplicate_non_success", existingStatus);
    }

    var nonceKey = "nonce_" + payload.nonce;
    if (properties.getProperty(nonceKey)) return relayResponse_(startedAt, "nonce_replay", "replay");

    var dailyCap = boundedIntegerProperty_(properties, "DAILY_SEND_CAP", 1, RELAY.maxDailyCap,
      RELAY.defaultDailyCap);
    var cooldownSeconds = boundedIntegerProperty_(properties, "RECIPIENT_COOLDOWN_SECONDS", 60, 86400,
      RELAY.defaultCooldownSeconds);
    if (MailApp.getRemainingDailyQuota() < 1) {
      return relayResponse_(startedAt, "mail_quota_exhausted", "quota_exhausted");
    }

    var recipientKey = "recipient_" + hmacHex_(
      "recipient\n" + payload.message_type + "\n" + payload.recipient.toLowerCase(), secret
    );
    var recipientRecord = parseRecord_(properties.getProperty(recipientKey));
    if (recipientRecord && Number(recipientRecord.cooldown_until_ms) > now) {
      return relayResponse_(startedAt, "recipient_cooldown", "cooldown");
    }

    var utcDate = new Date(now).toISOString().slice(0, 10);
    var dailyKey = "daily_" + utcDate;
    var dailyRecord = parseRecord_(properties.getProperty(dailyKey)) || { attempt_count: 0 };
    if (Number(dailyRecord.attempt_count) >= dailyCap) {
      return relayResponse_(startedAt, "project_daily_cap", "daily_cap");
    }

    var nonceTtl = boundedIntegerProperty_(properties, "NONCE_TTL_SECONDS", 300, 3600,
      RELAY.defaultNonceTtlSeconds);
    var idempotencyTtl = boundedIntegerProperty_(properties, "IDEMPOTENCY_TTL_SECONDS", 3600, 172800,
      RELAY.defaultIdempotencyTtlSeconds);
    reserved = {
      requestKey: requestKey,
      requestRecord: {
        hash: requestHash,
        status: "processing",
        expires_at_ms: now + idempotencyTtl * 1000
      },
      nonceKey: nonceKey,
      nonceRecord: { expires_at_ms: now + nonceTtl * 1000 },
      recipientKey: recipientKey,
      recipientRecord: { cooldown_until_ms: now + cooldownSeconds * 1000 },
      dailyKey: dailyKey,
      dailyRecord: { attempt_count: Number(dailyRecord.attempt_count) + 1 }
    };
    properties.setProperty(reserved.requestKey, JSON.stringify(reserved.requestRecord));
    properties.setProperty(reserved.nonceKey, JSON.stringify(reserved.nonceRecord));
    properties.setProperty(reserved.recipientKey, JSON.stringify(reserved.recipientRecord));
    properties.setProperty(reserved.dailyKey, JSON.stringify(reserved.dailyRecord));
    logRelayStage_(startedAt, "request_reserved");
  } catch (_error) {
    return relayResponse_(startedAt, "reservation_failed", "relay_error");
  } finally {
    lock.releaseLock();
  }

  logRelayStage_(startedAt, "mail_send_started");
  try {
    var message = fixedMessage_(payload.message_type, payload.action_url);
    MailApp.sendEmail({
      to: payload.recipient,
      subject: message.subject,
      body: message.body,
      name: "Dataset Doctor"
    });
    logRelayStage_(startedAt, "mail_app_accepted");
  } catch (_error) {
    // Do not return or log exception text: it may include recipient data.
    try {
      reserved.requestRecord.status = "failed";
      properties.setProperty(reserved.requestKey, JSON.stringify(reserved.requestRecord));
      logRelayStage_(startedAt, "failure_state_persisted");
    } catch (_recordError) {
      // A missing final record leaves "processing" and therefore still fails closed.
      logRelayStage_(startedAt, "failure_state_persistence_failed");
      return relayResponse_(startedAt, "delivery_state_uncertain", "delivery_unknown");
    }
    return relayResponse_(startedAt, "mail_send_failed", "delivery_failed");
  }

  try {
    reserved.requestRecord.status = "sent";
    properties.setProperty(reserved.requestKey, JSON.stringify(reserved.requestRecord));
  } catch (_stateError) {
    // MailApp accepted the message, but processing remains the durable state.
    // Keep this request id non-retryable and do not claim a persisted success.
    return relayResponse_(startedAt, "final_state_persistence_failed", "delivery_unknown");
  }
  logRelayStage_(startedAt, "final_state_persisted");
  return relayResponse_(startedAt, "relay_completed", "sent");
}

function validPayloadShape_(payload) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return false;
  var expectedKeys = ["action_url", "message_type", "nonce", "recipient", "request_id", "schema_version", "signature", "timestamp"];
  var actualKeys = Object.keys(payload).sort();
  if (actualKeys.join("|") !== expectedKeys.join("|")) return false;
  return payload.schema_version === 1 && Number.isSafeInteger(payload.timestamp) &&
    /^[a-f0-9]{32}$/.test(payload.nonce) &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(payload.request_id) &&
    (payload.message_type === "verification" || payload.message_type === "password_reset") &&
    typeof payload.recipient === "string" && typeof payload.action_url === "string" &&
    typeof payload.signature === "string" && /^[a-f0-9]{64}$/.test(payload.signature);
}

function canonicalMessage_(payload) {
  return [
    "dataset-doctor-email-relay-v1",
    String(payload.schema_version),
    String(payload.timestamp),
    payload.nonce,
    payload.request_id,
    payload.message_type,
    payload.recipient,
    payload.action_url
  ].join("\n");
}

function validRecipient_(recipient) {
  if (recipient.length > 254 || /[\r\n\s]/.test(recipient)) return false;
  return /^[A-Z0-9.!#$%&'*+\-/=?^_`{|}~]+@[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?(?:\.[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)+$/i.test(recipient);
}

function validActionUrl_(actionUrl, configuredBase, messageType) {
  try {
    var link = new URL(actionUrl);
    var base = new URL(configuredBase);
    var expectedPath = messageType === "verification" ? "/verify-email" : "/reset-password";
    var tokenValues = link.searchParams.getAll("token");
    var queryKeys = [];
    link.searchParams.forEach(function (_value, key) { queryKeys.push(key); });
    return base.protocol === "https:" && base.username === "" && base.password === "" &&
      (base.pathname === "/" || base.pathname === "") &&
      base.search === "" && base.hash === "" && link.protocol === "https:" && link.origin === base.origin && link.pathname === expectedPath &&
      link.username === "" && link.password === "" && link.hash === "" &&
      tokenValues.length === 1 && queryKeys.length === 1 &&
      /^[A-Za-z0-9_-]{40,256}$/.test(tokenValues[0]);
  } catch (_error) {
    return false;
  }
}

function fixedMessage_(messageType, actionUrl) {
  if (messageType === "verification") {
    return {
      subject: "Dataset Doctor — Verify your email address",
      body: "Hello,\n\nVerify your Dataset Doctor email address using this link:\n" +
        actionUrl + "\n\nThis single-use link expires automatically.\n\n— The Dataset Doctor Team"
    };
  }
  if (messageType === "password_reset") {
    return {
      subject: "Dataset Doctor — Password reset request",
      body: "Hello,\n\nReset your Dataset Doctor password using this single-use link:\n" +
        actionUrl + "\n\nThis single-use link expires automatically. If you did not request this, ignore this email.\n\n" +
        "— The Dataset Doctor Team"
    };
  }
  throw new Error("Unsupported message type");
}

function hmacHex_(message, secret) {
  return bytesToHex_(Utilities.computeHmacSha256Signature(message, secret, Utilities.Charset.UTF_8));
}

function sha256Hex_(message) {
  return bytesToHex_(Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, message, Utilities.Charset.UTF_8));
}

function bytesToHex_(bytes) {
  return bytes.map(function (byte) {
    return (byte & 0xff).toString(16).padStart(2, "0");
  }).join("");
}

function constantTimeEqual_(left, right) {
  if (typeof left !== "string" || typeof right !== "string" || left.length !== right.length) return false;
  var difference = 0;
  for (var i = 0; i < left.length; i += 1) difference |= left.charCodeAt(i) ^ right.charCodeAt(i);
  return difference === 0;
}

function boundedIntegerProperty_(properties, name, minimum, maximum, fallback) {
  var raw = properties.getProperty(name);
  if (raw === null || raw === "") return fallback;
  var value = Number(raw);
  if (!Number.isInteger(value) || value < minimum || value > maximum) throw new Error("Invalid relay setting");
  return value;
}

function parseRecord_(raw) {
  if (!raw) return null;
  try {
    var parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch (_error) {
    return null;
  }
}

function cleanupExpiredRecords_(properties, now) {
  var all = properties.getProperties();
  Object.keys(all).forEach(function (key) {
    var record = parseRecord_(all[key]);
    if (key.indexOf("nonce_") === 0 || key.indexOf("request_") === 0) {
      if (!record || Number(record.expires_at_ms) <= now) properties.deleteProperty(key);
      return;
    }
    if (key.indexOf("recipient_") === 0) {
      if (!record || Number(record.cooldown_until_ms) <= now) properties.deleteProperty(key);
      return;
    }
    if (key.indexOf("daily_") === 0) {
      var recordDate = new Date(key.slice(6) + "T00:00:00Z").getTime();
      var currentDate = new Date(new Date(now).toISOString().slice(0, 10) + "T00:00:00Z").getTime();
      if (!record || !Number.isFinite(recordDate) || recordDate < currentDate - 86400000) properties.deleteProperty(key);
    }
  });
}

function output_(result) {
  return ContentService.createTextOutput(JSON.stringify(result)).setMimeType(ContentService.MimeType.JSON);
}
