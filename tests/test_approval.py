from repo_vendor.approval import is_approval_comment


def test_approval_keywords():
    assert is_approval_comment("lgtm")
    assert is_approval_comment("LGTM!")
    assert is_approval_comment("Looks good to me — approved")
    assert is_approval_comment("ship it")
    assert is_approval_comment("+1")
    assert is_approval_comment("please ship it now")


def test_non_approval():
    assert not is_approval_comment("")
    assert not is_approval_comment(None)
    assert not is_approval_comment("please rename")
    assert not is_approval_comment("not yet")
    assert not is_approval_comment("looks okay")  # not in keyword list
