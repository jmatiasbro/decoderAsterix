from analysis.coverage import classify_fl, FL_BANDS

def test_classify_fl_buckets():
    assert classify_fl("50") == 50      # FL50 cae en banda 50
    assert classify_fl("120") == 100    # 125 > x >= 75 -> 100
    assert classify_fl("300") == 300
    assert classify_fl("400") == 300    # >=275 -> 300
    assert classify_fl("25000") == 250  # pies: 25000/100=250 -> banda 250

def test_classify_fl_feet_normalization():
    # valores > 450 se interpretan como pies y se dividen por 100
    assert classify_fl("5000") == 50    # 5000/100 = 50
    assert classify_fl("25000") == 250  # 25000/100 = 250

def test_classify_fl_invalid():
    assert classify_fl(None) is None
    assert classify_fl("---") is None
    assert classify_fl("abc") is None
    assert classify_fl("10") is None    # < 25, fuera de bandas
