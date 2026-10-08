import base64
import io
import os
import sqlite3
import tempfile
import unittest
import zipfile
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

    def test_word_table_and_pdf_page_are_read_in_full(self):
        xml = '''<?xml version="1.0"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
<w:p><w:r><w:t>Filling batch record</w:t></w:r></w:p>
<w:tbl><w:tr>
<w:tc><w:p><w:r><w:t>Fill-weight</w:t></w:r></w:p></w:tc>
<w:tc><w:p><w:r><w:t>blank</w:t></w:r></w:p></w:tc>
<w:tc><w:p><w:r><w:t>9.5-10.5 g</w:t></w:r></w:p></w:tc>
<w:tc><w:p><w:r><w:t></w:t></w:r></w:p></w:tc>
</w:tr></w:tbl>
</w:body></w:document>'''
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('word/document.xml', xml)
        encoded = base64.b64encode(buffer.getvalue()).decode()
        text = facilities.extract('batch.docx', encoded)
        self.assertIn('Fill-weight | blank | 9.5-10.5 g', text)
        stream = b'BT [(Fill-) 20 (weight) -300 (checks)] TJ T* (were not recorded) Tj ET'
        self.assertIn('Fill-weight checks', facilities._pdf_content_text(stream))
        self.assertIn('were not recorded', facilities._pdf_content_text(stream))

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
        compression_class = facilities.library(self.con, compression)['classes'][2]['id']
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
        several = facilities.batch_items({'items': [{'facility_ids': ['FAC-a', 'FAC-b', 'FAC-a'], 'query': 'The incubator qualification was incomplete.'}]})
        self.assertEqual(several[0]['facility_ids'], ['FAC-a', 'FAC-b'])
        self.assertEqual(several[0]['facility_id'], 'FAC-a')

    def test_saved_query_number_and_selected_facilities(self):
        plant = facilities.create_plant(self.con, {'name': 'Northbridge Plant'}, 'test-admin')
        other = facilities.create_plant(self.con, {'name': 'Southbridge Plant'}, 'test-admin')
        filling = facilities.create(self.con, {'plant_id': plant, 'name': 'Filling'}, 'test-admin')
        compression = facilities.create(self.con, {'plant_id': other, 'name': 'Compression'}, 'test-admin')
        packing = facilities.create(self.con, {'plant_id': other, 'name': 'Packing'}, 'test-admin')
        fill_class = facilities.library(self.con, filling)['classes'][0]['id']
        comp_class = facilities.library(self.con, compression)['classes'][2]['id']
        pack_class = facilities.library(self.con, packing)['classes'][0]['id']
        facilities.upload(self.con, filling, {'class_id': fill_class, 'document': {'id': 'SOP-FILL', 'title': 'Line clearance', 'version': '1', 'date': '2026-10-01', 'status': 'Approved', 'source': 'DMS'}, 'filename': 'fill.txt', 'file': base64.b64encode(b'Retained labels are checked at line clearance.').decode()}, 'test-admin')
        facilities.upload(self.con, compression, {'class_id': comp_class, 'document': {'id': 'BMR-COMP', 'title': 'Compression record', 'version': '1', 'date': '2026-10-01', 'status': 'Approved', 'source': 'DMS'}, 'filename': 'comp.txt', 'file': base64.b64encode(b'The yield and reviewer signature are recorded.').decode()}, 'test-admin')
        facilities.upload(self.con, packing, {'class_id': pack_class, 'document': {'id': 'SOP-PACK', 'title': 'Packing line', 'version': '1', 'date': '2026-10-01', 'status': 'Approved', 'source': 'DMS'}, 'filename': 'pack.txt', 'file': base64.b64encode(b'Packing checks are recorded.').decode()}, 'test-admin')
        saved = facilities.save_query_set(self.con, {'items': [
            {'facility_ids': [filling, compression], 'query': 'Retained labels were found at line clearance.', 'product_class': 'Vaccine'},
            {'facility_id': filling, 'query': 'Fill-weight checks were not recorded.', 'product_class': 'Vaccine'},
        ]}, 'test-user')
        self.assertEqual(saved['number'], 'QRY-0001')
        self.assertEqual(saved['count'], 2)
        again = facilities.save_query_set(self.con, {'items': [{'facility_id': filling, 'query': 'Cleaning residue was not recorded.'}]}, 'test-user')
        self.assertEqual(again['number'], 'QRY-0002')
        loaded = facilities.load_query_set(self.con, 'QRY-0001')
        self.assertEqual(loaded['items'][0]['facility_ids'], [filling, compression])
        self.assertTrue(loaded['items'][0]['title'].startswith('QRY-0001'))
        listed = facilities.list_query_sets(self.con)
        self.assertEqual([item['number'] for item in listed], ['QRY-0002', 'QRY-0001'])
        case, _ = facilities.audit_queries(self.con, filling, loaded['items'][0], 'test-user')
        found = {doc['id'] for doc in case['documents']}
        self.assertIn('SOP-FILL', found)
        self.assertIn('BMR-COMP', found)
        self.assertNotIn('SOP-PACK', found)
        self.assertIn('Filling', case['site_name'])
        self.assertIn('Compression', case['site_name'])
