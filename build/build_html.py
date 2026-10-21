import json, pandas as pd, numpy as np
R="/workspace/us-mfg-map/raw/"; D="/workspace/us-mfg-map/data/"; O="/workspace/us-mfg-map/"
def clean(df):
    return json.loads(df.replace({np.nan:None}).to_json(orient="records"))
L1=pd.read_csv(D+"layer1_manufacturing_peak_vs_current.csv"); L1d=pd.read_csv(D+"layer1_manufacturing_by_decade.csv")
L2=pd.read_csv(D+"layer2_federal_awards_points.csv"); L3=pd.read_csv(D+"layer3_federal_obligations_by_state.csv")
L4=pd.read_csv(D+"layer4_senate_by_state_by_decade.csv"); L5=pd.read_csv(D+"layer5_house_by_state_by_decade.csv")
DATA=dict(L1=clean(L1),L1d=clean(L1d),L2=clean(L2),L3=clean(L3),L4=clean(L4),L5=clean(L5),L6=clean(pd.read_csv(D+"layer6_power_fusion_awards.csv")),
  states=json.load(open(R+"states.geojson")),cds=json.load(open(R+"cds.geojson")))
html=open("/workspace/us-mfg-map/build/template.html").read().replace("/*__DATA__*/null",json.dumps(DATA,separators=(",",":")))
open(O+"index.html","w").write(html); print(len(html)//1024,"KB")
