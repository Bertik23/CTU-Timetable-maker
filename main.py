from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    redirect,
)
from flask_session import Session
import pprint


from kos_api import KOSApi, visualize_timetable_html, get_parallels_summary

app = Flask(__name__)

app.config["SESSION_TYPE"] = "filesystem"  # Store sessions on the server
app.config["SESSION_PERMANENT"] = False  # Optional: non-permanent sessions
app.config["SESSION_FILE_DIR"] = "./flask_session"  # Where to store session files
Session(app)

app.secret_key = "your_secret_key"


@app.route("/")
def home():
    kos: KOSApi | None = session.get("kos")
    if kos is None:
        return render_template("home.html")

    sem_courses = kos.get_courses()
    course_codes = dict()
    for sem, courses in sem_courses.items():
        course_codes[sem] = [c["code"] for c in courses if "code" in c]
    return render_template(
        "home.html",
        user_data=session.get("kos"),
        pformat=pprint.pformat,
        courses=kos.get_courses(),
        course_codes=course_codes.items(),
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        password = request.form["password"]

        kos = KOSApi(password)

        session["kos"] = kos
        return redirect("/")

    return render_template("login.html")


@app.route("/timetable")
def timetable():
    kos = session.get("kos")
    if kos is None:
        return redirect("/login")

    courses_raw = request.args.get("courses") or ""
    courses = [c.strip() for c in courses_raw.split(",") if c.strip()]
    semester = request.args.get("semester") or ""

    if not semester:
        try:
            semesters = kos.get_semesters()
            if semesters:
                semester = semesters[0].get("id", "")
        except Exception:
            semester = ""

    if not courses and semester:
        try:
            sem_courses = kos.get_courses()
            registered = sem_courses.get(semester, [])
            courses = [c["code"] for c in registered if "code" in c]
        except Exception:
            courses = []

    timetable_data = (
        kos.get_schedule_courses(courses, semester) if courses and semester else []
    )
    parallels_summary = get_parallels_summary(timetable_data)
    timetable_html = visualize_timetable_html(timetable_data)

    return render_template(
        "timetable.html",
        timetable=timetable_html,
        parallels_summary=parallels_summary,
        courses=courses,
        semester=semester,
        user_data=kos,
    )


@app.route("/logout")
def logout():
    session.pop("kos")
    return redirect("/")


if __name__ == "__main__":
    app.run(debug=True)
