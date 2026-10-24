import json, pandas as pd, numpy as np
R="/workspace/us-mfg-map/raw/"; D="/workspace/us-mfg-map/data/"; O="/workspace/us-mfg-map/"
def clean(df):
    return json.loads(df.replace({np.nan:None}).to_json(orient="records"))
L2=pd.read_csv(D+"layer2_federal_awards_points.csv",dtype={"pop_zip5":str,"naics":str}); L3=pd.read_csv(D+"layer3_federal_obligations_by_state.csv")
DATA=dict(L2=clean(L2),L3=clean(L3),L6=clean(pd.read_csv(D+"layer6_power_fusion_awards.csv")),
  states=json.load(open(R+"states.geojson")))
html=open("/workspace/us-mfg-map/build/template.html").read().replace("/*__DATA__*/null",json.dumps(DATA,separators=(",",":")))
open(O+"index.html","w").write(html); print(len(html)//1024,"KB")
