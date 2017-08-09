import objects
import predicates
import actions
from ownage_bot.msg import *

class Rule:
    """Condition-action pairs that the robot should follow."""    
    
    # Constants defining rule types
    forbidden = "forbidden"
    allowed = "allowed"
    obligatory = "obligatory"
    
    def __init__(self, action=actions.Empty, conditions=[],
                 detype="forbidden"):
        # Action to be performed
        self.action = action
        # Set of predicates that have to be true for the rule to follow
        self.conditions = set(conditions)
        # Deontic operator type
        self.detype = detype

    def __eq__(self, other):
        """Rules are equal if their conditions, actions and types are."""
        if isinstance(other, self.__class__):
            return (self.action.name == other.action.name &&
                    self.conditions == other.conditions &&
                    self.detype == other.detype)
        return NotImplemented

    def __ne__(self, other):
        if isinstance(other, self.__class__):
            return not self == other
        return NotImplemented

    def __hash__(self):
        """Hash using action name, condition hash and detype."""
        return hash((self.action.name, tuple(self.conditions), self.detype))
        
    def evaluate(self, tgt, exclusions=set()):
        """Evaluates if target satisfies the predicates."""
        truth = 1.0
        # Iterate through all non-excluded predicates
        for p in self.conditions if p not in exclusions:
            truth *= p.apply(tgt)
        return truth

    @classmethod
    def evaluateAnd(cls, rule_set, tgt):
        """Evaluates probabilistic conjunction of rules."""

        truth = 1.0
        exclusions = set()
        for r in rule_set:
            # Check for complementary predicates
            if any([p.negate() in exclusions for p in r.conditions]):
                return 0.0
            truth *= r.evaluate(tgt, exclusions)
            # Return early if possible
            if truth == 0.0:
                break
            # Do not double-count identical predicates
            exclusions.add(r.conditions)
        return truth

    @classmethod
    def evaluateOr(cls, rule_set, tgt, exclusions=set()):
        """Evaluates probabilistic disjunction of rules."""

        # Calculate truth probability of the first rule
        rule_set = set(rule_set)
        cur = rule_set.pop()
        truth = cur.evaluate(tgt, exclusions)

        # Bottom out if no more rules
        if len(rule_set) == 0:
            return truth

        # Break up complement of first rule into disjoint parts
        # e.g. !(A*B*C) -> (!A|!B|!C) -> (!A + A*!B + A*B*!C)
        conditions = list(cur.conditions)
        p_parts = [] # e.g. [A, A*!B, A*B*!C]
        p_part_probs = [] # e.g. [P(!A), P(A*!B), P(A*B*!C)]
        p_conj_probs = [1.0] # e.g. [1.0, P(A), P(A*B), P(A*B*C)]
        p_remainders = [] # Remainder rule sets for each part
        for i, p in enumerate(conditions):
            p_prob = p.apply(tgt)
            p_parts = conditions[0:i-1] + [p.negate()]
            p_part_probs.append((1-p_prob) * p_conj_probs[-1])
            p_conj_probs.append(p_prob * p_conj_probs[-1])
            p_remainders.append(set(rule_set))

        # Remove rules with complementary predicates
        for r in rule_set:
            for i, part in enumerate(p_parts):
                if any(c.negate() in r.conditions for c in part):
                    p_remainders[i].remove(r)

        # Recursively calculate probability of the remainder
        for prob, part, remainder in zip(p_part_probs, p_remainders):
            # Exclude potentially identical predicates (idempotency)
            truth += prob * cls.evaluateOr(remainder, tgt,
                                           exclusions.union(part))
                    
        return truth

    @classMethod
    def intersect(cls, r1, r2, negate_check=True):
        """Returns logical intersection of two rules."""
        if r1.action.name != r2.action.name || r1.detype != r2.detype:
            raise TypeError("Actions and deontic types must match.")
        new = cls(r1.action, r1.conditions.union(r2.conditions), r1.detype)
        if negate_check:
            for c in new.conditions:
                if c.negate in new.conditions:
                    new.conditions = set()
                    return new
        return new
                
    def toStr(self):
        return " ".join([self.action.name, "on"] +
                        [p.name for p, sub in self.conditions] +
                        ["target","is",self.detype])

    def toMsg(self):
        """Convert to ROS message."""
        msg = RuleMsg()
        msg.action = self.action.name        
        msg.conditions = tuple(c.toMsg() for c in self.conditions)
        msg.detype = self.detype
        msg.truth = 1.0
        
    @classmethod
    def fromMsg(cls, msg):
        """Convert from ROS message."""
        action = actions.db[msg.action]
        conditions = [predicates.Predicate.fromMsg(c) for
                      c in msg.conditions]
        return cls(action, conditions, msg.detype)

    @staticmethod
    def argsToStrings(predicate, args):
        strings = []
        for i, a in enumerate(args):
            if a == None:
                s = ''
            elif predicate.argtypes[i] == objects.Object:
                s = a.id
            elif predicate.argtypes[i] == objects.Agent:
                s = a.id                
            elif predicate.argtypes[i] == objects.Area:
                s = str(a.points)
            strings.append(s)
        return strings

    @staticmethod
    def stringsToArgs(predicate, strings):
        args = []
        for i, s in enumerate(strings):
            if s == '':
                a = None
            elif predicate.argtypes[i] == objects.Object:
                a = objects.Object(_lookupObject(int(s)))
            elif predicate.argtypes[i] == objects.Agent:
                a = objects.Agent(int(s))
            elif predicate.argtypes[i] == objects.Area:
                a = objects.Area(eval(s))
            args.append(arg)
        return args
    
# List of pre-defined rules
DoNotTouchRed = Rule(actions.PickUp, [(predicates.Red, [None])])
DoNotTouchGreen = Rule(actions.PickUp, [(predicates.Green, [None])])
DoNotTouchBlue = Rule(actions.PickUp, [(predicates.Blue, [None])])
DoNotTouchOwned = Rule(actions.PickUp, [(predicates.IsOwned, [None])])

DoNotTrashRed = Rule(actions.Trash, [(predicates.Red, [None])])
DoNotTrashGreen = Rule(actions.Trash, [(predicates.Green, [None])])
DoNotTrashBlue = Rule(actions.Trash, [(predicates.Blue, [None])])
DoNotTrashOwned = Rule(actions.Trash, [(predicates.IsOwned, [None])])
