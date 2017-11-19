import easyDomains
from consQueryAgents import ConsQueryAgent
import time
import random
import numpy
import scipy
import pickle
import getopt
import sys

OPEN = 1
CLOSED = 0

STEPPED = 1
CLEAN = 0

ON = 1
OFF = 0 

INPROCESS = 0
TERMINATED = 1

OPENDOOR = 'openDoor'
CLOSEDOOR = 'closeDoor'
TURNOFFSWITCH = 'turnOffSwitch'
EXIT = 'exit'

def classicOfficNav(method, k, numOfCarpets, constrainHuman, rnd, portionOfViolableCons=0, printRelPhi=False):
  """
  The office navigation domain specified in the report using a factored representation.
  There are state factors indicating whether some carpets are dirty.
     _________
  2 | |     |S|
  1 |  D_C_D  |
  0 |R___C____|
     0 1 2 3 4
     
  Also, consider randomize the room for experiments.

  FIXME hacking this function too much.
  """
  # specify the size of the domain, which are the robot's possible locations
  width = 10
  height = 10
  
  # do not occupy carpets.
  getBoundedRandLoc = lambda: (random.randint(1, width - 1), random.randint(0, height - 2))

  doors = []#[(width / 2, height / 2)]

  switch = (width - 1, height - 1)
  #switch = getRandLoc()

  carpets = [getBoundedRandLoc() for _ in range(numOfCarpets)]
  #carpets = [(width / 2, _) for _ in range(5)]
  
  lIndex = 0
  dIndexStart = lIndex + 1
  dSize = len(doors)
  sIndex = dIndexStart + dSize
  # note: time is needed when there are reversible features
  #tIndex = sIndex + 1
  
  dIndex = range(dIndexStart, dIndexStart + dSize)
  
  # pairs of adjacent locations that are blocked by a wall
  #walls = [[(0, 2), (1, 2)], [(1, 0), (1, 1)], [(2, 0), (2, 1)], [(3, 0), (3, 1)], [(3, 2), (4, 2)]]

  # splitting the room into two smaller rooms.
  # the robot can only access to the other room by going through a door in the middle or a corridor at the top
  #walls = [[(width / 2, _), (width / 2 + 1, _)] for _ in range(1, height - 1) if _ != height / 2]
  walls = []
  
  # location, box1, box2, door1, door2, carpet, switch
  allLocations = [(x, y) for x in range(width) for y in range(height)]
  sSets = [allLocations] +\
          [[CLOSED, OPEN] for _ in doors] +\
          [[0, 1]]
  
  directionalActs = [(1, 0), (0, 1), (1, 1)]
  aSets = directionalActs + [TURNOFFSWITCH]
 
  # check what the world is like
  for y in range(height):
    for x in range(width):
      if (x, y) in walls: print '[ X]',
      elif (x, y) in carpets: print '[%2d]' % carpets.index((x, y)),
      elif (x, y) == switch: print '[ S]',
      else: print '[  ]',
    print
  
  for _ in range(len(carpets)): print _, carpets[_]

  # factored transition function
  def navigate(s, a):
    loc = s[lIndex]
    if a in directionalActs:
      sp = (loc[0] + a[0], loc[1] + a[1])
      # not blocked by borders, closed doors or walls
      if (sp[0] >= 0 and sp[0] < width and sp[1] >= 0 and sp[1] < height) and\
         not any(s[idx] == CLOSED and sp == doors[idx - dIndexStart] for idx in dIndex) and\
         not any(loc in wall and sp in wall for wall in walls):
        return sp
    return loc
  
  def doorOpGen(idx, door):
    def doorOp(s, a):
      loc = s[lIndex]
      doorState = s[idx]
      if a in [OPENDOOR, CLOSEDOOR]:
        if loc in [(door[0] - 1, door[1]), (door[0], door[1])]:
          if a == CLOSEDOOR: doorState = CLOSED
          elif a == OPENDOOR: doorState = OPEN
          # otherwise the door state is unchanged
      return doorState
    return doorOp
  
  def switchOp(s, a):
    loc = s[lIndex]
    switchState = s[sIndex]
    if loc == switch and a == 'turnOffSwitch': switchState = OFF 
    return switchState
  
  tFunc = [navigate] +\
          [doorOpGen(dIndexStart + i, doors[i]) for i in range(dSize)] +\
          [switchOp]

  s0List = [(0, 0)] +\
           [CLOSED for _ in doors] +\
           [ON]
  s0 = tuple(s0List)
  
  terminal = lambda s: s[lIndex] == switch
  gamma = 1

  # if need to assign random rewards to all states
  #bonus = util.Counter()
  #for loc in allLocations: bonus[loc] = random.random() < .4

  def reward(s, a):
    if s[sIndex] == ON:
      return -1
    else:
      return 0
  rFunc = reward
  
  mdp = easyDomains.getFactoredMDP(sSets, aSets, rFunc, tFunc, s0, terminal, gamma)

  # states that should not be visited
  # let's not make carpets features but constraints directly
  consStates = [[s for s in mdp['S'] if s[lIndex] == _] for _ in carpets]
  agent = ConsQueryAgent(mdp, consStates, constrainHuman)

  if printRelPhi:
    relFeats, domPis = agent.findRelevantFeaturesAndDomPis()
    print len(relFeats)
    pickle.dump(len(relFeats), open('relPhi_' + str(numOfCarpets) + '_' + str(rnd) + '.pkl', 'wb'))
    sys.exit(0) # only need to know the number of relevant features

  # find dom pi (which may be used to find queries and will be used for evaluation)
  start = time.time()
  relFeats, domPis = agent.findRelevantFeaturesAndDomPis()
  end = time.time()
  domPiTime = end - start
  
  methods = ['brute', 'alg1', 'chain', 'relevantRandom', 'random', 'nq']
  #methods = ['alg1', 'chain', 'relevantRandom', 'random', 'nq']

  for method in methods:
    start = time.time()
    if method == 'brute':
      q = agent.findMinimaxRegretConstraintQBruteForce(k, relFeats, domPis)
    elif method == 'reallyBrute':
      # really brute still need domPis to find out MR...
      q = agent.findMinimaxRegretConstraintQBruteForce(k, agent.allCons, domPis)
    elif method == 'alg1':
      q = agent.findMinimaxRegretConstraintQ(k, relFeats, domPis)
    elif method == 'alg1NoFilter':
      q = agent.findMinimaxRegretConstraintQ(k, relFeats, domPis, filterHeu=False)
    elif method == 'alg1NoScope':
      q = agent.findMinimaxRegretConstraintQ(k, relFeats, domPis, scopeHeu=False)
    elif method == 'chain':
      q = agent.findChaindAdvConstraintQ(k, relFeats, domPis)
    elif method == 'relevantRandom':
      q = agent.findRelevantRandomConstraintQ(k, relFeats)
    elif method == 'random':
      q = agent.findRandomConstraintQ(k)
    elif method == 'nq':
      q = []
    elif method == 'domPiBruteForce':
      agent.findRelevantFeaturesBruteForce()
      q = []
    else:
      raise Exception('unknown method', method)
    end = time.time()

    runTime = end - start + (0 if method in ['random', 'nq'] else domPiTime)

    print method, q

    mr, advPi = agent.findMRAdvPi(q, relFeats, domPis, k, consHuman=False)
    mrk, advPi = agent.findMRAdvPi(q, relFeats, domPis, k, consHuman=True)

    regrets = {}
    # for print out regret (not maximum regret)
    for portionOfViolableCons in [0.1, 0.5, 0.9]:
      # some decoupling
      numpy.random.seed(int(10 * portionOfViolableCons) + rnd)
      violableIndices = numpy.random.choice(range(len(agent.allCons)), int(len(agent.allCons) * portionOfViolableCons), replace=False)
      print violableIndices
      violableCons = [agent.allCons[_] for _ in violableIndices]
    
      regrets[portionOfViolableCons] = agent.findRegret(q, violableCons)

    print mr, mrk, regrets, runTime
    
    saveToFile(method, k, numOfCarpets, constrainHuman, q, mr, mrk, runTime, regrets)

def saveToFile(method, k, numOfCarpets, constrainHuman, q, mr, mrk, runTime, regrets):
  ret = {}
  ret['mr'] = mr
  ret['mrk'] = mrk
  ret['regrets'] = regrets
  ret['time'] = runTime
  ret['q'] = q

  postfix = 'mrk' if constrainHuman else 'mr'

  # not distinguishing mr and mrk in filenames, so use a subdirectory
  pickle.dump(ret, open(method + '_' + postfix + '_' + str(k) + '_' + str(numOfCarpets) + '_' + str(rnd) + '.pkl', 'wb'))

if __name__ == '__main__':
  # default values
  method = 'alg1'
  k = 2
  numOfCarpets = 10
  constrainHuman = False
  ratioOfViolable = None
  printRelPhi = False

  try:
    opts, args = getopt.getopt(sys.argv[1:], 'k:n:cr:')
  except getopt.GetoptError:
    raise Exception('Unknown flag')
  for opt, arg in opts:
    if opt == '-k':
      k = int(arg)
    elif opt == '-n':
      numOfCarpets = int(arg)
    elif opt == '-c':
      constrainHuman = True
    elif opt == '-r':
      rnd = int(arg)

      random.seed(rnd)
      # not necessarily using the following packages, but just to be sure
      numpy.random.seed(rnd)
      scipy.random.seed(rnd)
      
      print 'random seed', rnd
    else:
      raise Exception('unknown argument')

  classicOfficNav(method, k, numOfCarpets, constrainHuman, rnd, ratioOfViolable, printRelPhi)
