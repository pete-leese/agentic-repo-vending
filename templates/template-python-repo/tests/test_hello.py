from example_pkg import hello


def test_hello():
    assert hello("vend") == "hello, vend"
