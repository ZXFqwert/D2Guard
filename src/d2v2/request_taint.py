"""Request contamination is distinct from immutable integrity provenance."""
import math


def source_request_taint(analysis, mode='taint_gate', source_sha=None):
    if not isinstance(analysis,dict) or analysis.get('structural_gap'):
        return True,'missing_or_structural_gap'
    if any(r.get('stance')=='requested' for d in analysis.get('directives',[]) for r in d.get('action_relations',[])):
        return True,'rule_requested'
    if mode=='rules_gate':return False,'rule_no_requested'
    s1=analysis.get('s1')
    if not isinstance(s1,dict) or s1.get('calibrated') is not True or s1.get('error_type'):
        return True,'s1_unavailable_or_uncalibrated'
    if (s1.get('coverage_complete') is not True or not isinstance(s1.get('windows'),int)
            or s1['windows']<1 or s1.get('expected_windows')!=s1['windows']
            or source_sha is None or s1.get('source_sha256')!=source_sha):
        return True,'s1_incomplete_coverage'
    probability=s1.get('probabilities',{}).get('request');threshold=s1.get('request_threshold')
    if (not isinstance(probability,(int,float)) or not math.isfinite(probability) or not 0<=probability<=1
            or not isinstance(threshold,(int,float)) or not math.isfinite(threshold) or not 0<=threshold<=1):
        return True,'s1_invalid_probability'
    if s1.get('threshold_passed') is not (probability>=threshold):return True,'s1_inconsistent_threshold'
    if probability>=threshold:return True,'s1_request'
    if s1.get('label') not in {'none','quoted'}:return True,'s1_invalid_negative'
    return False,'s1_'+s1['label']


def context_request_taint(sources, mode='taint_gate'):
    evidence=[]
    for sid,analysis,sha in sources:
        tainted,reason=source_request_taint(analysis,mode,sha)
        evidence.append({'source_id':sid,'request_tainted':tainted,'reason':reason})
    return any(e['request_tainted'] for e in evidence),evidence
