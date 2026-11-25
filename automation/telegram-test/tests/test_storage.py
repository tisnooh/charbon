import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from storage import Store

PARIS = ZoneInfo('Europe/Paris')


def when(hour, minute=0, day=25):
    return datetime(2026,11,day,hour,minute,tzinfo=PARIS)


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Store(str(Path(self.tmp.name)/'test.sqlite3'))

    def tearDown(self):
        self.tmp.cleanup()

    def test_single_post_and_single_send_claim(self):
        p, new = self.db.create_post('2026-11-25', 'Premier conseil')
        self.assertTrue(new)
        again, new_again = self.db.create_post('2026-11-25', 'Autre conseil')
        self.assertFalse(new_again)
        self.assertEqual(again['body'], 'Premier conseil')
        self.assertTrue(self.db.decide(p['id'], 'approve', when(9,20)))
        self.assertFalse(self.db.decide(p['id'], 'approve', when(9,21)))
        claimed = self.db.claim_publication('2026-11-25')
        self.assertEqual(claimed['id'], p['id'])
        self.assertIsNone(self.db.claim_publication('2026-11-25'))
        self.db.finish_publication(p['id'], 123)
        self.assertEqual(self.db.get_post(p['id'])['status'], 'published')

    def test_late_and_stale_approval_rejected(self):
        p,_ = self.db.create_post('2026-11-25', 'Une mission')
        self.assertFalse(self.db.decide(p['id'], 'approve', when(10,0)))
        self.assertFalse(self.db.decide(p['id'], 'approve', when(9,0,26)))
        self.assertEqual(self.db.get_post(p['id'])['status'], 'pending')
        self.db.expire_unapproved('2026-11-25')
        self.assertFalse(self.db.decide(p['id'], 'approve', when(9,1)))

    def test_edit_requires_fresh_validation(self):
        p,_ = self.db.create_post('2026-11-25', 'Message initial')
        self.assertTrue(self.db.decide(p['id'], 'edit', when(9,10)))
        self.assertIsNone(self.db.claim_publication('2026-11-25'))
        self.assertTrue(self.db.replace_edit(p['id'], '2026-11-25', 'Contenu modifié à valider', when(9,20)))
        self.assertEqual(self.db.get_post(p['id'])['status'], 'pending')
        self.assertTrue(self.db.decide(p['id'], 'approve', when(9,21)))
        self.assertEqual(self.db.get_post(p['id'])['body'], 'Contenu modifié à valider')

    def test_rejection_never_publishes(self):
        p,_ = self.db.create_post('2026-11-25', 'Conseil')
        self.assertTrue(self.db.decide(p['id'], 'reject', when(9,5)))
        self.assertIsNone(self.db.claim_publication('2026-11-25'))

    def test_quota(self):
        self.assertTrue(self.db.check_quota(123, '2026-11-25', 1000, daily_limit=2))
        self.assertFalse(self.db.check_quota(123, '2026-11-25', 1001, daily_limit=2))
        self.assertTrue(self.db.check_quota(123, '2026-11-25', 1021, daily_limit=2))
        self.assertFalse(self.db.check_quota(123, '2026-11-25', 1042, daily_limit=2))
        self.assertTrue(self.db.check_quota(123, '2026-11-26', 1050, daily_limit=2))


if __name__=='__main__':
    unittest.main()
