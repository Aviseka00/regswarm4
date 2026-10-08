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

    def test_doc_and_pdf_text_round_trip(self):
        doc = base64.b64encode(facilities.build_doc('Cleaning', ['Residue acceptance limits apply.'])).decode()
        pdf = base64.b64encode(facilities.build_pdf('Cleaning', ['Residue acceptance limits apply.'])).decode()
        self.assertIn('Residue acceptance limits', facilities.extract('note.doc', doc))
        self.assertIn('Residue acceptance limits', facilities.extract('note.pdf', pdf))
        self.assertTrue(facilities.build_doc('Cleaning', ['Residue limits.']).startswith(b'{\\rtf'))
        self.assertTrue(facilities.build_pdf('Cleaning', ['Residue limits.']).startswith(b'%PDF'))

    def test_cross_facility_class_rejected(self):
        with self.assertRaises(ValueError):
            facilities.upload(self.con,self.two,{'class_id':self.cls},'test-user')

    def test_plant_owns_facility_and_audit_query_uses_its_documents(self):
        plant = facilities.create_plant(self.con, {'name': 'Northbridge Plant'}, 'test-admin')
        facility = facilities.create(self.con, {'plant_id': plant, 'name': 'Filling and Packaging'}, 'test-admin')
        names = [item['name'] for item in facilities.library(self.con, facility)['classes']]
        self.assertEqual(names, list(facilities.DEFAULTS))
        listed = [item['name'] for item in facilities.listing(self.con, plant)]
        self.assertEqual(listed, ['Filling and Packaging'])
        cls = facilities.library(self.con, facility)['classes'][0]['id']
        facilities.upload(self.con, facility, {'class_id': cls, 'document': {'id': 'SOP-01', 'title': 'Cleaning', 'version': '1', 'date': '2026-10-01', 'status': 'Approved', 'source': 'DMS/01'}, 'filename': 'source.txt', 'file': base64.b64encode(b'Cleaning validation residue limits.').decode(), 'attachments': [{'filename': 'checklist.txt', 'file': base64.b64encode(b'Checklist: confirm residue limit before release.').decode()}]}, 'test-admin')
        case, _ = facilities.audit_queries(self.con, facility, {'queries': ['Residue limits were not recorded.', 'Line clearance was incomplete.']}, 'test-user')
        self.assertIn('Residue limits were not recorded.', case['observation'])
        self.assertEqual(case['documents'][0]['id'], 'SOP-01')
        self.assertEqual(len(facilities.library(self.con, facility)['documents'][0]['attachments']), 2)

    def test_query_indexes_the_current_document_from_every_facility(self):
        plant = facilities.create_plant(self.con, {'name': 'Northbridge Plant'}, 'test-admin')
        other = facilities.create_plant(self.con, {'name': 'Southbridge Plant'}, 'test-admin')
        filling = facilities.create(self.con, {'plant_id': plant, 'name': 'Filling'}, 'test-admin')
        compression = facilities.create(self.con, {'plant_id': other, 'name': 'Compression'}, 'test-admin')
        filling_class = facilities.library(self.con, filling)['classes'][0]['id']
        compression_class = facilities.library(self.con, compression)['classes'][0]['id']
        facilities.upload(self.con, filling, {'class_id': filling_class, 'document': {'id': 'SOP-FILL', 'title': 'Line clearance', 'version': '1', 'date': '2026-10-01', 'status': 'Approved', 'source': 'DMS'}, 'filename': 'fill.txt', 'file': base64.b64encode(b'Retained labels are checked at line clearance.').decode()}, 'test-admin')
        facilities.upload(self.con, compression, {'class_id': compression_class, 'document': {'id': 'BMR-COMP', 'title': 'Compression record', 'version': '1', 'date': '2026-10-01', 'status': 'Approved', 'source': 'DMS'}, 'filename': 'comp.txt', 'file': base64.b64encode(b'The yield and reviewer signature are recorded.').decode()}, 'test-admin')
        case, _ = facilities.audit_queries(self.con, filling, {'queries': ['Retained labels were found at line clearance.']}, 'test-user')
        found = {doc['id']: doc['title'] for doc in case['documents']}
        self.assertIn('SOP-FILL', found)
        self.assertIn('BMR-COMP', found)
        self.assertIn('Filling', found['SOP-FILL'])
        self.assertIn('Compression', found['BMR-COMP'])

    def test_batch_keeps_each_query_with_its_facility(self):
        items = facilities.batch_items({'items': [
            {'facility_id': 'FAC-a', 'query': 'Retained labels were found at line clearance.', 'product_class': 'Sterile drug product'},
            {'facility_id': 'FAC-b', 'query': 'The yield was not recorded.', 'product_class': 'Oral solid dosage'},
        ]})
        self.assertEqual([item['facility_id'] for item in items], ['FAC-a', 'FAC-b'])
        self.assertEqual(items[0]['queries'], ['Retained labels were found at line clearance.'])
        with self.assertRaises(ValueError):
            facilities.batch_items({'items': []})
        with self.assertRaises(ValueError):
            facilities.batch_items({'items': [{'facility_id': 'FAC-a', 'query': '   '}]})
