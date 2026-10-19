import unittest,numpy as np
from d2v2.s1_inference import softmax,QUESTION
class DeliveryInferenceTests(unittest.TestCase):
 def test_softmax_preserves_frozen_float64_semantics(self):
  z=np.array([[.1,.3,-4],[100,99,98]],dtype=np.float32)
  old=np.asarray(z,dtype=np.float64);p=np.exp(old-old.max(axis=-1,keepdims=True));p/=p.sum(axis=-1,keepdims=True)
  self.assertEqual(softmax(z).dtype,np.dtype('float64'));np.testing.assert_array_equal(softmax(z),p)
 def test_fixed_concrete_task_question(self):
  self.assertEqual(QUESTION['type'],'choice');self.assertEqual(list(QUESTION['criteria']),['A','B','C']);self.assertIn('current specific task',QUESTION['criteria']['A'])
