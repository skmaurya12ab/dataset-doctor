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
  "sent", "duplicate_sent", "misconfigured", "expired", "invalid_request",
  "invalid_envelope", "body_too_large", "invalid_json", "invalid_payload",
  "invalid_recipient", "invalid_action_url", "unauthorized",
  "busy", "cooldown", "daily_cap", "quota_exhausted", "relay_error", "delivery_unknown",
  "delivery_failed", "idempotency_conflict", "replay"
];
var SAFE_ACTION_URL_REASONS = [
  "base_whitespace", "base_protocol", "base_credentials", "base_path", "base_query", "base_fragment",
  "link_whitespace", "link_protocol", "origin_mismatch", "path_mismatch", "link_credentials",
  "link_fragment", "token_count", "unexpected_query", "token_format", "url_parse_error"
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

function relayResponse_(startedAt, stage, status, reason) {
  logRelayStage_(startedAt, stage);
  logRelayStage_(startedAt, "response_returned", status);
  var response = { status: status };
  if (status === "invalid_action_url") {
    response.reason = SAFE_ACTION_URL_REASONS.indexOf(reason) >= 0 ? reason : "url_parse_error";
  }
  return output_(response);
}

function doPost(event) {
  var startedAt = Date.now();
  logRelayStage_(startedAt, "request_received");
  if (!event || !event.postData || typeof event.postData.contents !== "string") {
    return relayResponse_(startedAt, "envelope_rejected", "invalid_envelope");
  }
  var raw = event.postData.contents;
  if (Utilities.newBlob(raw).getBytes().length > RELAY.maxBodyBytes) {
    return relayResponse_(startedAt, "body_size_rejected", "body_too_large");
  }

  var payload;
  try {
    payload = JSON.parse(raw);
  } catch (_error) {
    return relayResponse_(startedAt, "json_rejected", "invalid_json");
  }
  if (!validPayloadShape_(payload)) return relayResponse_(startedAt, "payload_rejected", "invalid_payload");
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
  if (!validRecipient_(payload.recipient)) {
    return relayResponse_(startedAt, "recipient_rejected", "invalid_recipient");
  }
  var actionUrlReason = actionUrlValidationReason_(payload.action_url, actionBase, payload.message_type);
  if (actionUrlReason !== null) {
    return relayResponse_(startedAt, "action_url_rejected", "invalid_action_url", actionUrlReason);
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
  return actionUrlValidationReason_(actionUrl, configuredBase, messageType) === null;
}

function actionUrlValidationReason_(actionUrl, configuredBase, messageType) {
  if (typeof configuredBase !== "string" || /[\s\u0000-\u001f\u007f]/.test(configuredBase)) return "base_whitespace";
  if (typeof actionUrl !== "string" || /[\s\u0000-\u001f\u007f]/.test(actionUrl)) return "link_whitespace";

  var base = parseAbsoluteUrlParts_(configuredBase);
  var link = parseAbsoluteUrlParts_(actionUrl);
  if (!base || !link) return "url_parse_error";

  if (base.scheme !== "https") return "base_protocol";
  if (base.hasCredentials) return "base_credentials";
  if (base.pathname !== "/" && base.pathname !== "") return "base_path";
  if (base.hasQuery) return "base_query";
  if (base.hasFragment) return "base_fragment";
  if (link.scheme !== "https") return "link_protocol";
  if (link.origin !== base.origin) return "origin_mismatch";

  var expectedPath;
  if (messageType === "verification") expectedPath = "/verify-email";
  else if (messageType === "password_reset") expectedPath = "/reset-password";
  else return "path_mismatch";
  if (link.pathname !== expectedPath) return "path_mismatch";
  if (link.hasCredentials) return "link_credentials";
  if (link.hasFragment) return "link_fragment";

  var queryParts = link.hasQuery && link.query !== "" ? link.query.split("&") : [];
  var tokenCount = 0;
  var tokenValue = "";
  for (var i = 0; i < queryParts.length; i += 1) {
    var equalsAt = queryParts[i].indexOf("=");
    var key = equalsAt < 0 ? queryParts[i] : queryParts[i].substring(0, equalsAt);
    if (key === "token") {
      tokenCount += 1;
      tokenValue = equalsAt < 0 ? "" : queryParts[i].substring(equalsAt + 1);
    }
  }
  if (tokenCount !== 1) return "token_count";
  if (queryParts.length !== 1) return "unexpected_query";
  if (!/^[A-Za-z0-9_-]{40,256}$/.test(tokenValue)) return "token_format";
  return null;
}

// Apps Script V8 does not provide the browser URL or URLSearchParams APIs.
// Parse only the absolute URL subset used by the relay, failing closed for
// ambiguous forms instead of depending on a web-runtime global.
function parseAbsoluteUrlParts_(value) {
  if (typeof value !== "string" || value.length === 0 || value.length > 4096 ||
      /[\s\u0000-\u001f\u007f\\]/.test(value)) return null;

  var schemeMatch = /^([A-Za-z][A-Za-z0-9+.-]*):\/\//.exec(value);
  if (!schemeMatch) return null;
  var scheme = schemeMatch[1].toLowerCase();
  var authorityStart = schemeMatch[0].length;
  var tail = value.substring(authorityStart);
  var authorityEnd = tail.search(/[\/?#]/);
  if (authorityEnd < 0) authorityEnd = tail.length;
  var authority = tail.substring(0, authorityEnd);
  if (!authority) return null;

  var hasCredentials = authority.indexOf("@") >= 0;
  var hostAndPort = hasCredentials ? authority.substring(authority.lastIndexOf("@") + 1) : authority;
  if (!hostAndPort) return null;

  var host;
  var portText = null;
  if (hostAndPort.charAt(0) === "[") {
    var bracketMatch = /^(\[[0-9A-Fa-f:.]+\])(?::([0-9]*))?$/.exec(hostAndPort);
    if (!bracketMatch) return null;
    var ipv6 = canonicalIpv6_(bracketMatch[1].substring(1, bracketMatch[1].length - 1));
    if (ipv6 === null) return null;
    host = "[" + ipv6 + "]";
    portText = bracketMatch[2] === undefined ? null : bracketMatch[2];
  } else {
    var hostPortMatch = /^([^:\[\]]+)(?::([0-9]*))?$/.exec(hostAndPort);
    if (!hostPortMatch) return null;
    host = hostPortMatch[1].toLowerCase();
    portText = hostPortMatch[2] === undefined ? null : hostPortMatch[2];
    if (!validDnsStyleHost_(host)) return null;
  }

  var port = null;
  if (portText !== null && portText !== "") {
    port = 0;
    for (var p = 0; p < portText.length; p += 1) {
      port = port * 10 + Number(portText.charAt(p));
      if (port > 65535) return null;
    }
  }

  var remainder = tail.substring(authorityEnd);
  var fragmentAt = remainder.indexOf("#");
  var hasFragment = fragmentAt >= 0;
  var fragment = hasFragment ? remainder.substring(fragmentAt + 1) : "";
  var beforeFragment = hasFragment ? remainder.substring(0, fragmentAt) : remainder;
  var queryAt = beforeFragment.indexOf("?");
  var hasQuery = queryAt >= 0;
  var query = hasQuery ? beforeFragment.substring(queryAt + 1) : "";
  var pathAndBeforeQuery = hasQuery ? beforeFragment.substring(0, queryAt) : beforeFragment;
  var pathname = pathAndBeforeQuery || "";
  if (pathname !== "" && pathname.charAt(0) !== "/") return null;

  var defaultPort = scheme === "https" ? 443 : (scheme === "http" ? 80 : null);
  var normalizedPort = port === null || port === defaultPort ? "" : ":" + String(port);
  return {
    scheme: scheme,
    host: host,
    origin: scheme + "://" + host + normalizedPort,
    hasCredentials: hasCredentials,
    pathname: pathname,
    hasQuery: hasQuery,
    query: query,
    hasFragment: hasFragment,
    fragment: fragment
  };
}

function validDnsStyleHost_(host) {
  if (host.length === 0 || host.length > 253 || host.indexOf("..") >= 0) return false;
  var labels = host.charAt(host.length - 1) === "." ? host.substring(0, host.length - 1).split(".") : host.split(".");
  if (labels.length === 0) return false;
  for (var i = 0; i < labels.length; i += 1) {
    if (labels[i].length === 0 || labels[i].length > 63 ||
        !/^[a-z0-9_](?:[a-z0-9_-]*[a-z0-9_])?$/.test(labels[i])) return false;
  }
  return true;
}

function canonicalIpv6_(address) {
  if (!address || address.indexOf("%") >= 0) return null;
  var normalizedAddress = address.toLowerCase();
  if (normalizedAddress.indexOf(".") >= 0) {
    var lastColon = normalizedAddress.lastIndexOf(":");
    if (lastColon < 0) return null;
    var ipv4 = normalizedAddress.substring(lastColon + 1).split(".");
    if (ipv4.length !== 4) return null;
    var octets = [];
    for (var i = 0; i < ipv4.length; i += 1) {
      if (!/^(0|[1-9][0-9]{0,2})$/.test(ipv4[i])) return null;
      var octet = Number(ipv4[i]);
      if (octet > 255) return null;
      octets.push(octet);
    }
    var high = ((octets[0] << 8) | octets[1]).toString(16);
    var low = ((octets[2] << 8) | octets[3]).toString(16);
    normalizedAddress = normalizedAddress.substring(0, lastColon + 1) + high + ":" + low;
  }

  var compressionAt = normalizedAddress.indexOf("::");
  if (compressionAt >= 0 && normalizedAddress.lastIndexOf("::") !== compressionAt) return null;
  var groups = normalizedAddress.split(":");
  var nonemptyGroups = [];
  for (var j = 0; j < groups.length; j += 1) {
    if (groups[j] !== "") {
      if (!/^[0-9a-f]{1,4}$/.test(groups[j])) return null;
      nonemptyGroups.push(parseInt(groups[j], 16));
    }
  }
  if (compressionAt >= 0) {
    if (nonemptyGroups.length >= 8) return null;
    var zeros = 8 - nonemptyGroups.length;
    var leftText = normalizedAddress.substring(0, compressionAt);
    var leftGroups = leftText === "" ? [] : leftText.split(":");
    var canonicalGroups = [];
    for (var k = 0; k < leftGroups.length; k += 1) canonicalGroups.push(parseInt(leftGroups[k], 16));
    for (var z = 0; z < zeros; z += 1) canonicalGroups.push(0);
    var rightText = normalizedAddress.substring(compressionAt + 2);
    var rightGroups = rightText === "" ? [] : rightText.split(":");
    for (var r = 0; r < rightGroups.length; r += 1) canonicalGroups.push(parseInt(rightGroups[r], 16));
    if (canonicalGroups.length !== 8) return null;
    nonemptyGroups = canonicalGroups;
  } else if (nonemptyGroups.length !== 8) {
    return null;
  }
  return nonemptyGroups.map(function (group) { return group.toString(16); }).join(":");
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
