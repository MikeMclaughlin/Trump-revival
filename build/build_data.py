import json, re, pandas as pd, numpy as np
R="/workspace/us-mfg-map/raw/"; D="/workspace/us-mfg-map/data/"
RET="2026-10-21"
fips=pd.read_csv(R+"2024_Gaz_counties_national.txt",sep="\t",dtype=str)
fips.columns=[c.strip() for c in fips.columns]
st_fips=fips.assign(sf=fips.GEOID.str[:2])[["USPS","sf"]].drop_duplicates().set_index("sf").USPS.to_dict()
# state names from census pop
pop=pd.read_csv(R+"pop2025.csv",dtype={"STATE":str})
pop=pop[pop.SUMLEV==40]
pop["usps"]=pop.STATE.map(st_fips)
names=dict(zip(pop.usps,pop.NAME))
STATES=sorted(k for k in names if k!="PR")  # 50 + DC
print(len(STATES))
# ---------------- Layer 3: spending by state ----------------
pop_now=dict(zip(pop.usps,pop.POPESTIMATE2025))
pop_base2020=dict(zip(pop.usps,pop.ESTIMATESBASE2020))
periods={"trump2":("2025-01-20",RET,pop_now,"Census Vintage 2025 (July 1, 2025) estimate"),
         "2020pre":("2020-01-01","2025-01-19",pop_base2020,"Census April 1, 2020 estimates base")}
sp=[]
for per,(s0,s1,pp,pl) in periods.items():
    months=(pd.Timestamp(s1)-pd.Timestamp(s0)).days/30.4375
    vals={}
    for g in ["contracts","grants"] + (["all"] if per=="trump2" else []):
        f=R+(f"geo_{g}.json" if per=="trump2" else f"geo_{g}_{per}.json")
        for x in json.load(open(f))["results"]: vals.setdefault(x["shape_code"],{})[g]=x["aggregated_amount"] or 0.0
    for s in STATES:
        v=vals.get(s,{})
        c,gr=v.get("contracts"),v.get("grants")
        cg=(c or 0)+(gr or 0) if (c is not None or gr is not None) else None
        sp.append(dict(state=s,name=names[s],period=per,start=s0,end=s1,months=round(months,2),contracts=c,grants=gr,contracts_plus_grants=cg,
            all_award_types=v.get("all"),population=pp.get(s),population_source=pl,
            per_capita_contracts_plus_grants=round(cg/pp[s],2) if cg is not None else None,
            per_capita_all=round(v["all"]/pp[s],2) if v.get("all") is not None else None,
            monthly_rate_contracts_plus_grants=round(cg/months) if cg is not None else None))
    terr=[k for k in vals if k not in STATES]
    print(per,"territories/other excluded:",terr, {k:round(sum(vals[k].values())/1e9,2) for k in terr})
L3=pd.DataFrame(sp); L3.to_csv(D+"layer3_federal_obligations_by_state.csv",index=False)
for per in periods: 
    x=L3[L3.period==per]; print(per, "c+g $B",round(x.contracts_plus_grants.sum()/1e9,1), "missing",x.contracts_plus_grants.isna().sum())
# ---------------- Layer 2: awards ----------------
aw=json.load(open(R+"awards_2016.json")); det=json.load(open(R+"award_details_2016.json"))
_seen=set(); aw=[r for r in aw if not (r["generated_internal_id"] in _seen or _seen.add(r["generated_internal_id"]))]
def admin(dt):
    if not dt: return None
    return "Obama" if dt<"2017-01-20" else "Trump I" if dt<"2021-01-20" else "Biden" if dt<"2025-01-20" else "Trump II"
zc=pd.read_csv(R+"2024_Gaz_zcta_national.txt",sep="\t",dtype=str); zc.columns=[c.strip() for c in zc.columns]
zc=dict(zip(zc.GEOID,zip(zc.INTPTLAT.astype(float),zc.INTPTLONG.astype(float))))
fips["key"]=fips.USPS+"|"+fips.NAME.str.upper().str.replace(r" (COUNTY|PARISH|BOROUGH|CITY AND BOROUGH|CENSUS AREA|MUNICIPALITY)$","",regex=True)
cty=dict(zip(fips.key,zip(fips.INTPTLAT.astype(float),fips.INTPTLONG.str.strip().astype(float))))
pl=pd.read_csv(R+"2024_Gaz_place_national.txt",sep="\t",dtype=str); pl.columns=[c.strip() for c in pl.columns]
pl["key"]=pl.USPS+"|"+pl.NAME.str.upper().str.replace(r" (CITY|TOWN|VILLAGE|CDP|BOROUGH|MUNICIPALITY)$","",regex=True)
plc=dict(zip(pl.key,zip(pl.INTPTLAT.astype(float),pl.INTPTLONG.str.strip().astype(float))))
pts=[]; excl=[]
for r in aw:
    gid=r["generated_internal_id"]; d=det[gid]; pop_=d.get("place_of_performance") or {}
    ppos=(d.get("period_of_performance") or {}).get("start_date")
    rec=dict(award_id=r["Award ID"],category=r["_category"],recipient=r["Recipient Name"],agency=r["Awarding Agency"],sub_agency=r.get("Awarding Sub Agency"),
        amount_obligated=d.get("total_obligation"),date_signed=d.get("date_signed"),period_start=ppos,description=(r.get("Description") or "")[:300],
        naics=(r.get("NAICS") or {}).get("code") if isinstance(r.get("NAICS"),dict) else None,
        pop_city=pop_.get("city_name"),pop_county=pop_.get("county_name"),pop_state=pop_.get("state_code"),pop_zip5=pop_.get("zip5"),pop_country=pop_.get("location_country_code"),
        url=f"https://www.usaspending.gov/award/{gid}")
    if pop_.get("location_country_code") not in (None,"USA") or not pop_.get("state_code"):
        rec["excluded_reason"]="Place of performance outside the US"; excl.append(rec); continue
    rec["administration"]=admin(rec["date_signed"] or ppos)
    if ppos and ppos<"2016-01-01":
        rec["excluded_reason"]=f"Award period began {ppos}, before Jan 1, 2016"; excl.append(rec); continue
    ll=None; prec=None; st=pop_["state_code"]
    if pop_.get("zip5") and pop_["zip5"] in zc: ll=zc[pop_["zip5"]]; prec="ZIP centroid"
    elif pop_.get("county_name") and f"{st}|{pop_['county_name'].upper().replace(' (CITY)','')}" in cty: ll=cty[f"{st}|{pop_['county_name'].upper().replace(' (CITY)','')}"]; prec="County centroid"
    elif pop_.get("city_name") and f"{st}|{pop_['city_name'].upper()}" in plc: ll=plc[f"{st}|{pop_['city_name'].upper()}"]; prec="City centroid"
    else:
        rz=((d.get("recipient") or {}).get("location") or {}).get("zip5")
        if rz and rz in zc: ll=zc[rz]; prec="Recipient ZIP (no place-of-performance location given)"
    if ll is None: rec["excluded_reason"]="Could not geocode"; excl.append(rec); continue
    rec.update(lat=round(ll[0],4),lon=round(ll[1],4),geocode=prec); pts.append(rec)
L2=pd.DataFrame(pts).sort_values("amount_obligated",ascending=False); L2.to_csv(D+"layer2_federal_awards_points.csv",index=False)
pd.DataFrame(excl).to_csv(D+"layer2_awards_excluded.csv",index=False)
print("points",len(L2),"excluded",len(excl), L2.geocode.value_counts().to_dict(), "total $B",round(L2.amount_obligated.sum()/1e9,1))
print(pd.DataFrame(excl)[["recipient","excluded_reason"]].to_string())
