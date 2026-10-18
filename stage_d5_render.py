"""Render generated insertions into the actual selected host spans, pre-review."""
import json
from stage_d5_protocol import OUT,read,write_rows,save,sha
from stage_d5_data import insert

def main():
    if not (OUT/'generation.json').exists():raise ValueError('Generation is not finished')
    if (OUT/'injected-votes.jsonl').exists():raise ValueError('Cannot alter already reviewed constructions')
    plans={r['id']:r for r in read(OUT/'injection-plan.jsonl')};original=OUT/'injected-generated.jsonl'
    if original.exists():raise ValueError('Rendering already performed')
    (OUT/'injected.jsonl').replace(original);rows=read(original)
    rebuilt=[insert(plans[r['id']],r['insertion']) for r in rows]
    write_rows('injected.jsonl',rebuilt)
    save('injection-render.json',{'input_n':len(rows),'output_n':len(rebuilt),'changed_text_n':sum(a['raw_text']!=b['raw_text'] for a,b in zip(rows,rebuilt)),'generated_insertion_unchanged':all(a['insertion']==b['insertion'] for a,b in zip(rows,rebuilt)),'reason':'Use the selected raw host slice; do not silently expand to an unsliced original tool description. Fixed before teacher review or model inference.','original_sha256':sha(original),'rendered_sha256':sha(OUT/'injected.jsonl')})
    print((OUT/'injection-render.json').read_text())

if __name__=='__main__':main()
