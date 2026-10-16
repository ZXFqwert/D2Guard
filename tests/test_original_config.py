import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from original_laya import OriginalLaya


class OriginalConfigurationTests(unittest.TestCase):
    def test_remote_only_cannot_load_incomplete_local_model_or_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            config=Path(folder)/'laya.json'
            config.write_text(json.dumps({'remote_only':True,'path':str(Path(folder)/'incomplete')}))
            with patch.dict(sys.modules,{'laya':None,'torch':None}):
                with self.assertRaisesRegex(RuntimeError,'no multilingual fallback'):
                    OriginalLaya(config)
