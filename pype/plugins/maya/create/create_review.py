from collections import OrderedDict
import avalon.maya
from pype.maya import lib


class CreateReview(avalon.maya.Creator):
    """Single baked camera"""

    name = "reviewDefault"
    label = "Review"
    family = "review"
    icon = "video-camera"

    def __init__(self, *args, **kwargs):
        super(CreateReview, self).__init__(*args, **kwargs)

        # get basic animation data : start / end / handles / steps
        data = OrderedDict(**self.data)
        animation_data = lib.collect_animation_data()
        for key, value in animation_data.items():
            data[key] = value

        self.data = data
