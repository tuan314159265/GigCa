import copy
import json
import unittest
from unittest.mock import patch
from api.llm_explanations import apply_explanations, validate_selection, evidence_for, classified_poi, poi_context, poi_group

TEXT='Trong các điểm đang so sánh, khu vực này có năng suất dự kiến tốt nhất. Bạn cần cân nhắc quãng đường di chuyển trước khi tới điểm chờ.'
class ExplanationTests(unittest.TestCase):
    def setUp(self):
        self.result={'objectives':{'max_trip_value':{'plan':{'summary':'Lý do từ engine.',
            'target_location':'Trung tâm','key_metrics':{'yield_vnd_per_hour':50000,
            'expected_wait_min':11,'reposition_km_estimated':1.7}}}},
            'areas':[{'name':'Trung tâm','lat':10.77,'lng':106.7}], 'snapshot':{'mode':'live'}}
        self.cfg={'GIGCA_LLM_EXPLANATIONS':'true','GIGCA_LLM_API_KEY':'test-secret',
                  'GIGCA_LLM_MODEL':'test-model','GIGCA_LLM_BASE_URL':'https://example.com/v1'}
    def document(self,text=TEXT,ids=None):
        return {'objectives':{'max_trip_value':{'text':text,'evidence_ids':ids or ['engine','tradeoff']}}}
    def test_rejects_invented_evidence_numbers_and_context(self):
        facts={'max_trip_value':{'engine':'a','tradeoff':'b'}}
        cases=[self.document(ids=['engine','made_up']),self.document(ids=['engine','engine']),
               self.document(TEXT+' Có nhiều trường học gần đây.'),self.document(TEXT+' Chờ 5 phút.'),
               self.document(TEXT+' Đang tan ca nên đông khách.')]
        for document in cases:
            with self.assertRaises(ValueError): validate_selection(document,facts)
    def test_natural_prose_is_used_without_changing_metrics(self):
        response={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(self.document())}}]}
        with patch('api.llm_explanations.settings',return_value=self.cfg), patch('api.llm_explanations.poi_context',return_value=[]), patch('api.llm_explanations.request_json',return_value=response), patch('api.llm_explanations.cached',side_effect=lambda k,t,f:f()):
            out=apply_explanations(copy.deepcopy(self.result))
        self.assertEqual(out['objectives']['max_trip_value']['plan']['summary'],TEXT)
        self.assertEqual(out['objectives']['max_trip_value']['plan']['key_metrics'],self.result['objectives']['max_trip_value']['plan']['key_metrics'])
        self.assertEqual(out['objectives']['max_trip_value']['plan']['target_location'],'Trung tâm')
    def test_scoped_ids_and_partial_response(self):
        facts={'max_trip_value':{'engine':'a','tradeoff':'b'},'maintain_position':{'engine':'c','income':'d'}}
        out=validate_selection(self.document(ids=['max_trip_value.engine','max_trip_value.tradeoff']),facts)
        self.assertEqual(out['max_trip_value']['text'],TEXT)
        self.assertNotIn('maintain_position',out)
    def test_objective_self_reference_normalizes_to_engine(self):
        facts={'max_trip_value':{'engine':'a','tradeoff':'b'}}
        out=validate_selection(self.document(ids=['max_trip_value','tradeoff']),facts)
        self.assertEqual(out['max_trip_value']['evidence_ids'],['engine','tradeoff'])

    def test_provider_failure_keeps_engine_summary(self):
        with patch('api.llm_explanations.settings',return_value=self.cfg), patch('api.llm_explanations.poi_context',return_value=[]), patch('api.llm_explanations.request_json',side_effect=TimeoutError), patch('api.llm_explanations.cached',side_effect=lambda k,t,f:f()):
            out=apply_explanations(copy.deepcopy(self.result))
        self.assertEqual(out['objectives'],self.result['objectives'])
        self.assertEqual(out['explanation_status']['source'],'engine')
    def test_disabled_does_not_call_provider(self):
        with patch('api.llm_explanations.settings',return_value={}), patch('api.llm_explanations.request_json') as call:
            apply_explanations(self.result)
        call.assert_not_called()
    def test_nearby_keeps_all_types_and_deduplicates(self):
        records=[]
        for i,label in enumerate(['Market','Hospital','Bus Station','Restaurant','Stationery','Unusual Local Service']):
            records.append({'id':str(i),'position':{'lat':10.77,'lon':106.7},'poi':{'name':f'Place {i}','categories':[label]}})
        records += [records[0], {'id':'outside','position':{'lat':11,'lon':107},'poi':{'name':'Outside','categories':['Market']}}]
        with patch('api.llm_explanations.tomtom_url',side_effect=lambda u,p:u), patch('api.llm_explanations.request_json',return_value={'results':records,'summary':{'totalResults':len(records)}}), patch('api.llm_explanations.cached',side_effect=lambda k,t,f:f()):
            groups=poi_context(10.77,106.7)
        self.assertEqual(sum(len(g['pois']) for g in groups),6)
        self.assertTrue({'market','hospital','transport','food','stationery'}.issubset({g['category'] for g in groups}))
        self.assertTrue(any(g['label']=='Unusual Local Service' for g in groups))
    def test_nearby_caps_diverse_context_without_category_filter(self):
        record=lambda i:{'id':str(i),'position':{'lat':10.77,'lon':106.7},'poi':{'name':f'Place {i}','categories':['Market']}}
        responses=[{'results':[record(i) for i in range(100)],'summary':{'totalResults':101}},
                   {'results':[record(100)],'summary':{'totalResults':101}}]
        with patch('api.llm_explanations.tomtom_url',side_effect=lambda u,p:u) as url, patch('api.llm_explanations.request_json',side_effect=responses), patch('api.llm_explanations.cached',side_effect=lambda k,t,f:f()):
            groups=poi_context(10.77,106.7)
        self.assertEqual(sum(len(g['pois']) for g in groups),10)
        self.assertEqual(url.call_count,1)
        self.assertEqual(groups[0]['selection_limit'],10)
        self.assertEqual(url.call_args_list[0].args[1]['limit'],100)
        self.assertNotIn('categorySet',url.call_args_list[0].args[1])
    def test_priority_types_share_ten_slots_before_other_types(self):
        records=[{'id':str(i),'position':{'lat':10.77,'lon':106.7},'poi':{'name':f'Place {i}','categories':[label]}}
                 for i,label in enumerate(['Restaurant']*12+['School']*4+['Shopping Center']*4+['Company']*4)]
        with patch('api.llm_explanations.tomtom_url',side_effect=lambda u,p:u), patch('api.llm_explanations.request_json',return_value={'results':records}), patch('api.llm_explanations.cached',side_effect=lambda k,t,f:f()):
            groups=poi_context(10.77,106.7)
        self.assertEqual(sum(len(g['pois']) for g in groups),10)
        self.assertEqual({g['category'] for g in groups},{'school','shopping','office'})

    def test_stationery_remains_retail_instead_of_office(self):
        self.assertEqual(poi_group({'name':'Văn phòng phẩm A','categories':['Stationery','Company']})[0],'stationery')

    def test_stationery_is_not_an_office(self):
        self.assertFalse(classified_poi('office',{'name':'Cửa hàng văn phòng phẩm Nhật Ký','categories':['Company']}))
        self.assertFalse(classified_poi('office',{'name':'Office Cafe','categories':['Cafe']}))
        self.assertTrue(classified_poi('office',{'name':'Công ty A','categories':['Company']}))
        self.assertTrue(classified_poi('school',{'name':'Trường A','categories':['School']}))
        self.assertFalse(classified_poi('industrial',{'name':'Khu công nghiệp A','categories':[]}))
    def test_multiple_poi_requires_three_classified_places(self):
        group={'category':'school','label':'trường học','pois':[{'name':'Trường A','distance_m':200}]}
        facts=evidence_for(self.result,'max_trip_value',[group])
        self.assertIn('không mô tả tập trung nhiều',facts['poi_school'])
        self.assertIn('Trường A',facts['poi_school'])

if __name__=='__main__': unittest.main()
