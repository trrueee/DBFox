import os
root_dirs=['.agent_eval/outputs','.agent_eval/results']
terms=['ORDER BY ARRAY','ORDER BY STRUCT']
found={t:[] for t in terms}
for rd in root_dirs:
    for dirpath,_,files in os.walk(rd):
        for name in files:
            fp=os.path.join(dirpath,name)
            try:
                s=open(fp,'r',encoding='utf-8',errors='ignore').read()
            except Exception:
                continue
            for t in terms:
                if t in s:
                    found[t].append(fp)
for t in terms:
    print(t+':', len(found[t]))
    for p in found[t][:20]:
        print('  ',p)
