from dataclasses import replace

from fakes import FakePage
from hirejutsu.applicant import Applicant, Position, School
from hirejutsu.workday import Field, Want, best_option, fill_step, find, step_name

DETAILS = Applicant(
    first_name="Asha",
    last_name="Rao",
    email="asha@example.com",
    phone="9876543210",
    phone_code="+91",
    address={"line1": "12 MG Road", "city": "Pune", "state": "Maharashtra", "postal_code": "411001", "country": "India"},
    links={"linkedin": "https://www.linkedin.com/in/asha", "github": "https://github.com/asha"},
    work=[
        Position("Backend Engineer", "Acme", "Pune", "2021-04", "", "Built the payments API."),
        Position("Developer", "Globex", "Mumbai", "2018-07", "2021-03"),
    ],
    education=[School("Pune University", "B.E.", "Computer Engineering", "2014", "2018", "8.1")],
    answers={"how_did_you_hear": "LinkedIn", "notice_period": "30 days"},
)

FIELDS = [
    Field(1, ("legalName--firstName",), "Given Name(s)"),
    Field(2, (), "Local Given Name(s)"),
    Field(3, (), "First Name"),
    Field(4, ("jobTitle",), "Job Title", section="Work Experience", entry=1),
    Field(5, ("jobTitle",), "Job Title", section="Work Experience", entry=2),
]
FIRST_NAME = ("legalName--firstName", "legalNameSection_firstName")


def test_find_looks_for_the_automation_id_first():
    assert find(FIELDS, Want("Asha", FIRST_NAME, r"first name")).ref == 1


def test_find_falls_back_to_the_start_of_the_label():
    assert find(FIELDS, Want("Asha", ("firstName",), r"first name")).ref == 3
    assert find(FIELDS[1:], Want("Asha", ("firstName",), r"given name")) is None


def test_find_keeps_to_the_section_and_entry():
    assert find(FIELDS, Want("Dev", ("jobTitle",), section=r"experience", entry=2)).ref == 5
    assert find(FIELDS, Want("Dev", ("jobTitle",), section=r"education", entry=2)) is None
    assert find(FIELDS, Want("Dev", ("jobTitle",))) is None


def test_step_name_comes_from_the_progress_bar():
    assert step_name("current step 2 of 6 My Information") == "My Information"
    assert step_name("current step 4 of 7 Application Questions") == "Application Questions"
    assert step_name("current step 6 of 7 Voluntary Self-Identification") == "Self Identify"
    assert step_name("current step 7 of 7 Review") == "Review"


def test_step_name_knows_the_step_containers_of_older_pages():
    assert step_name("contactInformationPage") == "My Information"
    assert step_name("applyFlowMyExpPage") == "My Experience"
    assert step_name("voluntaryDisclosuresPage") == "Voluntary Disclosures"
    assert step_name("selfIdentificationPage") == "Self Identify"


def test_other_steps_keep_their_label():
    assert step_name("current step 1 of 6 Autofill with Resume") == "Autofill with Resume"


def test_best_option_prefers_the_exact_option():
    assert best_option("No", ["No, never", "No"]) == 1


def test_best_option_takes_an_option_that_starts_with_the_answer():
    assert best_option("India", ["Indonesia (+62)", "India (+91)"]) == 1
    assert best_option("No", ["Yes, I have a disability", "No, I do not have a disability"]) == 1


def test_best_option_ignores_case_and_punctuation():
    assert best_option("b.e.", ["B.Tech", "BE"]) == 1
    assert best_option("mobile", ["Home", "Mobile/Cell"]) == 1


def test_best_option_needs_whole_words():
    assert best_option("No", ["None of the above"]) is None
    assert best_option("Male", ["Female"]) is None


def test_best_option_needs_an_answer():
    assert best_option("", ["Yes", "No"]) is None


def my_information():
    """The My Information step as Workday shows it, with India already picked as the country."""
    return [
        Field(1, ("source",), "How Did You Hear About Us?", "select", required=True),
        Field(2, ("candidateIsPreviousWorker",), "Have you previously worked for Acme?", "radio", options=("Yes", "No")),
        Field(3, ("country",), "Country", "select", "India", required=True),
        Field(4, ("legalName--firstName",), "Given Name(s)", required=True),
        Field(5, ("legalName--lastName",), "Family Name"),
        Field(6, ("addressLine1",), "Address Line 1", required=True),
        Field(7, ("city",), "City", required=True),
        Field(8, ("countryRegion",), "State", "select", options=("Gujarat", "Maharashtra")),
        Field(9, ("postalCode",), "Postal Code"),
        Field(10, ("phoneType",), "Phone Device Type", "select", options=("Landline", "Mobile")),
        Field(11, ("countryPhoneCode",), "Country Phone Code", "prompt", options=("Indonesia (+62)", "India (+91)")),
        Field(12, ("phoneNumber",), "Phone Number", required=True),
        Field(13, ("extension",), "Phone Extension"),
    ]


def test_my_information_is_filled_from_the_details():
    page = FakePage(my_information())
    report = fill_step(page, "My Information", DETAILS)
    values = {item.ref: item.value for item in page.fields()}
    assert values == {
        1: "LinkedIn", 2: "No", 3: "India", 4: "Asha", 5: "Rao", 6: "12 MG Road", 7: "Pune", 8: "Maharashtra",
        9: "411001", 10: "Mobile", 11: "India (+91)", 12: "9876543210", 13: "",
    }
    assert ("Given Name(s)", "Asha") in report.filled
    assert [item.label for item in report.left] == ["Phone Extension"]


def test_fields_that_have_a_value_are_kept():
    fields = my_information()
    fields[3] = replace(fields[3], value="Priya")
    page = FakePage(fields)
    fill_step(page, "My Information", DETAILS)
    assert page.value(4) == "Priya"
    assert "Given Name(s)" not in [label for label, _ in page.filled]


def test_older_pages_are_filled_by_their_ids():
    page = FakePage([
        Field(1, ("legalNameSection_firstName",), "First Name"),
        Field(2, ("addressSection_city",), "City or Town"),
        Field(3, ("phone-device-type",), "Phone Device Type", "select"),
        Field(4, ("phone-number",), "Phone"),
        Field(5, ("previousWorker",), "Have you worked here before?", "radio", options=("Yes", "No")),
    ])
    fill_step(page, "My Information", DETAILS)
    assert [item.value for item in page.fields()] == ["Asha", "Pune", "Mobile", "9876543210", "No"]


def test_fields_without_known_ids_are_found_by_label():
    page = FakePage([Field(1, ("a1b2",), "First Name"), Field(2, ("c3d4",), "Last Name"), Field(3, (), "Email Address")])
    fill_step(page, "My Information", DETAILS)
    assert [item.value for item in page.fields()] == ["Asha", "Rao", "asha@example.com"]


def test_worked_here_before_follows_the_answer():
    page = FakePage(my_information())
    fill_step(page, "My Information", replace(DETAILS, answers={"worked_here_before": "Yes"}))
    assert page.value(2) == "Yes"
    assert page.value(1) == ""


def work_entry():
    """The fields of one Work Experience entry."""
    return [
        Field(0, ("jobTitle",), "Job Title", required=True),
        Field(0, ("companyName",), "Company", required=True),
        Field(0, ("location",), "Location"),
        Field(0, ("currentlyWorkHere",), "I currently work here", "checkbox"),
        Field(0, ("startDate", "dateSectionMonth-input", "dateSectionYear-input"), "From", "date", required=True),
        Field(0, ("endDate", "dateSectionMonth-input", "dateSectionYear-input"), "To", "date"),
        Field(0, ("roleDescription",), "Role Description", "textarea"),
    ]


def test_each_job_gets_a_work_experience_entry():
    page = FakePage(entries={"Work Experience": work_entry()})
    fill_step(page, "My Experience", DETAILS)
    assert page.entry_values("Work Experience") == {
        1: {
            "Job Title": "Backend Engineer", "Company": "Acme", "Location": "Pune", "I currently work here": "Yes",
            "From": "04/2021", "To": "", "Role Description": "Built the payments API.",
        },
        2: {
            "Job Title": "Developer", "Company": "Globex", "Location": "Mumbai", "I currently work here": "",
            "From": "07/2018", "To": "03/2021", "Role Description": "",
        },
    }


def test_an_entry_workday_filled_from_the_resume_is_completed():
    filled = [replace(item, ref=number, section="Work Experience", entry=1) for number, item in enumerate(work_entry(), 1)]
    filled[0] = replace(filled[0], value="Developer")
    filled[1] = replace(filled[1], value="Globex Corp")
    page = FakePage(filled, entries={"Work Experience": work_entry()})
    fill_step(page, "My Experience", DETAILS)
    jobs = page.entry_values("Work Experience")
    assert (jobs[1]["Company"], jobs[1]["From"], jobs[1]["To"]) == ("Globex Corp", "07/2018", "03/2021")
    assert (jobs[2]["Company"], jobs[2]["From"]) == ("Acme", "04/2021")
    assert len(jobs) == 2


def test_jobs_need_a_section_to_go_in():
    page = FakePage([Field(1, ("other",), "Other")])
    report = fill_step(page, "My Experience", DETAILS)
    assert report.filled == []


def school_entry():
    """The fields of one Education entry."""
    return [
        Field(0, ("schoolName",), "School or University", required=True),
        Field(0, ("degree",), "Degree", "select", options=("Bachelor of Arts", "BE", "Master's Degree")),
        Field(0, ("fieldOfStudy",), "Field of Study", "prompt"),
        Field(0, ("gradeAverage",), "Overall Result (GPA)"),
        Field(0, ("firstYearAttended", "dateSectionYear-input"), "From", "date"),
        Field(0, ("lastYearAttended", "dateSectionYear-input"), "To", "date"),
    ]


def test_each_school_gets_an_education_entry():
    page = FakePage(entries={"Work Experience": work_entry(), "Education": school_entry()})
    fill_step(page, "My Experience", DETAILS)
    assert page.entry_values("Education") == {
        1: {
            "School or University": "Pune University", "Degree": "BE", "Field of Study": "Computer Engineering",
            "Overall Result (GPA)": "8.1", "From": "2014", "To": "2018",
        },
    }


def test_skills_from_the_resume_go_in_the_skills_box():
    page = FakePage([Field(1, ("skills",), "Type to Add Skills", "prompt", options=("Python", "Django", "AWS"))])
    report = fill_step(page, "My Experience", DETAILS, skills=["Python", "Kubernetes", "AWS"])
    assert page.value(1) == "Python, AWS"
    assert ("Type to Add Skills", "Python, AWS") in report.filled


def test_skills_already_in_the_box_are_kept():
    page = FakePage([Field(1, ("skills",), "Skills", "prompt", "Java")])
    fill_step(page, "My Experience", DETAILS, skills=["Python"])
    assert page.value(1) == "Java"


def resume_box(value="", section="Resume/CV"):
    return Field(1, ("file-upload-input-ref",), "Upload a file (5MB max)", "file", value, section=section)


def test_a_pdf_or_docx_resume_is_uploaded(tmp_path):
    for name in ("resume.pdf", "Resume.DOCX"):
        page = FakePage([resume_box()])
        fill_step(page, "My Experience", DETAILS, resume=tmp_path / name)
        assert page.value(1) == str(tmp_path / name)


def test_other_resumes_are_not_uploaded(tmp_path):
    page = FakePage([resume_box()])
    fill_step(page, "My Experience", DETAILS, resume=tmp_path / "resume.txt")
    assert page.value(1) == ""


def test_an_uploaded_file_is_kept(tmp_path):
    page = FakePage([resume_box("old.pdf")])
    fill_step(page, "My Experience", DETAILS, resume=tmp_path / "resume.pdf")
    assert page.value(1) == "old.pdf"


def test_only_the_resume_box_gets_the_resume(tmp_path):
    page = FakePage([resume_box(section="Cover Letter")])
    fill_step(page, "My Experience", DETAILS, resume=tmp_path / "resume.pdf")
    assert page.value(1) == ""


def website_entry():
    return [Field(0, ("url",), "URL", required=True)]


def test_links_go_in_the_linkedin_box_and_websites():
    page = FakePage([Field(1, ("linkedInAccount",), "LinkedIn", section="Social Network URLs")], {"Websites": website_entry()})
    fill_step(page, "My Experience", DETAILS)
    assert page.value(1) == "https://www.linkedin.com/in/asha"
    assert page.entry_values("Websites") == {1: {"URL": "https://github.com/asha"}}


def test_without_a_linkedin_box_every_link_is_a_website():
    page = FakePage(entries={"Websites": website_entry()})
    fill_step(page, "My Experience", DETAILS)
    assert page.entry_values("Websites") == {
        1: {"URL": "https://www.linkedin.com/in/asha"},
        2: {"URL": "https://github.com/asha"},
    }


def test_websites_already_listed_are_not_added_again():
    listed = Field(1, ("url",), "URL", value="github.com/asha", section="Websites", entry=1)
    page = FakePage([listed], {"Websites": website_entry()})
    fill_step(page, "My Experience", DETAILS)
    assert page.entry_values("Websites") == {1: {"URL": "github.com/asha"}, 2: {"URL": "https://www.linkedin.com/in/asha"}}


ANSWERS = {
    "notice_period": "30 days", "needs_sponsorship": "No", "authorized_to_work": "Yes",
    "expected_salary": "18 LPA", "current_salary": "12 LPA", "willing_to_relocate": "Yes",
}


def test_questions_get_the_answer_their_text_asks_for():
    page = FakePage([
        Field(1, ("a1",), "What is your notice period?"),
        Field(2, ("b2",), "Will you now or in the future require visa sponsorship?", "select", options=("Yes", "No")),
        Field(3, ("c3",), "Are you legally authorized to work in India?", "radio", options=("Yes", "No")),
        Field(4, ("d4",), "What are your salary expectations?", "textarea"),
        Field(5, ("e5",), "What is your current CTC?"),
        Field(6, ("f6",), "Are you willing to relocate to Bengaluru?", "select", options=("Yes", "No")),
        Field(7, ("g7",), "Why do you want to work here?", "textarea"),
    ])
    report = fill_step(page, "Application Questions", replace(DETAILS, answers=ANSWERS))
    assert [item.value for item in page.fields()] == ["30 days", "No", "Yes", "18 LPA", "12 LPA", "Yes", ""]
    assert [item.label for item in report.left] == ["Why do you want to work here?"]


def test_a_question_that_fits_two_answers_is_left():
    question = "Are you authorized to work in the US without needing sponsorship?"
    page = FakePage([Field(1, ("a1",), question, "select", options=("Yes", "No"))])
    fill_step(page, "Application Questions", replace(DETAILS, answers=ANSWERS))
    assert page.value(1) == ""


def test_questions_without_an_answer_are_left():
    page = FakePage([Field(1, ("a1",), "What is your notice period?")])
    fill_step(page, "Application Questions", replace(DETAILS, answers={}))
    assert page.value(1) == ""


def test_disclosures_are_answered_only_when_you_gave_an_answer():
    page = FakePage([
        Field(1, ("gender",), "Gender", "select", options=("Male", "Female", "I do not wish to answer")),
        Field(2, ("a1",), "Please select your ethnicity", "select", options=("Asian", "White")),
        Field(3, ("veteranStatus",), "Veteran Status", "select", options=("I am not a veteran", "I am a veteran")),
    ])
    fill_step(page, "Voluntary Disclosures", replace(DETAILS, answers={"gender": "Female", "ethnicity": "Asian"}))
    assert [item.value for item in page.fields()] == ["Female", "Asian", ""]


def test_the_disability_form_is_answered_by_its_choices():
    choices = ("Yes, I have a disability", "No, I do not have a disability", "I do not want to answer")
    page = FakePage([
        Field(1, ("name",), "Name"),
        Field(2, ("a1",), "Please check one of the boxes below:", "checkboxes", options=choices),
    ])
    fill_step(page, "Self Identify", replace(DETAILS, answers={"disability": "No"}))
    assert page.value(2) == "No, I do not have a disability"
    assert page.value(1) == ""


def test_nothing_that_asks_you_to_agree_is_answered():
    page = FakePage([
        Field(1, ("a1",), "I agree to relocate if the role needs it", "select", options=("Yes", "No")),
        Field(2, ("b2",), "I consent to sharing my gender", "select", options=("Female", "Male")),
        Field(3, ("c3",), "I acknowledge the terms of the privacy notice", "checkboxes", options=("Yes, I have a disability",)),
    ])
    answers = {"willing_to_relocate": "Yes", "gender": "Female", "disability": "Yes"}
    for step in ("Application Questions", "Voluntary Disclosures", "Self Identify"):
        fill_step(page, step, replace(DETAILS, answers=answers))
    assert [item.value for item in page.fields()] == ["", "", ""]
