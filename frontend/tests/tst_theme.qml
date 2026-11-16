import QtQuick
import QtTest
import "../theme/ThemeLogic.js" as ThemeLogic

TestCase {
    id: tc
    name: "ThemeLogicTests"

    readonly property string validRawA: JSON.stringify({
        bg: "#111413",
        surface: "#1e201f",
        elevated: "#282a2a",
        fg: "#e2e3e1",
        muted: "#c0c8c5",
        accent: "#9fd0c5",
        secondary: "#b7cbc5",
        warning: "#d79921",
        critical: "#ffb4ab"
    })

    readonly property string validRawB: JSON.stringify({
        bg: "#201010",
        surface: "#2a1818",
        elevated: "#342020",
        fg: "#f0e0e0",
        muted: "#b09090",
        accent: "#ff8888",
        secondary: "#cc9999",
        warning: "#e0a020",
        critical: "#ff4444"
    })

    function test_valid_file_applies_all_keys() {
        var res = ThemeLogic.evaluateThemeText(validRawA, "");
        verify(res.changed);
        verify(res.valid);
        verify(res.palette !== null);
        compare(res.reason, "ok");
        compare(res.palette.bg, "#111413");
        compare(res.palette.accent, "#9fd0c5");
        compare(res.palette.critical, "#ffb4ab");
    }

    function test_missing_key_is_rejected() {
        var partial = JSON.stringify({
            bg: "#111413",
            surface: "#1e201f",
            elevated: "#282a2a",
            fg: "#e2e3e1",
            muted: "#c0c8c5",
            secondary: "#b7cbc5",
            warning: "#d79921",
            critical: "#ffb4ab"
        });
        var res = ThemeLogic.evaluateThemeText(partial, validRawA);
        verify(res.changed);
        verify(!res.valid);
        compare(res.palette, null);
        compare(res.reason, "missing_key:accent");
    }

    function test_invalid_json_is_rejected() {
        var res = ThemeLogic.evaluateThemeText("{\"bg\": \"#111413\",", validRawA);
        verify(res.changed);
        verify(!res.valid);
        compare(res.palette, null);
        compare(res.reason, "invalid_json");

        var resArr = ThemeLogic.evaluateThemeText("[1, 2, 3]", validRawA);
        verify(resArr.changed);
        verify(!resArr.valid);
        compare(resArr.palette, null);
        compare(resArr.reason, "invalid_json");
    }

    function test_empty_file_is_rejected_without_churn() {
        var resEmpty = ThemeLogic.evaluateThemeText("", validRawA);
        verify(!resEmpty.changed);
        verify(!resEmpty.valid);
        compare(resEmpty.palette, null);
        compare(resEmpty.reason, "empty");

        var resWs = ThemeLogic.evaluateThemeText("   \n\t ", validRawA);
        verify(!resWs.changed);
        verify(!resWs.valid);
        compare(resWs.palette, null);
        compare(resWs.reason, "empty");
    }

    function test_identical_content_is_noop() {
        var res = ThemeLogic.evaluateThemeText(validRawA, validRawA);
        verify(!res.changed);
        verify(res.valid);
        compare(res.palette, null);
        compare(res.reason, "unchanged");
    }

    function test_changed_content_triggers_update() {
        var res = ThemeLogic.evaluateThemeText(validRawB, validRawA);
        verify(res.changed);
        verify(res.valid);
        verify(res.palette !== null);
        compare(res.reason, "ok");
        compare(res.palette.bg, "#201010");
        compare(res.palette.accent, "#ff8888");
    }
}
