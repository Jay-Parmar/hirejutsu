from hirejutsu.salary import parse_salary, salary_period


def salary(low, high, currency, period):
    return {"salary_min": low, "salary_max": high, "salary_currency": currency, "salary_period": period}


def test_range_in_thousands():
    assert parse_salary("$170k - $200k") == salary(170000, 200000, "USD", "year")
    assert parse_salary("OTE $25k - $35k") == salary(25000, 35000, "USD", "year")
    assert parse_salary("$170k to $230k Base + Equity") == salary(170000, 230000, "USD", "year")


def test_hourly_range():
    assert parse_salary("$50-$75 /hour") == salary(50, 75, "USD", "hour")
    assert parse_salary("$7.25\N{EN DASH}$10/hr") == salary(7.25, 10, "USD", "hour")


def test_k_on_the_upper_bound_counts_for_both():
    assert parse_salary("$130-240K+ (depending on role/level) + equity") == salary(130000, 240000, "USD", "year")
    assert parse_salary("\N{EURO SIGN}35-45k/year") == salary(35000, 45000, "EUR", "year")


def test_currency_symbols_and_codes():
    assert parse_salary("\N{EURO SIGN}75k\N{EN DASH}80k") == salary(75000, 80000, "EUR", "year")
    assert parse_salary("100\N{EN DASH}140k\N{EURO SIGN}") == salary(100000, 140000, "EUR", "year")
    assert parse_salary("100k-160k GBP + 0.25-0.75% Equity") == salary(100000, 160000, "GBP", "year")
    assert parse_salary("$120k-$150k CAD")["salary_currency"] == "CAD"
    assert parse_salary("$185K-$220K USD / $155K-$185K CAD")["salary_currency"] == "USD"


def test_thousands_and_decimal_separators():
    assert parse_salary("\N{POUND SIGN}80,000-150,000") == salary(80000, 150000, "GBP", "year")
    assert parse_salary("$35,3k- $52k") == salary(35300, 52000, "USD", "year")
    assert parse_salary("$3,500-$5,000 USD/month") == salary(3500, 5000, "USD", "month")


def test_single_amount():
    assert parse_salary("\N{POUND SIGN}120k") == salary(120000, 120000, "GBP", "year")
    assert parse_salary("$181K base + 15% bonus") == salary(181000, 181000, "USD", "year")


def test_numbers_inside_words_are_ignored():
    assert parse_salary("B2B from 200 PLN/h+") == salary(200, 200, "PLN", "hour")


def test_small_amounts_without_a_period_are_hourly():
    assert parse_salary("$45")["salary_period"] == "hour"


def test_text_without_an_amount():
    assert parse_salary("Competitive salary") == {}
    assert parse_salary("") == {}


def test_salary_period_normalises_words():
    assert salary_period("annual") == "year"
    assert salary_period("yearly") == "year"
    assert salary_period("monthly") == "month"
    assert salary_period("weekly") == "week"
    assert salary_period("hourly") == "hour"
    assert salary_period("per day") == "day"
    assert salary_period("") == ""
