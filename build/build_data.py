import json, re, pandas as pd, numpy as np, geopandas as gpd
from lxml import etree
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
# ---------------- Layer 1: manufacturing ----------------
def load(f):
    d=pd.read_csv(R+f,sep=r"\s+",header=None,names=["sid","year","period","value","fn"],engine="python",dtype={"sid":str})
    d["usps"]=d.sid.str[3:5].map(st_fips); return d
sm=load("sm_mfg.txt"); sa=load("sa_mfg.txt")
smA=sm[sm.period=="M13"]; saA=sa[sa.period=="M13"]
cm=pd.read_csv(R+"cm_wagejobs_transcribed.csv")
rows=[]; dec=[]
for s in STATES:
    a=saA[saA.usps==s].set_index("year").value*1000  # thousands -> persons
    n=smA[smA.usps==s].set_index("year").value*1000
    sic_start=int(a.index.min()); 
    # post-WWII peak: SIC 1946-1989, NAICS 1990-2025
    comb=pd.concat([a[(a.index>=1946)&(a.index<=1989)], n[(n.index>=1990)]])
    py=int(comb.idxmax()); pv=float(comb.max())
    m=sm[(sm.usps==s)&(sm.period!="M13")].copy(); m["mo"]=m.period.str[1:].astype(int)
    m=m.sort_values(["year","mo"]); last=m.iloc[-1]
    last12=m.iloc[-12:].value.mean()*1000
    lbl=f"{int(m.iloc[-12].year)}-{int(m.iloc[-12].mo):02d} to {int(last.year)}-{int(last.mo):02d}"
    flag=""
    if sic_start>1946: flag=f"SIC series starts {sic_start}; an earlier post-war peak ({'1946' if sic_start==1947 else '1946-'+str(sic_start-1)}) would not be captured"
    rows.append(dict(state=s,name=names[s],peak_year=py,peak_jobs=round(pv),peak_basis="BLS SIC (1946-1989)" if py<1990 else "BLS NAICS (1990-2025)",
        sic_series_start=sic_start,coverage_flag=flag,current_12mo_avg=round(last12),current_period=lbl,
        latest_month=f"{int(last.year)}-{int(last.mo):02d}",latest_month_nsa=round(last.value*1000),
        change_vs_peak=round(last12-pv),pct_change_vs_peak=round((last12-pv)/pv*100,1),
        naics_1990_jobs=round(n.get(1990,np.nan)),annual_2024=round(n.get(2024)),annual_2025=round(n.get(2025)),
        chg_2024_to_last12=round(last12-n.get(2024)), pct_2024_to_last12=round((last12-n.get(2024))/n.get(2024)*100,1)))
    c=cm[cm.state==s]
    for decade,yr in [(1900,"y1899"),(1910,"y1919"),(1920,"y1929")]:
        v=int(c[yr].iloc[0]) if len(c) else None
        dec.append(dict(state=s,decade=decade,value=v,basis=f"Census of Manufactures {yr[1:]} wage earners (avg for year)" if v is not None else "",
                        note="" if v is not None else "Not in Census table (not a state / no data)"))
    def davg(ser,lo,hi): x=ser[(ser.index>=lo)&(ser.index<=hi)]; return (round(x.mean()),f"{int(x.index.min())}-{int(x.index.max())}",len(x)) if len(x) else (None,"",0)
    v,rng,k=davg(a,1939,1939); dec.append(dict(state=s,decade=1930,value=v,basis="BLS SIC annual avg, 1939 only (series starts 1939)" if v else "",note="" if v else f"SIC series starts {sic_start}"))
    for d0 in [1940,1950,1960,1970,1980]:
        v,rng,k=davg(a,d0,d0+9)
        dec.append(dict(state=s,decade=d0,value=v,basis=f"BLS SIC annual avg, mean of {rng} ({k} yrs)" if v else "",
                        note=("partial decade: SIC series starts "+str(sic_start)) if v and k<10 else ("" if v else f"SIC series starts {sic_start}")))
    for d0 in [1990,2000,2010]:
        v,rng,k=davg(n,d0,d0+9); dec.append(dict(state=s,decade=d0,value=v,basis=f"BLS NAICS annual avg, mean of {rng}",note=""))
    dec.append(dict(state=s,decade=2020,value=round(last12),basis=f"BLS NAICS, latest 12-month avg ({lbl}, not seasonally adjusted)",note="Current"))
L1=pd.DataFrame(rows); L1d=pd.DataFrame(dec)
# national check: SIC sums
us_peak_check=saA.groupby("year").value.sum()*1000
L1.to_csv(D+"layer1_manufacturing_peak_vs_current.csv",index=False)
L1d.to_csv(D+"layer1_manufacturing_by_decade.csv",index=False)
print("L1 current total",L1.current_12mo_avg.sum(), "sum of state peaks",L1.peak_jobs.sum(), "SIC sum-of-states max year", us_peak_check.idxmax(), us_peak_check.max())
# ---------------- Layer 3: spending by state ----------------
pop_now=dict(zip(pop.usps,pop.POPESTIMATE2025))
pop_base2020=dict(zip(pop.usps,pop.ESTIMATESBASE2020))
ie=pd.read_csv(R+"st-est00int.csv",dtype={"STATE":str}); ie=ie[(ie.SEX==0)&(ie.ORIGIN==0)&(ie.RACE==0)&(ie.AGEGRP==0)&(ie.STATE!="00")]
pop2010=dict(zip(ie.STATE.map(st_fips),ie.CENSUS2010POP))
periods={"trump2":("2025-01-20",RET,pop_now,"Census Vintage 2025 (July 1, 2025) estimate"),
         "2020pre":("2020-01-01","2025-01-19",pop_base2020,"Census April 1, 2020 estimates base"),
         "2010s":("2010-01-01","2019-12-31",pop2010,"Census 2010 count"),
         "2000s":("2007-10-01","2009-12-31",pop2010,"Census 2010 count")}
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
aw=json.load(open(R+"awards.json")); det=json.load(open(R+"award_details.json"))
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
    if ppos and ppos<"2025-01-20":
        rec["excluded_reason"]=f"Award period began {ppos}, before Jan 20, 2025"; excl.append(rec); continue
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
# ---------------- Layer 4/5: Congress ----------------
sx=etree.parse(R+"senators.xml"); sen=[]
for m in sx.findall("member"):
    sen.append(dict(state=m.findtext("state"),name=f"{m.findtext('first_name').strip()} {m.findtext('last_name').strip()}",party=m.findtext("party"),cls=m.findtext("class")))
sen=pd.DataFrame(sen)
hx=etree.parse(R+"house.xml"); hs=[]
for m in hx.findall(".//members/member"):
    mi=m.find("member-info"); sd=m.findtext("statedistrict"); st=sd[:2]
    if st not in STATES or st=="DC": continue
    nm=(mi.findtext("official-name") or "").strip(); p=(mi.findtext("party") or "").strip()
    hs.append(dict(state=st,district=sd[2:],member=nm or "VACANT",party=p or "Vacant",caucus=(mi.findtext("caucus") or "").strip()))
hs=pd.DataFrame(hs); hs.to_csv(D+"layer5_house_current_members.csv",index=False)
print("house seats",len(hs),hs.party.value_counts().to_dict())
vv=pd.read_csv(R+"voteview_members.csv"); vp=pd.read_csv(R+"voteview_parties.csv")[["party_code","party_name"]].drop_duplicates("party_code")
pn=dict(zip(vp.party_code,vp.party_name))
def pabbr(code): return {100:"D",200:"R"}.get(code,"O")
CONG={1900:57,1910:62,1920:67,1930:72,1940:77,1950:82,1960:87,1970:92,1980:97,1990:102,2000:107,2010:112}
startyr={c:1789+2*(c-1) for c in CONG.values()}
s_rows=[]; h_rows=[]
for s in STATES:
    if s=="DC": continue
    x=sen[sen.state==s]
    nd=(x.party=="D").sum(); nr=(x.party=="R").sum(); ni=(x.party=="I").sum()
    s_rows.append(dict(state=s,decade=2020,congress=119,as_of=f"Senate.gov senators list retrieved {RET}",D=nd,R=nr,other=ni,vacant=2-len(x),
        members="; ".join(f"{a} ({b}, {c})" for a,b,c in zip(x.name,x.party,x.cls))))
    y=hs[hs.state==s]
    h_rows.append(dict(state=s,decade=2020,congress=119,as_of=f"Clerk MemberData.xml publish-date {hx.getroot().get('publish-date')}",D=(y.party=="D").sum(),R=(y.party=="R").sum(),
        other=(y.party=="I").sum(),vacant=(y.party=="Vacant").sum(),seats=len(y),members="; ".join(f"{d}: {m} ({p})" for d,m,p in zip(y.district,y.member,y.party))))
    for d0,c in CONG.items():
        for ch,rows_ in [("Senate",s_rows),("House",h_rows)]:
            z0=vv[(vv.congress==c)&(vv.chamber==ch)&(vv.state_abbrev==s)].copy(); z0["occ"]=z0.occupancy.fillna(0)
            if ch=="Senate": z=z0.sort_values("occ").head(2)
            else:
                parts=[]
                for dc,g in z0.groupby("district_code"):
                    k=max(1,int((g.occ==0).sum())) if dc>=98 else 1  # 98/99 = multi-member at-large (general ticket)
                    parts.append(g.sort_values("occ",kind="stable").head(k))
                z=pd.concat(parts) if parts else z0
            if len(z)==0:
                rows_.append(dict(state=s,decade=d0,congress=c,as_of=f"Voteview, {c}th Congress (convened {startyr[c]})",D=None,R=None,other=None,vacant=None,members="",note="No members: not yet a state, or no data")); continue
            oth=z[~z.party_code.isin([100,200])]
            row=dict(state=s,decade=d0,congress=c,as_of=f"Voteview, {c}th Congress (convened {startyr[c]}); first occupant of each seat",D=int((z.party_code==100).sum()),R=int((z.party_code==200).sum()),
                other=int(len(oth)),members="; ".join(f"{b.title() if isinstance(b,str) else b} ({pn.get(p,p)})" for b,p in zip(z.bioname,z.party_code)))
            if ch=="Senate": row["vacant"]=max(0,2-len(z)); row["note"]="Seat(s) with no Voteview member" if len(z)<2 else ""
            else: row["vacant"]=None; row["seats"]=len(z); row["note"]=""
            if len(oth): row["other_parties"]=", ".join(sorted(set(pn.get(p,str(p)) for p in oth.party_code)))
            rows_.append(row)
L4=pd.DataFrame(s_rows); L5=pd.DataFrame(h_rows)
L4.to_csv(D+"layer4_senate_by_state_by_decade.csv",index=False); L5.to_csv(D+"layer5_house_by_state_by_decade.csv",index=False)
for dd in [1900,1950,2010,2020]:
    a=L4[L4.decade==dd]; b=L5[L5.decade==dd]; print(dd,"Senate",a.D.sum(),a.R.sum(),a.other.sum(),"vac",a.vacant.sum(),"| House",b.D.sum(),b.R.sum(),b.other.sum(), "states w/o data",a.D.isna().sum())
print(L4[(L4.decade<2020)&(L4.note.fillna("")!="")&(L4.D.notna())][["state","decade","D","R","other","note"]].head(30).to_string())
json.dump(dict(names=names),open(R+"names.json","w"))
