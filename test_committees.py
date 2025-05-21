from itertools import combinations

from abcvoting import properties
from gurobipy import GurobiError

from random_po_committee_vote import RandomPOCommitteeVote
from numpy import random
import logging


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(levelname)s: %(message)s',
        handlers=[
            logging.FileHandler('po_committee.log'),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger(__name__)

    f_extend = open('extendable.csv', 'a')
    f_replace = open('replaceable.csv', 'a')

    f_no_extend = open('not_extendable.csv', 'a')
    f_no_replace = open('not_replaceable.csv', 'a')

    working = True

    test1 = RandomPOCommitteeVote(5, 10)
    test2 = RandomPOCommitteeVote(5, 10, test1.np_seed, test1.approval_seed)
    if test1.committee != test2.committee or test1.profile.str_compact() != test2.profile.str_compact():
        print(f'p: test1: {test1.approval_probability}, test2: {test2.approval_probability}\n'
              f'test1: {test1.committee}, test2: {test2.committee}\n'
              f'test1: {test1.profile.str_compact()}, test2: {test2.profile.str_compact()}')
        working = False

    try:
        while True:
            if not working:
                break
            k = random.randint(2, 9)
            num_candidates = random.randint(k + 1, 5 * k)
            logger.debug(f'Calculate size {k} committee for {num_candidates} candidates')
            po_comm_vote = RandomPOCommitteeVote(k, num_candidates)
            if po_comm_vote.committee is None:
                logger.debug(f'Too large to check for Pareto optimality')
                continue
            logger.debug(
                f'Committee: {po_comm_vote.committee}, np_seed: {po_comm_vote.np_seed}, approval_seed: {po_comm_vote.approval_seed}')

            logger.debug(f'Checking extendability...')
            extended_comm = po_comm_vote.check_extendable()
            f_extend.write(
                f'{k},{num_candidates},{po_comm_vote.np_seed},{po_comm_vote.approval_seed},{int(extended_comm is not None)},\n'
            )
            if extended_comm is None:
                logger.warning(f'Committee for {k}, {num_candidates} with seeds {po_comm_vote.np_seed}, '
                               f'{po_comm_vote.approval_seed} is not extendable!')
                f_no_extend.write(
                    f'{k},{num_candidates},{po_comm_vote.np_seed},{po_comm_vote.approval_seed},{int(extended_comm is not None)},\n'
                )
                f_no_extend.flush()

            logger.debug(f'Checking replaceability...')
            replaced_comm = po_comm_vote.check_replaceable()
            f_replace.write(
                f'{k},{num_candidates},{po_comm_vote.np_seed},{po_comm_vote.approval_seed},{int(replaced_comm is not None)},\n'
            )
            if replaced_comm is None:
                logger.warning(f'Committee for {k}, {num_candidates} with seeds {po_comm_vote.np_seed}, '
                               f'{po_comm_vote.approval_seed} has no replacement!')
                comm_counter = 0
                for comb in combinations(range(po_comm_vote.num_candidates), po_comm_vote.k):
                    try:
                        if properties.check_pareto_optimality(po_comm_vote.profile, comb):
                            comm_counter += 1
                    except GurobiError as e:
                        logging.error(e)
                        break
                    pass

                f_no_replace.write(
                    f'{k},{num_candidates},{po_comm_vote.np_seed},{po_comm_vote.approval_seed},{comm_counter},\n'
                )
                f_no_replace.flush()
                pass
            pass
        pass
    except KeyboardInterrupt:
        f_extend.close()
        f_replace.close()
        f_no_extend.close()
        f_no_replace.close()

        logger.info('User interrupted.')
        pass
