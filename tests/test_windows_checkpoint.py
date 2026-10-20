import json
import struct
import tempfile
import unittest
from pathlib import Path


class WindowsCheckpointTests(unittest.TestCase):
    def test_expansion_is_exact_and_corrupt_cache_is_rebuilt(self):
        import numpy as np
        import torch
        from d2v2.windows_checkpoint import mapped_state
        original = np.array([0,1,-1,.123,65504],dtype='<f2')
        header = json.dumps({'weight':{'dtype':'F16','shape':[5],'data_offsets':[0,10]}}).encode()
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/'model.safetensors'
            source.write_bytes(struct.pack('<Q',len(header))+header+original.tobytes())
            expected = {'weight':torch.empty(5,device='meta')}
            values,mapping = mapped_state(source,expected)
            self.assertTrue(np.array_equal(values['weight'].numpy(), original.astype('<f4')))
            self.assertFalse(mapping.flags.writeable)
            del values
            mapping._mmap.close()
            cache = next(Path(tmp).glob('inference-fp32-*.bin'))
            cache.write_bytes(b'\0'*20)
            values,mapping = mapped_state(source,expected)
            self.assertTrue(np.array_equal(values['weight'].numpy(), original.astype('<f4')))
            del values
            mapping._mmap.close()

    def test_checkpoint_shape_is_not_silently_accepted(self):
        import torch
        from d2v2.windows_checkpoint import mapped_state
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'x'
            header=json.dumps({'w':{'dtype':'F16','shape':[2],'data_offsets':[0,4]}}).encode()
            path.write_bytes(struct.pack('<Q',len(header))+header+b'\0'*4)
            with self.assertRaises(ValueError):
                mapped_state(path,{'w':torch.empty(3,device='meta')})
