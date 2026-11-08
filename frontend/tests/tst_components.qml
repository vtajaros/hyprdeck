import QtQuick
import QtTest
import "../theme"
import "../services"
import "../components"
import "../components/keymap.js" as KeyMap

Item {
    id: testRoot
    width: 800
    height: 600
    visible: true

    Component {
        id: editDialogComp
        KeybindEditDialog {}
    }

    Component {
        id: confirmDialogComp
        EditConfirmDialog {}
    }

    Component {
        id: recorderComp
        KeybindRecorder {}
    }

    TestCase {
        id: testCase
        name: "ComponentHeadlessTests"
        when: windowShown

        // 1. Pure-JS argument validation tests
        function test_argument_validation() {
            // Required arg
            var res1 = KeyMap.validateArgument("", { required: true });
            compare(res1.valid, false);
            compare(res1.error, "Argument is required");

            var res2 = KeyMap.validateArgument("   ", { required: true });
            compare(res2.valid, false);

            var res3 = KeyMap.validateArgument("valid-arg", { required: true });
            compare(res3.valid, true);

            // Newline rejection
            var resNl1 = KeyMap.validateArgument("foo\nbar");
            compare(resNl1.valid, false);
            compare(resNl1.error, "Newlines are not allowed in arguments");

            var resNl2 = KeyMap.validateArgument("foo\rbar");
            compare(resNl2.valid, false);

            // Quotes rejection
            var resQ1 = KeyMap.validateArgument('foo"bar', { rejectQuotes: true });
            compare(resQ1.valid, false);
            compare(resQ1.error, "Quotes are not allowed in this argument");

            var resQ2 = KeyMap.validateArgument("foo'bar", { rejectQuotes: true });
            compare(resQ2.valid, false);

            var resQ3 = KeyMap.validateArgument('foo`bar', { rejectQuotes: true });
            compare(resQ3.valid, false);

            var resQ4 = KeyMap.validateArgument("normal-arg", { rejectQuotes: true });
            compare(resQ4.valid, true);
        }

        // 2. Edit mode: review button enable/disable and flags visibility
        function test_edit_dialog_edit_mode() {
            EditService.dialogMode = "edit";
            var dialog = editDialogComp.createObject(testRoot, {
                visible: true,
                mode: "edit",
                bind: {
                    id: "bind_test_1",
                    modifiers: ["SUPER"],
                    key: "Q",
                    submap: "",
                    dispatcher: { path: "killactive", arg_summary: "" },
                    flags: { locked: false, repeating: false },
                    source_file: "hyprland.lua",
                    source_line: 10
                }
            });
            verify(dialog !== null);
            dialog.initFromBind(dialog.bind);

            // In edit mode without any change, canReview must be false
            compare(dialog.canReview, false, "canReview false when unchanged in edit mode");

            // Flags section must NOT be visible in edit mode
            var flagsSec = findChild(dialog, "flagsSection");
            verify(flagsSec !== null, "flagsSection found");
            compare(flagsSec.visible, false, "flagsSection hidden in edit mode");

            // Submap selector must NOT be visible in edit mode
            var submapSec = findChild(dialog, "submapSection");
            verify(submapSec !== null, "submapSection found");
            compare(submapSec.visible, false, "submapSection hidden in edit mode");

            // Change shortcut -> canReview becomes true
            dialog.newKey = "W";
            compare(dialog.hasShortcutChanged, true);
            compare(dialog.canReview, true, "canReview true after key changed");

            // Empty shortcut -> canReview becomes false
            dialog.newKey = "";
            compare(dialog.canReview, false, "canReview false when newKey empty");
            compare(dialog.validationHint, "Select or record a keyboard shortcut");

            // Restore shortcut and change dispatcher -> canReview becomes true
            dialog.newKey = "Q";
            dialog.preserveDispatcher = false;
            dialog.selectedDispatcherId = "exec_cmd";
            compare(dialog.hasDispatcherChanged, true);
            compare(dialog.canReview, true, "canReview true after dispatcher changed");

            // If recorder becomes active, canReview is blocked
            RecorderService.active = true;
            compare(dialog.canReview, false, "canReview false when recorder active");
            RecorderService.active = false;

            dialog.destroy();
        }

        // 3. Add mode: review button rules, validation hints, flags visible
        function test_edit_dialog_add_mode() {
            EditService.dialogMode = "add";
            var dialog = editDialogComp.createObject(testRoot, {
                visible: true,
                mode: "add"
            });
            verify(dialog !== null);
            compare(dialog.isAddMode, true);
            dialog.initAddMode();

            // Flags section must be visible in add mode
            var flagsSec = findChild(dialog, "flagsSection");
            verify(flagsSec !== null, "flagsSection found");
            compare(flagsSec.visible, true, "flagsSection visible in add mode");

            // Initially without key: canReview is false
            dialog.newKey = "";
            compare(dialog.canReview, false);
            compare(dialog.validationHint, "Select or record a keyboard shortcut");

            // Key given, but no dispatcher:
            dialog.newKey = "T";
            dialog.rawExpressionMode = false;
            dialog.selectedDispatcherId = "";
            compare(dialog.canReview, false);
            compare(dialog.validationHint, "Choose an action / dispatcher");

            // Dispatcher selected with required argument:
            dialog.selectedDispatcherId = "exec_cmd";
            dialog.selectedDispatcherLabel = "Launch Application / Command";
            dialog.selectedSchema = [{ name: "command", type: "string", required: true }];
            dialog.selectedArgValue = "";
            compare(dialog.canReview, false);
            compare(dialog.validationHint, "Enter required argument for Launch Application / Command");

            // Required argument filled -> canReview is true, validationHint is empty
            dialog.selectedArgValue = "kitty";
            compare(dialog.canReview, true);
            compare(dialog.validationHint, "");

            // Raw expression mode without text -> canReview false
            dialog.rawExpressionMode = true;
            dialog.rawExpressionText = "";
            compare(dialog.canReview, false);
            compare(dialog.validationHint, "Enter a raw expression");

            // Raw expression mode with text -> canReview true
            dialog.rawExpressionText = 'hl.dispatch("exec", "kitty")';
            compare(dialog.canReview, true);
            compare(dialog.validationHint, "");

            dialog.destroy();
        }

        // 4. Conflict banner visibility
        function test_conflict_banner_visibility() {
            EditService.dialogMode = "add";
            var dialog = editDialogComp.createObject(testRoot, {
                visible: true,
                mode: "add"
            });
            verify(dialog !== null);

            var banner = findChild(dialog, "conflictBanner");
            verify(banner !== null, "conflictBanner found");

            // Initially no conflict
            ConflictCheckService.hasConflicts = false;
            ConflictCheckService.disabledHeld = false;
            compare(banner.visible, false, "conflictBanner hidden when no conflicts");

            // Set hasConflicts = true
            ConflictCheckService.hasConflicts = true;
            compare(banner.visible, true, "conflictBanner visible when hasConflicts is true");

            // Reset
            ConflictCheckService.hasConflicts = false;
            ConflictCheckService.disabledHeld = true;
            compare(banner.visible, true, "conflictBanner visible when disabledHeld is true");

            ConflictCheckService.reset();
            compare(banner.visible, false);

            dialog.destroy();
        }

        // 5. KeybindRecorder: acceptance and leave() calls
        function test_recorder_flow_and_exit_paths() {
            var recorder = recorderComp.createObject(testRoot);
            verify(recorder !== null);

            var leaveCount = 0;
            RecorderService.leaveHandler = function(cb) {
                leaveCount++;
                if (cb) cb({ success: true, submap: "default" });
            };
            RecorderService.statusHandler = function(cb) {
                if (cb) cb({ submap: "default" });
            };

            // Test accepted signal on synthesized key event
            var acceptedReceived = false;
            var capturedMask = 0;
            var capturedK = "";
            var capturedDisp = "";

            recorder.accepted.connect(function(mask, k, disp) {
                acceptedReceived = true;
                capturedMask = mask;
                capturedK = k;
                capturedDisp = disp;
            });

            recorder.open();
            recorder.recorderState = "listening";

            // Synthesize Super+Return key sequence
            var event = {
                modifiers: Qt.MetaModifier,
                key: Qt.Key_Return,
                nativeScanCode: 36,
                accepted: false
            };
            recorder.handleKeyEvent(event);

            compare(recorder.recorderState, "captured");
            compare(recorder.capturedKey, "Return");
            compare(recorder.capturedModmask, 64);

            // Commit captured -> emits accepted and calls leaveAndClose
            var prevLeave = leaveCount;
            recorder.commitCaptured();
            verify(acceptedReceived, "accepted signal emitted");
            compare(capturedK, "Return");
            compare(capturedMask, 64);
            compare(leaveCount, prevLeave + 1, "leave() called on commitCaptured");

            // Exit path 2: cancel via leaveAndClose(true)
            prevLeave = leaveCount;
            var cancelledReceived = false;
            recorder.cancelled.connect(function() {
                cancelledReceived = true;
            });
            recorder.open();
            recorder.leaveAndClose(true);
            verify(cancelledReceived, "cancelled signal emitted");
            compare(leaveCount, prevLeave + 1, "leave() called on cancel");

            // Exit path 3: commitManual
            prevLeave = leaveCount;
            recorder.manualKeyText = "Escape";
            recorder.manualModmask = 0;
            recorder.commitManual();
            compare(leaveCount, prevLeave + 1, "leave() called on commitManual");

            recorder.destroy();
        }

        // 6. EditConfirmDialog instantiation
        function test_confirm_dialog_instantiation() {
            var confirm = confirmDialogComp.createObject(testRoot);
            verify(confirm !== null);
            confirm.destroy();
        }
    }
}
