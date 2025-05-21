import logging
from concurrent.futures import as_completed, wait
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import Manager

from abcvoting.preferences import Profile
from abcvoting import properties
from itertools import combinations, batched

from gurobipy import GurobiError
from prefsampling import approval
from numpy import random
from numpy import uint64 as npuint64

import math


class RandomPOCommitteeVote:
    def __init__(self, k, num_candidates, num_processes=1, np_seed=None, approval_seed=None,
                 approval_culture_generator=approval.impartial):
        self.k = k
        self.num_candidates = num_candidates
        self.num_processes = num_processes
        self.committee = None
        if np_seed is not None:
            self.np_seed = np_seed
        else:
            self.np_seed = random.randint(0, int(2 ** 32 - 1), dtype=npuint64)
        self._rng = random.default_rng(seed=self.np_seed)

        self.num_voters = self._rng.integers(1, 3 * self.num_candidates)

        if approval_seed is not None:
            self.approval_seed = approval_seed
        else:
            self.approval_seed = random.randint(0, int(2 ** 32 - 1), dtype=npuint64)

        self.approval_probability = self._rng.random()
        self._approval_list = approval_culture_generator(num_voters=self.num_voters, num_candidates=self.num_candidates,
                                                         p=self.approval_probability, seed=self.approval_seed)
        self.profile = Profile(num_cand=self.num_candidates)
        self.profile.add_voters(self._approval_list)

        self._create_po_committee()

    def _create_po_committee_single_threaded(self, combinations_to_check, flag):
        for comb in combinations_to_check:
            try:
                if flag.is_set():
                    return None
                if properties.check_pareto_optimality(self.profile, comb):
                    po_committee = comb
                    return po_committee
            except GurobiError as e:
                logging.error(e)
                return None
            pass
        pass

    def _create_po_committee_multi_threaded(self):
        logging.debug(f'Creating po committee with {self.num_processes} processes')
        po_committee = None
        all_combinations = list(combinations(range(self.num_candidates), self.k))
        self._rng.shuffle(all_combinations)
        grouped_combinations = batched(all_combinations,
                                       round(math.comb(self.num_candidates, self.k) / self.num_processes + .5))
        with ProcessPoolExecutor(max_workers=self.num_processes) as executor, Manager() as manager:
            flag = manager.Event()
            futures = {executor.submit(self._create_po_committee_single_threaded, combs, flag): combs for combs in
                       grouped_combinations}
            for future in as_completed(futures):
                po_committee = future.result()
                if po_committee is not None:
                    logging.debug(f'Found a po committee')
                    flag.set()
                    break
                pass
            executor.shutdown(wait=True, cancel_futures=True)
            pass
        return po_committee

    def _create_po_committee(self):
        if self.num_processes == 1:
            with Manager() as dummy:
                flag = dummy.Event()
                all_combinations = list(combinations(range(self.num_candidates), self.k))
                self._rng.shuffle(all_combinations)
                self.committee = self._create_po_committee_single_threaded(
                    all_combinations, flag)
        else:
            self.committee = self._create_po_committee_multi_threaded()

    def seeds(self):
        return [self.np_seed, self.approval_seed]

    @staticmethod
    def _check_extendable_single_threaded(profile, committee, first_candidate, past_last_candidate, flag):
        for c in range(first_candidate, past_last_candidate):
            if c in committee:
                continue
            extended_committee = committee + (c,)
            try:
                if flag.is_set():
                    return None
                if properties.check_pareto_optimality(profile, extended_committee):
                    return extended_committee
            except GurobiError as e:
                logging.error(e)
                return ()
            pass
        return None

    def _check_extendable_multi_threaded(self):
        logging.debug(f'Check extendability of po committee with {self.num_processes} processes')
        step_size = round(self.num_candidates / self.num_processes + .5)
        extended_committee = None
        ranges = [(i, max(i + step_size, self.num_candidates)) for i in range(0, self.num_candidates, step_size)]
        with ProcessPoolExecutor(max_workers=self.num_processes) as executor, Manager() as manager:
            flag = manager.Event()
            futures = {
                executor.submit(self._check_extendable_single_threaded, self.profile, self.committee,
                                *candidate_range, flag): candidate_range
                for
                candidate_range in ranges}
            for future in as_completed(futures):
                extended_committee = future.result()
                if extended_committee is not None:
                    flag.set()
                    logging.debug(f'Found an extended committee')
                    break
                pass

            remaining_futures = [f for f in futures if not f.done()]
            wait(remaining_futures)
            pass
        return extended_committee

    def check_extendable(self):
        if self.num_processes == 1:
            with Manager() as dummy:
                flag = dummy.Event()
                return self._check_extendable_single_threaded(self.profile, self.committee, 0,
                                                              self.num_candidates, flag)
        else:
            return self._check_extendable_multi_threaded()

    @staticmethod
    def _check_replaceable_single_threaded(profile, committee, num_candidates, candidates, flag):
        for cw in candidates:
            for c in range(num_candidates):
                if c in committee:
                    continue
                new_committee = tuple([d for d in committee if d != cw]) + (c,)
                try:
                    if flag.is_set():
                        return None
                    if properties.check_pareto_optimality(profile, new_committee):
                        return new_committee
                except GurobiError as e:
                    logging.error(e)
                    return ()
                pass
            pass
        return None

    def _check_replaceable_multi_threaded(self):
        logging.debug(f'Checking replaceablitiy of committee with {self.num_processes} processes')
        groups = [list(self.committee)[i::self.num_processes] for i in range(self.num_processes)]
        new_committee = None
        with ProcessPoolExecutor(max_workers=self.num_processes) as executor, Manager() as manager:
            flag = manager.Event()
            futures = {executor.submit(self._check_replaceable_single_threaded, self.profile, self.committee,
                                       self.num_candidates, tuple(group), flag): group for group in
                       groups}
            for future in as_completed(futures):
                new_committee = future.result()
                if new_committee is not None:
                    flag.set()
                    logging.debug(f'Found a replacement')
                    break
                pass

            remaining_futures = [f for f in futures if not f.done()]
            wait(remaining_futures)
            pass
        return new_committee

    def check_replaceable(self):
        if self.num_processes == 1:
            with Manager() as dummy:
                flag = dummy.Event()
                return self._check_replaceable_single_threaded(self.profile, self.committee, self.num_candidates,
                                                               self.committee, flag)
        else:
            return self._check_replaceable_multi_threaded()

    @staticmethod
    def _count_po_committees_single_threaded(profile, combinations_to_check):
        comm_counter = 0
        for comb in combinations_to_check:
            try:
                if properties.check_pareto_optimality(profile, comb):
                    comm_counter += 1
            except GurobiError as e:
                print(e.message)
                break
            pass
        return comm_counter

    def _count_po_committees_multi_threaded(self):
        logging.debug(f'Counting po committees with {self.num_processes} processes')
        comm_counter = 0
        all_combinations = combinations(range(self.num_candidates), self.k)
        grouped_combinations = batched(all_combinations,
                                       round(math.comb(self.num_candidates, self.k) / self.num_processes + .5))
        with ProcessPoolExecutor(max_workers=self.num_processes) as executor:
            futures = {executor.submit(self._count_po_committees_single_threaded, self.profile, combs): combs for combs
                       in
                       grouped_combinations}
            for future in as_completed(futures):
                comm_counter += future.result()
                pass
            pass
        return comm_counter

    def count_po_committees(self):
        if self.num_processes == 1:
            return self._count_po_committees_single_threaded(self.profile,
                                                             combinations(range(self.num_candidates), self.k))
        else:
            return self._count_po_committees_multi_threaded()


if __name__ == '__main__':
    test1 = RandomPOCommitteeVote(5, 25, 2)
    print("SUCCESS")
