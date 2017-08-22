#!/usr/bin/env python
import rospy
from collections import namedtuple
from geometry_msgs.msg import Point
from ownage_bot import *
from ownage_bot.msg import *
from ownage_bot.srv import *

# Named tuple for performance metric info
PerfMetric = namedtuple('PerfMetric',
                        ['tp', 'tn', 'fp', 'fn',
                         'prec', 'rec', 'acc', 'm_est'])

class RuleManager:
    """Manages, updates and learns (ownership) rules."""
    
    def __init__(self):
        # Learning parameters
        self.add_perm_thresh = rospy.get_param("~add_perm_thresh", 0.5)
        self.sub_perm_thresh = rospy.get_param("~sub_perm_thresh", 0.5)
        self.add_rule_thresh = rospy.get_param("~add_rule_thresh", 0.1)
        self.sub_rule_thresh = rospy.get_param("~sub_rule_thresh", 0.1)
        self.max_cand_rules = rospy.get_param("~max_cand_rules", 3)
        self.m_param = rospy.get_param("~m_param", 3)
        
        # Database of actively-followed rules
        self.active_rule_db = dict()
        # Database of rules given by users
        self.given_rule_db = dict()
        # Database of object specific permissions
        self.perm_db = dict()

        # Initialize databases with empty dicts/sets
        for a in actions.db.iterkeys():
            self.active_rule_db[a] = set()
            self.given_rule_db[a] = dict()
            self.perm_db[a] = dict()

        # Subscribers
        self.perm_sub = rospy.Subscriber("perm_input", PredicateMsg,
                                         self.permInputCb)
        self.rule_sub = rospy.Subscriber("rule_input", RuleMsg,
                                         self.ruleInputCb)
        # Servers
        self.lkp_perm_srv = rospy.Service("lookup_perm", LookupPerm,
                                           self.lookupPermCb)
        self.lkp_rule_srv = rospy.Service("lookup_rules", LookupRules,
                                           self.lookupRulesCb)

    def lookupPermCb(self, req):
        """Returns action permission for requested action-target pair."""
        if req.action in self.perm_db:
            action = actions.db[req.action]
            tgt = (None if action.tgtype is type(None) else
                   action.tgtype.fromStr(req.target))
            if tgt in self.perm_db[action.name]:
                perm = self.perm_db[action.name][tgt]
                return LookupPermResponse(perm)
        # Reports non forbidden if not in database
        return LookupPermResponse(0.0)
        
    def lookupRulesCb(self, req):
        """Returns rule set for requested action."""
        if req.action in self.active_rule_db:
            rule_set = [r.toMsg() for r in self.active_rule_db[req.action]]
        else:
            rule_set = []
            rospy.logwarn("Action %s not recognized, no rules to lookup.",
                          req.action)
        return LookupRulesResponse(rule_set)
        
    def permInputCb(self, msg):
        """Updates database with new permission, then accomodates the rules."""
        # Ignore perms which are not about actions
        if msg.predicate not in actions.db:
            return

        action = actions.db[msg.predicate]

        # Handle actions without targets
        if len(msg.bindings) == 0 and action.tgtype is type(None):
            self.perm_db[action.name][None] = msg.truth
            return
        if len(msg.bindings) > 1:
            raise TypeError("Action perm should have at most one argument.")
        
        tgt = action.tgtype.fromStr(msg.bindings[0])

        # Overwrite old value if permission already exists
        self.perm_db[action.name][tgt] = msg.truth
        # Update rules to accomodate new permission
        self.accomPerm(action.name, tgt, msg.truth)

    def ruleInputCb(self, msg):
        """Updates given rule database, adjusts active rule database."""
        action = actions.db[msg.action]
        rule = Rule.fromMsg(msg)

        # Overwrites old value if given rule already exists
        self.given_rule_db[action.name][rule] = msg.truth
        # Accomdate the given rule
        self.accomRule(rule, msg.truth)
        
    def accomPerm(self, act_name, tgt, truth):
        """Tries to accommodate the new permission by modifying rule base."""
        rule_set = self.active_rule_db[act_name]
        prediction = Rule.evaluateOr(rule_set, tgt)       

        if truth >= 0.5 and prediction < 0.5:
            self.coverPerm(act_name, tgt, truth)
        elif truth < 0.5 and prediction >= 0.5:
            self.uncoverPerm(act_name, tgt, truth)

    def coverPerm(self, act_name, tgt, truth):
        """Covers positive perm via general-to-specific search for a rule."""
        rule_set = self.active_rule_db[act_name]
        perm_set = self.perm_db[act_name]
        neg_perms = {k: v for k, v in perm_set.items() if v < 0.5}

        # Search only for inactive rules (pointless to refine active rules) 
        inactive_f = lambda r : r not in rule_set
        # Candidate rules must cover the new permission
        cover_f = lambda r : r.evaluate(tgt) >= truth
        # Compute score as false positive value for each candidate rule
        score_f = lambda r : sum([max(r.evaluate(n_tgt) - n_val, 0) for
                                  n_tgt, n_val in neg_perms.items()])

        # Search for rule starting with empty rule
        init_rule = Rule(actions.db[act_name], conditions=[])
        score_thresh = self.add_perm_thresh
        new_rule, new_score, success = \
            self.ruleSearch(init_rule, score_thresh,
                            score_f, [inactive_f, cover_f])

        # Add new rule if one is found
        if success:
            self.mergeRule(rule_set, new_rule)
        else:
            rospy.logdebug(("Cannot cover perm with [%s]" + 
                            "w/o too many false positives."),
                           new_rule.toPrint())
            
    def uncoverPerm(self, act_name, tgt, truth):
        """Uncover negative permission by refining overly general rules."""
        rule_set = self.active_rule_db[act_name]
        perm_set = self.perm_db[act_name]

        # Find set of high-certainty covering rules
        cover_rules = [r for r in rule_set if r.evaluate(tgt) >= 0.5]

        # Candidate rules must cover negative perm
        cover_f = lambda r : r.evaluate(tgt) >= (1-truth)

        # Subtract minimal rule that covers new perm from each covering rule
        for init_rule in cover_rules:
            # Find set of covered positive perms
            pos_perms = {k: v for k, v in perm_set.items()
                         if v >= 0.5 and init_rule.evaluate(k) >= 0.5}

            # Compute score as true positive value for each candidate rule
            score_f = lambda r : sum([min(p_val, r.evaluate(p_tgt)) for
                                      p_tgt, p_val in pos_perms.items()])

            # Search for rule that minimizes positive perms covered
            score_thresh = self.sub_perm_thresh
            new_rule, new_score, success = \
                self.ruleSearch(init_rule, score_thresh,
                                score_f, [cover_f])

            # Subtract found rule from covering rule
            if success:
                remainder = Rule.difference(init_rule, new_rule)
                rule_set.remove(init_rule)
                for new in remainder:
                    self.mergeRule(rule_set, new)
            else:
                rospy.logdebug(("Cannot uncover perm from [%s]" +
                                " w/o too much false negatives."),
                                init_rule.toPrint())

    def accomRule(self, given_rule, truth):
        """Tries to accommodate the given rule by modifying rule base."""
        if truth >= 0.5:
            self.coverRule(given_rule, truth)
        else:
            self.uncoverRule(given_rule, truth)

    def coverRule(self, given_rule, truth, force=False):
        """Cover given positive rule if not already covered."""
        rule_set = self.active_rule_db[given_rule.action.name]
        perm_set = self.perm_db[given_rule.action.name]
        neg_perms = {k: v for k, v in perm_set.items() if v < 0.5}
        n_neg = len(neg_perms)
        
        # Do nothing if given rule is specialization of an active rule
        for r in rule_set:
            if r.conditions <= given_rule.conditions:
                return

        # Score candidate rules according to false positive value 
        score_f = lambda r : sum([max(r.evaluate(tgt) - val, 0) for
                                  tgt, val in neg_perms.items()])
            
        # Specialize rule so that false positives are minimized
        score_thresh = self.add_rule_thresh * n_neg
        new_rule, new_score, success = \
            self.ruleSearch(given_rule, score_thresh, score_f)

        # Add specialized rule if false positive fraction is low enough
        if force or success:
            self.mergeRule(rule_set, new_rule)
        else:
            rospy.logdebug("Cannot add [%s] w/o too much over-covering.",
                           new_rule.toPrint())
        
    def uncoverRule(self, given_rule, truth, force=False):
        """Uncover negative rule by refining existing rules."""
        rule_set = self.active_rule_db[given_rule.action.name]
        perm_set = self.perm_db[given_rule.action.name]
        pos_perms = {k: v for k, v in perm_set.items() if v >= 0.5} 
        n_pos = len(pos_perms)        
        
        # Score candidate rules according to true positive value 
        score_f = lambda r : sum([min(r.evaluate(tgt), val) for
                                  tgt, val in pos_perms.items()])

        # Specialize rule so that true positives are minimized
        score_thresh = self.sub_perm_thresh * n_pos
        new_rule, new_score, success = \
            self.ruleSearch(given_rule, score_thresh, score_f)

        # Terminate if rule to be removed covers too many positive perms
        if not force and not success:
            rospy.logdebug("Cannot subtract [%s] w/o too much uncovering.",
                           new_rule.toPrint())
            return
        
        # Logically subtract (refined) given rule from each active rule
        for r in list(rule_set):
            remainder = Rule.difference(r, new_rule)
            # Skip if intersection is empty
            if r in remainder:
                continue
            # Replace rule with remainder
            rule_set.remove(r)
            for new in remainder:
                self.mergeRule(rule_set, new)
            
    def ruleSearch(self, init_rule, score_thresh, score_f, filters=[]):
        """Performs general to specific search for minimal-scoring rule."""
        best_rule, best_score = init_rule, score_f(init_rule)
        cand_rules = [best_rule]
        success = (all([f(init_rule) for f in filters]) and
                   best_score <= score_thresh)
        while len(cand_rules) > 0:
            # Terminate if score beats threshold
            if success:
                break
            # Construct list of refinements from previous candidates
            new_rules = [self.refineRule(r) for r in cand_rules]
            new_rules = [r for l in new_rules for r in l]
            # Select rules which match filters
            for f in filters:
                new_rules = filter(f, new_rules)
            # Return if no more rules
            if len(new_rules) == 0:
                return best_rule
            # Compute and sort by scores
            scores = [score_f(r) for r in new_rules]
            sort_rules = sorted(zip(new_rules, scores), key=lambda p:p[1])
            # Select top few candidates for next round of refinement
            cand_rules = [r for r, s in sort_rules[0:self.max_cand_rules]]
            # Check if best candidate beats best rule
            if len(sort_rules) > 0 and sort_rules[0][1] < best_score:
                best_rule, best_score = sort_rules[0]
                success = best_score <= score_thresh
        return best_rule, best_score, success

    def refineRule(self, rule):
        """Return list of refinements by adding predicates to rule."""
        refinements = []
        conditions = set(predicates.db.values())

        # Exhaustively substitute all 2nd-place arguments
        for p in list(conditions):
            if p.n_args < 2:
                continue
            if p.n_args > 2:
                raise TypeError("Only up to 2-place predicates supported.")
            conditions.remove(p)
            subs = p.argtypes[1].universe()
            bound = set([p.bind([None, s]) for s in subs])
            conditions |= bound
                
        for p in conditions:
            # Check for idempotency / complementation
            if p in rule.conditions or p.negate() in rule.conditions:
                continue
            n1 = Rule(rule.action, rule.conditions, rule.detype)
            n2 = Rule(rule.action, rule.conditions, rule.detype)
            n1.conditions.add(p)
            n2.conditions.add(p.negate())
            refinements += [n1, n2]
        return refinements
            
    def mergeRule(self, rule_set, new):
        """Merge new rule into rule set."""
        # Merge with adjacent rules (e.g. (A & B) | (A & !B) -> A)
        for r in list(rule_set):
            sym_diff = new.conditions ^ r.conditions
            if len(sym_diff) == 2:
                c1, c2 = sym_diff.pop(), sym_diff.pop()
                if c1.name != c2.name:
                    continue
                elif c1 == c2.negate():
                    new.conditions.discard(c1)
                    new.conditions.discard(c2)
                    rule_set.remove(r)

        # Search for generalizations or specializations after merging
        for r in list(rule_set):
            # Do not add if generalization is already in rule set
            if new.conditions <= r.conditions:
                break
            # Remove specializations that exist in rule set
            if new.conditions >= r.conditions:
                rule_set.remove(r)
        else:
            # Add rule if no generalizations found
            rule_set.add(new)
            
    def evalRuleSet(self, rule_set, perm_set):
        """Evaluates rule set and returns a performance metric tuple."""
        n_perms = len(perm_set)
        n_true = sum(perm_set.values())
        n_false = n_perms - n_true
        tp, tn, fp, fn = 0.0, 0.0, 0.0, 0.0
        for tgt, truth in perm_set.items():
            predict = Rule.evaluateOr(rule_set, tgt)
            tpi, tni = min(truth, predict), min(1-truth, 1-predict)
            fpi, fni = max(0, (1-truth)-tni), max(0, truth-tpi)
            tp, tn = tp + tpi, tn + tni
            fp, fn = fp + fpi, fn + fni
        prec = tp / (tp + fp)
        rec = tp / (tp + fn)
        acc = (tp + tn) / n_perms
        m_est = (tp + self.m_param * n_true/n_false) / (tp + fp)
        return PerfMetric(tp, tn, fp, fn, prec, rec, acc, m_est)
            
if __name__ == '__main__':
    rospy.init_node('rule_manager')
    rule_manager = RuleManager()
    rospy.spin()
