from math import ceil
from pprint import pprint
import requests
import matplotlib.pyplot as plt
import matplotlib.colors as pltc
from datetime import datetime, time
from functools import lru_cache

import hashlib


def name_to_color(name):
    # Hash the name using SHA256 (or any hash function)
    hash_object = hashlib.sha256(name.encode("utf-8"))
    hex_digest = hash_object.hexdigest()

    # Extract RGB components from the hash
    red = hex_digest[:2]  # First 2 hex digits
    green = hex_digest[2:4]  # Next 2 hex digits
    blue = hex_digest[4:6]  # Following 2 hex digits

    return f"#{red}{green}{blue}"


def generate_colormap_colors(num):
    colormap = plt.cm.get_cmap("tab20", num)  # Use 'tab20' or other colormaps
    return [
        (pltc.to_hex(colormap(i)), best_text_color([int(a * 255) for a in colormap(i)]))
        for i in range(num)
    ]


def calculate_luminance(color):
    # Convert RGB (0-255) to linear values (0-1)
    r, g, b = [x / 255.0 for x in color][:3]
    linear = lambda x: x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
    r, g, b = linear(r), linear(g), linear(b)
    # Calculate luminance
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def best_text_color(background_color):
    white = (255, 255, 255)
    black = (0, 0, 0)
    # Calculate contrast ratios
    background_luminance = calculate_luminance(background_color)
    white_contrast = (calculate_luminance(white) + 0.05) / (background_luminance + 0.05)
    black_contrast = (background_luminance + 0.05) / (calculate_luminance(black) + 0.05)
    # Return the color with higher contrast
    return "white" if white_contrast > black_contrast else "black"


base = "https://kos.cvut.cz/rest/api/"


class KOSApi:
    def __init__(self, password):
        self.s = requests.Session()
        self.s.get("https://kos.cvut.cz/rest/login")
        xsrf_token = self.s.cookies.get("XSRF-TOKEN")
        if xsrf_token:
            self.s.headers["X-XSRF-TOKEN"] = xsrf_token
        self.s.headers["Authorization"] = password
        login = self.s.get(
            "https://kos.cvut.cz/rest/api/me",
        )
        self.login_data = login.json()
        pprint(self.login_data)
        self.cached_courses = dict()

    def get_schedule_course(self, code: str, semester: str):
        try:
            res = self.s.get(
                base + "course-semesters",
                params={
                    "expanded": "semester",
                    "query": f"semesterId=={semester};code=={code}",
                    "size": 1,
                },
            ).json()
            elements = res.get("elements", [])
            if not elements:
                return []
            sid = elements[0].get("courseId")
            if not sid:
                return []
        except Exception:
            return []

        try:
            res_tt = self.s.get(
                base + "timetables/timetable-tickets",
                params={
                    "expanded": "parallelClass.teachers,parallelClass.parallelType,room",
                    "query": f"courseId=={sid};semesterId=={semester}",
                    "size": 0,
                },
            ).json()
            timetable = res_tt.get("elements", [])
        except Exception:
            return []

        out = []
        for ticket in timetable:
            try:
                p_class = ticket.get("parallelClass") or {}

                p_id_raw = p_class.get("id")
                p_code_raw = p_class.get("code") or p_class.get("number")

                p_type_obj = p_class.get("parallelType") or {}
                p_type = p_type_obj.get("code") or "P"

                p_id = (
                    str(p_id_raw)
                    if (p_id_raw is not None and p_id_raw != "")
                    else (str(p_code_raw) if p_code_raw else f"{code}_{p_type}")
                )
                p_code = str(p_code_raw) if p_code_raw else p_id

                teachers_list = p_class.get("teachers") or []
                teacher_names = []
                for t in teachers_list:
                    if isinstance(t, dict):
                        fname = t.get("firstName") or ""
                        lname = t.get("lastName") or ""
                        name_str = f"{fname} {lname}".strip()
                        if name_str:
                            teacher_names.append(name_str)
                teachers_str = ", ".join(teacher_names)

                room_obj = ticket.get("room") or {}
                room_str = room_obj.get("roomNumber") or ""

                day_num = ticket.get("dayNumber")
                if day_num is None:
                    continue
                day_idx = int(day_num) - 1

                starttime = ticket.get("ticketStart") or "00:00"
                endtime = ticket.get("ticketEnd") or "00:00"

                out.append(
                    {
                        "id": ticket.get("id"),
                        "parallel_id": p_id,
                        "parallel_code": p_code,
                        "name": code,
                        "type": p_type,
                        "day": day_idx,
                        "starttime": starttime,
                        "endtime": endtime,
                        "room": room_str,
                        "teachers": teachers_str,
                        "weeks": ticket.get("evenOddWeek"),
                    }
                )
            except Exception:
                continue
        return out

    def get_schedule_courses(self, codes: list[str], semester: str):
        out = []
        for code in codes:
            out.extend(self.get_schedule_course(code, semester))
        return out

    def get_semesters(self):
        return self.login_data["studies"][0]["semesters"]

    def get_available_courses(self, semester):
        if not semester:
            return []
        if semester in self.cached_courses:
            return self.cached_courses[semester]
        self.cached_courses[semester] = self.s.get(
            base + "course-semesters",
            params={
                "studyId": self.login_data["studies"][0]["id"],
                "size": 0,
                "hideFinished": False,
                "query": f"semesterId=={semester}",
            },
        ).json()["elements"]

        return self.cached_courses[semester]

    def get_courses(self):
        courses = self.s.get(
            base + "registered-courses",
            params={
                "query": f"studyId=={self.login_data['studies'][0]['id']}",
                "size": 0,
            },
        ).json()["elements"]

        courses_by_semester = dict()
        for c in courses:
            if c["semester"]["id"] not in courses_by_semester:
                courses_by_semester[c["semester"]["id"]] = []
            courses_by_semester[c["semester"]["id"]].append(c)

        return courses_by_semester

    @property
    def name(self):
        return " ".join(
            [
                self.login_data["person"]["firstName"],
                self.login_data["person"]["lastName"],
            ]
        )


# Days in the week for ordering
days_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
days_order = list(range(5))

hour_start_times = [
    time(hour=h, minute=m)
    for h, m in [(7, 30), (9, 15), (11, 00), (12, 45), (14, 30), (16, 15), (18, 00)]
]


def visualize_timetable(timetable):
    fig, ax = plt.subplots(figsize=(12, 6))

    # Group events by day and sort by start time
    grouped_events = {day: [] for day in days_order}
    for event in timetable:
        grouped_events[event["day"]].append(event)

    for day in grouped_events:
        grouped_events[day].sort(key=lambda e: e["starttime"])

    # pprint(grouped_events)

    # Compute rows for overlapping events
    plotted_events = []
    day_rows = dict()
    prefix_rows = {-1: 0}
    for day, events in grouped_events.items():
        used_rows = []  # Track active rows for events
        for event in events:
            start = (
                datetime.strptime(event["starttime"], "%H:%M").hour
                + datetime.strptime(event["starttime"], "%H:%M").minute / 60
            )
            end = (
                datetime.strptime(event["endtime"], "%H:%M").hour
                + datetime.strptime(event["endtime"], "%H:%M").minute / 60
            )

            # Find an available row for the event
            row = 0
            while row < len(used_rows) and used_rows[row] > start:
                row += 1
            if row == len(used_rows):
                used_rows.append(end)  # Add a new row
            else:
                used_rows[row] = end  # Update the row's end time

            plotted_events.append((prefix_rows[day - 1] + row + 0.5, start, end, event))
        day_rows[day] = len(used_rows)
        prefix_rows[day] = prefix_rows[day - 1] + max(1, day_rows[day])

    # Plot the events
    for y_position, start, end, event in plotted_events:
        ax.barh(
            -y_position,
            end - start,
            left=start,
            color=name_to_color(event["name"]),
            edgecolor="black",
        )
        ax.text(
            start + (end - start) / 2,
            -y_position,
            f"{event['name']} - {event['type']}\n{event['teachers']}\n{event['room']}",
            ha="center",
            va="center",
            fontsize=8,
            color="black",
        )

    prefix_rows[len(days_order)] = prefix_rows[len(days_order) - 1] + 1

    # Set y-axis labels and ticks
    ticks = list(map(lambda x: -(prefix_rows[x - 1] + prefix_rows[x]) / 2, days_order))

    for day in days_order:
        ax.axhspan(
            -prefix_rows[day - 1],
            -prefix_rows[day],
            color="lightgray" if day % 2 == 0 else "white",
            alpha=0.5,
        )

    ax.set_yticks(ticks)
    ax.set_yticklabels(days_names)
    ax.set_xticks(list(map(lambda x: x.hour + x.minute / 60, hour_start_times)))
    ax.set_xticklabels(list(map(lambda x: x.strftime("%H:%M"), hour_start_times)))
    ax.set_xlabel("Time (hours)")
    ax.set_title("Weekly Timetable")

    ax.grid(axis="x", linestyle="--", alpha=0.7)

    return fig


def get_parallels_summary(timetable):
    """
    Groups timetable tickets by course name -> parallel type (P, C, L, etc.) -> parallel_id.
    Returns a dictionary structure suitable for rendering the Parallel Selection Control Panel.
    """
    summary = {}
    for event in timetable:
        try:
            course = event.get("name") or "Unknown"
            ptype = event.get("type") or "P"
            pid = str(event.get("parallel_id") or "")
            pcode = str(event.get("parallel_code") or pid)

            if course not in summary:
                summary[course] = {}
            if ptype not in summary[course]:
                summary[course][ptype] = {}

            if pid not in summary[course][ptype]:
                summary[course][ptype][pid] = {
                    "parallel_id": pid,
                    "parallel_code": pcode,
                    "type": ptype,
                    "course": course,
                    "teachers": event.get("teachers") or "",
                    "room": event.get("room") or "",
                    "slots": [],
                }

            day_idx = event.get("day", 0)
            day_name = (
                days_names[day_idx]
                if (isinstance(day_idx, int) and 0 <= day_idx < len(days_names))
                else f"Day {day_idx}"
            )

            summary[course][ptype][pid]["slots"].append(
                {
                    "day": day_idx,
                    "day_name": day_name,
                    "starttime": event.get("starttime") or "",
                    "endtime": event.get("endtime") or "",
                    "room": event.get("room") or "",
                    "teachers": event.get("teachers") or "",
                }
            )
        except Exception:
            continue

    return summary


def visualize_timetable_html(timetable):
    grouped_events = {day: [] for day in days_order}
    for event in timetable:
        grouped_events[event["day"]].append(event)

    for day in grouped_events:
        grouped_events[day].sort(key=lambda e: e["starttime"])

    # Compute rows for overlapping events
    plotted_events = []
    min_time = 24
    max_time = 0
    for day, events in grouped_events.items():
        used_rows = []  # Track active rows for events
        plotted_events.append([])
        for event in events:
            start = (
                datetime.strptime(event["starttime"], "%H:%M").hour
                + datetime.strptime(event["starttime"], "%H:%M").minute / 60
            )
            min_time = min(min_time, start)
            end = (
                datetime.strptime(event["endtime"], "%H:%M").hour
                + datetime.strptime(event["endtime"], "%H:%M").minute / 60
            )
            max_time = max(max_time, end)

            # Find an available row for the event
            row = 0
            while row < len(used_rows) and used_rows[row] > start:
                row += 1
            if row == len(used_rows):
                used_rows.append(end)  # Add a new row
            else:
                used_rows[row] = end  # Update the row's end time

            while len(plotted_events[-1]) < row + 1:
                plotted_events[-1].append([])
            plotted_events[-1][row].append((start, end, event))

    if min_time >= max_time:
        min_time = 7.5
        max_time = 19.5

    type_to_class = {
        "P": "ctm-event-lecture",
        "C": "ctm-event-seminar",
        "L": "ctm-event-lab",
    }

    unique_courses = list(dict.fromkeys(x["name"] for x in timetable))
    colorpalet = generate_colormap_colors(max(1, len(unique_courses)))
    course_colors = {course: colorpalet[i] for i, course in enumerate(unique_courses)}

    out = '<div class="ctm-table">'
    lenght = max_time - min_time
    out += '<div class="ctm-grid-wrapper-wrapper">'
    out += '<div class="ctm-grid-wrapper">'
    out += '<div class="ctm-grid">'
    out += '<svg width="100%" height="100%">'
    for hour in range(ceil(min_time), ceil(max_time)):
        out += f'<line stroke="rgb(27,27,27)" stroke-width="1" y1="0%" y2="100%" x1={(hour - min_time) * 100 / lenght}% x2={(hour - min_time) * 100 / lenght}%></line>'
    out += "</svg>"
    out += "</div>"
    out += "</div>"
    out += "</div>"
    for i, day in enumerate(plotted_events):
        out += f'<div class="ctm-day" id="day-{i}" style="height:{max(4, 4 * len(day))}rem">'
        out += f'<div class="ctm-day-label">{days_names[i]}</div>'
        out += '<div class="ctm-day-rows">'
        for j, row in enumerate(day):
            out += f'<div class="ctm-row" id="row-{i}-{j}">'
            for event in row:
                ev_data = event[2]
                ev_type = ev_data["type"]
                type_cls = type_to_class.get(ev_type, "ctm-event-other")
                p_id = str(ev_data.get("parallel_id", ""))
                p_code = str(ev_data.get("parallel_code", ""))
                c_name = ev_data["name"]

                out += f'<div class="ctm-event {type_cls}" '
                out += f'data-course="{c_name}" '
                out += f'data-parallel-id="{p_id}" '
                out += f'data-parallel-code="{p_code}" '
                out += f'data-type="{ev_type}" '
                out += f'style="width:{(event[1] - event[0]) * 100 / lenght}%;left:{(event[0] - min_time) * 100 / lenght}%;'
                out += f'background-color: {course_colors[c_name][0]}; color: {course_colors[c_name][1]}">'
                out += f'<div class="ctm-event-actions">'
                out += f'<button type="button" class="ctm-act-btn ctm-act-select" title="Keep ONLY this parallel in table" data-action="select-only">&#10003;</button>'
                out += f'<button type="button" class="ctm-act-btn ctm-act-remove" title="Remove/Hide this parallel from table" data-action="remove">&#215;</button>'
                out += f"</div>"
                out += f'<span class="ctm-event-header"><strong>{c_name}</strong> [{ev_type}{p_code}]</span><br>'
                if ev_data["teachers"]:
                    out += f'<span class="ctm-event-teacher">{ev_data["teachers"]}</span><br>'
                if ev_data["room"]:
                    out += f'<span class="ctm-event-room">{ev_data["room"]}</span><br>'
                out += f'<span class="ctm-event-time">{ev_data["starttime"]} - {ev_data["endtime"]}</span>'
                out += "</div>"
            out += "</div>"
            out += "<script>"
            out += "function setRowSizes(row_id) { return () => { var max_height = 0; "
            out += "var children = document.getElementById(row_id).children;"
            out += """for (var i = 0; i < children.length; i++) {
                  var tableChild = children[i];
                  if (tableChild.classList.contains('ctm-hidden')) continue;
                  max_height = tableChild.offsetHeight < max_height ? max_height : tableChild.offsetHeight;
                }
                """
            out += 'document.getElementById(row_id).style.height = max_height + "px";'
            out += "}}"
            out += f"window.addEventListener('resize', setRowSizes('row-{i}-{j}'));"
            out += f"window.addEventListener('load', setRowSizes('row-{i}-{j}'))"
            out += "</script>"
        out += "</div>"
        out += "<script>"
        out += "function setDaySizes(row_id) { return () => { var max_height = 0; "
        out += "var children = document.getElementById(row_id).children;"
        out += """for (var i = 0; i < children.length; i++) {
              var tableChild = children[i];
              max_height = tableChild.offsetHeight < max_height ? max_height : tableChild.offsetHeight;
            }
            """
        out += f'document.getElementById("day-{i}").style.height = max_height + "px";'
        out += "}}"
        out += f"window.addEventListener('resize', setDaySizes('day-{i}'));"
        out += f"window.addEventListener('load', setDaySizes('day-{i}'))"
        out += "</script>"
        out += "</div>"

    out += "</div>"
    return out


# visualize_timetable(timetable)
