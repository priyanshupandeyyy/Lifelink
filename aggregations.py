"""
aggregations.py - Ten aggregation pipelines answering real blood-bank questions.

Each pipeline is a function returning a list of stages, so it can be printed,
explained and modified easily during the viva.
Stages/operators covered: $match $group $project $sort $limit $lookup $unwind
$bucket $facet $objectToArray $dateToString $cond $round $avg $sum $max
"""
from datetime import datetime, timedelta, timezone

from db import show


def p1_donors_by_blood_group():
    """How many donors per blood group, their average age and how many are available?"""
    return [
        {"$group": {"_id": "$blood_group", "donors": {"$sum": 1},
                    "avg_age": {"$avg": "$age"},
                    "available": {"$sum": {"$cond": ["$is_available", 1, 0]}}}},
        {"$project": {"_id": 0, "blood_group": "$_id", "donors": 1, "available": 1,
                      "avg_age": {"$round": ["$avg_age", 1]}}},
        {"$sort": {"donors": -1}},
    ]


def p2_units_per_hospital():
    """Which hospitals collect the most blood? (group + $lookup join + $unwind)"""
    return [
        {"$match": {"status": "completed"}},
        {"$group": {"_id": "$hospital_id", "units": {"$sum": "$units"},
                    "donations": {"$sum": 1}, "avg_hb": {"$avg": "$hemoglobin"}}},
        {"$lookup": {"from": "hospitals", "localField": "_id",
                     "foreignField": "_id", "as": "h"}},
        {"$unwind": "$h"},
        {"$project": {"_id": 0, "hospital": "$h.name", "city": "$h.city", "units": 1,
                      "donations": 1, "avg_hemoglobin": {"$round": ["$avg_hb", 2]}}},
        {"$sort": {"units": -1}},
    ]


def p3_monthly_trend():
    """Units collected per month (time-series style grouping)."""
    return [
        {"$match": {"status": "completed"}},
        {"$group": {"_id": {"$dateToString": {"format": "%Y-%m", "date": "$donation_date"}},
                    "units": {"$sum": "$units"}}},
        {"$sort": {"_id": 1}},
        {"$project": {"_id": 0, "month": "$_id", "units": 1}},
    ]


def p4_top_donors():
    """Top 5 most frequent donors, joined with donor details."""
    return [
        {"$match": {"status": "completed"}},
        {"$group": {"_id": "$donor_id", "times": {"$sum": 1},
                    "last_donated": {"$max": "$donation_date"}}},
        {"$sort": {"times": -1, "last_donated": -1}},
        {"$limit": 5},
        {"$lookup": {"from": "donors", "localField": "_id",
                     "foreignField": "_id", "as": "d"}},
        {"$unwind": "$d"},
        {"$project": {"_id": 0, "donor": "$d.name", "blood_group": "$d.blood_group",
                      "city": "$d.city", "times": 1, "last_donated": 1}},
    ]


def p5_demand_vs_supply():
    """Open demand per blood group vs. currently available donors (sub-pipeline $lookup)."""
    return [
        {"$match": {"status": "open"}},
        {"$group": {"_id": "$blood_group", "units_needed": {"$sum": "$units_needed"},
                    "open_requests": {"$sum": 1}}},
        {"$lookup": {
            "from": "donors",
            "let": {"bg": "$_id"},
            "pipeline": [
                {"$match": {"$expr": {"$eq": ["$blood_group", "$$bg"]},
                            "is_available": True}},
                {"$count": "n"}],
            "as": "avail"}},
        {"$project": {"_id": 0, "blood_group": "$_id", "units_needed": 1,
                      "open_requests": 1,
                      "available_donors": {"$ifNull": [{"$arrayElemAt": ["$avail.n", 0]}, 0]}}},
        {"$sort": {"units_needed": -1}},
    ]


def p6_age_distribution():
    """Donor age groups using $bucket."""
    return [
        {"$bucket": {"groupBy": "$age", "boundaries": [18, 26, 36, 46, 66],
                     "default": "other",
                     "output": {"donors": {"$sum": 1}, "avg_age": {"$avg": "$age"}}}},
    ]


def p7_stock_by_blood_group():
    """Total stock per blood group across all hospitals; scarcest first.
    $objectToArray turns the blood_stock sub-document into [{k, v}, ...]."""
    return [
        {"$project": {"stock": {"$objectToArray": "$blood_stock"}}},
        {"$unwind": "$stock"},
        {"$group": {"_id": "$stock.k", "units_in_stock": {"$sum": "$stock.v"}}},
        {"$sort": {"units_in_stock": 1}},
    ]


def p8_donor_dashboard():
    """Several summaries in ONE pass with $facet."""
    return [
        {"$facet": {
            "by_city": [{"$group": {"_id": "$city", "donors": {"$sum": 1}}},
                        {"$sort": {"donors": -1}}],
            "by_gender": [{"$group": {"_id": "$gender", "donors": {"$sum": 1}}}],
            "totals": [{"$group": {"_id": None, "donors": {"$sum": 1},
                                   "lifetime_donations": {"$sum": "$total_donations"}}}],
        }},
    ]


def p9_fulfilment_time():
    """Average hours to fulfil a request, by urgency."""
    return [
        {"$match": {"status": "fulfilled"}},
        {"$group": {"_id": "$urgency", "requests": {"$sum": 1},
                    "avg_hours": {"$avg": {"$divide": [
                        {"$subtract": ["$fulfilled_on", "$requested_on"]}, 3600000]}}}},
        {"$project": {"_id": 0, "urgency": "$_id", "requests": 1,
                      "avg_hours": {"$round": ["$avg_hours", 1]}}},
        {"$sort": {"avg_hours": 1}},
    ]


def p10_eligible_by_city():
    """Donors eligible to donate today (90+ days since last donation), by city."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    return [
        {"$match": {"$or": [{"last_donation_date": None},
                            {"last_donation_date": {"$lte": cutoff}}]}},
        {"$group": {"_id": "$city", "eligible": {"$sum": 1},
                    "groups": {"$addToSet": "$blood_group"}}},
        {"$sort": {"eligible": -1}},
    ]


PIPELINES = [
    ("1. Donors per blood group", "donors", p1_donors_by_blood_group),
    ("2. Blood collected per hospital", "donations", p2_units_per_hospital),
    ("3. Monthly donation trend", "donations", p3_monthly_trend),
    ("4. Top 5 donors", "donations", p4_top_donors),
    ("5. Open demand vs available donors", "requests", p5_demand_vs_supply),
    ("6. Donor age distribution", "donors", p6_age_distribution),
    ("7. Total stock per blood group", "hospitals", p7_stock_by_blood_group),
    ("8. Donor dashboard ($facet)", "donors", p8_donor_dashboard),
    ("9. Avg fulfilment time by urgency", "requests", p9_fulfilment_time),
    ("10. Eligible donors by city", "donors", p10_eligible_by_city),
]


def run_all(db):
    print("\n=== AGGREGATION PIPELINES ===")
    for title, collection, build in PIPELINES:
        show(f"{title}  [{collection}]", list(db[collection].aggregate(build())))
