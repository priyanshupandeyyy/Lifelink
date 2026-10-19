"""
menu.py - Interactive, user-friendly terminal menu for LifeLink.

The user picks a number and types details; PyMongo runs the queries.
No MongoDB queries need to be typed by the user.

    python menu.py

(Run `python main.py` once first so the database has data.)
"""
import re
import sys
from datetime import datetime, timedelta, timezone

from pymongo.errors import DuplicateKeyError, ServerSelectionTimeoutError, WriteError

import aggregations
from db import DB_NAME, MONGO_URI, get_db, show
from schema import BLOOD_GROUPS

URGENCY_ORDER = {"critical": 0, "high": 1, "normal": 2}


# ----------------------------------------------------------------- input helpers
def ask(prompt, required=True):
    while True:
        value = input(prompt).strip()
        if value or not required:
            return value
        print("  This field cannot be empty.")


def ask_int(prompt, lo, hi):
    while True:
        try:
            value = int(input(prompt).strip())
            if lo <= value <= hi:
                return value
        except ValueError:
            pass
        print(f"  Please enter a whole number between {lo} and {hi}.")


def ask_float(prompt, lo, hi):
    while True:
        try:
            value = float(input(prompt).strip())
            if lo <= value <= hi:
                return value
        except ValueError:
            pass
        print(f"  Please enter a number between {lo} and {hi}.")


def ask_choice(prompt, options):
    """Show numbered options, return the chosen option."""
    print(prompt)
    for i, opt in enumerate(options, start=1):
        print(f"  {i}. {opt}")
    return options[ask_int("Choose number: ", 1, len(options)) - 1]


def ask_blood_group(required=True):
    while True:
        value = ask(f"Blood group ({', '.join(BLOOD_GROUPS)}): ", required).upper()
        if not value or value in BLOOD_GROUPS:
            return value
        print("  Invalid blood group.")


def fmt_date(d):
    return d.strftime("%d-%b-%Y") if d else "-"


def print_donors(docs):
    if not docs:
        print("  (no donors found)")
        return
    print(f"  {'Name':<22}{'BG':<5}{'Age':<5}{'City':<12}{'Phone':<12}{'Avail':<7}{'Donations':<10}Last donated")
    print("  " + "-" * 88)
    for d in docs:
        print(f"  {d['name']:<22}{d['blood_group']:<5}{d['age']:<5}{d['city']:<12}"
              f"{d['phone']:<12}{'Yes' if d['is_available'] else 'No':<7}"
              f"{d['total_donations']:<10}{fmt_date(d.get('last_donation_date'))}")


def find_donor(db):
    phone = ask("Donor phone number: ")
    donor = db.donors.find_one({"phone": phone})
    if not donor:
        print("  No donor found with that phone number.")
    return donor


def choose_hospital(db):
    hospitals = list(db.hospitals.find().sort("name", 1))
    print("Hospitals:")
    for i, h in enumerate(hospitals, start=1):
        print(f"  {i}. {h['name']} ({h['city']})")
    return hospitals[ask_int("Choose hospital number: ", 1, len(hospitals)) - 1]


# --------------------------------------------------------------- DONOR: CRUD
def add_donor(db):
    print("\n-- Add new donor --")
    doc = {
        "name": ask("Full name: "),
        "blood_group": ask_blood_group(),
        "age": ask_int("Age (18-65): ", 18, 65),
        "gender": ask_choice("Gender:", ["Male", "Female", "Other"]),
        "phone": ask("Phone (10 digits, starts with 6-9): "),
        "city": ask("City: ").title(),
        "is_available": True,
        "total_donations": 0,
        "last_donation_date": None,
        "medical_conditions": [],
        "registered_on": datetime.now(timezone.utc),
    }
    email = ask("Email (optional, press Enter to skip): ", required=False)
    if email:
        doc["email"] = email
    try:
        db.donors.insert_one(doc)
        print("  Donor added successfully.")
    except DuplicateKeyError:
        print("  Rejected: a donor with this phone number already exists.")
    except WriteError:
        print("  Rejected by validation rules. Check: name length, phone must be 10 digits "
              "starting with 6-9, email format.")


def search_donors(db):
    print("\n-- Search donors (press Enter to skip a filter) --")
    query = {}
    bg = ask_blood_group(required=False)
    if bg:
        query["blood_group"] = bg
    city = ask("City: ", required=False)
    if city:
        query["city"] = {"$regex": f"^{re.escape(city)}$", "$options": "i"}
    if ask("Only available donors? (y/n): ", required=False).lower() == "y":
        query["is_available"] = True
    docs = list(db.donors.find(query).sort("name", 1).limit(50))
    print(f"\n  {len(docs)} donor(s) found (showing max 50)")
    print_donors(docs)


def update_donor(db):
    print("\n-- Update donor --")
    donor = find_donor(db)
    if not donor:
        return
    print_donors([donor])
    field = ask_choice("What do you want to update?",
                       ["Phone number", "City", "Availability (toggle)", "Add a medical condition"])
    if field == "Phone number":
        update = {"$set": {"phone": ask("New phone: ")}}
    elif field == "City":
        update = {"$set": {"city": ask("New city: ").title()}}
    elif field.startswith("Availability"):
        update = {"$set": {"is_available": not donor["is_available"]}}
    else:
        update = {"$addToSet": {"medical_conditions": ask("Condition: ")}}
    try:
        res = db.donors.update_one({"_id": donor["_id"]}, update)
        print("  Updated successfully." if res.modified_count else "  Nothing changed.")
    except DuplicateKeyError:
        print("  Rejected: that phone number belongs to another donor.")
    except WriteError:
        print("  Rejected by validation rules.")


def delete_donor(db):
    print("\n-- Delete donor --")
    donor = find_donor(db)
    if not donor:
        return
    print_donors([donor])
    if ask("Type YES to confirm deletion: ").upper() == "YES":
        db.donors.delete_one({"_id": donor["_id"]})
        print("  Donor deleted. (Their past donation records are kept for history.)")
    else:
        print("  Cancelled.")


# ------------------------------------------------------------------ DONATIONS
def record_donation(db):
    print("\n-- Record a donation --")
    donor = find_donor(db)
    if not donor:
        return
    now = datetime.now(timezone.utc)
    last = donor.get("last_donation_date")
    if last and (now - last).days < 90:
        wait = 90 - (now - last).days
        print(f"  Donor is not eligible yet. Last donated {fmt_date(last)}; "
              f"must wait {wait} more day(s).")
        return
    hospital = choose_hospital(db)
    hb = ask_float("Hemoglobin level (g/dL): ", 0, 30)
    if hb < 12.5:
        print("  Donation deferred: hemoglobin is below the 12.5 g/dL minimum.")
        return
    db.donations.insert_one({
        "donor_id": donor["_id"], "hospital_id": hospital["_id"],
        "blood_group": donor["blood_group"], "units": 1, "hemoglobin": round(hb, 1),
        "donation_date": now, "status": "completed"})
    db.donors.update_one({"_id": donor["_id"]}, {
        "$inc": {"total_donations": 1},
        "$set": {"last_donation_date": now, "is_available": False}})
    db.hospitals.update_one({"_id": hospital["_id"]},
                            {"$inc": {f"blood_stock.{donor['blood_group']}": 1}})
    print(f"  Donation recorded. {hospital['name']} stock of {donor['blood_group']} +1.")


# ------------------------------------------------------------------- REQUESTS
def raise_request(db):
    print("\n-- Raise a blood request --")
    hospital = choose_hospital(db)
    doc = {
        "hospital_id": hospital["_id"],
        "patient_name": ask("Patient name: "),
        "blood_group": ask_blood_group(),
        "units_needed": ask_int("Units needed (1-10): ", 1, 10),
        "urgency": ask_choice("Urgency:", ["critical", "high", "normal"]),
        "status": "open",
        "requested_on": datetime.now(timezone.utc),
    }
    try:
        db.requests.insert_one(doc)
        print("  Request created.")
    except WriteError:
        print("  Rejected by validation rules.")


def get_open_requests(db):
    reqs = list(db.requests.aggregate([
        {"$match": {"status": "open"}},
        {"$lookup": {"from": "hospitals", "localField": "hospital_id",
                     "foreignField": "_id", "as": "h"}},
        {"$unwind": "$h"},
    ]))
    reqs.sort(key=lambda r: (URGENCY_ORDER[r["urgency"]], r["requested_on"]))
    return reqs


def print_requests(reqs):
    if not reqs:
        print("  (no open requests)")
        return
    print(f"  {'#':<4}{'Urgency':<10}{'BG':<5}{'Units':<7}{'Patient':<22}{'Hospital':<38}Requested")
    print("  " + "-" * 96)
    for i, r in enumerate(reqs, start=1):
        print(f"  {i:<4}{r['urgency']:<10}{r['blood_group']:<5}{r['units_needed']:<7}"
              f"{r['patient_name']:<22}{r['h']['name']:<38}{fmt_date(r['requested_on'])}")


def view_open_requests(db):
    print("\n-- Open blood requests (most urgent first) --")
    print_requests(get_open_requests(db))


def fulfil_request(db):
    print("\n-- Fulfil a request --")
    reqs = get_open_requests(db)
    print_requests(reqs)
    if not reqs:
        return
    req = reqs[ask_int("Request number to fulfil: ", 1, len(reqs)) - 1]
    matches = list(db.donors.find(
        {"blood_group": req["blood_group"], "is_available": True, "city": req["h"]["city"]}
    ).limit(5))
    print(f"\n  Available {req['blood_group']} donors in {req['h']['city']} (up to 5):")
    print_donors(matches)
    if ask("\nMark this request as fulfilled? (y/n): ").lower() == "y":
        db.requests.update_one({"_id": req["_id"]},
                               {"$set": {"status": "fulfilled",
                                         "fulfilled_on": datetime.now(timezone.utc)}})
        print("  Request marked as fulfilled.")


# -------------------------------------------------------------------- REPORTS
def reports(db):
    print("\n-- Reports (aggregation pipelines) --")
    titles = [t for t, _, _ in aggregations.PIPELINES]
    for i, t in enumerate(titles, start=1):
        print(f"  {i:>2}. {t}")
    title, collection, build = aggregations.PIPELINES[ask_int("Choose report number: ", 1, len(titles)) - 1]
    show(title, list(db[collection].aggregate(build())))


# ----------------------------------------------------------------------- MAIN
MENU = [
    ("Add donor", add_donor),
    ("Search donors", search_donors),
    ("Update donor", update_donor),
    ("Delete donor", delete_donor),
    ("Record a donation", record_donation),
    ("Raise a blood request", raise_request),
    ("View open requests", view_open_requests),
    ("Fulfil a request", fulfil_request),
    ("Reports (aggregations)", reports),
]


def main():
    try:
        db = get_db()
    except ServerSelectionTimeoutError:
        sys.exit(f"Could not connect to MongoDB at {MONGO_URI}. Start MongoDB and try again.")
    if db.donors.count_documents({}) == 0 or db.hospitals.count_documents({}) == 0:
        sys.exit("The database is empty. Run `python main.py` first to create and seed it.")

    print(f"\nLifeLink - Blood Donation Management   (database: {DB_NAME})")
    while True:
        print("\n==================== MENU ====================")
        for i, (label, _) in enumerate(MENU, start=1):
            print(f"  {i}. {label}")
        print("  0. Exit")
        choice = ask_int("Enter your choice: ", 0, len(MENU))
        if choice == 0:
            print("Goodbye!")
            break
        try:
            MENU[choice - 1][1](db)
        except Exception as exc:          # keep the menu alive on unexpected errors
            print(f"  Something went wrong: {exc}")
        input("\nPress Enter to return to the menu...")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nGoodbye!")
