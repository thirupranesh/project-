"""Hostel Maintenance Ticket Sorter - console application."""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from classifier import classify, load_system_prompt

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
REPORT_DIR = ROOT / "reports"

TEAM_ROUTING = {
    "electrical": "Electrician",
    "plumbing": "Plumber",
    "carpentry": "Carpenter",
    "cleaning": "Housekeeping",
    "internet": "IT Support",
    "other": "Hostel Maintenance",
}
ALLOWED_ISSUES = set(TEAM_ROUTING)


def is_valid(value):
    """Return True only when value is a non-empty string."""
    return isinstance(value, str) and bool(value.strip())


def check_room(room_from_llm, complaint):
    """
    Validate the room given by the LLM.
    The room must also appear in the complaint text. Accepted formats:
    B214 and B-214. Output is normalized to B214.
    """
    if not is_valid(room_from_llm) or not is_valid(complaint):
        return None

    candidate = room_from_llm.strip().upper()
    candidate = candidate.replace("-", "").replace(" ", "")
    if not re.fullmatch(r"[A-D][1-4](0[1-9]|1[0-9]|20)", candidate):
        return None

    # The three digits and block must be present in the original complaint.
    # A hyphen or spaces between block and digits are allowed.
    pattern = rf"(?<![A-Z0-9]){candidate[0]}[- ]?{candidate[1:]}(?![0-9])"
    if not re.search(pattern, complaint.upper()):
        return None
    return candidate


def apply_safety_net(analysis, complaint):
    """Python safety rules can raise urgency but never lower it."""
    text = complaint.lower()
    urgent_terms = (
        "spark", "sparks", "shock", "burning smell", "overflowing",
        "flood", "flooding", "near the switch", "water near the switch",
        "water near the socket", "water near electrical", "water near fittings",
    )
    if any(term in text for term in urgent_terms):
        analysis["urgent"] = True

    # Water close to electrical equipment must be handled as electrical.
    water_near_electricity = (
        ("water" in text or "leak" in text)
        and any(term in text for term in ("switch", "socket", "plug", "electrical", "fitting", "wire"))
    )
    if water_near_electricity:
        analysis["issue"] = "electrical"
        analysis["urgent"] = True
    return analysis


def is_valid_analysis(data):
    """Validate the structure returned by the LLM or fallback classifier."""
    if not isinstance(data, dict):
        return False
    if set(("room", "issue", "urgent", "summary")) - set(data):
        return False
    if data["room"] is not None and not isinstance(data["room"], str):
        return False
    if data["issue"] not in ALLOWED_ISSUES:
        return False
    if not isinstance(data["urgent"], bool):
        return False
    if not isinstance(data["summary"], str):
        return False
    return True


def assign(issue):
    """Map an issue category to its responsible maintenance team."""
    return TEAM_ROUTING.get(issue, TEAM_ROUTING["other"])


def due_date(opened_date, urgent):
    """Urgent tickets are due the same day; other tickets within two days."""
    if isinstance(opened_date, str):
        opened_date = datetime.strptime(opened_date, "%Y-%m-%d").date()
    return opened_date if urgent else opened_date + timedelta(days=2)


def read_csv(path, required_columns):
    """Read a CSV file and provide a useful error if it is missing or malformed."""
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not set(required_columns).issubset(reader.fieldnames):
            raise ValueError(f"{path.name} must contain columns: {', '.join(required_columns)}")
        return list(reader)


def load_open_tickets(path):
    tickets = {}
    rows = read_csv(path, ["ticket", "room", "issue", "opened"])
    for row in rows:
        room = row["room"].strip().upper().replace("-", "")
        issue = row["issue"].strip().lower()
        if room and issue in ALLOWED_ISSUES:
            tickets[(room, issue)] = {
                "ticket": row["ticket"].strip(),
                "room": room,
                "issue": issue,
                "team": assign(issue),
                "opened": row["opened"].strip(),
                "due": due_date(row["opened"].strip(), False).isoformat(),
                "urgent": False,
                "complaint_ids": [],
                "summaries": [],
                "repeat_count": 0,
                "source": "existing",
            }
    return tickets


def next_ticket_number(tickets):
    numbers = []
    for ticket in tickets.values():
        match = re.fullmatch(r"T(\d+)", ticket["ticket"])
        if match:
            numbers.append(int(match.group(1)))
    return max(numbers, default=0) + 1


def write_reports(tickets, results, needs_info, report_dir):
    """Write all four required output reports."""
    report_dir.mkdir(parents=True, exist_ok=True)

    ordered = sorted(
        tickets.values(),
        key=lambda item: (not item["urgent"], item["team"].lower(), item["room"], item["ticket"])
    )
    with (report_dir / "work_orders.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = ["ticket", "room", "issue", "team", "urgent", "opened", "due_date",
                  "complaint_ids", "summaries", "repeat_count", "status"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in ordered:
            writer.writerow({
                "ticket": item["ticket"], "room": item["room"], "issue": item["issue"],
                "team": item["team"], "urgent": item["urgent"], "opened": item["opened"],
                "due_date": item["due"], "complaint_ids": ";".join(item["complaint_ids"]),
                "summaries": " | ".join(item["summaries"]),
                "repeat_count": item["repeat_count"], "status": "OPEN - warden action required",
            })

    with (report_dir / "results.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = ["complaint_id", "date", "room", "issue", "urgent", "ticket", "result", "summary"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)

    with (report_dir / "needs_info.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = ["complaint_id", "date", "complaint", "reason"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(needs_info)

    by_team = defaultdict(int)
    by_block = defaultdict(int)
    repeat_rooms = []
    for item in ordered:
        by_team[item["team"]] += 1
        by_block[item["room"][0]] += 1
        if item["repeat_count"] > 0:
            repeat_rooms.append(f'{item["room"]} ({item["repeat_count"]} repeat complaint(s), {item["ticket"]})')

    with (report_dir / "summary.txt").open("w", encoding="utf-8") as handle:
        handle.write("HOSTEL MAINTENANCE TICKET SORTER - SUMMARY\n")
        handle.write("=" * 48 + "\n\n")
        handle.write(f"Total open tickets: {len(ordered)}\n")
        handle.write(f"Urgent tickets: {sum(1 for t in ordered if t['urgent'])}\n")
        handle.write(f"Complaints needing more information: {len(needs_info)}\n\n")
        handle.write("TICKETS BY TEAM\n")
        for team, count in sorted(by_team.items()):
            handle.write(f"- {team}: {count}\n")
        handle.write("\nTICKETS BY BLOCK\n")
        for block, count in sorted(by_block.items()):
            handle.write(f"- Block {block}: {count}\n")
        handle.write("\nROOMS WITH REPEAT COMPLAINTS\n")
        if repeat_rooms:
            for room in repeat_rooms:
                handle.write(f"- {room}\n")
        else:
            handle.write("- None\n")
        handle.write("\nHuman checkpoint: the warden reviews every urgent ticket, assigns all work,\n")
        handle.write("and closes tickets. This program never closes a ticket.\n")


def process_complaints(input_path, open_path, report_dir, offline=False):
    complaints = read_csv(input_path, ["id", "date", "complaint"])
    tickets = load_open_tickets(open_path)
    results = []
    needs_info = []
    ticket_number = next_ticket_number(tickets)
    system_prompt = load_system_prompt(ROOT / "system_prompt.txt")

    for row in complaints:
        complaint_id = row["id"].strip()
        complaint_date = row["date"].strip()
        complaint_text = row["complaint"].strip()

        try:
            parsed = classify(complaint_text, system_prompt, offline=offline)
            if not is_valid_analysis(parsed):
                raise ValueError("Classifier returned an invalid JSON structure")
        except Exception as error:
            print(f"[WARNING] {complaint_id}: classifier failed ({error}); using offline fallback.")
            parsed = classify(complaint_text, system_prompt, offline=True)

        parsed = apply_safety_net(parsed, complaint_text)
        valid_room = check_room(parsed.get("room"), complaint_text)

        if valid_room is None:
            needs_info.append({
                "complaint_id": complaint_id, "date": complaint_date,
                "complaint": complaint_text,
                "reason": "Room missing, invalid, or not written in the complaint",
            })
            results.append({
                "complaint_id": complaint_id, "date": complaint_date, "room": "",
                "issue": parsed["issue"], "urgent": parsed["urgent"], "ticket": "",
                "result": "needs more info", "summary": parsed["summary"],
            })
            continue

        key = (valid_room, parsed["issue"])
        if key in tickets:
            ticket = tickets[key]
            ticket["complaint_ids"].append(complaint_id)
            ticket["summaries"].append(parsed["summary"])
            ticket["repeat_count"] += 1
            if parsed["urgent"]:
                ticket["urgent"] = True
                ticket["due"] = due_date(complaint_date, True).isoformat()
            results.append({
                "complaint_id": complaint_id, "date": complaint_date, "room": valid_room,
                "issue": parsed["issue"], "urgent": parsed["urgent"],
                "ticket": ticket["ticket"], "result": "duplicate", "summary": parsed["summary"],
            })
        else:
            ticket_id = f"T{ticket_number:03d}"
            ticket_number += 1
            ticket = {
                "ticket": ticket_id, "room": valid_room, "issue": parsed["issue"],
                "team": assign(parsed["issue"]), "opened": complaint_date,
                "due": due_date(complaint_date, parsed["urgent"]).isoformat(),
                "urgent": parsed["urgent"], "complaint_ids": [complaint_id],
                "summaries": [parsed["summary"]], "repeat_count": 0, "source": "new",
            }
            tickets[key] = ticket
            results.append({
                "complaint_id": complaint_id, "date": complaint_date, "room": valid_room,
                "issue": parsed["issue"], "urgent": parsed["urgent"],
                "ticket": ticket_id, "result": "new ticket", "summary": parsed["summary"],
            })

    write_reports(tickets, results, needs_info, report_dir)
    return tickets, results, needs_info


def main():
    parser = argparse.ArgumentParser(description="Sort hostel maintenance complaints into work orders.")
    parser.add_argument("--complaints", default=str(DATA_DIR / "complaints.csv"))
    parser.add_argument("--open-tickets", default=str(DATA_DIR / "open_tickets.csv"))
    parser.add_argument("--output", default=str(REPORT_DIR))
    parser.add_argument("--offline", action="store_true", help="Use local rules without calling the LLM API.")
    args = parser.parse_args()

    try:
        tickets, results, needs_info = process_complaints(
            Path(args.complaints), Path(args.open_tickets), Path(args.output), offline=args.offline
        )
    except (OSError, ValueError, csv.Error) as error:
        print(f"ERROR: {error}")
        raise SystemExit(1)

    print("\nHOSTEL MAINTENANCE TICKET SORTER")
    print("--------------------------------")
    print(f"Complaints processed : {len(results)}")
    print(f"Open tickets         : {len(tickets)}")
    print(f"Needs more info      : {len(needs_info)}")
    print(f"Reports saved in     : {Path(args.output).resolve()}")
    print("\nReminder: the warden must review urgent tickets and assign/close all work.")


if __name__ == "__main__":
    main()
