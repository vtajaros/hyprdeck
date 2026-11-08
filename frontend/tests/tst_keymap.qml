import QtQuick 2.15
import QtTest 1.0
import "../components/keymap.js" as KeyMap

TestCase {
    name: "KeyMapTests"

    function test_modifiers() {
        compare(KeyMap.extractModmask(Qt.NoModifier), 0);
        compare(KeyMap.extractModmask(Qt.ShiftModifier), 1);
        compare(KeyMap.extractModmask(Qt.ControlModifier), 4);
        compare(KeyMap.extractModmask(Qt.AltModifier), 8);
        compare(KeyMap.extractModmask(Qt.MetaModifier), 64);
        compare(KeyMap.extractModmask(Qt.MetaModifier | Qt.ShiftModifier), 65);
        compare(KeyMap.extractModmask(Qt.MetaModifier | Qt.ControlModifier | Qt.AltModifier), 76);
    }

    function test_letters_and_digits() {
        var evQ = { modifiers: Qt.MetaModifier, key: Qt.Key_Q, nativeScanCode: 24 };
        var resQ = KeyMap.translateKeyEvent(evQ);
        verify(resQ.recognized);
        compare(resQ.modmask, 64);
        compare(resQ.key, "q");
        compare(resQ.display, "SUPER + q");

        var ev1 = { modifiers: Qt.MetaModifier, key: Qt.Key_1, nativeScanCode: 10 };
        var res1 = KeyMap.translateKeyEvent(ev1);
        compare(res1.key, "1");
        compare(res1.display, "SUPER + 1");
    }

    function test_shifted_symbols_map_to_base() {
        // Shift+1 gives Key_Exclam
        var ev = { modifiers: Qt.MetaModifier | Qt.ShiftModifier, key: Qt.Key_Exclam, nativeScanCode: 10 };
        var res = KeyMap.translateKeyEvent(ev);
        verify(res.recognized);
        compare(res.modmask, 65);
        compare(res.key, "1");
        compare(res.display, "SUPER + SHIFT + 1");

        // Shift+~ gives Key_AsciiTilde -> grave
        var evTilde = { modifiers: Qt.ShiftModifier, key: Qt.Key_AsciiTilde, nativeScanCode: 49 };
        compare(KeyMap.translateKeyEvent(evTilde).key, "grave");

        // Shift+_ gives Key_Underscore -> minus
        var evUnderscore = { modifiers: Qt.ShiftModifier, key: Qt.Key_Underscore, nativeScanCode: 20 };
        compare(KeyMap.translateKeyEvent(evUnderscore).key, "minus");
    }

    function test_navigation_and_editing_keys() {
        var ret = KeyMap.translateKeyEvent({ modifiers: Qt.MetaModifier, key: Qt.Key_Return, nativeScanCode: 36 });
        compare(ret.key, "Return");
        compare(ret.display, "SUPER + Return");

        var tab = KeyMap.translateKeyEvent({ modifiers: Qt.AltModifier, key: Qt.Key_Tab, nativeScanCode: 23 });
        compare(tab.key, "Tab");
        compare(tab.display, "ALT + Tab");

        var space = KeyMap.translateKeyEvent({ modifiers: Qt.AltModifier, key: Qt.Key_Space, nativeScanCode: 65 });
        compare(space.key, "space");
        compare(space.display, "ALT + space");

        var bs = KeyMap.translateKeyEvent({ modifiers: 0, key: Qt.Key_Backspace, nativeScanCode: 22 });
        compare(bs.key, "BackSpace");

        var del = KeyMap.translateKeyEvent({ modifiers: 0, key: Qt.Key_Delete, nativeScanCode: 119 });
        compare(del.key, "Delete");

        var esc = KeyMap.translateKeyEvent({ modifiers: 0, key: Qt.Key_Escape, nativeScanCode: 9 });
        compare(esc.key, "Escape");
    }

    function test_arrows_and_function_keys() {
        var up = KeyMap.translateKeyEvent({ modifiers: Qt.MetaModifier, key: Qt.Key_Up, nativeScanCode: 111 });
        compare(up.key, "Up");

        var f12 = KeyMap.translateKeyEvent({ modifiers: 0, key: Qt.Key_F12, nativeScanCode: 96 });
        compare(f12.key, "F12");
    }

    function test_media_keys() {
        var vup = KeyMap.translateKeyEvent({ modifiers: 0, key: Qt.Key_VolumeUp, nativeScanCode: 123 });
        compare(vup.key, "XF86AudioRaiseVolume");

        var vdown = KeyMap.translateKeyEvent({ modifiers: 0, key: Qt.Key_VolumeDown, nativeScanCode: 122 });
        compare(vdown.key, "XF86AudioLowerVolume");

        var mute = KeyMap.translateKeyEvent({ modifiers: 0, key: Qt.Key_VolumeMute, nativeScanCode: 121 });
        compare(mute.key, "XF86AudioMute");

        var play = KeyMap.translateKeyEvent({ modifiers: 0, key: Qt.Key_MediaPlay, nativeScanCode: 172 });
        compare(play.key, "XF86AudioPlay");
    }

    function test_unrecognized_fallback_to_keycode() {
        // Unknown key 0x12345 with scancode 248
        var ev = { modifiers: Qt.MetaModifier, key: 0x12345, nativeScanCode: 248 };
        var res = KeyMap.translateKeyEvent(ev);
        verify(res.recognized);
        compare(res.key, "code:248");
        compare(res.display, "SUPER + code:248");
    }

    function test_format_display() {
        compare(KeyMap.formatDisplay(64, "Return"), "SUPER + Return");
        compare(KeyMap.formatDisplay(65, "1"), "SUPER + SHIFT + 1");
        compare(KeyMap.formatDisplay(76, "grave"), "SUPER + CTRL + ALT + grave");
        compare(KeyMap.formatDisplay(0, "XF86AudioMute"), "XF86AudioMute");
    }

    function test_modmask_roundtrip_tokens() {
        var mask = 64 | 4 | 1; // SUPER + CTRL + SHIFT = 69
        var parts = [];
        if (mask & 64) parts.push("SUPER");
        if (mask & 4) parts.push("CTRL");
        if (mask & 8) parts.push("ALT");
        if (mask & 1) parts.push("SHIFT");
        compare(parts.join("+"), "SUPER+CTRL+SHIFT");
    }
}
