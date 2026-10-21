"""Authorized whole-cohort replacement; preserve originals and enforce early gate."""
import json,time
from stage_d5_protocol import OUT,read,save,write_rows
from stage_d5_data import generate
from stage_d5_teacher import review
from stage_d5_resume_glm import agreement,main

def run():
    plans=read(OUT/'injection-quoted-plan.jsonl')
    for target in (208,640):
        name=f'quoted-replacement-plan-{target}.jsonl'
        if not (OUT/name).exists():write_rows(name,plans[:target])
        record=f'generation-quoted-replacement-{target}'
        if not (OUT/(record+'.json')).exists():generate(OUT/name,output_name='injected-quoted',record_name=record,resume=True,workers=8,batch_size=8)
        rows=read(OUT/'injected-quoted.jsonl')
        review('injected-quoted',rows,resume=True,teachers=None,finalize=False,workers=8,batch_size=8)
        counts=agreement('injected-quoted',rows)
        q=counts['quoted'];passed=q['paired_n']>=180 and q['rate']>=.70
        result={'passed':passed,'counts':counts,'coverage_passed':q['paired_n']>=180,'policy':'whole-cohort replacement; unchanged 70% gate','generated_target':target}
        save(f'quoted-replacement-gate-{target}.json',result);print(json.dumps(result),flush=True)
        if not passed:
            save('stage-stop.json',{'error_type':'TeacherEarlyAgreementGate','queue':'injected-quoted','stopped_unix':time.time(),'training_clock_started':False,'gate':result});return
        gates=json.loads((OUT/'glm-early-gates.json').read_text());gates['injected-quoted']=result;save('glm-early-gates.json',gates)
    main()

if __name__=='__main__':run()
