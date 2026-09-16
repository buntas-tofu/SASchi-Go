"""Include the canonical rulebook in built distributions without a source copy."""
from pathlib import Path
from setuptools import setup
from setuptools.command.build_py import build_py


class BuildWithRulebook(build_py):
    def run(self):
        super().run()
        target = Path(self.build_lib) / 'saschi' / 'data'
        target.mkdir(parents=True, exist_ok=True)
        self.copy_file('docs/sasconversionrulebook.yaml', str(target / 'sasconversionrulebook.yaml'))


setup(cmdclass={'build_py': BuildWithRulebook})
