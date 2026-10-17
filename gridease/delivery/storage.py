"""Content-addressed attachments and immutable release archives, outside source files."""
import hashlib
import os
from pathlib import Path
import tempfile

MAX_FILE_BYTES=10*1024*1024
ALLOWED_EXTENSIONS={'.pdf','.png','.jpg','.jpeg','.svg','.csv','.txt','.json','.zip','.kmz','.xlsx','.docx'}


def put_blob(store,pid,content,kind='attachments'):
    store._path(pid)  # enforce project-ID path boundary
    if not content or len(content)>MAX_FILE_BYTES*10:raise ValueError('Empty or excessive file size')
    digest=hashlib.sha256(content).hexdigest()
    folder=store.root.parent/kind/pid;folder.mkdir(parents=True,exist_ok=True)
    target=folder/digest
    with tempfile.NamedTemporaryFile(dir=folder,delete=False) as tmp:
        temp=Path(tmp.name);tmp.write(content);tmp.flush();os.fsync(tmp.fileno())
    try:temp.replace(target)
    finally:temp.unlink(missing_ok=True)
    return digest


def get_blob(store,pid,digest,kind='attachments'):
    store._path(pid)
    if len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):raise ValueError('Invalid content hash')
    content=(store.root.parent/kind/pid/digest).read_bytes()
    if hashlib.sha256(content).hexdigest()!=digest:raise ValueError('Attachment hash mismatch; restore a verified backup')
    return content
