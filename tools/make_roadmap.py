"""Generated content/roadmap.json once. Edit content/roadmap.json directly (its sources were updated there after competitor references were removed)."""
#!/usr/bin/env python3
"""Generates content/roadmap.json (run once; edit roadmap.json directly afterwards)."""
import json, re
from pathlib import Path

CLUSTERS = {
    "planning": {"name": "Wedding planning", "cornerstone": 35, "goal": ["/wedding-planning", "Find wedding planners on Roko"], "cats": ["wedding-planning"]},
    "venues": {"name": "Wedding venues", "cornerstone": 16, "goal": ["/wedding-venues-and-accommodation", "Browse wedding venues on Roko"], "cats": ["wedding-venues-and-accommodation", "wedding-venues"]},
    "photography": {"name": "Wedding photography", "cornerstone": 59, "goal": ["/wedding-photographers", "Find wedding photographers on Roko"], "cats": ["wedding-photographers", "wedding-videographers"]},
    "destination": {"name": "Destination weddings", "cornerstone": 29, "goal": ["/wedding-destination-venues", "Explore destination venues on Roko"], "cats": ["wedding-destination-venues", "wedding-villas"]},
    "flowers-styling": {"name": "Flowers and styling", "cornerstone": 48, "goal": ["/wedding-flowers-and-decor", "Find florists and stylists on Roko"], "cats": ["wedding-flowers-and-decor"]},
    "catering": {"name": "Wedding catering", "cornerstone": 67, "goal": ["/wedding-caterers", "Find wedding caterers on Roko"], "cats": ["wedding-caterers", "wedding-catering-and-drinks"]},
    "entertainment": {"name": "Wedding entertainment", "cornerstone": 63, "goal": ["/wedding-entertainment", "Find wedding entertainment on Roko"], "cats": ["wedding-entertainment", "wedding-bands", "wedding-djs"]},
    "luxury": {"name": "Luxury weddings", "cornerstone": 78, "goal": ["/wedding-vendors", "Discover exceptional wedding businesses on Roko"], "cats": ["wedding-castles-and-estates", "wedding-planning"]},
    "private-events": {"name": "Private events", "cornerstone": 87, "goal": ["/wedding-parties-and-experiences", "Find party and event specialists on Roko"], "cats": ["wedding-parties-and-experiences", "wedding-private-chefs", "wedding-party-venues"]},
    "suppliers": {"name": "Wedding suppliers and professionals", "cornerstone": 94, "goal": ["/wedding-vendors", "Discover wedding suppliers on Roko"], "cats": ["wedding-vendors"]},
}

# n | title | cluster | type | keyword | categories (blank = cluster's) | refs | time-sensitive (y/n) | goal override
ROWS = """
1|Luxury wedding ideas for every budget|luxury|inspiration|luxury wedding ideas||bridebook_trends,pinterest_wedding_2026,bridebook_cost|n|
2|Wedding colour palettes that work in every season|flowers-styling|inspiration|wedding colour palettes|wedding-flowers-and-decor,wedding-stationery|pinterest_wedding_2026,bridebook_trends|n|
3|Autumn wedding ideas|flowers-styling|inspiration|autumn wedding ideas|wedding-flowers-and-decor|bridebook_trends,pinterest_wedding_2026|n|
4|Winter wedding ideas|flowers-styling|inspiration|winter wedding ideas|wedding-flowers-and-decor|bridebook_trends|n|
5|Wedding tablescape ideas|flowers-styling|inspiration|wedding tablescape ideas|wedding-flowers-and-decor,wedding-rentals-and-production|pinterest_wedding_2026,bridebook_trends|n|
6|Spring wedding ideas|flowers-styling|inspiration|spring wedding ideas|wedding-flowers-and-decor|bridebook_trends|n|
7|Summer wedding ideas|flowers-styling|inspiration|summer wedding ideas|wedding-flowers-and-decor,wedding-gardens-and-outdoor-venues|bridebook_trends|n|
8|Wedding lighting ideas|flowers-styling|inspiration|wedding lighting ideas|wedding-rentals-and-production|pinterest_wedding_2026|n|
9|Wedding ceremony backdrop ideas|flowers-styling|inspiration|wedding ceremony backdrop|wedding-flowers-and-decor,wedding-ceremony|pinterest_wedding_2026|n|
10|Wedding stationery ideas and etiquette|planning|guide|wedding stationery|wedding-stationery|bridebook_checklist|n|/wedding-stationery
11|Wedding dessert table ideas|catering|inspiration|wedding dessert table|wedding-desserts,wedding-cakes|bridebook_cake_cost|n|/wedding-desserts
12|Micro wedding ideas|planning|inspiration|micro wedding ideas|wedding-venues|ons_marriages_2024_2025,bridebook_cost|n|
13|Luxury wedding venues in the UK|venues|guide|luxury wedding venues UK|wedding-castles-and-estates,wedding-hotels-and-resorts,wedding-venues|bridebook_venue_cost,bridebook_report|y|/wedding-venues-and-accommodation/united-kingdom
14|Country house wedding venues|venues|guide|country house wedding venues|wedding-castles-and-estates|bridebook_venue_cost|y|/wedding-castles-and-estates
15|Barn wedding venues|venues|guide|barn wedding venues|wedding-barns-and-farms|bridebook_venue_cost|y|/wedding-barns-and-farms
16|How to choose a wedding venue: the complete guide|venues|cornerstone|how to choose a wedding venue||bridebook_venue_cost,bridebook_report,hitched_average,gov_marriage_uk|y|
17|Wedding venue costs in the UK|venues|guide|wedding venue costs UK||bridebook_venue_cost,bridebook_cost,hitched_cost_2026|y|
18|Castle wedding venues|venues|guide|castle wedding venues|wedding-castles-and-estates|bridebook_venue_cost|y|/wedding-castles-and-estates
19|Small wedding venues|venues|guide|small wedding venues|wedding-venues,wedding-restaurants|bridebook_venue_cost,ons_marriages_2024_2025|y|
20|Outdoor wedding venues|venues|guide|outdoor wedding venues|wedding-gardens-and-outdoor-venues|bridebook_venue_cost,gov_marriage_uk|y|/wedding-gardens-and-outdoor-venues
21|Exclusive-use wedding venues explained|venues|guide|exclusive use wedding venues|wedding-castles-and-estates,wedding-hotels-and-resorts|bridebook_venue_cost|y|
22|London wedding venues|venues|guide|London wedding venues|wedding-venues|bridebook_venue_cost|y|/wedding-venues/united-kingdom/london
23|Questions to ask a wedding venue|venues|guide|questions to ask a wedding venue||bridebook_venue_cost,bridebook_checklist|n|
24|Wedding venue contracts explained|venues|guide|wedding venue contract||bridebook_venue_cost|n|
25|The best destination wedding countries|destination|guide|best destination wedding countries||gov_marriage_abroad,bridebook_report,knot_cost|y|
26|Getting married in Italy|destination|guide|getting married in Italy|wedding-destination-venues,wedding-villas|gov_italy,gov_italy_nulla_osta,visititaly_weddings|y|/wedding-vendors/italy
27|Getting married in France|destination|guide|getting married in France|wedding-destination-venues|gov_france|y|/wedding-vendors/france
28|Getting married in Greece|destination|guide|getting married in Greece|wedding-destination-venues|gov_greece|y|/wedding-vendors/greece
29|Destination wedding guide|destination|cornerstone|destination wedding guide||gov_marriage_abroad,bridebook_report,knot_cost|y|
30|Getting married in Portugal|destination|guide|getting married in Portugal|wedding-destination-venues|gov_portugal|y|/wedding-vendors/portugal
31|Dubai wedding venues|destination|guide|Dubai wedding venues|wedding-hotels-and-resorts,wedding-venues|visitdubai_weddings,gov_uae|y|/wedding-venues-and-accommodation/united-arab-emirates/dubai
32|Getting married in Spain|destination|guide|getting married in Spain|wedding-destination-venues|gov_spain|y|/wedding-vendors/spain
33|Destination wedding costs|destination|guide|destination wedding cost||knot_cost,bridebook_report,gov_marriage_abroad|y|
34|Legal requirements for getting married abroad|destination|guide|legal requirements getting married abroad||gov_marriage_abroad,gov_italy,gov_france,gov_spain|y|
35|The complete wedding planning checklist|planning|cornerstone|wedding planning checklist||bridebook_checklist,knot_checklist,gov_marriage_uk,bridebook_cost|n|
36|UK wedding budget breakdown|planning|guide|UK wedding budget breakdown||bridebook_cost,hitched_cost_2026,hitched_average,bridebook_report|y|
37|When to book every wedding supplier|planning|guide|wedding supplier booking timeline|wedding-vendors|bridebook_checklist,knot_checklist|n|/wedding-vendors
38|How to choose a wedding photographer|photography|guide|choosing a wedding photographer|wedding-photographers|bridebook_photo_cost,knot_vendor_costs|n|/wedding-photographers
39|What does a wedding planner do?|suppliers|guide|what does a wedding planner do|wedding-planning|bridebook_planner_cost|n|/wedding-planning
40|How to write your wedding guest list|planning|guide|wedding guest list||bridebook_cost,hitched_average|n|
41|Questions to ask wedding suppliers before you book|suppliers|guide|questions to ask wedding suppliers|wedding-vendors|bridebook_checklist|n|/wedding-vendors
42|How to plan your wedding day timeline|planning|guide|wedding day timeline||bridebook_checklist|n|
43|How to plan a wedding in six months|planning|guide|plan a wedding in 6 months||bridebook_checklist,gov_marriage_uk|n|
44|Wedding insurance explained|planning|guide|wedding insurance||bridebook_cost|y|
45|Planning a multicultural wedding|planning|guide|multicultural wedding|wedding-ceremony,wedding-indian-catering|ons_marriages_2024_2025|n|
46|Wedding guest etiquette for couples and guests|planning|guide|wedding guest etiquette||hitched_average|n|
47|Wedding styling on any budget|flowers-styling|guide|wedding styling|wedding-flowers-and-decor|bridebook_flower_cost,bridebook_cost|y|
48|The complete guide to wedding flowers|flowers-styling|cornerstone|wedding flowers guide|wedding-flowers-and-decor|bridebook_flower_cost,pinterest_wedding_2026,bridebook_trends|y|
49|Seasonal wedding flowers in the UK|flowers-styling|guide|seasonal wedding flowers UK|wedding-flowers-and-decor|bridebook_flower_cost|n|
50|Wedding flower costs|flowers-styling|guide|wedding flower costs|wedding-flowers-and-decor|bridebook_flower_cost,knot_vendor_costs|y|
51|Bridal bouquet styles|flowers-styling|inspiration|bridal bouquet styles|wedding-flowers-and-decor|pinterest_wedding_2026|n|
52|Sustainable wedding flowers|flowers-styling|guide|sustainable wedding flowers|wedding-flowers-and-decor|bridebook_flower_cost|n|
53|Wedding centrepiece ideas|flowers-styling|inspiration|wedding centrepiece ideas|wedding-flowers-and-decor|pinterest_wedding_2026|n|
54|Wedding arch and floral installation ideas|flowers-styling|inspiration|wedding arch ideas|wedding-flowers-and-decor|pinterest_wedding_2026|n|
55|How to choose a wedding florist|flowers-styling|guide|choosing a wedding florist|wedding-flowers-and-decor|bridebook_flower_cost|n|
56|Dried and preserved wedding flowers|flowers-styling|inspiration|dried wedding flowers|wedding-flowers-and-decor|pinterest_wedding_2026|n|
57|Editorial vs documentary wedding photography|photography|guide|editorial vs documentary wedding photography|wedding-photographers|bridebook_photo_cost|n|/wedding-photographers
58|Wedding photographer costs|photography|guide|wedding photographer cost|wedding-photographers|bridebook_photo_cost,knot_vendor_costs|y|/wedding-photographers
59|The complete guide to wedding photography and film|photography|cornerstone|wedding photography guide|wedding-photographers,wedding-videographers|bridebook_photo_cost,bridebook_video_cost,knot_vendor_costs|y|/wedding-photographers
60|Wedding videography guide|photography|guide|wedding videographer|wedding-videographers|bridebook_video_cost|y|/wedding-videographers
61|Wedding photo shot list|photography|guide|wedding photo shot list|wedding-photographers|bridebook_photo_cost|n|/wedding-photographers
62|Wedding band or DJ: how to decide|entertainment|guide|wedding band vs DJ|wedding-bands,wedding-djs|bridebook_band_cost,bridebook_dj_cost,knot_vendor_costs|y|/wedding-entertainment
63|The complete guide to wedding entertainment|entertainment|cornerstone|wedding entertainment ideas|wedding-entertainment|bridebook_band_cost,bridebook_dj_cost|y|
64|Wedding ceremony music|entertainment|guide|wedding ceremony music|wedding-entertainment,wedding-ceremony|bridebook_band_cost|n|
65|Film wedding photography|photography|guide|film wedding photography|wedding-photographers|bridebook_photo_cost|n|/wedding-photographers
66|Engagement shoot guide|photography|guide|engagement shoot|wedding-engagement-and-pre-wedding-shoots|bridebook_photo_cost|n|/wedding-engagement-and-pre-wedding-shoots
67|The complete guide to wedding catering|catering|cornerstone|wedding catering guide|wedding-caterers|bridebook_catering_cost,knot_vendor_costs|y|
68|Wedding catering costs|catering|guide|wedding catering cost|wedding-caterers|bridebook_catering_cost,knot_vendor_costs|y|
69|Wedding menu ideas|catering|inspiration|wedding menu ideas|wedding-caterers|bridebook_catering_cost,pinterest_wedding_2026|n|
70|Wedding cake guide|catering|guide|wedding cake guide|wedding-cakes|bridebook_cake_cost|y|/wedding-cakes
71|Sharing, family-style or plated wedding menus|catering|guide|family style wedding menu|wedding-caterers|bridebook_catering_cost|n|
72|Wedding drinks and bar guide|catering|guide|wedding drinks guide|wedding-bars,wedding-mobile-bars,wedding-drinks-suppliers|bridebook_catering_cost|y|/wedding-bars
73|Late-night wedding food ideas|catering|inspiration|late night wedding food|wedding-late-night-food,wedding-food-trucks|bridebook_catering_cost|n|/wedding-late-night-food
74|Dietary requirements at weddings|catering|guide|wedding dietary requirements|wedding-caterers,wedding-gluten-free-and-allergy-catering|bridebook_catering_cost|n|
75|Luxury wedding trends for 2027|luxury|inspiration|luxury wedding trends 2027||bridebook_trends,pinterest_wedding_2026,bridebook_report|y|
76|What makes a wedding feel luxurious?|luxury|guide|what makes a wedding luxurious||bridebook_report,bridebook_cost|n|
77|The State of Weddings 2027|luxury|report|wedding industry report 2027||bridebook_report,hitched_cost_2026,knot_cost,ons_marriages_2024_2025,savills_weddings|y|
78|The luxury wedding guide|luxury|cornerstone|luxury wedding guide|wedding-planning,wedding-castles-and-estates|bridebook_report,bridebook_cost,bridebook_planner_cost|y|
79|Working with a luxury wedding planner|luxury|guide|luxury wedding planner|wedding-planning|bridebook_planner_cost|n|/wedding-planning
80|How to plan a luxury wedding budget|luxury|guide|luxury wedding budget||bridebook_cost,bridebook_report,knot_cost|y|
81|Luxury wedding stationery|luxury|inspiration|luxury wedding stationery|wedding-stationery|pinterest_wedding_2026|n|/wedding-stationery
82|Couture and designer wedding dresses|luxury|guide|designer wedding dresses|wedding-bridal-and-groom|bridebook_cost|n|/wedding-bridal-and-groom
83|Luxury honeymoon destinations|destination|inspiration|luxury honeymoon destinations||gov_marriage_abroad|y|
84|Wedding guest experience ideas|luxury|inspiration|wedding guest experience ideas|wedding-parties-and-experiences|pinterest_wedding_2026|n|
85|Luxury birthday party ideas|private-events|inspiration|luxury birthday party ideas|wedding-parties-and-experiences,wedding-party-venues||n|
86|How to plan a private dinner party|private-events|guide|private dinner party planning|wedding-private-chefs,wedding-caterers||n|/wedding-private-chefs
87|The complete guide to planning a private event|private-events|cornerstone|private event planning|wedding-parties-and-experiences,wedding-party-venues||n|
88|Engagement party ideas|private-events|inspiration|engagement party ideas|wedding-parties-and-experiences,wedding-party-venues||n|
89|Anniversary celebration ideas|private-events|inspiration|anniversary celebration ideas|wedding-parties-and-experiences||n|
90|How to choose a corporate event venue|private-events|guide|corporate event venues|wedding-corporate-and-conferences,wedding-conference-centres||y|/wedding-corporate-and-conferences
91|Hiring a private chef for an event|private-events|guide|hire a private chef|wedding-private-chefs||y|/wedding-private-chefs
92|Milestone birthday venues|private-events|guide|milestone birthday venues|wedding-party-venues,wedding-private-members-clubs||n|/wedding-party-venues
93|Meet the Makers|suppliers|feature|wedding suppliers interview|wedding-vendors||n|/list-your-business
94|Wedding suppliers: who you need and when to book them|suppliers|cornerstone|wedding suppliers list|wedding-vendors|bridebook_cost,knot_vendor_costs,bridebook_checklist|y|
95|Wedding hair and makeup guide|suppliers|guide|wedding hair and makeup|wedding-beauty|bridebook_hair_cost|y|/wedding-beauty
96|What a wedding stationer does|suppliers|guide|wedding stationer|wedding-stationery|bridebook_checklist|n|/wedding-stationery
97|How wedding suppliers price their services|suppliers|guide|wedding supplier pricing|wedding-vendors|bridebook_report,knot_vendor_costs|y|/list-your-business
98|Wedding industry insights from Roko|suppliers|research|wedding industry insights||bridebook_report,hitched_cost_2026,knot_cost|y|/list-your-business
99|UK wedding market snapshot|suppliers|research|UK wedding market||bridebook_report,ons_marriages_2024_2025,hitched_cost_2026|y|
100|What couples search for on Roko|suppliers|research|wedding search trends||bridebook_trends|y|
"""

# The first 90 days, in publishing order (from the editorial plan).
FIRST_90 = [35, 13, 1, 16, 38, 25, 36, 48, 75, 29, 39, 57, 17, 3, 67, 26, 5, 41, 2, 58, 85, 14, 62, 76, 37, 31, 69, 93, 77, 86]
WHY = {35: "Broad evergreen search", 13: "Direct directory relevance", 1: "Strong editorial introduction", 16: "High-intent planning",
       38: "Supplier discovery", 25: "International positioning", 36: "Practical search demand", 48: "Strong visual content",
       75: "Timely editorial", 29: "Destination cluster", 39: "Planner discovery", 57: "Specific search intent", 17: "Venue conversion",
       3: "Seasonal content", 67: "Caterer discovery", 26: "International SEO", 5: "Pinterest-friendly", 41: "Decision-stage content",
       2: "Evergreen inspiration", 58: "Commercial research", 85: "Expand beyond weddings", 14: "Venue cluster", 62: "Supplier comparison",
       76: "Brand positioning", 37: "Practical evergreen", 31: "International growth", 69: "Catering discovery", 93: "Vendor acquisition",
       77: "Original research", 86: "Broader event market"}


def slugify(s):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return re.sub(r"^(the|how-to)-", lambda m: m.group(0), s)[:70].strip("-")


items = []
for line in ROWS.strip().splitlines():
    n, title, cluster, typ, kw, cats, refs, ts, goal = line.split("|")
    n = int(n); c = CLUSTERS[cluster]
    slug = slugify(title.replace("?", "").replace(":", ""))
    if n == 93:
        slug = "meet-the-makers"
    g = goal.strip() or c["goal"][0]
    label = c["goal"][1] if not goal.strip() else ("List your business on Roko" if g == "/list-your-business" else "Discover " + kw.replace("wedding ", "").strip() + " on Roko")
    if g == "/list-your-business":
        gtype = "register"
    elif g.startswith("/vendors/"):
        gtype = "vendor"
    else:
        gtype = "category"
    week = FIRST_90.index(n) // 3 + 1 if n in FIRST_90 else None
    if n == 93: week = 10
    if n == 77: week = 11
    if n == 86: week = 12
    items.append({
        "n": n, "title": title, "slug": slug, "cluster": cluster, "type": typ,
        "cornerstone": c["cornerstone"] == n, "keyword": kw,
        "categories": [x for x in (cats.split(",") if cats else c["cats"]) if x],
        "refs": [r for r in refs.split(",") if r], "time_sensitive": ts == "y",
        "goal": {"type": gtype, "url": g, "label": label},
        "priority": FIRST_90.index(n) + 1 if n in FIRST_90 else None, "week": week, "why": WHY.get(n, ""),
    })

out = {"clusters": {k: {"name": v["name"], "cornerstone": v["cornerstone"]} for k, v in CLUSTERS.items()},
       "first_90_days": FIRST_90, "items": items}
Path(__file__).resolve().parent.parent.joinpath("content", "roadmap.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
print(len(items), "items")
