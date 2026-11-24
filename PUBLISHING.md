# Publishing to PyPI (you do this once, with your own account)

PyPI and TestPyPI are free and do not ask for a card.

1. Create accounts at https://test.pypi.org and https://pypi.org, and turn on 2FA (required).
2. Check that the name is free: https://pypi.org/project/payload-doctor/ should show "Not Found".
   If it is taken, change `name` in pyproject.toml (for example `payload-doctor-b2b`).
3. Build and check the package:
   ```bash
   pip install build twine
   python -m build
   twine check dist/*
   ```
4. Upload to TestPyPI first and test it in a clean virtual environment:
   ```bash
   twine upload --repository testpypi dist/*
   python -m venv /tmp/t && /tmp/t/bin/pip install -i https://test.pypi.org/simple/ \
       --extra-index-url https://pypi.org/simple payload-doctor
   /tmp/t/bin/pdoc --version
   ```
5. Upload to PyPI: `twine upload dist/*`
6. Tag the release: `git tag v0.1.0 && git push --tags`

Use an API token (Account settings -> API tokens), not your password, when twine asks.
