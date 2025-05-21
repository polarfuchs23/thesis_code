"""
I have the hypothesis that in a PO committee with a non-maximal summed approval score (some selection of k candidates has a higher sum of approval scores) some candidate of the committee can be replaced by a candidate with a higher approval score not in the committee.

So: Let $C$ be a set of candidates and $V$ be a set of voters with an approval profile $\mathcal{A}$. For $C' \subseteq C$ we denote $S(C')$ as the sum of approval scores $\sum_{c\in C'} |V(c)|$. Let $W \subseteq C$ be a Pareto optimal committee of size $k$ for this vote. We set $S_m := \max\{S(C')|C' \subseteq C\}$ as the highest possible approval score of a size $k$ committee.

If $S(W) \neq S_m$, there exist some $c_r \in C \setminus W$ and $c_w \in W$ s.t. $W - c_w + c_r$ is Pareto optimal.

(This would lead to the reconfiguration graph being connected, because all committees with maximal approval score are Pareto optimal and can be transformed by replacement of one candidate trivially)

"""

import logging

from abcvoting import properties
from random_po_committee_vote import RandomPOCommitteeVote
from numpy import random
from tqdm import tqdm
from multiprocessing import Manager
from concurrent.futures import ProcessPoolExecutor, as_completed, wait
import os


def _check_hypothesis_on_instance_single_threaded(po_comm_vote, candidates, approval_scores, flag):
    found_replacement = False
    highest_approval = True
    for cw in candidates:
        for c in range(po_comm_vote.num_candidates):
            if c in po_comm_vote.committee:
                continue
            if approval_scores[c] <= approval_scores[cw]:
                continue
            highest_approval = False
            new_committee = tuple([d for d in po_comm_vote.committee if d != cw]) + (c,)
            if flag.is_set():
                return None
            if properties.check_pareto_optimality(po_comm_vote.profile, new_committee):
                found_replacement = True
                break
            pass
        pass
    return highest_approval, found_replacement


def _check_hypothesis_on_instance_multi_threaded(po_comm_vote, approval_scores):
    logging.debug(f'Checking hypothesis on {po_comm_vote.num_processes} processes')
    groups = [list(po_comm_vote.committee)[i::po_comm_vote.num_processes] for i in range(po_comm_vote.num_processes)]
    highest_approval = True
    found_replacement = False
    with ProcessPoolExecutor(max_workers=num_processes) as executor, Manager() as manager:
        flag = manager.Event()
        futures = {executor.submit(_check_hypothesis_on_instance_single_threaded, po_comm_vote, candidates,
                                   approval_scores, flag): candidates for candidates in groups}
        i = 0
        for future in as_completed(futures):
            highest_approval_part, found_replacement_part = future.result()

            if found_replacement_part:
                # hypothesis holds
                flag.set()
                found_replacement = True
                break

            # if every candidate has an approval score at least as high as all candidates not in the committee
            # all candidates have a higher score than non committee candidates --> AND over all these booleans
            highest_approval = highest_approval and highest_approval_part
            pass

        remaining_futures = [f for f in futures if not f.done()]
        wait(remaining_futures)
        pass

    # no replacement found, if the candidates have a highest approval score -> hypothesis holds, else -> wrong hypothesis
    return highest_approval or found_replacement


def check_hypothesis_on_instance(po_comm_vote):
    approval_scores = [0] * po_comm_vote.num_candidates
    for voter in po_comm_vote.profile:
        for candidate_str in voter.approved:
            approval_scores[int(candidate_str)] += 1
        pass
    if po_comm_vote.num_processes == 1:
        with Manager() as dummy:
            flag = dummy.Event()
            highest_approval, found_replacement = _check_hypothesis_on_instance_single_threaded(po_comm_vote,
                                                                                                po_comm_vote.committee,
                                                                                                approval_scores,
                                                                                                flag)
        return highest_approval or found_replacement
    else:
        return _check_hypothesis_on_instance_multi_threaded(po_comm_vote, approval_scores)


if __name__ == '__main__':
    num_comm_for_test = 500
    min_k = 3
    max_k = 7
    num_processes = os.cpu_count() - 4
    num_processes = 4
    print(f'Using {num_processes} processes')

    logging.basicConfig(filename="hypothesis_test.log", format='%(levelname)s:%(name)s - %(asctime)s : %(message)s',
                        datefmt='%H:%M:%S', level=logging.DEBUG)

    progress_bar = tqdm(range(num_comm_for_test))
    for _ in progress_bar:
        k = random.randint(min_k, max_k + 1)
        num_candidates = random.randint(k + 1, 5 * k)
        progress_bar.set_description_str(f'k:{k},n:{num_candidates}')
        random_vote = RandomPOCommitteeVote(k, num_candidates, num_processes=num_processes)

        if random_vote.committee is None:
            print(f'ERROR: Too large to check for Pareto optimality')
            continue

        if not check_hypothesis_on_instance(random_vote):
            if random_vote.count_po_committees() > 1:
                print(
                    f'There is no replacement of said kind in PO generated by {k} {num_candidates} {random_vote.np_seed} {random_vote.approval_seed}')
                break
            pass
        pass
    else:
        print(f'Did not find any violations')
        pass
