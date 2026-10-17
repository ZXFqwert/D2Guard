"""Host-owned JSON memory. The Agent can choose a key, never a host path."""
import json
import os
import re
import uuid
from pathlib import Path
from .store import digest, encode


class MemoryStore:
    def __init__(self, root):
        self.root=Path(root)
        self.root.mkdir(parents=True,exist_ok=True)
        if self.root.is_symlink():raise ValueError('Memory root cannot be a link')
        self.root=self.root.resolve()

    def path(self,key):
        if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',key):
            raise ValueError('Memory key must be 1-64 letters, numbers, underscores or hyphens')
        path=self.root/(key+'.json')
        if path.is_symlink() or not path.resolve().is_relative_to(self.root):
            raise ValueError('Memory links are forbidden')
        return path

    def write(self,key,content,metadata):
        if not isinstance(content,str) or len(content.encode())>65536:raise ValueError('Memory exceeds 64 KiB')
        path=self.path(key)
        entry={'key':key,'content':content,'content_sha256':digest(content),**metadata}
        tmp=self.root/(uuid.uuid4().hex+'.tmp')
        try:
            with tmp.open('x',encoding='utf-8',newline='\n') as stream:stream.write(encode(entry))
            os.replace(tmp,path)
        finally:
            if tmp.exists():tmp.unlink()
        return entry

    def read(self,key):
        entry=json.loads(self.path(key).read_text(encoding='utf-8'))
        if entry.get('key')!=key or digest(entry['content'])!=entry.get('content_sha256'):
            raise ValueError('Memory content hash mismatch')
        return entry
