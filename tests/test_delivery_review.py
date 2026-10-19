import unittest,json,httpx
from d2v2.review import request_assessment
class DeliveryReviewTests(unittest.TestCase):
 def exercise(self, bodies):
  calls=[]
  value={'semantic_alignment':'INSUFFICIENT','recommended_verdict':'ASK','explainable_report_zh':'证据有限','supporting_event_ids':['e'],'citations':[{'event_id':'e','sha256':'abc','char_span':[0,1]}]}
  def handler(req):
   calls.append(json.loads(req.content));status,text=bodies[min(len(calls)-1,len(bodies)-1)]
   text=text.replace('VALID',json.dumps(value))
   return httpx.Response(status,json={'choices':[{'message':{'content':text}}]})
  with httpx.Client(transport=httpx.MockTransport(handler)) as c:
   result=request_assessment(c,'http://localhost/review',{}, {'messages':[], 'response_format':{'type':'json_object'}}, value['citations'])
  return result,calls
 def test_retry_invalid_json(self):
  r,c=self.exercise([(200,'broken'),(200,'VALID')]);self.assertEqual(len(c),2);self.assertIn('JSONDecodeError',c[1]['messages'][-1]['content'])
 def test_retry_schema(self):
  r,c=self.exercise([(200,'{}'),(200,'VALID')]);self.assertIn('ValidationError',c[1]['messages'][-1]['content'])
 def test_json_mode_unsupported(self):
  r,c=self.exercise([(400,''),(200,'VALID')]);self.assertNotIn('response_format',c[1])
 def test_retry_bounded(self):
  with self.assertRaises(json.JSONDecodeError):self.exercise([(200,'broken')])
 def test_outer_object(self):
  r,c=self.exercise([(200,'说明```json\nVALID\n```')]);self.assertEqual(r['recommended_verdict'],'ASK')
 def test_invalid_reference_not_accepted(self):
  with self.assertRaises(ValueError):self.exercise([(200,'{"semantic_alignment":"INSUFFICIENT","recommended_verdict":"ASK","explainable_report_zh":"x","supporting_event_ids":["fake"],"citations":[{"event_id":"fake","sha256":"abc","char_span":[0,1]}]}')])
