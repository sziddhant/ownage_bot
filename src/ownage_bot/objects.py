import math
import copy
import rospy
import numpy as np
import matplotlib.path as mplPath
from ownage_bot.msg import *
from ownage_bot.srv import *
from geometry_msgs.msg import Point, Quaternion

class Object:
    """Represents objects in the workspace and their properties."""

    _lookupObject = rospy.ServiceProxy("lookup_object", LookupObject)
    _listObjects = rospy.ServiceProxy("list_objects", ListObjects)
    
    def __init__(self, id=-1, name="",
                 position=Point(), orientation=Quaternion(),
                 color="none", owners=[], categories=[], is_avatar=False):
        self.id = id
        self.name = name
        self.last_update = rospy.get_rostime()
        self.position = position
        self.orientation = orientation
        self.proximities = [] # List of distances to avatars
        self.color = color # Name of color
        self.ownership = dict() # Dictionary of ownership probabilities
        self.categories = dict() # Dictionary of category membership
        self.is_avatar = is_avatar # Whether object is an avatar
        for o in owners:
            self.ownership[o] = 1.0
        for c in categories:
            self.categories[c] = 1.0

    def __eq__(self, other):
        """Objects are equal if their ids are."""
        if isinstance(other, self.__class__):
            return self.id == other.id
        return NotImplemented
        
    def __ne__(self, other):
        if isinstance(other, self.__class__):
            return not self == other
        return NotImplemented

    def __hash__(self):
        """Hash only the ID."""
        return hash(self.id)
        
    def toMsg(self):
        """Converts Object to a ROS message."""
        msg = ObjectMsg()
        uncopyable = ["ownership"] 
        for k, v in self.__dict__.items():
            if k in uncopyable:
                continue
            setattr(msg, k, copy.deepcopy(v))
        msg.owners = self.ownership.keys()
        msg.ownership = self.ownership.values()
        return msg

    def toStr(self):
        """Minimal string representation of object."""
        return str(self.id)
    
    @classmethod
    def fromMsg(cls, msg):
        """Copy constructor from ObjectMsg."""
        obj = cls()
        if not isinstance(msg, ObjectMsg):
            raise TypeError("Copy constructor expects ObjectMsg.")
        copyable = ["id", "name", "last_update", "position", "orientation",
                    "proximities", "color", "is_avatar"]
        for attr in copyable:
            val = getattr(msg, attr)
            if type(val) is tuple:
                val = list(val)
            obj.__dict__[attr] = copy.deepcopy(val)
        obj.ownership = dict(zip(msg.owners, msg.ownership))
        obj.categories = dict(zip(msg.categories, msg.categoriness))
        return obj

    @classmethod
    def fromStr(cls, s):
        """Convert ID string to Object by looking up database."""
        return cls.fromID(int(s))

    @classmethod
    def fromID(cls, oid):
        """Convert ID to Object by looking up database."""
        return cls.fromMsg(cls._lookupObject(oid).object)

    @classmethod
    def universe(cls):
        """Returns the set of all known Objects."""
        rospy.wait_for_service("list_objects")
        return set([cls.fromMsg(m) for m in cls._listObjects().objects])
    
class Agent:
    """Represents an agent that can own and act on objects."""

    _lookupAgent = rospy.ServiceProxy("lookup_agent", LookupAgent)
    _listAgents = rospy.ServiceProxy("list_agents", ListAgents)
    
    def __init__(self, id=-1, name="", avatar_id=-1):
        self.id = id # Unique ID
        self.name = name # Human-readable name
        self.avatar_id = avatar_id # Object ID of avatar representing agent

    def __eq__(self, other):
        """Agents are equal if their ids are."""
        if isinstance(other, self.__class__):
            return self.id == other.id
        return NotImplemented
        
    def __ne__(self, other):
        if isinstance(other, self.__class__):
            return not self == other
        return NotImplemented

    def __hash__(self):
        """Hash only the ID."""
        return hash(self.id)

    def toStr(self):
        """Minimal string representation."""
        return str(self.id)

    def toMsg(self):
        """Converts Agent to a ROS message."""
        msg = AgentMsg()
        for k, v in self.__dict__.items():
            setattr(msg, k, copy.deepcopy(v))
        return msg
    
    @classmethod
    def fromStr(cls, s):
        """Convert to Agent from string."""
        rospy.wait_for_service("list_agents")
        return cls.fromMsg(cls._lookupAgent(int(s)).agent)

    @classmethod
    def fromMsg(cls, msg):
        """Copy constructor from AgentMsg."""
        agent = cls()
        if not isinstance(msg, AgentMsg):
            raise TypeError("Copy constructor expects AgentMsg.")
        copyable = ["id", "name", "avatar_id"]
        for attr in copyable:
            val = getattr(msg, attr)
            if type(val) is tuple:
                val = list(val)
            agent.__dict__[attr] = copy.deepcopy(val)
        return agent
    
    @classmethod
    def universe(cls):
        """Returns the set of all known Agents."""
        return set([cls.fromMsg(m) for m in cls._listAgents().agents])
    
class Area:
    """Defines a 2D polygonal area."""
    def __init__(self, points, name=""):
        """Takes an iterable of 2-tuples and stores them."""
        self.name = name
        self.n_sides = len(points)
        self.points = tuple([tuple(p[0:2]) for p in points])
        self.path = mplPath.Path(np.array(self.points))

    def __eq__(self, other):
        """Areas are equal if their vertices are."""
        if isinstance(other, self.__class__):
            return self.points == other.points
        return NotImplemented
        
    def __ne__(self, other):
        if isinstance(other, self.__class__):
            return not self == other
        return NotImplemented

    def __hash__(self):
        """Hash only the vertices."""
        return hash(self.points)

    def toStr(self):
        """Minimal string representation."""
        return str(self.points)

    @classmethod
    def fromStr(cls, s):
        """Convert to Area from string."""
        return cls(eval(s))

    @classmethod
    def universe(cls):
        """Returns the set of all known Areas (defined in param server)."""
        area_set = set()
        areas = rospy.get_param("areas", dict())
        for k, v in areas.iteritems():
            points = v["corners"]
            area_set.add(cls(points, name=k))
        return area_set
    
class Location:
    """Defines a location in space."""
    def __init__(self, point):
        """Takes a 3-tuple and stores it."""
        if len(point) != 3:
            raise ValueError("Position should be in 3 dimensions.")
        self.name = ""
        self.position = tuple(point)

    def __eq__(self, other):
        """Locations are equal if their vertices are."""
        if isinstance(other, self.__class__):
            return self.position == other.position
        return NotImplemented
        
    def __ne__(self, other):
        if isinstance(other, self.__class__):
            return not self == other
        return NotImplemented

    def __hash__(self):
        """Hash only the vertices."""
        return hash(self.position)

    def toStr(self):
        """Minimal string representation."""
        return str(self.position)

    @classmethod
    def fromStr(cls, s):
        """Convert to Location."""
        return cls(eval(s))

class Category:
    """Defines a category of objects."""
    def __init__(self, name):
        self.name = name # Human-readable name

    def __eq__(self, other):
        if type(other) == self.__class__:
            return self.name == other.name
        return NotImplemented
        
    def __ne__(self, other):
        if type(other) == self.__class__:
            return not self == other
        return NotImplemented

    def __hash__(self):
        return hash(self.name)

    def toStr(self):
        return self.name

    @classmethod
    def fromStr(cls, s):
        return cls(s)

    @classmethod
    def universe(cls):
        """Returns the set of all known Categories."""
        names = rospy.get_param("categories", [])
        return set([cls(n) for n in names])

class Color(Category):
    """Defines a color category."""
    def __init__(self, name, hsv_range=[[0,0,0],[0,0,0]]):
        self.name = name # Human-readable name
        self.hsv_range = (tuple(hsv_range[0]), tuple(hsv_range[1]))

    def __hash__(self):
        return hash((self.name, self.hsv_range))

    @classmethod
    def fromStr(cls, s):
        hsv_range = rospy.get_param("colors/" + s)
        return cls(s, hsv_range)

    @classmethod
    def universe(cls):
        """Returns the set of all known Colors."""
        colors = rospy.get_param("colors", dict())
        return set([cls(name, hsv_range) for
                    name, hsv_range in colors.items()])
    
def dist(obj1, obj2):
    """Calculates Euclidean distance between two objects."""
    p1 = obj1.position
    p2 = obj2.position
    diff = [p1.x-p2.x, p1.y-p2.y, p1.z-p2.z]
    return math.sqrt(sum([d*d for d in diff]))

def inArea(obj, area):
    """Checks if object is located in area."""
    return bool(area.path.contains_point((obj.position.x, obj.position.y)))
