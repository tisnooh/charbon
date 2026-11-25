import os
import unittest
from unittest.mock import patch
from config import Settings

class ConfigTest(unittest.TestCase):
    def test_test_channel_only(self):
        with patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': 'dummy', 'OWNER_TELEGRAM_ID': '123',
                                     'TEST_CHANNEL_ID': '-1003912244927'}, clear=True):
            cfg = Settings.load()
            self.assertFalse(cfg.publishing_enabled)
            self.assertFalse(cfg.assistant_enabled)
        with patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': 'dummy', 'OWNER_TELEGRAM_ID': '123',
                                     'TEST_CHANNEL_ID': '-1009999999999'}, clear=True):
            with self.assertRaisesRegex(ValueError, 'only CHARBON TEST'):
                Settings.load()

if __name__=='__main__':
    unittest.main()
