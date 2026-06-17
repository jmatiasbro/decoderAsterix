import pickle
import sys
import os

cache_path = "C:/Users/Usuario/AppData/Local/Temp/75da1508b752f5da7ef1eb38cd2a8894.cache.pkl"
with open(cache_path, 'rb') as f:
    data = pickle.load(f)

plots = data.get('plots', [])
print(f"Total plots: {len(plots)}")
ids = [p.id for p in plots]
print(f"Unique ids: {len(set(ids))}")
if len(plots) > 0:
    print("First plot:", plots[0])
    # count duplicates of first plot
    matches = [p for p in plots if p.time == plots[0].time and p.lat == plots[0].lat and p.lon == plots[0].lon]
    print(f"Matches for first plot coordinates/time: {len(matches)}")
    for m in matches[:5]:
        print("  -", m.id, m.sac_sic, m.category)
