"""Pure metadata canaries; no models, API, network or fresh corpus imports."""
import hashlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

root=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("record_worker",root/"worker.py")
w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)

class RecordTests(unittest.TestCase):
    counter=0
    def setUp(self):
        type(self).counter+=1
        self.folder=root/("fixture-"+str(self.counter));self.folder.mkdir()
        owner=self.folder/"example.dist-info";owner.mkdir()
        self.raw=b"example.py,sha256=abc,12\r\nexample.dist-info/RECORD,,\r\n"
        (owner/"RECORD").write_bytes(self.raw)
        class Dist:
            metadata={"Name":"example"};version="1.0";_path=owner
            def read_text(inner,name):return (owner/name).read_text(encoding="utf-8")
        self.dist=Dist()
        self.frozen={"python":sys.version,"executable":str(Path(sys.executable).resolve()),"distributions":[{"name":"example","version":"1.0","record_sha256":hashlib.sha256(self.raw).hexdigest()}]}
        self.file=self.folder/"frozen.json";self.persist()
        self.mock=patch.object(w.importlib.metadata,"distributions",return_value=[self.dist]);self.mock.start();self.addCleanup(self.mock.stop)
    def persist(self):self.file.write_text(json.dumps(self.frozen),encoding="utf-8")
    def test_crlf_raw_bytes_pass(self):
        self.assertNotEqual(hashlib.sha256(self.dist.read_text("RECORD").encode()).hexdigest(),self.frozen["distributions"][0]["record_sha256"])
        self.assertEqual(w.runtime_check(self.file)["runtime_packages_verified"],1)
    def test_changed_raw_bytes_fail(self):
        (self.dist._path/"RECORD").write_bytes(self.raw+b"x")
        with self.assertRaises(ValueError):w.runtime_check(self.file)
    def test_changed_version_fails(self):
        self.dist.version="2.0"
        with self.assertRaises(ValueError):w.runtime_check(self.file)
    def test_missing_distribution_fails(self):
        with patch.object(w.importlib.metadata,"distributions",return_value=[]):
            with self.assertRaises(ValueError):w.runtime_check(self.file)
    def test_unrelated_vendored_record_cannot_substitute(self):
        other=self.folder/"vendored.dist-info";other.mkdir();(other/"RECORD").write_bytes(self.raw)
        self.frozen["distributions"][0]["record_sha256"]=hashlib.sha256(b"owner different").hexdigest();self.persist()
        with self.assertRaises(ValueError):w.runtime_check(self.file)
    def test_missing_owner_record_fails(self):
        self.dist._path=self.folder/"missing.dist-info"
        with self.assertRaises(ValueError):w.runtime_check(self.file)
    def test_different_python_fails(self):
        self.frozen["python"]="different";self.persist()
        with self.assertRaises(ValueError):w.runtime_check(self.file)

if __name__=="__main__":unittest.main(verbosity=2)
