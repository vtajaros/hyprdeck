import QtQuick
import QtTest
import "../components"
import "../shared_components"

TestCase {
    id: tc
    name: "tst_settings_controls"

    CloseGuard {
        id: guard
        recorderActive: false
        editDialogOpen: false
        dialogOpen: false
    }

    SettingControlLogic {
        id: boolLogic
        optionType: "bool"
        value: true
    }

    SettingControlLogic {
        id: enumLogic
        optionType: "enum"
    }

    SettingControlLogic {
        id: intLogic
        optionType: "int"
        value: 8
        minValue: 0
        maxValue: 50
        stepValue: 1
    }

    SettingControlLogic {
        id: floatLogic
        optionType: "float"
        value: 0.95
        minValue: 0.1
        maxValue: 1.0
        stepValue: 0.05
    }

    SettingControlLogic {
        id: colorLogic
        optionType: "color"
        value: "0xee0b0e10"
    }

    DisplayControlLogic {
        id: dispLogic
    }

    InputControlLogic {
        id: inputLogic
    }

    AudioControlLogic {
        id: audioLogic
    }

    BluetoothControlLogic {
        id: btLogic
    }

    NetworkControlLogic {
        id: netLogic
    }

    ThemesControlLogic {
        id: themesLogic
    }

    PowerControlLogic {
        id: pwrLogic
    }

    KeyboardControlLogic {
        id: kbLogic
    }

    function test_close_guard_blocks_when_prompt_open() {
        guard.dialogOpen = false;
        verify(guard.closeAllowed);
        guard.dialogOpen = true;
        verify(!guard.closeAllowed);
        guard.dialogOpen = false;
    }

    function test_int_clamping_and_step() {
        compare(intLogic.clampNumber(-5), 0);
        compare(intLogic.clampNumber(100), 50);
        compare(intLogic.clampNumber(12.4), 12);
    }

    function test_float_clamping() {
        compare(floatLogic.clampNumber(0.0), 0.1);
        compare(floatLogic.clampNumber(1.5), 1.0);
        verify(Math.abs(floatLogic.clampNumber(0.55) - 0.55) < 0.001);
    }

    function test_color_validation() {
        verify(colorLogic.isValidColor("0xee0b0e10"));
        verify(colorLogic.isValidColor("#0b0e10"));
        verify(!colorLogic.isValidColor("not-a-color"));
    }

    function test_display_clean_scale_and_warning() {
        verify(dispLogic.isCleanScale(1920, 1200, 1.0));
        verify(dispLogic.isCleanScale(1920, 1200, 1.25));
        verify(dispLogic.isCleanScale(1920, 1200, 1.5));
        verify(dispLogic.isCleanScale(1920, 1200, 2.0));
        verify(!dispLogic.isCleanScale(1920, 1200, 1.75));
        verify(!dispLogic.isCleanScale(1920, 1200, 1.33));
        compare(dispLogic.scaleWarningText(1920, 1200, 1.25), "");
        compare(dispLogic.scaleWarningText(1920, 1200, 1.75), "fractional: may blur");
    }

    function test_display_brightness_floor() {
        compare(dispLogic.clampBrightness(0), 5);
        compare(dispLogic.clampBrightness(4), 5);
        compare(dispLogic.clampBrightness(-10), 5);
        compare(dispLogic.clampBrightness(5), 5);
        compare(dispLogic.clampBrightness(68), 68);
        compare(dispLogic.clampBrightness(140), 100);
    }

    function test_display_last_output_guard() {
        var single = [{ name: "eDP-1", disabled: false }];
        verify(!dispLogic.canDisableOutput(single, {}, "eDP-1"));

        var dual = [{ name: "eDP-1", disabled: false }, { name: "HDMI-A-1", disabled: false }];
        verify(dispLogic.canDisableOutput(dual, {}, "HDMI-A-1"));
        verify(!dispLogic.canDisableOutput(dual, { "HDMI-A-1": { disabled: true } }, "eDP-1"));
    }

    function test_display_transform_labels() {
        compare(dispLogic.transformLabel(0), "Normal");
        compare(dispLogic.transformLabel(1), "90°");
        compare(dispLogic.transformLabel(3), "270°");
        compare(dispLogic.transformLabel(7), "Flipped 270°");
    }

    function test_input_layout_list_operations() {
        var r1 = inputLogic.addLayout(["us"], ["intl"], "de", "nodeadkeys");
        compare(r1.layouts.join(","), "us,de");
        compare(r1.variants.join(","), "intl,nodeadkeys");

        var r2 = inputLogic.moveLayout(r1.layouts, r1.variants, 1, -1);
        compare(r2.layouts.join(","), "de,us");
        compare(r2.variants.join(","), "nodeadkeys,intl");

        var r3 = inputLogic.removeLayout(r2.layouts, r2.variants, 0);
        compare(r3.layouts.join(","), "us");
        compare(r3.variants.join(","), "intl");

        // Cannot remove the last remaining layout
        var r4 = inputLogic.removeLayout(r3.layouts, r3.variants, 0);
        compare(r4.layouts.join(","), "us");
    }

    function test_input_risky_detection_and_modal_state() {
        var catalog = [
            { id: "input.repeat_rate", risky: false },
            { id: "input.kb_layout", risky: true },
            { id: "input.sensitivity", risky: true }
        ];
        verify(!inputLogic.hasRiskyChanges({ "input.repeat_rate": 35 }, {}, catalog));
        verify(inputLogic.hasRiskyChanges({ "input.kb_layout": "de" }, {}, catalog));
        verify(inputLogic.hasRiskyChanges({}, { "at-translated-set-2-keyboard": { enabled: false } }, catalog));
        verify(inputLogic.modalActive(true, false));
        verify(inputLogic.modalActive(false, true));
        verify(!inputLogic.modalActive(false, false));
    }

    function test_input_virtual_device_filtering_and_last_device_guard() {
        var devs = [
            { name: "at-translated-set-2-keyboard", category: "keyboard", virtual: false, enabled: true },
            { name: "fcitx5-virtual-kbd", category: "keyboard", virtual: true, enabled: true },
            { name: "elan-touchpad", category: "touchpad", virtual: false, enabled: true }
        ];
        compare(inputLogic.filterDevices(devs, false).length, 2);
        compare(inputLogic.filterDevices(devs, true).length, 3);
        verify(!inputLogic.canDisableDevice(devs, {}, "at-translated-set-2-keyboard"));
        verify(!inputLogic.canDisableDevice(devs, {}, "elan-touchpad"));
        verify(inputLogic.canDisableDevice(devs, {}, "fcitx5-virtual-kbd"));
    }

    function test_audio_volume_clamping_and_labels() {
        compare(audioLogic.clampVolume(-5, 100), 0);
        compare(audioLogic.clampVolume(120, 100), 100);
        compare(audioLogic.clampVolume(120, 150), 120);
        compare(audioLogic.clampVolume(200, 200), 150);
        compare(audioLogic.kindLabel("bluez"), "Bluetooth");
        compare(audioLogic.kindLabel("hdmi"), "HDMI");
        compare(audioLogic.kindLabel("alsa"), "ALSA");
        compare(audioLogic.kindLabel("other"), "Other");
        compare(audioLogic.muteLabel(true), "Muted");
        compare(audioLogic.muteLabel(false), "Mute");
        compare(audioLogic.balanceWarningText(0), "");
        compare(audioLogic.balanceWarningText(12), "L/R diff: 12%");
    }

    function test_bluetooth_filters_and_destructive_confirm() {
        var devs = [
            { address: "D4:50:8A:CA:53:FF", alias: "YSD Speaker", paired: true, connected: true, is_default_sink: true },
            { address: "11:22:33:44:55:66", alias: "Keychron K2", paired: true, connected: false, is_default_sink: false },
            { address: "AA:BB:CC:DD:EE:FF", alias: "Nearby Buds", paired: false, connected: false, is_default_sink: false, rssi: -58 }
        ];
        var safety = {
            disconnecting_default_audio: true,
            default_audio_name: "YSD Speaker",
            powering_off_disconnects: true,
            connected_names: ["YSD Speaker"]
        };
        compare(btLogic.pairedDevices(devs).length, 2);
        compare(btLogic.discoveredDevices(devs).length, 1);
        verify(btLogic.needsConfirm("power_off", null, safety));
        verify(btLogic.destructiveConsequence("power_off", null, safety).indexOf("YSD Speaker") >= 0);
        verify(btLogic.needsConfirm("disconnect", devs[0], safety));
        verify(!btLogic.needsConfirm("disconnect", devs[1], safety));
        verify(btLogic.needsConfirm("remove", devs[1], safety));
        compare(btLogic.rssiLabel(-58), "-58 dBm");
        compare(btLogic.rssiLabel(null), "");
    }

    function test_network_connectivity_and_destructive_confirm() {
        compare(netLogic.connectivityLabel("full"), "Online");
        compare(netLogic.connectivityLabel("none"), "Offline");
        var safetyCut = { wifi_off_would_cut_session: true };
        verify(netLogic.needsConfirm("wifi_off", null, safetyCut));
        verify(netLogic.destructiveConsequence("wifi_off", null, safetyCut).indexOf("only active connection") >= 0);

        var devCut = { name: "wlp0s20f3", would_cut_current_session: true };
        var devSafe = { name: "enp62s0", would_cut_current_session: false };
        verify(netLogic.needsConfirm("disconnect", devCut, {}));
        verify(!netLogic.needsConfirm("disconnect", devSafe, {}));

        var connCut = { name: "EWAKWI-FI_5G", would_cut_current_session: true };
        verify(netLogic.destructiveConsequence("forget", connCut, {}).indexOf("only active connection") >= 0);
        compare(netLogic.wifiStateBanner(false, true, {}), "NetworkManager is unavailable.");
        compare(netLogic.wifiStateBanner(true, false, {}), "No Wi-Fi device found.");
    }

    function test_themes_scope_labels_and_cursor_clamp() {
        compare(themesLogic.applyScopeLabel("live"), "Applies live");
        compare(themesLogic.applyScopeLabel("new_apps"), "Applies to new apps (restart apps to pick up)");
        compare(themesLogic.applyScopeLabel("next_login"), "Requires re-login (overridden by GTK_THEME env)");
        compare(themesLogic.iconBadgeText("Papirus-Dynamic"), "Follows wallpaper (recommended)");
        compare(themesLogic.iconBadgeText("Papirus-Dark"), "Resets on next wallpaper change");
        compare(themesLogic.clampCursorSize(8), 16);
        compare(themesLogic.clampCursorSize(100), 64);
        compare(themesLogic.clampCursorSize(32), 32);
        verify(themesLogic.hasConflict([{ id: "gtk_theme_env_override" }], "gtk_theme_env_override"));
        verify(!themesLogic.hasConflict([], "gtk_theme_env_override"));
    }

    function test_power_minutes_ordering_and_turbo_confirm() {
        compare(pwrLogic.secToMin(300), 5);
        compare(pwrLogic.secToMin(0), 1);
        compare(pwrLogic.secToMin(100000), 1440);
        compare(pwrLogic.minToSec(10), 600);
        compare(pwrLogic.minToSec(0.5), 30);
        compare(pwrLogic.minToSec(0), 30);
        compare(pwrLogic.minToSec(2000), 86400);
        compare(pwrLogic.validateIdleOrder(300, 600, 900), "");
        verify(pwrLogic.validateIdleOrder(600, 600, 900).length > 0);
        verify(pwrLogic.validateIdleOrder(300, 900, 900).length > 0);
        verify(pwrLogic.validateIdleOrder(10, 600, 900).length > 0);
        verify(pwrLogic.validateIdleOrder(300, 600, 90000).length > 0);
        compare(pwrLogic.roleLabel("dim"), "Dim screen");
        compare(pwrLogic.roleLabel("lock"), "Lock session");
        compare(pwrLogic.roleLabel("dpms"), "Turn off display");
        compare(pwrLogic.roleLabel("suspend"), "Suspend");
        compare(pwrLogic.roleLabel("other"), "Custom listener");
        compare(pwrLogic.eppLabel("balance_performance"), "Balanced");
        verify(pwrLogic.needsTurboConfirm(false));
        verify(!pwrLogic.needsTurboConfirm(true));
        var txt = pwrLogic.formatCopyAllText({ hostname: "arch-del", os_name: "Arch Linux" });
        verify(txt.indexOf("Hostname: arch-del") >= 0);
        verify(txt.indexOf("Machine ID") < 0);
    }

    function test_keyboard_status_and_button_labels() {
        compare(kbLogic.statusText(false, false, false), "Keybind Studio launcher script not found");
        compare(kbLogic.statusText(false, true, true), "Keybind Studio launcher script not found");
        compare(kbLogic.statusText(true, false, false), "Not currently running (launches on demand)");
        compare(kbLogic.statusText(true, true, false), "Background daemon running (window closed)");
        compare(kbLogic.statusText(true, true, true), "Keybind Studio is open");
        compare(kbLogic.statusText(true, false, null), "Not currently running (launches on demand)");

        compare(kbLogic.windowStateBadge(false, false), "Closed");
        compare(kbLogic.windowStateBadge(true, false), "Standby");
        compare(kbLogic.windowStateBadge(true, true), "Open");

        compare(kbLogic.buttonLabel(false, false), "Open Keybind Studio");
        compare(kbLogic.buttonLabel(false, null), "Open Keybind Studio");
        compare(kbLogic.buttonLabel(false, true), "Focus Keybind Studio");
        compare(kbLogic.buttonLabel(true, false), "Opening...");
        compare(kbLogic.buttonLabel(true, true), "Opening...");
    }

    function test_input_group_options_mouse_and_touchpad() {
        var sampleOpts = [
            { id: "input.kb_layout", group: "Keyboard", capable: true },
            { id: "input.repeat_rate", group: "Keyboard", capable: true },
            { id: "input.follow_mouse", group: "Mouse", capable: true },
            { id: "input.sensitivity", group: "Mouse", capable: true },
            { id: "input.touchpad.natural_scroll", group: "Touchpad", capable: true },
            { id: "input.touchpad.tap_to_click", group: "Touchpad", capable: false }
        ];
        var mouseOpts = inputLogic.groupOptions(sampleOpts, inputLogic.mouseGroupName(), []);
        compare(mouseOpts.length, 2);
        compare(mouseOpts[0].id, "input.follow_mouse");

        var tpOpts = inputLogic.groupOptions(sampleOpts, inputLogic.touchpadGroupName(), []);
        compare(tpOpts.length, 1);
        compare(tpOpts[0].id, "input.touchpad.natural_scroll");

        var kbOpts = inputLogic.groupOptions(sampleOpts, inputLogic.keyboardGroupName(), ["input.kb_layout"]);
        compare(kbOpts.length, 1);
        compare(kbOpts[0].id, "input.repeat_rate");
    }

    function test_network_rescan_on_show_logic() {
        // Trigger on show when empty or stale (> 30s)
        verify(netLogic.shouldAutoRescanOnShow(true, true, true, true, false, false, false, 0, 100000, 105000, 30000));
        verify(netLogic.shouldAutoRescanOnShow(true, true, true, true, false, false, false, 5, 0, 105000, 30000));
        verify(netLogic.shouldAutoRescanOnShow(true, true, true, true, false, false, false, 5, 100000, 131000, 30000));
        // Skip when recent (<= 30s) and non-empty
        verify(!netLogic.shouldAutoRescanOnShow(true, true, true, true, false, false, false, 5, 100000, 120000, 30000));
        // Skip when not visible, unavailable, no wifi, wifi off, busy, scanning, or loading
        verify(!netLogic.shouldAutoRescanOnShow(false, true, true, true, false, false, false, 0, 0, 100000, 30000));
        verify(!netLogic.shouldAutoRescanOnShow(true, false, true, true, false, false, false, 0, 0, 100000, 30000));
        verify(!netLogic.shouldAutoRescanOnShow(true, true, false, true, false, false, false, 0, 0, 100000, 30000));
        verify(!netLogic.shouldAutoRescanOnShow(true, true, true, false, false, false, false, 0, 0, 100000, 30000));
        verify(!netLogic.shouldAutoRescanOnShow(true, true, true, true, true, false, false, 0, 0, 100000, 30000));
        verify(!netLogic.shouldAutoRescanOnShow(true, true, true, true, false, true, false, 0, 0, 100000, 30000));
        verify(!netLogic.shouldAutoRescanOnShow(true, true, true, true, false, false, true, 0, 0, 100000, 30000));
    }

    function test_setting_control_enum_label_default() {
        compare(enumLogic.enumOptionLabel(""), "Default");
        compare(enumLogic.enumOptionLabel(null), "Default");
        compare(enumLogic.enumOptionLabel("flat"), "flat");
        compare(enumLogic.enumOptionLabel("adaptive"), "adaptive");
    }

    function test_input_xkb_search_and_common_filter() {
        var groups = [
            { group: "grp", description: "Switching to another layout", options: [
                { code: "grp:alt_shift_toggle", description: "Alt+Shift" },
                { code: "grp:win_space_toggle", description: "Win+Space" }
            ] },
            { group: "caps", description: "Caps Lock behavior", options: [
                { code: "caps:escape", description: "Make Caps Lock an additional Esc" }
            ] },
            { group: "keypad", description: "Numeric keypad", options: [
                { code: "keypad:pointerkeys", description: "Mouse keys" }
            ] }
        ];
        var common = inputLogic.commonXkbGroups(groups);
        compare(common.length, 2);
        compare(common[0].group, "grp");
        compare(common[1].group, "caps");

        var filtered = inputLogic.filterXkbOptionGroups(groups, "esc");
        compare(filtered.length, 1);
        compare(filtered[0].group, "caps");
        compare(filtered[0].options.length, 1);
        compare(filtered[0].options[0].code, "caps:escape");
    }

    function test_audio_partition_active_and_inactive() {
        var devs = [
            { name: "sink1", is_default: true, running_state: "SUSPENDED" },
            { name: "sink2", is_default: false, running_state: "RUNNING" },
            { name: "sink3", is_default: false, running_state: "SUSPENDED" },
            { name: "sink4", is_default: false, running_state: "IDLE" }
        ];
        var part = audioLogic.partitionDevices(devs);
        compare(part.active.length, 3);
        compare(part.active[0].name, "sink1");
        compare(part.active[1].name, "sink2");
        compare(part.active[2].name, "sink4");
        compare(part.inactive.length, 1);
        compare(part.inactive[0].name, "sink3");
    }

    function test_network_dedupe_saved_connections() {
        var devices = [
            { name: "wlp0s20f3", is_active: true, active_connection: "HomeWiFi" },
            { name: "enp62s0", is_active: false, active_connection: "" }
        ];
        var conns = [
            { uuid: "u1", name: "HomeWiFi", active: true },
            { uuid: "u2", name: "OfficeWiFi", active: false },
            { uuid: "u3", name: "Wired connection 1", active: false }
        ];
        var saved = netLogic.savedConnectionsExcludingActiveDevices(conns, devices);
        compare(saved.length, 2);
        compare(saved[0].uuid, "u2");
        compare(saved[1].uuid, "u3");
    }

    function test_themes_chip_truncation_with_current() {
        var items = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "CurTheme"];
        var collapsed = themesLogic.visibleThemeChips(items, "CurTheme", false, 8);
        compare(collapsed.length, 9);
        compare(collapsed[0], "CurTheme");
        compare(collapsed[1], "A");
        compare(collapsed[8], "H");

        var expanded = themesLogic.visibleThemeChips(items, "CurTheme", true, 8);
        compare(expanded.length, 11);
    }

    function test_responsive_layout_class_boundaries_and_hysteresis() {
        compare(ResponsiveLogic.computeLayoutClass(350, ""), "compact");
        compare(ResponsiveLogic.computeLayoutClass(439, ""), "compact");
        compare(ResponsiveLogic.computeLayoutClass(440, ""), "medium");
        compare(ResponsiveLogic.computeLayoutClass(679, ""), "medium");
        compare(ResponsiveLogic.computeLayoutClass(680, ""), "wide");
        compare(ResponsiveLogic.computeLayoutClass(999, ""), "wide");
        compare(ResponsiveLogic.computeLayoutClass(1000, ""), "expanded");

        // +/- 24px hysteresis around 440, 680, 1000
        compare(ResponsiveLogic.computeLayoutClass(455, "compact"), "compact");
        compare(ResponsiveLogic.computeLayoutClass(464, "compact"), "medium");
        compare(ResponsiveLogic.computeLayoutClass(425, "medium"), "medium");
        compare(ResponsiveLogic.computeLayoutClass(415, "medium"), "compact");

        compare(ResponsiveLogic.computeLayoutClass(695, "medium"), "medium");
        compare(ResponsiveLogic.computeLayoutClass(704, "medium"), "wide");
        compare(ResponsiveLogic.computeLayoutClass(660, "wide"), "wide");
        compare(ResponsiveLogic.computeLayoutClass(655, "wide"), "medium");

        compare(ResponsiveLogic.computeLayoutClass(1015, "wide"), "wide");
        compare(ResponsiveLogic.computeLayoutClass(1024, "wide"), "expanded");
        compare(ResponsiveLogic.computeLayoutClass(980, "expanded"), "expanded");
        compare(ResponsiveLogic.computeLayoutClass(975, "expanded"), "wide");
    }

    function test_responsive_sidebar_modes_and_short_viewport() {
        compare(ResponsiveLogic.sidebarModeForWindowWidth(1880), "full");
        compare(ResponsiveLogic.sidebarModeForWindowWidth(1100), "full");
        compare(ResponsiveLogic.sidebarModeForWindowWidth(1099), "narrow");
        compare(ResponsiveLogic.sidebarModeForWindowWidth(930), "narrow");
        compare(ResponsiveLogic.sidebarModeForWindowWidth(760), "narrow");
        compare(ResponsiveLogic.sidebarModeForWindowWidth(759), "rail");
        compare(ResponsiveLogic.sidebarModeForWindowWidth(455), "rail");

        compare(ResponsiveLogic.sidebarWidthForMode("full"), 230);
        compare(ResponsiveLogic.sidebarWidthForMode("narrow"), 196);
        compare(ResponsiveLogic.sidebarWidthForMode("rail"), 64);

        compare(ResponsiveLogic.isLayoutShort(560), true);
        compare(ResponsiveLogic.isLayoutShort(639), true);
        compare(ResponsiveLogic.isLayoutShort(640), false);
        compare(ResponsiveLogic.isLayoutShort(738), false);
    }

    function test_responsive_header_and_setting_row_wrap_decisions() {
        // Header actions wrap when min(title, 180) + spacing + actions exceeds availableWidth
        compare(ResponsiveLogic.shouldWrapHeaderActions(700, 120, 220, 12), false);
        compare(ResponsiveLogic.shouldWrapHeaderActions(400, 120, 220, 12), true);
        compare(ResponsiveLogic.shouldWrapHeaderActions(500, 120, 0, 12), false);

        // SettingRow stacking
        compare(ResponsiveLogic.shouldStackSettingRow(680, 220, 352, 12), false);
        compare(ResponsiveLogic.shouldStackSettingRow(500, 220, 352, 12), true);

        // DeviceCard actions wrap
        compare(ResponsiveLogic.shouldWrapDeviceActions(680, 240, 210, 12), false);
        compare(ResponsiveLogic.shouldWrapDeviceActions(420, 240, 210, 12), true);
    }
}
