# tests/

Offline unit and integration tests for `tools/`, the shell scripts and the contract. They need no network and
no model.

    python -I -m unittest discover -s tests          # the whole suite (slow: some tests drive bash)
    python -I -m unittest tests.test_contract        # one file

`test_contract.py` pins the public contract in `ci/contract.json`. `test_generic.py` checks that no personal
or company name is in the tree. `e2e_onboard.py` runs the installer end to end and is started by CI, not by
discovery. `python -I ci/gates.py` runs this suite together with the other gates.
