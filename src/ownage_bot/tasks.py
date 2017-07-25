import rospy
import objects
import actions
from Queue import Queue
from geometry_msgs.msg import Point

class Task:
    "Higher-level tasks that construct actions based on the world state."
    
    def __init__(self, name):
        # Human-readable name
        self.name = name
        # Whether task has been completed
        self.done = False
        # Default implementation of updateActions
        self._updateActions = lambda action_queue, object_db : 0;
        # Default implementation of checkActionUndone
        self._checkActionUndone = lambda action, obj : True

    def updateActions(self, action_queue, object_db):
        """Updates the queue of actions to perform based on the object list.
           
        action_queue -- a Queue of Action-target pairs
        object_db -- a dict of (id, Object) pairs

        Returns the number of actions added."""
        if not self.done:
            return self._updateActions(action_queue, object_db)
        return 0
        
    def updateOnce(self, action, tgt, action_queue):
        """Prototype action to be used for one-shot tasks."""
        if not self.done:
            action_queue.put((action, tgt))
            self.done = True
            return 1
        return 0

    def checkActionUndone(self, action, obj):
        """Double checks if action is still undone."""
        return self._checkActionUndone(action, obj)
    
    @staticmethod
    def oneShot(action, tgt=None):
        """Constructs one-shot task from action-target pair."""
        if not isinstance(tgt, action.tgtype)
        if tgt is None:
            name = action.name
        elif isinstance(tgt, objects.Object)
            name = action.name + "Obj" + obj.id
        elif isinstance(tgt, Point):
            name = (action.name + "Loc" +
                    " ".join(str(p) for p in [tgt.x, tgt.y, tgt.z])
        task = Task(name)
        task._updateActions = lambda action_queue, object_db : \
            task.updateOnce(action, obj, action_queue)
        return task
        
# Pre-defined high-level tasks
Idle = Task("idle")

CollectAll = Task("collectAll")
def _collectAll(action_queue, object_db):
    """Collects all objects not in the home area."""
    actions_added = 0
    home_corners = rospy.get_param("home_area/corners",
                                   [[0.39,0.07], [0.39,0.29],
                                    [0.62,0.29], [0.39,0.29]]]
    # Determine uncollected objects
    uncollected = [oid if not objects.inArea(obj, objects.Area(home_corners))
                   for oid, obj in object_db.iteritmes()]
    # Determine objects queued to be collected
    queued = [o.id if a.name == actions.Collect.name
              for a, o in list(action_queue.queue)]
    # Append actions for objects not already in queue
    for oid in uncollected:
        if oid not in queued:
            action_queue.put((actions.Collect, object_db[oid]))
            actions_added = actions_added + 1    
    return actions_added
CollectAll._updateActions = _collectAll

def _collectAllCheck(action, obj):
    """Check that object is not already in home area before collecting."""
    home_corners = rospy.get_param("home_area/corners",
                                   [[0.39,0.07], [0.39,0.29],
                                    [0.62,0.29], [0.39,0.29]]]
    # Assume undone if action is not Collect
    if action.name != actions.Collect.name:
        return True
    # Return true if object not in home area
    return not objects.inArea(obj, objects.Area(home_corners)):
CollectAll._checkActionUndone = _collectAllCheck

TrashAll = Task("trashAll")
def _trashAll(action_queue, object_db):
    """Trashes all objects not in the trash area."""
    actions_added = 0    
    trash_corners = rospy.get_param("trash_area/corners",
                                    [[-0.20,0.70], [-0.20,1.00],
                                     [0.10,1.00], [0.10,0.70]])
    # Determine untrashed objects
    untrashed = [oid if not objects.inArea(obj, objects.Area(trash_corners))
                 for oid, obj in object_db.iteritmes()]
    # Determine objects queued to be trashed
    queued = [o.id if a.name == actions.Trash.name
              for a, o in list(action_queue.queue)]
    # Append actions for objects not already in queue
    for oid in untrashed:
        if oid not in queued:
            action_queue.put((actions.Trash, object_db[oid]))
            actions_added = actions_added + 1
    return actions_added
TrashAll._updateActions = _trashAll

def _trashAllCheck(action, obj):
    """Check that object is not already in home area before trashing."""
    trash_corners = rospy.get_param("trash_area/corners",
                                    [[-0.20,0.70], [-0.20,1.00],
                                     [0.10,1.00], [0.10,0.70]])
    # Assume undone if action is not Trash
    if action.name != actions.Trash.name:
        return True
    # Return true if object not in home area
    return not objects.inArea(obj, objects.Area(trash_corners)):
TrashAll._checkActionUndone = _trashAllCheck
