"""Independent toy histories for the report-only episode aggregation."""
import copy
import unittest

from report_metrics import episode_metrics


def row(hour, status, episodes):
    return dict(hour=hour,status=status,loop=dict(
        version="post-mission-verification-episodes/1",episodes=copy.deepcopy(episodes)))


class EpisodeCounting(unittest.TestCase):
    def test_repeated_snapshots_are_one_expired_window(self):
        episode=dict(receipt_ids=['work-1'],opened_at=4,available_boundary=4,due_hour=16,
                     original_deadline_missed=False)
        closed={**episode,'closed_at':16,'outcome':'verification deadline missed'}
        history=[row(4,'scheduled',[episode]),row(5,'unresolved',[episode]),
                 row(16,'escalation-required',[closed]),row(17,'escalation-required',[closed])]
        m=episode_metrics(history)
        self.assertEqual((m['windows_opened'],m['expired_windows'],m['escalation_intervals']),(1,1,2))

    def test_escalation_without_receipt_is_not_a_postmission_window(self):
        m=episode_metrics([row(16,'escalation-required',[])])
        self.assertEqual((m['windows_opened'],m['expired_windows'],m['escalation_intervals']),(0,0,1))

    def test_separate_mission_retains_old_failure(self):
        old=dict(receipt_ids=['work-1'],opened_at=4,available_boundary=4,due_hour=16,
                 closed_at=16,outcome='verification deadline missed',original_deadline_missed=False)
        new=dict(receipt_ids=['work-2'],opened_at=22,available_boundary=22,due_hour=34,
                 closed_at=25,outcome='observer confirmed',original_deadline_missed=True)
        m=episode_metrics([row(16,'escalation-required',[old]),row(25,'inactive',[old,new])])
        self.assertEqual((m['windows_opened'],m['expired_windows'],m['observer_confirmed_windows']),(2,1,1))
        self.assertEqual(m['original_deadline_already_missed_windows'],1)

    def test_missing_is_not_a_success(self):
        self.assertFalse(episode_metrics([])['applicable'])
        with self.assertRaises(ValueError):episode_metrics([dict(hour=0,status='inactive')])

    def test_boundaries_and_closed_outcomes_cannot_be_rewritten(self):
        e=dict(receipt_ids=['work-1'],opened_at=4,available_boundary=4,due_hour=16,
               closed_at=16,outcome='verification deadline missed')
        for changed in ({**e,'due_hour':28},{**e,'outcome':'observer confirmed'}):
            with self.assertRaises(ValueError):
                episode_metrics([row(16,'escalation-required',[e]),row(17,'inactive',[changed])])


if __name__=='__main__':unittest.main()
