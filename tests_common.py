import utilities
from freezegun import freeze_time


@freeze_time("2020-03-01 13:00:00")
def test_get_day_start_yesterday_leap_day():
    assert str(utilities.get_day_start()) == "2020-02-29 17:00:00"


@freeze_time("2020-01-01 17:00:00")
def test_get_day_start_today_right_on():
    assert str(utilities.get_day_start()) == "2020-01-01 17:00:00"


@freeze_time("2020-01-02 16:56:00")
def test_get_day_start_today_slightly_before():
    assert str(utilities.get_day_start()) == "2020-01-01 17:00:00"


@freeze_time("2020-01-01 17:56:00")
def test_get_day_start_today_slightly_after():
    assert str(utilities.get_day_start()) == "2020-01-01 17:00:00"


@freeze_time("2020-01-01 21:12:34")
def test_get_day_start_today_after():
    assert str(utilities.get_day_start()) == "2020-01-01 17:00:00"


@freeze_time("2020-01-31 21:12:34")
def test_get_month_start_last_day():
    assert str(utilities.get_month_start()) == "2020-01-01 17:00:00"


@freeze_time("2020-02-01 15:12:34")
def test_get_month_start_day_one():
    assert str(utilities.get_month_start()) == "2020-01-01 17:00:00"


@freeze_time("2020-02-01 15:12:34")
def test_get_month_start_day_one_near():
    assert str(utilities.get_month_start()) == "2020-01-01 17:00:00"


@freeze_time("2020-02-01 17:12:34")
def test_get_month_start_day_one_after():
    assert str(utilities.get_month_start()) == "2020-02-01 17:00:00"
