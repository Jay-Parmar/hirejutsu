from hirejutsu.workday import best_option


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
