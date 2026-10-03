from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from analyze_qa_repeats import paired_statistics


class PairedStatisticsTests(unittest.TestCase):
    def test_equal_timing_has_unit_interval_and_no_faster_trials(self):
        pairs=[dict(trial=t,total_speedup=1.0,same_output_tokens=True) for t in range(5)]
        result=paired_statistics(pairs)
        self.assertEqual(result['geometric_mean_speedup'],1)
        self.assertEqual(result['bootstrap_trial_95_low'],1)
        self.assertEqual(result['bootstrap_trial_95_high'],1)
        self.assertEqual(result['candidate_faster_pairs'],0)

    def test_trial_cluster_not_each_repeated_question_is_resampled(self):
        pairs=[dict(trial=0,total_speedup=2.0,same_output_tokens=True)]*6
        pairs += [dict(trial=1,total_speedup=.5,same_output_tokens=False)]*6
        result=paired_statistics(pairs)
        self.assertEqual(result['trials'],2)
        self.assertEqual(result['pairs'],12)
        self.assertAlmostEqual(result['geometric_mean_speedup'],1)
        self.assertEqual(result['bootstrap_trial_95_low'],.5)
        self.assertEqual(result['bootstrap_trial_95_high'],2)
        self.assertEqual(result['identical_outputs'],6)
