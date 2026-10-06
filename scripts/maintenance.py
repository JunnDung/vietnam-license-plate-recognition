"""Consistent SQLite/image backups and explicit, dry-run-first history retention."""
import argparse
from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def image_path(data, image_id):
    if not re.fullmatch('[0-9a-f]{32}', image_id):
        raise ValueError('Invalid image ID in database; stop maintenance.')
    return data/'images'/(image_id+'.jpg')


def backup(data, destination):
    destination = Path(destination).resolve()
    if destination.exists():
        raise FileExistsError('Choose a new backup filename; existing backups are preserved.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix+'.partial')
    if partial.exists():
        raise FileExistsError('An unfinished backup exists; inspect it before retrying.')
    with tempfile.TemporaryDirectory() as folder, closing(sqlite3.connect(data/'history.sqlite3', timeout=30)) as guard:
        guard.execute('BEGIN IMMEDIATE')
        owned_partial = False
        try:
            if destination.exists():
                raise FileExistsError('The backup filename was used by another operation.')
            rows = guard.execute('SELECT image_id,crop_id FROM records').fetchall()
            ids = {value for row in rows for value in row}
            database = Path(folder)/'history.sqlite3'
            with closing(sqlite3.connect(data/'history.sqlite3')) as source, closing(sqlite3.connect(database)) as target:
                source.backup(target)
            hashes = {}
            with zipfile.ZipFile(partial, 'x', zipfile.ZIP_DEFLATED) as archive:
                owned_partial = True
                for path, name in [(database,'history.sqlite3')] + [(image_path(data,value),f'images/{value}.jpg') for value in sorted(ids)]:
                    raw = path.read_bytes()
                    hashes[name] = hashlib.sha256(raw).hexdigest()
                    archive.writestr(name, raw)
                archive.writestr('manifest.json',json.dumps({'created_at':datetime.now(timezone.utc).isoformat(),
                    'records':len(rows),'images':len(ids),'sha256':hashes},indent=2))
            verify_backup(partial)
            partial.replace(destination)
            return {'backup':str(destination),'records':len(rows),'images':len(ids),'verified':True}
        except Exception:
            if owned_partial:
                partial.unlink(missing_ok=True)
            raise
        finally:
            guard.rollback()


def verify_backup(path):
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        if set(archive.namelist()) != set(manifest['sha256']) | {'manifest.json'}:
            raise ValueError('Unexpected backup contents.')
        for name, digest in manifest['sha256'].items():
            if name != 'history.sqlite3' and not re.fullmatch(r'images/[0-9a-f]{32}\.jpg',name):
                raise ValueError('Invalid backup path.')
            if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                raise ValueError(f'Backup checksum mismatch: {name}')
        return {'verified':True,'records':manifest['records'],'images':manifest['images']}


def prune(data, days, apply=False):
    cutoff = (datetime.now(timezone.utc)-timedelta(days=days)).isoformat()
    with closing(sqlite3.connect(data/'history.sqlite3', timeout=30)) as db:
        db.execute('BEGIN IMMEDIATE')
        rows = db.execute('''SELECT id,image_id,crop_id FROM records WHERE created_at < ? AND id NOT IN
            (SELECT entry_record_id FROM parking_sessions UNION SELECT exit_record_id FROM parking_sessions WHERE exit_record_id IS NOT NULL)''', (cutoff,)).fetchall()
        candidates = {value for row in rows for value in row[1:]}
        for value in candidates:
            image_path(data,value)
        if apply:
            db.executemany('DELETE FROM records WHERE id=?', [(row[0],) for row in rows])
            referenced = {value for row in db.execute('SELECT image_id,crop_id FROM records') for value in row}
            db.commit()
        else:
            db.rollback()
    if apply:
        for value in candidates-referenced:
            image_path(data,value).unlink(missing_ok=True)
    return {'dry_run':not apply,'older_than_days':days,'eligible_records':len(rows),'protected_parking_evidence':True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data',type=Path,default=Path(os.getenv('PLATE_DATA_DIR',ROOT/'runtime')))
    commands = parser.add_subparsers(dest='command',required=True)
    commands.add_parser('backup').add_argument('--output',type=Path,required=True)
    commands.add_parser('verify').add_argument('archive',type=Path)
    cleanup = commands.add_parser('prune');cleanup.add_argument('--days',type=int,default=30);cleanup.add_argument('--apply',action='store_true')
    args = parser.parse_args()
    if args.command == 'prune' and args.days < 1:
        parser.error('--days must be positive')
    if args.command != 'verify' and not (args.data/'history.sqlite3').is_file():
        parser.error('History database does not exist; start the API first.')
    result = backup(args.data,args.output) if args.command == 'backup' else verify_backup(args.archive) if args.command == 'verify' else prune(args.data,args.days,args.apply)
    print(json.dumps(result,ensure_ascii=False))


if __name__ == '__main__':
    main()
