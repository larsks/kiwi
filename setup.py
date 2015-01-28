from distutils.core import setup

with open('requirements.txt') as fd:
    setup(name='kiwi',
          version='1',
          packages=['kiwi'],
          install_requires=fd.readlines(),
          entry_points={
              'console_scripts': [
                  'kiwi = kiwi.main:main',
              ],
          }
          )
