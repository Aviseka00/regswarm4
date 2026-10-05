import base64
import os
import sqlite3
import tempfile
import unittest
from regswarm import facilities, intake


class FacilityLibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.con = sqlite3.connect(os.path.join(self.tmp.name, 'library.db'))
        self.con.row_factory = sqlite3.Row
        self.one = facilities.create(self.con, {}, 'test-admin')
        self.two = facilities.create(self.con, {}, 'test-admin')
        self.cls = facilities.library(self.con,self.one)['classes'][0]['id']

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def upload(self, version='1'):
        return facilities.upload(self.con,self.one,{'class_id':self.cls,'document':{'id':'SOP-01','title':'Cleaning validation','version':version,'date':'2026-10-01','status':'Approved','source':'DMS/01'},'filename':'source.txt','file':base64.b64encode(b'Cleaning validation requires residue acceptance limits.').decode()},'test-admin')[0]

    def test_defaults_custom_classes_and_numbering(self):
        self.assertEqual([f['name'] for f in facilities.listing(self.con)],['Facility 01','Facility 02'])
        self.assertEqual(len(facilities.library(self.con,self.one)['classes']),8)
        facilities.category(self.con,self.one,{'name':'Validation report'})
        self.assertEqual(len(facilities.library(self.con,self.one)['classes']),9)

    def test_parallel_search_isolates_facilities(self):
        identifier = self.upload()
        result = facilities.search(self.con,self.one,'cleaning residue')
        self.assertEqual(result['hits'][0]['record_id'],identifier)
        self.assertEqual(len(result['workers']),8)
        self.assertEqual(facilities.search(self.con,self.two,'cleaning residue')['hits'],[])

    def test_version_snapshot_and_cross_facility_rejection(self):
        identifier = self.upload()
        body = {'title':'Observation','product_class':'Sterile','observation':'Assess cleaning controls','document_ids':[identifier]}
        case,_ = facilities.case(self.con,self.one,body,'test-user')
        self.upload('2')
        restored = intake.load(self.con,case['id'])
        self.assertEqual(restored['documents'][0]['version'],'1')
        self.assertEqual(restored['facility_id'],self.one)
        with self.assertRaises(ValueError): facilities.case(self.con,self.two,body,'test-user')
        with self.assertRaises(ValueError): self.upload()

    def test_cross_facility_class_rejected(self):
        with self.assertRaises(ValueError):
            facilities.upload(self.con,self.two,{'class_id':self.cls},'test-user')
