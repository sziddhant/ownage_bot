#!/usr/bin/env python
import rospy
from std_msgs.msg import UInt32
import geometry_msgs.msg
from ownage_bot.msg import *
from ownage_bot.srv import *

class ObjectClassifier:
    """A class for classifying objects into ownership categories."""

    def __init__(self):
        self.object_db = dict()
        self.avatar_ids = (rospy.get_param("avatar_ids") if
                           rospy.has_param("avatar_ids") else [])
        self.landmark_ids = (rospy.get_param("landmark_ids") if
                             rospy.has_param("landmark_ids") else [])
        rospy.Service("classifyObjects", ClassifyObjects, self.handleClassify)

    def handleClassify(self, req):
        msg = rospy.wait_for_message("object_db", RichObjectArray)
        objects = msg.objects
        return ClassifyObjectsResponse(objects)

    def feedbackCallback(self, msg):
        """Callback upon receiving blacklisted object."""
        pass

if __name__ == '__main__':
    rospy.init_node('object_classifier')
    objectClassifier = ObjectClassifier()
    # Subscribe to feedback from ObjectCollector
    rospy.Subscriber("feedback", RichFeedback,
                     objectClassifier.feedbackCallback)
    rospy.spin()
