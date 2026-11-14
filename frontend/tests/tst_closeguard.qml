import QtQuick
import QtTest
import "../components"

Item {
    id: testRoot
    width: 400
    height: 300
    visible: true

    Component { id: guardComp; CloseGuard {} }
    Component { id: inputComp; TextInput {} }
    Component { id: rectComp; Rectangle {} }

    TestCase {
        name: "CloseGuardTests"
        when: windowShown

        function test_defaults_allow_close_and_escape() {
            var g = createTemporaryObject(guardComp, testRoot);
            compare(g.closeAllowed, true);
            compare(g.escapeAllowed, true);
        }

        function test_recorder_active_blocks_both() {
            var g = createTemporaryObject(guardComp, testRoot, { recorderActive: true });
            compare(g.closeAllowed, false);
            compare(g.escapeAllowed, false);
        }

        function test_edit_dialog_blocks_both() {
            var g = createTemporaryObject(guardComp, testRoot, { editDialogOpen: true });
            compare(g.closeAllowed, false);
            compare(g.escapeAllowed, false);
        }

        function test_confirm_dialog_blocks_both() {
            var g = createTemporaryObject(guardComp, testRoot, { dialogOpen: true });
            compare(g.closeAllowed, false);
            compare(g.escapeAllowed, false);
        }

        function test_text_input_focus_blocks_escape_only() {
            var g = createTemporaryObject(guardComp, testRoot);
            var ti = createTemporaryObject(inputComp, testRoot);
            g.focusItem = ti;
            compare(g.textInputFocused, true);
            compare(g.escapeAllowed, false, "Escape must not steal from text inputs");
            compare(g.closeAllowed, true, "close button is still allowed");
        }

        function test_non_text_focus_allows_escape() {
            var g = createTemporaryObject(guardComp, testRoot);
            var r = createTemporaryObject(rectComp, testRoot);
            g.focusItem = r;
            compare(g.textInputFocused, false);
            compare(g.escapeAllowed, true);
        }

        function test_null_focus_item_is_not_text_input() {
            var g = createTemporaryObject(guardComp, testRoot);
            compare(g.isTextInput(null), false);
            compare(g.isTextInput(undefined), false);
        }

        function test_state_changes_are_reactive() {
            var g = createTemporaryObject(guardComp, testRoot);
            g.recorderActive = true;
            compare(g.closeAllowed, false);
            g.recorderActive = false;
            compare(g.closeAllowed, true);
        }
    }
}
