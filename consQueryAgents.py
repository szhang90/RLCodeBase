from lp import lpDual, computeValue
import setcover
import pprint
from util import powerset
import copy
import numpy
import itertools
import config
from UCT import MCTS
from itertools import combinations


class ConsQueryAgent():
  """
  Find queries in constraint-uncertain mdps.
  """
  def __init__(self, mdp, consStates, consProbs=None, constrainHuman=False):
    """
    can't think of a class it should inherit..

    mdp: a factored mdp
    consSets: [[states that \phi is changed] for \phi in unknown features]
    goalConsStates: states where the goals are not satisfied
    """
    self.mdp = mdp

    # indices of constraints
    self.consStates = consStates
    self.consIndices = range(len(consStates))
    
    self.consProbs = consProbs
    
    # derive different definition of MR
    self.constrainHuman = constrainHuman

    self.allCons = self.consIndices
  
  def initialSafePolicyExists(self):
    """
    Run the LP solver with all constraints and see if the LP problem is feasible.
    """
    return self.findConstrainedOptPi(self.allCons)['feasible']

  def findConstrainedOptPi(self, activeCons):
    mdp = self.mdp

    zeroConstraints = self.constructConstraints(activeCons, mdp)
                           
    if config.METHOD == 'lp':
      return lpDual(mdp, zeroConstraints=zeroConstraints)
    elif config.METHOD == 'mcts':
      return MCTS(**mdp)
    else:
      raise Exception('unknown method')
  
  def findAllIISs(self):
    """
    a brute force way to find all iiss and return their indicies
    can be O(2^|unknown features|)
    """
    allConsPowerset = powerset(self.allCons)
    feasible = {}
    iiss = []
    
    for cons in allConsPowerset:
      # if any subset is already infeasible, no need to check this set. it's definitely infeasible and not an iis
      if len(cons) > 0 and any(not feasible[subset] for subset in combinations(cons, len(cons) - 1)):
        feasible[cons] = False
        continue

      # find if the lp is feasible by posing cons
      sol = self.findConstrainedOptPi(cons)
      feasible[cons] = sol['feasible']
      
      # must be feasible without unknown feature constraint (only with flow conservation constraints)
      # otherwise implementation error in mdp
      if len(cons) == 0: assert sol['feasible']
      
      # if it is infeasible and all its subsets are feasible (only need to check the subsets with one less element)
      # then it's an iis
      if not feasible[cons] and all(feasible[subset] for subset in combinations(cons, len(cons) - 1)):
        iiss.append(cons)

    return iiss
  
  def findGreedyQueryForFeasibility(self, iiss, knownLockedCons, knownFreeCons):
    """
    return the next feature to query by greedily cover the most number of sets
    return None if no more features are needed or nothing left to query about
    
    iiss: the set of IISs
    knownLockedCons: priorly-known or queried and known to be locked/unchangeable
    knownFreeCons: priorly-known or queried and known to be free/changeable
    """
    # make sure the constraints that are already queried are not going to be queried again
    unknownCons = set(self.consIndices) - set(knownFreeCons) - set(knownLockedCons)

    # find the maximum frequency constraint weighted by the probability
    return setcover.findHighestFrequencyElement(unknownCons, knownFreeCons, iiss, weight=lambda _: self.consProbs[_])

  #FIXME what is this for?? just to check the computation time?
  def findRelevantFeaturesBruteForce(self):
    allConsPowerset = set(powerset(self.allCons))

    for subsetsToConsider in allConsPowerset:
      self.findConstrainedOptPi(subsetsToConsider)

  def findRelevantFeaturesAndDomPis(self):
    """
    Incrementally add dominating policies to a set
    DomPolicies algorithm in the IJCAI paper
    """
    beta = [] # rules to keep
    dominatingPolicies = {}

    allCons = set()
    allConsPowerset = set(powerset(allCons))
    subsetsConsidered = []

    # iterate until no more dominating policies are found
    while True:
      subsetsToConsider = allConsPowerset.difference(subsetsConsidered)

      if len(subsetsToConsider) == 0: break

      # find the subset with the smallest size
      activeCons = min(subsetsToConsider, key=lambda _: len(_))
      subsetsConsidered.append(activeCons)

      skipThisCons = False
      for enf, relax in beta:
        if enf.issubset(activeCons) and len(relax.intersection(activeCons)) == 0:
          # this subset can be ignored
          skipThisCons = True
          break
      if skipThisCons:
        continue

      sol = self.findConstrainedOptPi(activeCons)
      assert sol['feasible']
      
      x = sol['pi']
      printOccSA(x)
      print self.computeValue(x)

      dominatingPolicies[activeCons] = x

      # check violated constraints
      if x == {}:
        violatedCons = ()
      else:
        violatedCons = self.findViolatedConstraints(x)

      print 'x violates', violatedCons

      # beta records that we would not enforce activeCons and relax occupiedFeats in the future
      beta.append((set(activeCons), set(violatedCons)))

      allCons.update(violatedCons)

      allConsPowerset = set(powerset(allCons))
    
    domPis = []
    for pi in dominatingPolicies.values():
      if pi not in domPis: domPis.append(pi)
      
    print 'rel cons', allCons, 'num of domPis', len(domPis)
    return allCons, domPis

  def findMinimaxRegretConstraintQBruteForce(self, k, relFeats, domPis):
    mrs = {}

    if len(relFeats) < k:
      # we have a chance to ask about all of them!
      return tuple(relFeats)
    else:
      for q in itertools.combinations(relFeats, k):
        mr, advPi = self.findMRAdvPi(q, relFeats, domPis, k)
        mrs[q] = mr
        
        print q, mr

      if mrs == {}:
        mmq = () # no need to ask anything
      else:
        mmq = min(mrs.keys(), key=lambda _: mrs[_])
    
      return mmq

  def findMinimaxRegretConstraintQ(self, k, relFeats, domPis, scopeHeu=True, filterHeu=True):
    """
    Finding a minimax k-element constraint query.
    
    The pruning rule depends on two heuristics: sufficient features (scopeHeu) and query dominance (filterHeu).
    Set each to be true to enable the filtering aspect.
    (We only compared enabling both, which is MMRQ-k, with some baseliens. We didn't analyze the effect of enabling only one of them.)
    """
    if len(relFeats) < k:
      # we have a chance to ask about all of them!
      return tuple(relFeats)

    # candidate queries and their violated constraints
    candQVCs = {}
    mrs = {}

    # first query to consider
    q = self.findChainedAdvConstraintQ(k, relFeats, domPis)
    
    if len(q) < k: return q # mr = 0 in this case

    # all sufficient features
    allCons = set()
    allCons.update(q)

    if scopeHeu:
      allConsPowerset = set(itertools.combinations(allCons, k))
    else:
      allConsPowerset = set(itertools.combinations(relFeats, k))

    qChecked = []

    while True:
      qToConsider = allConsPowerset.difference(qChecked)

      if len(qToConsider) == 0: break

      # find the subset with the smallest size
      q = qToConsider.pop()
      qChecked.append(q)

      # check the pruning condition
      dominatedQ = False
      if filterHeu:
        for candQ in candQVCs.keys():
          if set(q).intersection(candQVCs[candQ]).issubset(candQ):
            dominatedQ = True
            break
        if dominatedQ:
          print q, 'is dominated'
          continue

      mr, advPi = self.findMRAdvPi(q, relFeats, domPis, k)
      
      print q, mr
      #printOccSA(advPi) # for debug

      candQVCs[q] = self.findViolatedConstraints(advPi)
      allCons.update(candQVCs[q])
      if scopeHeu:
        allConsPowerset = set(itertools.combinations(allCons, k))
      # allConsPowerset is consistent (all k-subsets) if not scope. no need to update. 

      mrs[q] = mr
      
    mmq = min(mrs.keys(), key=lambda _: mrs[_])
  
    return mmq

  def findChainedAdvConstraintQ(self, k, relFeats, domPis, informed=False):
    q = []
    while len(q) < k:
      sizeOfQ = len(q)
      
      if informed:
        mr, advPi = self.findMRAdvPi(q, relFeats, domPis, k - sizeOfQ, consHuman=True, tolerated=q)
      else:
        mr, advPi = self.findMRAdvPi(q, relFeats, domPis, k, consHuman=False)
        
      violatedCons = self.findViolatedConstraints(advPi)
      print 'vio cons', violatedCons

      # we want to be careful about this, add unseen features to q
      # not disturbing the order of features in q
      for con in violatedCons:
        if con not in q:
          q.append(con)
      
      if len(q) == sizeOfQ: break # no more constraints to add
    
    # may exceed k constraints. return the first k constraints only
    mmq = list(q)[:k]
    return mmq

  def findRelevantRandomConstraintQ(self, k, relFeats):
    if len(relFeats) == 0: # possibly k == 0, make a separate case here
      return []
    elif len(relFeats) > k:
      relFeats = list(relFeats)
      indices = range(len(relFeats))
      randIndices = numpy.random.choice(indices, k, replace=False)
      q = [relFeats[_] for _ in randIndices]
    else:
      # no more than k relevant features
      q = relFeats
    
    return q
 
  def findRandomConstraintQ(self, k):
    if len(self.consIndices) >= k:
      q = numpy.random.choice(self.consIndices, k, replace=False)
    else:
      # no more than k constraints, should not design exp in this way though
      q = self.consIndices
    
    return q
  
  def findRegret(self, q, violableCons):
    """
    A utility function that finds regret given the true violable constraints
    """
    consRobotCanViolate = set(q).intersection(violableCons)
    rInvarCons = set(self.allCons).difference(consRobotCanViolate)
    robotPi = self.findConstrainedOptPi(rInvarCons)['pi']
    
    hInvarCons = set(self.allCons).difference(violableCons)
    humanPi = self.findConstrainedOptPi(hInvarCons)['pi']
    
    hValue = self.computeValue(humanPi)
    rValue = self.computeValue(robotPi)
    
    regret = hValue - rValue
    assert regret >= -0.00001, 'human %f, robot %f' % (hValue, rValue)

    return regret

  def findRobotDomPis(self, q, relFeats, domPis):
    """
    Find the set of dominating policies adoptable by the robot.
    """
    invarFeats = set(relFeats).difference(q)
    pis = []

    for rPi in domPis:
      if self.piSatisfiesCons(rPi, invarFeats):
        pis.append(rPi)

    return pis

  def findMRAdvPi(self, q, relFeats, domPis, k, consHuman=None, tolerated=[]):
    """
    Find the adversarial policy given q and domPis
    
    consHuman can be set to override self.constrainHuman
    makesure that |humanViolated \ tolerated| <= k
    
    Now searching over all dominating policies, maybe take some time.. can use MILP instead?
    """
    if consHuman == None: consHuman = self.constrainHuman

    maxRegret = 0
    advPi = None

    for pi in domPis:
      humanViolated = self.findViolatedConstraints(pi)
      humanValue = self.computeValue(pi)

      if consHuman and len(set(humanViolated).difference(tolerated)) > k:
        # we do not consider the case where the human's optimal policy violates more than k constraints
        # unfair to compare.
        continue

      # intersection of q and constraints violated by pi
      consRobotCanViolate = set(q).intersection(humanViolated)
      
      # the robot's optimal policy given the constraints above
      invarFeats = set(relFeats).difference(consRobotCanViolate)
      
      robotValue = -numpy.inf
      robotPi = None
      for rPi in domPis:
        if self.piSatisfiesCons(rPi, invarFeats):
          rValue = self.computeValue(rPi)
          if rValue > robotValue:
            robotValue = rValue
            robotPi = rPi

      regret = humanValue - robotValue
      
      assert robotPi != None
      # ignore numerical issues
      assert regret >= -0.00001, 'human %f, robot %f' % (humanValue, robotValue)

      if regret > maxRegret or (regret == maxRegret and advPi == None):
        maxRegret = regret
        advPi = pi
  
    # even with constrainHuman, the non-constraint-violating policy is in \Gamma
    assert advPi != None
    return maxRegret, advPi

  def constructConstraints(self, cons, mdp):
    """
    The set of state, action pairs that should not be visited when cons are active constraints.
    """
    return [(s, a) for a in mdp.A for con in cons for s in self.consStates[con]]

  def computeValue(self, x):
    return computeValue(x, self.mdp.r, self.mdp.S, self.mdp.A)

  def piSatisfiesCons(self, x, cons):
    violatedCons = self.findViolatedConstraints(x)
    return set(cons).isdisjoint(set(violatedCons))

  def findViolatedConstraints(self, x):
    # set of changed features
    var = set()
    
    for idx in self.consIndices:
      # states violated by idx
      for s, a in x.keys():
        if any(x[s, a] > 0 for a in self.mdp.A) and s in self.consStates[idx]:
          var.add(idx)
    
    return set(var)
    
  def statesWithDifferentFeats(self, idx, mdp):
    return filter(lambda s: s[idx] != mdp.s0[idx], mdp.S)

  # FIXME remove or not? only used by depreciated methods
  """
  def statesTransitToDifferentFeatures(self, idx, value):
    ret = []
    for s in self.mdp['S']:
      if s[idx] == value:
        for a in self.mdp['A']:
          for sp in self.mdp['S']:
            if self.mdp['T'](s, a, sp) > 0 and sp[idx] != value:
              ret.append((s, a))
              break
    return ret
  """


def printOccSA(x):
  for sa, occ in x.items():
    if occ > 0: print sa, occ
