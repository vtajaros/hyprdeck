.pragma library

// Qt Key to Hyprland Key & Modifier Translation Library for HyprDeck

// Modifiers bitmask constants matching Hyprland / HyprDeck
var MOD_SHIFT = 1;
var MOD_CTRL  = 4;
var MOD_ALT   = 8;
var MOD_SUPER = 64;

var MOD_NAMES = [
    { mask: MOD_SUPER, name: "SUPER" },
    { mask: MOD_CTRL,  name: "CTRL" },
    { mask: MOD_ALT,   name: "ALT" },
    { mask: MOD_SHIFT, name: "SHIFT" }
];

function extractModmask(modifiers) {
    var mask = 0;
    if (modifiers & Qt.ShiftModifier) mask |= MOD_SHIFT;
    if (modifiers & Qt.ControlModifier) mask |= MOD_CTRL;
    if (modifiers & Qt.AltModifier) mask |= MOD_ALT;
    if (modifiers & Qt.MetaModifier) mask |= MOD_SUPER;
    return mask;
}

function modmaskToParts(modmask) {
    var parts = [];
    for (var i = 0; i < MOD_NAMES.length; i++) {
        if ((modmask & MOD_NAMES[i].mask) !== 0) {
            parts.push(MOD_NAMES[i].name);
        }
    }
    return parts;
}

function isModifierOnlyKey(key) {
    return key === Qt.Key_Shift ||
           key === Qt.Key_Control ||
           key === Qt.Key_Meta ||
           key === Qt.Key_Alt ||
           key === Qt.Key_AltGr ||
           key === Qt.Key_Super_L ||
           key === Qt.Key_Super_R ||
           key === Qt.Key_Hyper_L ||
           key === Qt.Key_Hyper_R;
}

// US keyboard layout shifted symbols mapped back to base keys
var SHIFT_MAP = {};
SHIFT_MAP[Qt.Key_Exclam] = "1";
SHIFT_MAP[Qt.Key_At] = "2";
SHIFT_MAP[Qt.Key_NumberSign] = "3";
SHIFT_MAP[Qt.Key_Dollar] = "4";
SHIFT_MAP[Qt.Key_Percent] = "5";
SHIFT_MAP[Qt.Key_AsciiCircum] = "6";
SHIFT_MAP[Qt.Key_Ampersand] = "7";
SHIFT_MAP[Qt.Key_Asterisk] = "8";
SHIFT_MAP[Qt.Key_ParenLeft] = "9";
SHIFT_MAP[Qt.Key_ParenRight] = "0";
SHIFT_MAP[Qt.Key_Underscore] = "minus";
SHIFT_MAP[Qt.Key_Plus] = "equal";
SHIFT_MAP[Qt.Key_BraceLeft] = "bracketleft";
SHIFT_MAP[Qt.Key_BraceRight] = "bracketright";
SHIFT_MAP[Qt.Key_Bar] = "backslash";
SHIFT_MAP[Qt.Key_Colon] = "semicolon";
SHIFT_MAP[Qt.Key_QuoteDbl] = "apostrophe";
SHIFT_MAP[Qt.Key_Less] = "comma";
SHIFT_MAP[Qt.Key_Greater] = "period";
SHIFT_MAP[Qt.Key_Question] = "slash";
SHIFT_MAP[Qt.Key_AsciiTilde] = "grave";

// General Key Map
var KEY_MAP = {};

// Letters (lowercase as Hyprland expects)
for (var code = 65; code <= 90; code++) { // 'A' .. 'Z'
    KEY_MAP[code] = String.fromCharCode(code).toLowerCase();
}

// Digits 0..9
for (var digit = 48; digit <= 57; digit++) { // '0' .. '9'
    KEY_MAP[digit] = String.fromCharCode(digit);
}

// Function keys F1..F24
KEY_MAP[Qt.Key_F1] = "F1";
KEY_MAP[Qt.Key_F2] = "F2";
KEY_MAP[Qt.Key_F3] = "F3";
KEY_MAP[Qt.Key_F4] = "F4";
KEY_MAP[Qt.Key_F5] = "F5";
KEY_MAP[Qt.Key_F6] = "F6";
KEY_MAP[Qt.Key_F7] = "F7";
KEY_MAP[Qt.Key_F8] = "F8";
KEY_MAP[Qt.Key_F9] = "F9";
KEY_MAP[Qt.Key_F10] = "F10";
KEY_MAP[Qt.Key_F11] = "F11";
KEY_MAP[Qt.Key_F12] = "F12";
KEY_MAP[Qt.Key_F13] = "F13";
KEY_MAP[Qt.Key_F14] = "F14";
KEY_MAP[Qt.Key_F15] = "F15";
KEY_MAP[Qt.Key_F16] = "F16";
KEY_MAP[Qt.Key_F17] = "F17";
KEY_MAP[Qt.Key_F18] = "F18";
KEY_MAP[Qt.Key_F19] = "F19";
KEY_MAP[Qt.Key_F20] = "F20";
KEY_MAP[Qt.Key_F21] = "F21";
KEY_MAP[Qt.Key_F22] = "F22";
KEY_MAP[Qt.Key_F23] = "F23";
KEY_MAP[Qt.Key_F24] = "F24";

// Navigation & Editing
KEY_MAP[Qt.Key_Return] = "Return";
KEY_MAP[Qt.Key_Enter] = "Return";
KEY_MAP[Qt.Key_Tab] = "Tab";
KEY_MAP[Qt.Key_Backtab] = "Tab";
KEY_MAP[Qt.Key_Space] = "space";
KEY_MAP[Qt.Key_Backspace] = "BackSpace";
KEY_MAP[Qt.Key_Delete] = "Delete";
KEY_MAP[Qt.Key_Insert] = "Insert";
KEY_MAP[Qt.Key_Escape] = "Escape";
KEY_MAP[Qt.Key_Home] = "Home";
KEY_MAP[Qt.Key_End] = "End";
KEY_MAP[Qt.Key_PageUp] = "Prior";
KEY_MAP[Qt.Key_PageDown] = "Next";
KEY_MAP[Qt.Key_Print] = "Print";
KEY_MAP[Qt.Key_Pause] = "Pause";
KEY_MAP[Qt.Key_ScrollLock] = "Scroll_Lock";

// Arrows
KEY_MAP[Qt.Key_Left] = "Left";
KEY_MAP[Qt.Key_Right] = "Right";
KEY_MAP[Qt.Key_Up] = "Up";
KEY_MAP[Qt.Key_Down] = "Down";

// Base Symbols
KEY_MAP[Qt.Key_Minus] = "minus";
KEY_MAP[Qt.Key_Equal] = "equal";
KEY_MAP[Qt.Key_BracketLeft] = "bracketleft";
KEY_MAP[Qt.Key_BracketRight] = "bracketright";
KEY_MAP[Qt.Key_Backslash] = "backslash";
KEY_MAP[Qt.Key_Semicolon] = "semicolon";
KEY_MAP[Qt.Key_Apostrophe] = "apostrophe";
KEY_MAP[Qt.Key_QuoteLeft] = "grave";
KEY_MAP[Qt.Key_Comma] = "comma";
KEY_MAP[Qt.Key_Period] = "period";
KEY_MAP[Qt.Key_Slash] = "slash";

// Keypad
KEY_MAP[Qt.Key_KP_0] = "KP_0";
KEY_MAP[Qt.Key_KP_1] = "KP_1";
KEY_MAP[Qt.Key_KP_2] = "KP_2";
KEY_MAP[Qt.Key_KP_3] = "KP_3";
KEY_MAP[Qt.Key_KP_4] = "KP_4";
KEY_MAP[Qt.Key_KP_5] = "KP_5";
KEY_MAP[Qt.Key_KP_6] = "KP_6";
KEY_MAP[Qt.Key_KP_7] = "KP_7";
KEY_MAP[Qt.Key_KP_8] = "KP_8";
KEY_MAP[Qt.Key_KP_9] = "KP_9";
KEY_MAP[Qt.Key_KP_Add] = "KP_Add";
KEY_MAP[Qt.Key_KP_Subtract] = "KP_Subtract";
KEY_MAP[Qt.Key_KP_Multiply] = "KP_Multiply";
KEY_MAP[Qt.Key_KP_Divide] = "KP_Divide";
KEY_MAP[Qt.Key_KP_Enter] = "KP_Enter";
KEY_MAP[Qt.Key_KP_Decimal] = "KP_Decimal";

// Media & Hardware Keys
KEY_MAP[Qt.Key_VolumeUp] = "XF86AudioRaiseVolume";
KEY_MAP[Qt.Key_VolumeDown] = "XF86AudioLowerVolume";
KEY_MAP[Qt.Key_VolumeMute] = "XF86AudioMute";
KEY_MAP[Qt.Key_MicMute] = "XF86AudioMicMute";
KEY_MAP[Qt.Key_MediaPlay] = "XF86AudioPlay";
KEY_MAP[Qt.Key_MediaPause] = "XF86AudioPause";
KEY_MAP[Qt.Key_MediaTogglePlayPause] = "XF86AudioPlay";
KEY_MAP[Qt.Key_MediaNext] = "XF86AudioNext";
KEY_MAP[Qt.Key_MediaPrevious] = "XF86AudioPrev";
KEY_MAP[Qt.Key_MediaStop] = "XF86AudioStop";
KEY_MAP[Qt.Key_MonBrightnessUp] = "XF86MonBrightnessUp";
KEY_MAP[Qt.Key_MonBrightnessDown] = "XF86MonBrightnessDown";
KEY_MAP[Qt.Key_Calculator] = "XF86Calculator";
KEY_MAP[Qt.Key_Mail] = "XF86Mail";
KEY_MAP[Qt.Key_HomePage] = "XF86HomePage";
KEY_MAP[Qt.Key_Search] = "XF86Search";
KEY_MAP[Qt.Key_Tools] = "XF86Tools";

function formatDisplay(modmask, key) {
    var parts = modmaskToParts(modmask);
    if (key) {
        parts.push(key);
    }
    return parts.join(" + ");
}

function translateKeyEvent(event) {
    var modmask = extractModmask(event.modifiers);
    var keyInt = event.key;
    var scanCode = event.nativeScanCode || 0;

    if (isModifierOnlyKey(keyInt)) {
        return {
            isModifierOnly: true,
            recognized: true,
            modmask: modmask,
            key: "",
            display: formatDisplay(modmask, ""),
            rawKey: keyInt,
            nativeScanCode: scanCode
        };
    }

    var keyName = null;

    // Check shifted symbol first if Shift was active
    if (SHIFT_MAP[keyInt] !== undefined) {
        keyName = SHIFT_MAP[keyInt];
    } else if (KEY_MAP[keyInt] !== undefined) {
        keyName = KEY_MAP[keyInt];
    } else if (scanCode > 0) {
        // Fallback to Hyprland keycode syntax: code:<nativeScanCode>
        keyName = "code:" + scanCode;
    }

    if (!keyName) {
        return {
            isModifierOnly: false,
            recognized: false,
            modmask: modmask,
            key: "",
            display: "",
            rawKey: keyInt,
            nativeScanCode: scanCode
        };
    }

    return {
        isModifierOnly: false,
        recognized: true,
        modmask: modmask,
        key: keyName,
        display: formatDisplay(modmask, keyName),
        rawKey: keyInt,
        nativeScanCode: scanCode
    };
}

function validateArgument(value, options) {
    options = options || {};
    var val = (value === undefined || value === null) ? "" : String(value);
    if (options.required && !val.trim()) {
        return { valid: false, error: "Argument is required" };
    }
    if (options.rejectNewlines !== false && /[\r\n]/.test(val)) {
        return { valid: false, error: "Newlines are not allowed in arguments" };
    }
    if (options.rejectQuotes && /["'`]/.test(val)) {
        return { valid: false, error: "Quotes are not allowed in this argument" };
    }
    return { valid: true, error: "" };
}
