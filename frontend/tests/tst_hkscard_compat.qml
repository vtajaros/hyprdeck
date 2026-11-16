import QtQuick
import QtTest
import "../theme"
import "../pages" as HksPages

Item {
    id: testRoot
    width: 760
    height: 560
    visible: true

    property int closeCount: 0

    HksPages.AllKeybindings {
        id: cardPage
        width: 760
        height: 516
        onRequestClose: testRoot.closeCount += 1
    }

    TestCase {
        name: "HksCardCompatTests"
        when: windowShown

        function test_card_instantiation_size_and_request_close() {
            compare(cardPage.width, 760);
            compare(cardPage.height, 516);
            compare(cardPage.layoutClass, "wide");
            var before = testRoot.closeCount;
            cardPage.requestClose();
            compare(testRoot.closeCount, before + 1);
        }
    }
}
