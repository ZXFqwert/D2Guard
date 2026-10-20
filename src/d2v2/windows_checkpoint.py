"""Read-only, file-backed FP32 weights for memory-constrained Windows inference.

Stored FP16 values are expanded exactly to FP32, matching Laya's ordinary loader.
The derived file is checked against freshly converted source bytes at every load.
"""
import hashlib
import json
import os
import struct
import uuid
from pathlib import Path


def mapped_state(source, expected):
    import numpy as np
    import torch
    source = Path(source)
    with source.open('rb') as stream:
        length = struct.unpack('<Q', stream.read(8))[0]
        if not 0 < length < 16_000_000:
            raise ValueError('Invalid checkpoint header')
        header = json.loads(stream.read(length))
    header.pop('__metadata__', None)
    if set(header) != set(expected):
        raise ValueError('Checkpoint state keys differ from the model')
    layout, position = {}, 0
    for name, item in header.items():
        if item['dtype'] not in ('F16','F32') or tuple(item['shape']) != tuple(expected[name].shape):
            raise ValueError('Unsupported checkpoint tensor: '+name)
        a, b = item['data_offsets']
        size = expected[name].numel()
        unit = 2 if item['dtype']=='F16' else 4
        if not 0 <= a <= b <= source.stat().st_size-8-length or b-a != size*unit:
            raise ValueError('Invalid checkpoint tensor offsets')
        layout[name] = {'offset':position, 'shape':item['shape'], 'size':size}
        position += size*4

    def converted():
        with source.open('rb') as stream:
            for item in header.values():
                a,b = item['data_offsets']
                stream.seek(8+length+a)
                dtype = '<f2' if item['dtype']=='F16' else '<f4'
                for offset in range(a,b,1024*1024):
                    data = stream.read(min(1024*1024,b-offset))
                    if len(data) != min(1024*1024,b-offset):
                        raise ValueError('Truncated checkpoint')
                    yield np.frombuffer(data,dtype=dtype).astype('<f4').tobytes()

    wanted = hashlib.sha256()
    for chunk in converted():
        wanted.update(chunk)
    cache = source.with_name('inference-fp32-'+wanted.hexdigest()[:20]+'.bin')
    valid = False
    if cache.is_file() and cache.stat().st_size==position:
        with cache.open('rb') as stream:
            valid = hashlib.file_digest(stream,'sha256').hexdigest()==wanted.hexdigest()
    if not valid:
        temp = cache.with_suffix('.'+uuid.uuid4().hex+'.tmp')
        try:
            with temp.open('wb') as stream:
                for chunk in converted():
                    stream.write(chunk)
            os.replace(temp,cache)
        finally:
            temp.unlink(missing_ok=True)
    # ACCESS_READ, unlike copy-on-write mappings, does not reserve the whole
    # weight file in the Windows page file. Evaluation never mutates parameters.
    mapping = np.memmap(cache,dtype='<f4',mode='r')
    state = {name:torch.from_numpy(mapping[item['offset']//4:item['offset']//4+item['size']].reshape(item['shape']))
             for name,item in layout.items()}
    return state, mapping


def materialize_buffers(model):
    import torch
    for module in model.modules():
        for name, value in list(module._buffers.items()):
            if value is None or value.device.type != 'meta':
                continue
            if name == 'position_ids':
                module._buffers[name] = torch.arange(value.shape[-1],dtype=value.dtype).expand(value.shape)
            elif name == 'token_type_ids':
                module._buffers[name] = torch.zeros(value.shape,dtype=value.dtype)
            elif name == 'inv_freq' and hasattr(module, 'rope_init_fn'):
                frequency, scaling = module.rope_init_fn(module.config, torch.device('cpu'))
                module._buffers[name] = frequency
                module.original_inv_freq = frequency
                module.attention_scaling = scaling
            else:
                raise ValueError('Unsupported nonpersistent meta buffer: '+name)
