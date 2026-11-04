from hirejutsu.workday import best_option, step_name


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
