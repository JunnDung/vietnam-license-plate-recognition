"""Backup completeness/corruption and retention protection using a temporary database."""
from datetime import datetime, timedelta, timezone
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import zipfile

from scripts.maintenance import backup, prune, verify_backup


class MaintenanceChecks(unittest.TestCase):
    def test_backup_and_protected_pruning(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root/'images').mkdir()
            with closing(sqlite3.connect(root/'history.sqlite3')) as db, db:
                db.execute('CREATE TABLE records(id TEXT,created_at TEXT,image_id TEXT,crop_id TEXT)')
                db.execute('CREATE TABLE parking_sessions(entry_record_id TEXT,exit_record_id TEXT)')
                old = (datetime.now(timezone.utc)-timedelta(days=100)).isoformat()
                for index in range(2):
                    image_id,crop_id = f'{index:032x}',f'{index+10:032x}'
                    db.execute('INSERT INTO records VALUES (?,?,?,?)',(str(index),old,image_id,crop_id))
                    for value in (image_id,crop_id): (root/'images'/(value+'.jpg')).write_bytes(b'proof')
                db.execute('INSERT INTO parking_sessions VALUES (?,NULL)',('1',))
            result = backup(root,root/'backup.zip')
            self.assertEqual((result['records'],result['images']), (2,4))
            self.assertTrue(verify_backup(root/'backup.zip')['verified'])
            with self.assertRaises(FileExistsError): backup(root,root/'backup.zip')
            self.assertEqual(prune(root,30)['eligible_records'],1)
            self.assertEqual(len(list((root/'images').glob('*.jpg'))),4)
            self.assertFalse(prune(root,30,True)['dry_run'])
            self.assertEqual(len(list((root/'images').glob('*.jpg'))),2)
            with closing(sqlite3.connect(root/'history.sqlite3')) as db:
                self.assertEqual(db.execute('SELECT id FROM records').fetchall(),[('1',)])
            with zipfile.ZipFile(root/'backup.zip') as good, zipfile.ZipFile(root/'bad.zip','w') as bad:
                for name in good.namelist(): bad.writestr(name,b'broken' if name.endswith('.jpg') else good.read(name))
            with self.assertRaises(ValueError): verify_backup(root/'bad.zip')


if __name__ == '__main__':
    unittest.main()
