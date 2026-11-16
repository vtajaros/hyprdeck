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
}
