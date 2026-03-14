import {BabylonObject} from "../../objects";


export class ClusterTool extends BabylonObject {




    buildObject() {
        return undefined;
    }

    highlight(state) {
        return undefined;
    }

    update(data) {
        // here we can update the clustertool
        const angle = data.arm_angle ? data.arm_angle : 0;

    }

    test_function(x) {
        console.log(x);
    }

    onMessage(message) {
        return undefined;
    }
}