import logging
from itertools import combinations

from abcvoting import properties
from gurobipy import GurobiError

from random_po_committee_vote import RandomPOCommitteeVote

import sys

if __name__ == '__main__':
    if len(sys.argv) != 5:
        print('Usage: python test_specific_committee.py <committee_size> <num_candidates> <np_seed> <approval_seed>')
        sys.exit(1)
    k = int(sys.argv[1])
    num_candidates = int(sys.argv[2])
    np_seed = int(sys.argv[3])
    approval_seed = int(sys.argv[4])

    test_vote = RandomPOCommitteeVote(k, num_candidates, np_seed, approval_seed)
    print(f'The profile generated is {test_vote.profile.str_compact()}')
    print(f'The Pareto optimal committee is {test_vote.committee}')

    extended = test_vote.check_extendable()
    replaced = test_vote.check_replaceable()

    if extended is not None:
        print(f'{extended} is an extended committee')
    else:
        print("The committee is not extendable")

    if replaced is not None:
        print(f'{replaced} is a committee with a replacement')
    else:
        comm_counter = 0
        for comb in combinations(range(test_vote.num_candidates), test_vote.k):
            try:
                if properties.check_pareto_optimality(test_vote.profile, comb):
                    comm_counter += 1
            except GurobiError as e:
                logging.error(e)
                break
            pass
        print(f'The committee has no replaceable candidate. There are {comm_counter} PO committees of size {k} in total.')
