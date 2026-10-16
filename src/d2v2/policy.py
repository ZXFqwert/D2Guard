"""Reuse the reviewed five-rule YAML/AST contract without retaining raw call history."""
import fnmatch
from pathlib import Path
import yaml
from d2core.execution import exec_violation
from d2core.policy_engine import PolicyRule, normalized_path


class HardPolicies:
    def __init__(self,workspace):
        path=Path(__file__).resolve().parents[1]/'d2core/policies.yaml'
        data=yaml.safe_load(path.read_text(encoding='utf-8'))
        self.rules={r['id']:PolicyRule.model_validate(r).model_dump() for r in data['rules']}
        if len(self.rules)!=5:raise ValueError('Expected five hard policies')
        self.workspace=workspace

    def check(self,name,args,readonly,hits):
        fs=self.rules['POL-FS-WRITE-SENSITIVE']
        if name in fs['tools']:
            path=normalized_path(args.get('path',''),self.workspace)
            if any(c in path.split('/') for c in fs['sensitive_components']) or any(fnmatch.fnmatchcase(path,p) for p in fs['path_patterns']):
                return fs['id'],'写入凭证目录、计划任务或自启动目录被硬策略禁止。'
        if name in self.rules['POL-GIT-REVIEW-NO-PUSH']['tools'] and readonly:
            return 'POL-GIT-REVIEW-NO-PUSH','只读任务不得提交或推送代码。'
        if name in self.rules['POL-EXEC-RESTRICT']['tools']:
            reason=exec_violation(args.get('command',args.get('cmd','')),self.rules['POL-EXEC-RESTRICT'],readonly=readonly)
            if reason:return 'POL-EXEC-RESTRICT',reason
        if hits and name in self.rules['POL-NET-SECRET-EXFIL']['tools']:
            # This experimental deployment is intentionally stricter than the 50% ceiling:
            # any matching keyed 8-byte secret fragment is held, including partial exports.
            return 'POL-NET-SECRET-EXFIL','外发参数命中已登记的敏感凭据或分片。'
        if hits and name in self.rules['POL-SUBAGENT-SECRET-LEAK']['tools']:
            return 'POL-SUBAGENT-SECRET-LEAK','子任务参数携带敏感凭据或分片。'
        return None,None
