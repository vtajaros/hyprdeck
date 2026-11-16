.pragma library

var EXPECTED_KEYS = [
    "bg",
    "surface",
    "elevated",
    "fg",
    "muted",
    "accent",
    "secondary",
    "warning",
    "critical"
];

function evaluateThemeText(rawText, lastAppliedRaw) {
    if (rawText === undefined || rawText === null) {
        return { changed: false, valid: false, palette: null, reason: "empty" };
    }
    var raw = String(rawText);
    if (raw.trim().length === 0) {
        return { changed: false, valid: false, palette: null, reason: "empty" };
    }
    if (lastAppliedRaw !== undefined && lastAppliedRaw !== null && raw === String(lastAppliedRaw)) {
        return { changed: false, valid: true, palette: null, reason: "unchanged" };
    }
    var trimmed = raw.trim();
    if (trimmed.charAt(0) !== "{") {
        return { changed: true, valid: false, palette: null, reason: "invalid_json" };
    }
    var data = null;
    try {
        data = JSON.parse(trimmed);
    } catch (e) {
        return { changed: true, valid: false, palette: null, reason: "invalid_json" };
    }
    if (!data || typeof data !== "object" || Array.isArray(data)) {
        return { changed: true, valid: false, palette: null, reason: "invalid_object" };
    }
    var palette = {};
    for (var i = 0; i < EXPECTED_KEYS.length; i++) {
        var k = EXPECTED_KEYS[i];
        var v = data[k];
        if (typeof v !== "string" || v.trim().length === 0) {
            return { changed: true, valid: false, palette: null, reason: "missing_key:" + k };
        }
        palette[k] = v.trim();
    }
    return { changed: true, valid: true, palette: palette, reason: "ok" };
}
