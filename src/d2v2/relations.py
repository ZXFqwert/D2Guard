"""Bounded lexical operation/target relations, not a general semantic parser.

Relations preserve what a source requests. They do not establish user permission,
actual execution, credential possession, or causal influence on the Agent.
"""
import re

VERB = re.compile(
    r'\b(?:net_fetch\s+(?:GET|POST)|fs_read|fs_write|read|review|inspect|write|create|save|generate|POST|upload|send|GET|fetch|download)\b'
    r'|读取|查阅|写入|保存|创建|生成|上传|外发|发送|获取|下载',re.I)
NEGATIVE = re.compile(r'\b(?:not|never|avoid|without|prohibit)\b|禁止|不要|不得|不允许',re.I)
QUOTE = re.compile(r'\b(?:example|quoted?|illustration)\b|示例|引用',re.I)
FLOW = re.compile(r'\b(?:contents?|body|upload|send|post)\b|内容|上传|发送|外发',re.I)


def relation_segments(clause, find_targets):
    verbs=list(VERB.finditer(clause))
    relations=[];flows=[];incomplete=False
    for index,verb in enumerate(verbs):
        stop=verbs[index+1].start() if index+1<len(verbs) else len(clause)
        tail=clause[verb.end():stop]
        # Keep coordinated objects ("read a.txt and b.txt"). The next verb
        # already bounds this segment; splitting on every "and" loses objects.
        prefix=clause[:verb.start()]
        prefix=re.split(r'[,;]|\b(?:and|then|but)\b|然后|但是|并且',prefix,flags=re.I)[-1]
        stance='negated' if NEGATIVE.search(prefix) else 'quoted' if QUOTE.search(clause) else 'requested'
        value=verb.group().lower()
        if value in {'read','review','inspect','fs_read','读取','查阅'}:op='fs.read'
        elif value in {'write','create','save','generate','fs_write','写入','保存','创建','生成'}:op='fs.write'
        elif value.endswith('post') or value in {'upload','send','上传','发送','外发'}:op='net.fetch:POST'
        else:op='net.fetch:GET'
        mentioned=find_targets(tail)
        urls=[t for t in mentioned if t.lower().startswith(('http://','https://'))]
        files=[t for t in mentioned if t not in urls]
        objects=urls if op.startswith('net.') else files
        # Unknown endpoints are a coverage gap, not a fabricated file-as-host edge.
        if op.startswith('net.') and files and not urls:incomplete=True
        for target in objects:
            relations.append({'op':op,'target':target,'stance':stance})
        if op=='net.fetch:POST' and FLOW.search(clause[verb.start():stop]):
            for destination in urls:
                for source in files:
                    flows.append({'source_asset':source,'destination':destination,
                                  'operation':op,'stance':stance,'status':'source_requested_not_executed'})
    def unique(items):
        return [dict(items_tuple) for items_tuple in dict.fromkeys(tuple(i.items()) for i in items)]
    return unique(relations),unique(flows),incomplete


def contextual_cues(clause):
    claims=[]
    if re.search(r'\b(?:provisioned|provided|approved|authorized|required)\b.{0,100}\b(?:project owner|administrator|developer|system)\b',clause,re.I):
        claims.append('claims_higher_authority')
    if re.search(r'\b(?:before|prerequisite|required first)\b|之前|前置|先.{0,30}再',clause,re.I):
        claims.append('claims_workflow_precondition')
    if re.search(r'\b(?:without including|do not mention|hide|secretly)\b|不要提及|隐瞒|偷偷',clause,re.I):
        claims.append('requests_output_omission')
    return claims
