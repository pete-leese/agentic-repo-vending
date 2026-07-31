from repo_vendor.workflow import _parse_rename_candidate


def test_parse_rename_candidate():
    assert _parse_rename_candidate("Please rename to python-better-name") == "python-better-name"
    assert _parse_rename_candidate("new name: terraform-module-s3-bucket-aws") == (
        "terraform-module-s3-bucket-aws"
    )
