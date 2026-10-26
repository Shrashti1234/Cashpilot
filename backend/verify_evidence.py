"""Offline checksum verification. Integrity does not establish authenticity."""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile,BadZipFile
MAX_BYTES=16_000_000


def verify_bundle(path):
    if Path(path).stat().st_size>MAX_BYTES+1_000_000:raise ValueError('Archive exceeds the supported size')
    with ZipFile(path) as archive:
        entries=archive.infolist();names=[e.filename for e in entries]
        if len(entries)>20 or sum(e.file_size for e in entries)>MAX_BYTES+100_000:raise ValueError('Archive exceeds the supported uncompressed limits')
        if len(names)!=len(set(names)) or 'manifest.json' not in names:raise ValueError('Missing manifest or duplicate file entries')
        manifest=json.loads(archive.read('manifest.json'))
        if not isinstance(manifest,dict) or manifest.get('format_version')!=1 or not isinstance(manifest.get('files'),dict):raise ValueError('Unsupported manifest')
        if set(names)!=set(manifest['files'])|{'manifest.json'}:raise ValueError('File list differs from manifest')
        for name,info in manifest['files'].items():
            if not isinstance(info,dict):raise ValueError('Invalid file metadata')
            if '/' in name or '\\' in name or name in {'.','..'}:raise ValueError('Unexpected archive entry name')
            content=archive.read(name)
            if info.get('bytes')!=len(content) or info.get('sha256')!=hashlib.sha256(content).hexdigest():raise ValueError('Checksum verification failed')
        return len(manifest['files'])


def main():
    parser=argparse.ArgumentParser(description='Verify CashPilot invoice bundle checksums without extracting files')
    parser.add_argument('archive');args=parser.parse_args()
    try:count=verify_bundle(args.archive)
    except (OSError,ValueError,BadZipFile,KeyError,TypeError,RuntimeError):print('Bundle verification failed. Check the file and manifest.');return 1
    print(f'Checksums verified for {count} files. This does not establish source authenticity.');return 0


if __name__=='__main__':raise SystemExit(main())
