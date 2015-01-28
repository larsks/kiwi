from setuptools import setup, find_packages

with open('requirements.txt') as fd:
    setup(name='kiwi',
          version='1',
          packages=find_packages(),
          install_requires=fd.readlines(),
          entry_points={
              'console_scripts': [
                  'kiwi = kiwi.main:main',
              ],
          }
          )
