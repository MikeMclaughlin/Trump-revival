"""Power & fusion layer: federal awards since Jan 20, 2025 (USAspending) + official DOE announcements not yet obligated."""
import json, re, glob, requests, pandas as pd, concurrent.futures as cf, os
R="/workspace/us-mfg-map/raw/"; P=R+"power/"; D="/workspace/us-mfg-map/data/"
END="2026-10-21"
recs={}
def add(f,kind):
    for x in json.load(open(P+f)): x["_kind"]=kind; recs.setdefault(x["generated_internal_id"],x)
for f in ["fusion_grants.json","g_81049_fusion.json","g_81135.json","cfda_81121.json","cfda_81254.json","cfda_81087.json","cfda_81089.json","g_doe_all.json"]: add(f,"grant")
for f in ["c_doe_kw.json","c_all_microreactor.json"]: add(f,"contract")
for f in ["l_doe.json","l_rus.json"]: add(f,"loan")
FUS=re.compile(r"\bFUSION\b(?! SPLICER)|TOKAMAK|STELLARATOR|FIRE COLLABORATIVE|INERTIAL CONFINEMENT|\bIFE\b|SPARC|PLASMA[- ]FACING|BREEDING BLANKET|\bINFUSE\b",re.I)
FIS=re.compile(r"NUCLEAR|MICROREACTOR|\bSMR\b|HALEU|URANIUM|ENRICHMENT|\bLEU\b|FISSION",re.I)
GRID=re.compile(r"TRANSMISSION|\bGRID\b|SUBSTATION|DISTRIBUTION LINE|LONG-DURATION ENERGY STORAGE|\bLDES\b|MICROGRID",re.I)
GEO=re.compile(r"GEOTHERMAL",re.I)
HYD=re.compile(r"HYDROPOWER|HYDROELECTRIC|WATER POWER|MARINE ENERGY|WAVE ENERGY|TIDAL|HYDROKINETIC|PUMPED STORAGE",re.I)
FOS=re.compile(r"POWER PLANT|COAL[- ]FIRED|COAL PLANT|GAS TURBINE|COMBUSTION TURBINE|TURBINE|COFIRING|CO-FIRING|ROTATING DETONATION|BOILER|GENERATING (STATION|UNIT)|POWER GENERATION",re.I)
OTH=re.compile(r"SOLAR|PHOTOVOLTAIC|WIND (ENERGY|TURBINE|POWER)|OFFSHORE WIND|BIOPOWER|POWER GENERATION|ELECTRICITY GENERATION",re.I)
EXCL=re.compile(r"FUSION WELDING|MAGNITO|NONPROLIFERATION|CRITICAL MINERAL|RARE EARTH|GRAPHITE|CARBON STORAGE|CARBON CAPTURE TEST CENTER|NAVAL REACTORS|INCURRED COST AUDIT|SPENT NUCLEAR FUEL|RADIOACTIVE WASTE|WASTE TRANSMUT|DARK MATTER|QUANTUM|WILDFIRE",re.I)
def classify(x):
    t=" ".join(str(x.get(k) or "") for k in ["Description","Recipient Name"]); cfda=x.get("CFDA Number") or ""
    if x["_kind"]=="loan":
        return "Federal power loans: DOE (LPO/EDF)" if cfda=="81.126" else "Federal power loans: USDA rural electric (RUS)"
    if EXCL.search(t) or cfda in ("81.117","81.086","81.041","81.042","81.128","81.119"): return None
    if FUS.search(t) and cfda in ("81.049","81.135","81.302",""): return "Fusion"
    if cfda in ("81.121","81.114") or FIS.search(t): return "Nuclear fission & fuel"
    if GEO.search(t): return "Geothermal"
    if HYD.search(t): return "Hydro & marine"
    if cfda in ("81.254","81.300","81.122") or GRID.search(t): return "Grid, transmission & storage"
    if FOS.search(t) and cfda in ("81.089",""): return "Coal & gas power"
    if OTH.search(t) and cfda in ("81.087","81.135","81.255","81.089",""): return "Other generation (solar, wind, etc.)"
    return None
cand={k:v for k,v in recs.items() if classify(v)}
print("candidates",len(cand))
cache=P+"details.json"; det=json.load(open(cache)) if os.path.exists(cache) else {}
def g(k):
    for _ in range(3):
        try:
            r=requests.get(f"https://api.usaspending.gov/api/v2/awards/{k}/",timeout=60)
            if r.status_code==200: return k,r.json()
        except Exception: pass
    return k,None
todo=[k for k in cand if k not in det]
with cf.ThreadPoolExecutor(6) as ex:
    for k,v in ex.map(g,todo): det[k]=v
json.dump(det,open(cache,"w"))
zc=pd.read_csv(R+"2024_Gaz_zcta_national.txt",sep="\t",dtype=str); zc.columns=[c.strip() for c in zc.columns]
zc=dict(zip(zc.GEOID,zip(zc.INTPTLAT.astype(float),zc.INTPTLONG.str.strip().astype(float))))
fips=pd.read_csv(R+"2024_Gaz_counties_national.txt",sep="\t",dtype=str); fips.columns=[c.strip() for c in fips.columns]
fips["key"]=fips.USPS+"|"+fips.NAME.str.upper().str.replace(r" (COUNTY|PARISH|BOROUGH|CITY AND BOROUGH|CENSUS AREA|MUNICIPALITY)$","",regex=True)
cty=dict(zip(fips.key,zip(fips.INTPTLAT.astype(float),fips.INTPTLONG.str.strip().astype(float))))
stc=fips.assign(lat=fips.INTPTLAT.astype(float),lon=fips.INTPTLONG.str.strip().astype(float),pop=fips.ALAND.astype(float)).groupby("USPS")[["lat","lon"]].mean().to_dict("index")
rows=[]
for k,x in cand.items():
    d=det.get(k) or {}; pop=d.get("place_of_performance") or {}; rl=((d.get("recipient") or {}).get("location") or {})
    cat=classify(x); loan=x["_kind"]=="loan"
    amt=x.get("Loan Value") if loan else (d.get("total_obligation") if d.get("total_obligation") is not None else x.get("Award Amount"))
    ds=d.get("date_signed") or x.get("Start Date") or x.get("Issued Date"); ps=(d.get("period_of_performance") or {}).get("start_date")
    st=pop.get("state_code"); ll=None; geo=None; state_for_total=st
    if pop.get("location_country_code") not in (None,"USA"): continue
    if pop.get("zip5") in zc: ll=zc[pop["zip5"]]; geo="Place-of-performance ZIP"
    elif pop.get("county_name") and st and f"{st}|{pop['county_name'].upper()}" in cty: ll=cty[f"{st}|{pop['county_name'].upper()}"]; geo="Place-of-performance county"
    elif rl.get("zip5") in zc: ll=zc[rl["zip5"]]; geo="Recipient ZIP (no place of performance given)"; st=st or rl.get("state_code"); state_for_total=st
    note=""
    rn=x["Recipient Name"]
    if rn.startswith("ANDP HOLDCO"):
        note="Westinghouse AP1000 long-lead items for up to 10 reactors at sites not yet named. Conditional commitment: DOE recorded it as obligated, but the loan has not closed (DOE/Westinghouse, Jun 23, 2026). Plotted at the recipient HQ; excluded from state totals."
        state_for_total=None; geo="Recipient HQ (multi-site, sites not named)"
    if rn.startswith("AEP TEXAS"):
        note="DOE: about 100 transmission projects across Texas (Jul 8, 2026). No place of performance in USAspending, so it is counted in TX and plotted at the Texas center."
        st="TX"; state_for_total="TX"; ll=(stc["TX"]["lat"],stc["TX"]["lon"]); geo="State center (statewide program)"
    if rn.startswith("CONSTELLATION"):
        note="USAspending lists a $3.0B face value, but DOE and Constellation's SEC 8-K (Nov 17-18, 2025) state a $1.0B loan. Both figures are shown; the DOE figure is used in totals."
    if rn.startswith(("GEORGIA POWER","ALABAMA POWER")):
        note="DOE: gas generation, nuclear uprates and license renewals, hydro modernization, storage and transmission (Feb 25, 2026)."
    if rn.startswith("SHINE"): note="Medical-isotope plant (fusion-based neutron source); not power generation. Conditional commitment."
    flag="Period of performance began before Jan 20, 2025 (first obligation after)" if (ps and ps<"2025-01-20") else ""
    if ds and ds<"2025-01-20": continue
    rows.append(dict(category=cat,status=("Loan face value (conditional commitment)" if loan and (rn.startswith(("ANDP","SHINE"))) else "Loan face value (closed)" if loan else "Obligated"),
        recipient=rn,program=(f"CFDA {x.get('CFDA Number')}" if x.get("CFDA Number") else "Contract")+(" · "+(x.get("Awarding Sub Agency") or "") if x.get("Awarding Sub Agency") else ""),
        agency=x.get("Awarding Agency"),amount=amt,amount_used_in_totals=(1.0e9 if rn.startswith("CONSTELLATION") else amt),
        subsidy_cost=x.get("Subsidy Cost") if loan else None,date=ds,period_start=ps,state=st,state_for_totals=state_for_total,
        lat=round(ll[0],4) if ll else None,lon=round(ll[1],4) if ll else None,geocode=geo,
        description=(x.get("Description") or "")[:300].replace("\n"," "),flag=flag,note=note,award_id=x.get("Award ID"),
        source="USAspending.gov",url=f"https://www.usaspending.gov/award/{k}"))
df=pd.DataFrame(rows)
# announced (official DOE), not found as obligated in USAspending as of retrieval
ann=[
 dict(category="Nuclear fission & fuel",recipient="Tennessee Valley Authority (BWRX-300, Clinch River)",program="DOE NE Gen III+ SMR program, Tier 1",amount=400e6,date="2025-12-02",state="TN",lat=35.889,lon=-84.385,url="https://www.energy.gov/articles/energy-department-selects-tva-and-holtec-advance-deployment-us-small-modular-reactors",note="Selected 'up to' amount; cost-shared"),
 dict(category="Nuclear fission & fuel",recipient="Holtec Government Services (2x SMR-300, Palisades site, Covert MI)",program="DOE NE Gen III+ SMR program, Tier 1",amount=400e6,date="2025-12-02",state="MI",lat=42.322,lon=-86.315,url="https://www.energy.gov/articles/energy-department-selects-tva-and-holtec-advance-deployment-us-small-modular-reactors",note="Selected 'up to' amount; cost-shared"),
 dict(category="Coal & gas power",recipient="AES Warrior Run (recommission 180 MW net coal plant, Cumberland MD)",program="DOE HGEO Restoring Reliability: Coal Recommissioning & Modernization (DE-FOA-0003605, Topic 1)",amount=78e6,date="2026 (DOE selection page is undated)",state="MD",lat=39.62,lon=-78.77,url="https://www.energy.gov/hgeo/project-selections-broad-agency-announcement-de-foa-0003605-restoring-reliability-coal-0",note="Selection; DOE share"),
 dict(category="Coal & gas power",recipient="Terra Energy Center Corp. (1,250 MW coal + CCUS design, Mat-Su Borough AK)",program="DOE HGEO Coal Recommissioning & Modernization (Topic 1)",amount=89e6,date="2026 (DOE selection page is undated)",state="AK",lat=61.58,lon=-149.44,url="https://www.energy.gov/hgeo/project-selections-broad-agency-announcement-de-foa-0003605-restoring-reliability-coal-0",note="Selection; DOE share; engineering/design phase"),
 dict(category="Coal & gas power",recipient="TerraSpark West Virginia Energy Campus (1,600 MW coal, Mt Storm WV)",program="DOE HGEO Coal Recommissioning & Modernization (Topic 1)",amount=18.5e6,date="2026 (DOE selection page is undated)",state="WV",lat=39.20,lon=-79.26,url="https://www.energy.gov/hgeo/project-selections-broad-agency-announcement-de-foa-0003605-restoring-reliability-coal-0",note="Selection; DOE share; FEED + initial design"),
 dict(category="Coal & gas power",recipient="AES Puerto Rico (510 MW coal plant modernization, Guayama PR)",program="DOE HGEO Coal Recommissioning & Modernization (Topic 1)",amount=164.5e6,date="2026 (DOE selection page is undated)",state="PR",lat=None,lon=None,url="https://www.energy.gov/hgeo/project-selections-broad-agency-announcement-de-foa-0003605-restoring-reliability-coal-0",note="Puerto Rico: not on the 50-state map"),
 dict(category="Coal & gas power",recipient="6 rural coal-plant modernization projects (WV x2, OH x2, NC, KY)",program="DOE coal modernization, $175M announcement",amount=175e6,date="2026-02-12",state="MULTI",lat=None,lon=None,url="https://netl.doe.gov/node/15267",note="Multi-site; DOE did not give per-project amounts in the announcement, so not mapped or assigned to states"),
 dict(category="Coal & gas power",recipient="13 coal plants + West Gateway export terminal (DPA Title III)",program="DOE Defense Production Act Title III coal selections",amount=500e6,date="2026-06-04",state="MULTI",lat=None,lon=None,url="https://www.energy.gov/hgeo/funding-defense-production-act-title-iii",note="'Up to' amount; multi-site, not mapped. $75M of it is for a coal export terminal"),
 dict(category="Fusion",recipient="FIRE Collaboratives (7 teams) + INFUSE (20 projects)",program="DOE Office of Science FES: FIRE $128M + INFUSE $6.1M",amount=134.1e6,date="2025-09-10",state="MULTI",lat=None,lon=None,url="https://www.energy.gov/articles/energy-department-announces-134-million-advance-us-fusion-leadership-through-targeted",note="Multi-year total (FIRE: $31M in FY2025 dollars, rest subject to appropriations). Some FIRE grants already appear as obligated USAspending awards above, so this figure partly overlaps them. Shown separately and never added to obligated totals"),
]
an=pd.DataFrame(ann).assign(status="Announced / selected, not yet obligated in USAspending",source="DOE announcement",amount_used_in_totals=lambda x:x.amount,state_for_totals=lambda x:x.state.where(~x.state.isin(["MULTI","PR"])))
out=pd.concat([df,an],ignore_index=True).sort_values(["status","amount"],ascending=[True,False])
out=out[out.amount>0]  # drop $0 records (de-obligated or placeholder)
out.to_csv(D+"layer6_power_fusion_awards.csv",index=False)
print(out.groupby(["status","category"]).agg(n=("amount","size"),total=("amount_used_in_totals","sum")).assign(total=lambda x:(x.total/1e6).round(1)))
print("no location:",out[out.lat.isna()][["recipient","state"]].to_string())
