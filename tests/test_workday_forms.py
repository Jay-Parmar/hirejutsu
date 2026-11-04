from hirejutsu.workday import Field, Want, best_option, find, step_name

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
